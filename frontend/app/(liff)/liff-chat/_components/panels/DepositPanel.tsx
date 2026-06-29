// Copyright (c) Ultra AutoTrade. All rights reserved.
"use client"

import { useState, useCallback, useEffect } from "react"
import { AlertTriangle, Loader2 } from "lucide-react"
import { useTranslations } from "next-intl"
import { useLanguage } from "@/lib/useLanguage"
import { liffFetch } from "@/lib/liff/liff-fetch"
import { useFundWallet } from "@privy-io/react-auth"
import { base, baseSepolia } from "wagmi/chains"
import { useWallet } from "@/hooks/useWallet"
import { useUsdcBalance } from "@/hooks/useUsdcBalance"
import { DEPOSIT_GATE_USD } from "@/lib/web3/config"
import { track, EV } from "@/lib/posthog"

// ---- 型定義 ---------------------------------------------------------------

type Tab = "deposit" | "withdraw"

// 入金目安表示用 JPY → USDC 変換レートのフォールバック値（API 失敗時に使用）。
// 実値は GET /api/market/prices の usd_jpy を MARKET-C で動的取得する。
const JPY_PER_USDC_FALLBACK = 155

// 出金ネットワーク手数料概算 (USDC)
const WITHDRAW_FEE = 0.08

// v3: 出金 UI は非表示（paymaster 未配線）。v4 以降は NEXT_PUBLIC_WITHDRAW_ENABLED=true で有効化。
const WITHDRAW_ENABLED: boolean = process.env.NEXT_PUBLIC_WITHDRAW_ENABLED === "true"

// ---- 確認シート（出金専用） -------------------------------------------------

interface ConfirmSheetProps {
  open: boolean
  title: string
  executeLabel: string
  cancelLabel: string
  rows: { label: string; value: string }[]
  onConfirm: () => void | Promise<void>
  onCancel: () => void
  busy: boolean
  error: string | null
}

function ConfirmSheet({ open, title, executeLabel, cancelLabel, rows, onConfirm, onCancel, busy, error }: ConfirmSheetProps) {
  if (!open) return null
  return (
    <>
      <div
        className="fixed inset-0 z-[60] bg-black/60"
        onClick={!busy ? onCancel : undefined}
      />
      <div className="fixed bottom-0 left-0 right-0 z-[70] ax-card-warm rounded-t-2xl border-t border-[#1c1a27]/15 px-4 pb-8 pt-3 animate-in slide-in-from-bottom duration-300">
        <div className="mx-auto mb-4 h-1 w-8 rounded-full bg-[#1c1a27]/10" />
        <h2 className="text-base font-semibold text-[#1c1a27] mb-4">{title}</h2>
        <div className="space-y-3 mb-6">
          {rows.map((r) => (
            <div key={r.label} className="flex justify-between items-baseline gap-2">
              <span className="text-xs text-[#736f7e] shrink-0">{r.label}</span>
              <span className="text-sm text-[#1c1a27] text-right">{r.value}</span>
            </div>
          ))}
        </div>
        {error && (
          <div className="flex items-start gap-2 mb-3 text-red-600 text-xs">
            <AlertTriangle className="w-4 h-4 shrink-0 mt-0.5" />
            <span>{error}</span>
          </div>
        )}
        <button
          onClick={() => { void onConfirm() }}
          disabled={busy}
          className="w-full flex items-center justify-center gap-2 bg-[#1D9E75] hover:bg-[#1a8f6a]
                     disabled:opacity-50 disabled:cursor-not-allowed text-white font-semibold
                     py-3 rounded-xl transition-colors"
        >
          {busy && <Loader2 className="w-4 h-4 animate-spin" />}
          {executeLabel}
        </button>
        <button
          onClick={onCancel}
          disabled={busy}
          className="mt-2 w-full py-3 rounded-xl border border-[#1c1a27]/15 text-[#736f7e]
                     hover:bg-black/5 disabled:opacity-50 disabled:cursor-not-allowed
                     text-sm font-medium transition-colors"
        >
          {cancelLabel}
        </button>
      </div>
    </>
  )
}

// ---- メインコンポーネント ---------------------------------------------------

export function DepositPanel() {
  const t = useTranslations("Liff.panels.deposit")
  const { language } = useLanguage()
  const [tab, setTab] = useState<Tab>("deposit")

  // JPY→USDC 換算レート（MARKET-C: /api/market/prices の usd_jpy をリアルタイム取得）。
  // 取得失敗時はフォールバック値 155 のまま（入金画面は崩壊しない）。
  const [jpyPerUsdc, setJpyPerUsdc] = useState<number>(JPY_PER_USDC_FALLBACK)
  useEffect(() => {
    liffFetch("/api/market/prices")
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => {
        if (d && d.usd_jpy) setJpyPerUsdc(Number(d.usd_jpy))
      })
      .catch(() => {})
  }, [])

  // Privy ウォレット情報（useFundWallet 用）
  const { address, chainId } = useWallet()

  // 残高 = ユーザー自身のウォレットの USDC オンチェーン残高（非カストディアル）。
  // 出金先/入金先アドレスも settings 依存をやめ useWallet の address を正とする。
  const { balanceUsd, loading: balanceLoading, refetch: refetchBalance } = useUsdcBalance()
  const balance = balanceUsd
  const walletAddress = address

  // 入金フォーム（金額は送金目安の表示用）
  const [depositAmount, setDepositAmount] = useState("")
  // Privy fundWallet 処理中フラグ
  const [isFunding, setIsFunding] = useState(false)

  // 出金フォーム
  const [withdrawAmount, setWithdrawAmount] = useState("")

  // 確認シート（出金専用）
  const [confirmOpen, setConfirmOpen] = useState(false)
  const [confirmBusy, setConfirmBusy] = useState(false)
  const [confirmError, setConfirmError] = useState<string | null>(null)
  const [successMsg, setSuccessMsg] = useState<string | null>(null)

  // 残高はオンチェーン取得（useUsdcBalance が自動取得）。入金/出金後は refetchBalance() で更新する。

  // ---- Privy fundWallet --------------------------------------------------

  const { fundWallet } = useFundWallet({
    onUserExited: () => {
      setIsFunding(false)
      refetchBalance()
    },
  })

  const handleFundWallet = useCallback(async () => {
    if (!address) return
    track(EV.DEPOSIT_FUND)
    setIsFunding(true)
    try {
      // 入力単位は言語で異なる: 英語=USD（USDC と 1:1）/ 日本語=¥（÷155 で USDC 換算）。
      // Privy fundWallet の amount は USDC 建てのため、ここで USDC へ正規化する
      // （旧実装は ¥ 値をそのまま USDC として渡していた不具合を修正）。
      const num = parseFloat(depositAmount) || 0
      const usdc = language === "en" ? num : num / jpyPerUsdc
      await fundWallet({
        address,
        options: {
          chain: chainId === 84532 ? baseSepolia : base,
          amount: usdc > 0 ? usdc.toFixed(2) : "200",
          asset: "USDC",
        },
      })
    } catch (e) {
      if (e instanceof Error && !e.message.toLowerCase().includes("exit")) {
        // ユーザーキャンセル以外のエラーはコンソールに記録（UI は onUserExited で復旧）
        console.error("[DepositPanel] fundWallet error:", e.message)
      }
    } finally {
      setIsFunding(false)
      refetchBalance()
    }
  }, [address, chainId, depositAmount, language, jpyPerUsdc, refetchBalance, fundWallet])

  // ---- 出金可能額上限（全額ボタン用） ----------------------------------------

  const maxWithdraw = balance ?? 0

  // ---- 受取予定額計算 -------------------------------------------------------

  const withdrawNum = parseFloat(withdrawAmount) || 0
  const receiveAmount = Math.max(0, withdrawNum - WITHDRAW_FEE)
  const depositNum = parseFloat(depositAmount) || 0
  // 入力単位: 英語=USD（≈USDC 1:1）/ 日本語=¥（÷155 で USDC 換算）
  const isEn = language === "en"
  const depositUsdc = isEn ? depositNum : depositNum / jpyPerUsdc

  // ---- タブ切替 ------------------------------------------------------------

  const handleTabChange = (t: Tab) => {
    setTab(t)
    setConfirmOpen(false)
    setConfirmError(null)
    setSuccessMsg(null)
  }

  // ---- 出金確認シート -------------------------------------------------------

  const withdrawRows = [
    { label: t("confirmSheetWithdrawAmount"), value: `$${withdrawNum.toFixed(2)} USDC` },
    { label: t("confirmSheetNetworkFee"), value: `≈ $${WITHDRAW_FEE.toFixed(2)}` },
    { label: t("confirmSheetReceiveAmount"), value: `$${receiveAmount.toFixed(2)} USDC` },
    { label: t("confirmSheetDest"), value: walletAddress ? `${walletAddress.slice(0, 6)}...${walletAddress.slice(-4)}` : t("withdrawDestDefault") },
  ]

  // 出金は (user)/withdraw（Privy 本人署名 + 記録専用 /api/users/withdrawals）を正とする。
  // 以前ここから呼んでいた POST /api/transactions/withdraw は backend に存在せず本番で 404 に
  // なるため除去した。出金タブは disabled（準備中）で到達不能だが、誤 endpoint 呼び出しの
  // 配線を物理的に断つため no-op 化する。出金 UI 有効化は (user)/withdraw 側 + #391 money gate。
  const handleWithdrawConfirm = useCallback(async () => {
    setConfirmError(t("withdrawComingSoon"))
  }, [t])

  // ---- 残高ラベル（タブ依存） -----------------------------------------------

  const balanceLabel = tab === "deposit" ? t("currentBalance") : t("withdrawableBalance")

  // ---- レンダリング --------------------------------------------------------

  return (
    <div className="pb-2">
      {/* タブ（出金は準備中表示のみ・クリック不可） */}
      <div className="flex border-b border-[#1c1a27]/15 mb-4">
        <button
          onClick={() => handleTabChange("deposit")}
          className={[
            "flex-1 py-2 text-sm font-medium transition-colors",
            tab === "deposit"
              ? "border-b-2 border-[#1D9E75] text-[#1D9E75]"
              : "text-[#736f7e]",
          ].join(" ")}
        >
          {t("tabDeposit")}
        </button>
        <button
          disabled
          className="flex-1 py-2 text-sm font-medium text-[#736f7e] opacity-40 cursor-not-allowed flex items-center justify-center gap-1"
        >
          {t("tabWithdraw")}
          <span className="text-[10px] bg-[#736f7e]/20 rounded px-1 py-0.5 leading-none">
            {t("withdrawComingSoon")}
          </span>
        </button>
      </div>

      {/* 残高カード */}
      <div className="bg-gradient-to-br from-[#b9a4f2] via-[#ecaccd] to-[#fbd9a0] rounded-xl px-4 py-4 mb-4">
        <p className="text-xs text-[#736f7e] mb-1">{balanceLabel}</p>
        {balanceLoading ? (
          <div className="flex items-center gap-2">
            <Loader2 className="w-4 h-4 animate-spin text-[#736f7e]" />
            <span className="text-[#736f7e] text-sm">{t("balanceLoading")}</span>
          </div>
        ) : (
          <p className="text-2xl font-bold text-[#1c1a27]">
            {balance != null ? `$${balance.toFixed(2)}` : "---"}
            <span className="text-sm font-normal text-[#736f7e] ml-2">USDC</span>
          </p>
        )}
        <p className="text-xs text-[#736f7e] mt-1">{t("network")}</p>
      </div>

      {/* $200 入金ゲート状態（入金自体は許可。自動運用の開始可否を明示） */}
      {!balanceLoading && balance != null && (
        balance >= DEPOSIT_GATE_USD ? (
          <div className="ax-card-warm border border-[#1D9E75] rounded-xl px-4 py-2.5 mb-4 text-xs text-[#1D9E75]">
            {t("gateMet", { gate: String(DEPOSIT_GATE_USD) })}
          </div>
        ) : (
          <div className="ax-card-warm border border-[#E5484D] rounded-xl px-4 py-2.5 mb-4 text-xs text-[#E5484D]">
            {t("gateShortfall", {
              gate: String(DEPOSIT_GATE_USD),
              remaining: (DEPOSIT_GATE_USD - balance).toFixed(2),
            })}
          </div>
        )
      )}

      {/* 成功メッセージ */}
      {successMsg && (
        <div className="ax-card-warm border border-[#1D9E75] rounded-xl px-4 py-3 mb-4 text-sm text-[#1D9E75]">
          {successMsg}
        </div>
      )}

      {/* ====== 入金タブ ====== */}
      {tab === "deposit" && (
        <div className="space-y-4">
          {/* 金額入力（送金額の目安） */}
          <div>
            <label className="block text-xs text-[#736f7e] mb-1">{t("depositAmountLabel")}</label>
            <div className="relative">
              <span className="absolute left-3 top-1/2 -translate-y-1/2 text-[#736f7e] text-sm">{isEn ? "$" : "¥"}</span>
              <input
                type="number"
                min="0"
                placeholder={t("depositAmountPlaceholder")}
                value={depositAmount}
                onChange={(e) => setDepositAmount(e.target.value)}
                className="w-full ax-card-warm text-[#1c1a27] text-lg pl-7 pr-4 py-3 rounded-xl
                           border border-[#1c1a27]/15 focus:border-[#1D9E75] focus:outline-none
                           placeholder-[#736f7e]"
              />
            </div>
            {depositNum > 0 && (
              <p className="text-xs text-[#736f7e] mt-1">
                ≈ ${depositUsdc.toFixed(2)} USDC
              </p>
            )}
          </div>

          {/* クイックボタン */}
          <div className="grid grid-cols-4 gap-2">
            {(isEn ? [100, 300, 500, 1000] : [10000, 30000, 50000, 100000]).map((amt) => (
              <button
                key={amt}
                onClick={() => setDepositAmount(String(amt))}
                className="ax-card-warm hover:bg-black/5 text-[#1c1a27] text-xs py-2 rounded-lg
                           border border-[#1c1a27]/15 transition-colors"
              >
                {isEn
                  ? `$${amt.toLocaleString()}`
                  : `¥${(amt / 10000).toFixed(0)}${t('unitMan')}`}
              </button>
            ))}
          </div>

          {/* 入金方法の案内 */}
          <div className="ax-card-warm border border-[#1c1a27]/15 rounded-xl px-4 py-3 space-y-2">
            <p className="text-xs font-medium text-[#1c1a27]">{t("depositMethodTitle")}</p>
            <p className="text-xs text-[#736f7e] leading-relaxed">
              {t("depositMethodDesc")}
            </p>
            <ul className="text-xs text-[#736f7e] leading-relaxed space-y-0.5 list-disc list-inside">
              <li>{t("depositMethodNote1")}</li>
              <li>{t("depositMethodNote2")}</li>
              <li>{t("depositMethodNote3")}</li>
            </ul>
          </div>

          {/* 入金ボタン（Privy fundWallet モーダルを開く。カード購入・送金・
              ネットワーク選択を一括で扱う。EN モードでは下に MoonPay on-ramp も提示する） */}
          <button
            onClick={() => { void handleFundWallet() }}
            disabled={!address || isFunding}
            className="w-full flex items-center justify-center gap-2 bg-[#1D9E75] hover:bg-[#1a8f6a]
                       disabled:opacity-40 disabled:cursor-not-allowed
                       text-white font-semibold py-3 rounded-xl transition-colors"
          >
            {isFunding && <Loader2 className="w-4 h-4 animate-spin" />}
            {t("depositBtn")}
          </button>

          {/* MoonPay on-ramp — v3 は日本在住ユーザーのみのため非表示。v4 海外ユーザー対応時に復活予定 */}
        </div>
      )}

      {/* ====== 出金タブ（v3 非表示 / v4 で paymaster と共に有効化） ====== */}
      {WITHDRAW_ENABLED && tab === "withdraw" && (
        <div className="space-y-4">
          {/* 金額入力 */}
          <div>
            <label className="block text-xs text-[#736f7e] mb-1">{t("withdrawAmountLabel")}</label>
            <div className="relative">
              <span className="absolute left-3 top-1/2 -translate-y-1/2 text-[#736f7e] text-sm">$</span>
              <input
                type="number"
                min="0"
                step="0.01"
                placeholder={t("withdrawAmountPlaceholder")}
                value={withdrawAmount}
                onChange={(e) => setWithdrawAmount(e.target.value)}
                className="w-full ax-card-warm text-[#1c1a27] text-lg pl-7 pr-4 py-3 rounded-xl
                           border border-[#1c1a27]/15 focus:border-[#1D9E75] focus:outline-none
                           placeholder-[#736f7e]"
              />
            </div>
          </div>

          {/* クイックボタン */}
          <div className="grid grid-cols-4 gap-2">
            {[100, 500, 1000].map((amt) => (
              <button
                key={amt}
                onClick={() => setWithdrawAmount(String(amt))}
                className="ax-card-warm hover:bg-black/5 text-[#1c1a27] text-xs py-2 rounded-lg
                           border border-[#1c1a27]/15 transition-colors"
              >
                ${amt}
              </button>
            ))}
            <button
              onClick={() => setWithdrawAmount(maxWithdraw > 0 ? maxWithdraw.toFixed(2) : "")}
              className="ax-card-warm hover:bg-black/5 text-[#1c1a27] text-xs py-2 rounded-lg
                         border border-[#1c1a27]/15 transition-colors"
            >
              {t("quickMax")}
            </button>
          </div>

          {/* 出金先（変更不可） */}
          <div>
            <label className="block text-xs text-[#736f7e] mb-1">{t("withdrawDestLabel")}</label>
            <div className="ax-card-warm border border-[#1c1a27]/15 rounded-xl px-4 py-3">
              <p className="text-sm text-[#1c1a27] font-mono">
                {walletAddress
                  ? `${walletAddress.slice(0, 6)}...${walletAddress.slice(-4)}`
                  : t("withdrawDestDefault")}
              </p>
              <p className="text-xs text-[#736f7e] mt-0.5">{t("withdrawDestImmutable")}</p>
            </div>
          </div>

          {/* 手数料・受取予定額 */}
          <div className="ax-card-warm border border-[#1c1a27]/15 rounded-xl px-4 py-3 space-y-2">
            <div className="flex justify-between text-xs text-[#736f7e]">
              <span>{t("networkFeeLabel")}</span>
              <span>≈ ${WITHDRAW_FEE.toFixed(2)}</span>
            </div>
            <div className="flex justify-between text-sm font-semibold">
              <span className="text-[#736f7e]">{t("receiveAmountLabel")}</span>
              <span className="text-[#1c1a27]">
                {withdrawNum > 0 ? `$${receiveAmount.toFixed(2)} USDC` : "---"}
              </span>
            </div>
          </div>

          {/* 警告 */}
          <div className="flex items-start gap-2 text-yellow-600 text-xs">
            <AlertTriangle className="w-4 h-4 shrink-0 mt-0.5" />
            <p>
              {t("withdrawWarning")}
            </p>
          </div>

          {/* 出金ボタン */}
          <button
            disabled={!withdrawAmount || withdrawNum <= 0}
            onClick={() => {
              setConfirmError(null)
              setSuccessMsg(null)
              setConfirmOpen(true)
            }}
            className="w-full bg-[#1D9E75] hover:bg-[#1a8f6a]
                       disabled:opacity-40 disabled:cursor-not-allowed
                       text-white font-semibold py-3 rounded-xl transition-colors"
          >
            {t("withdrawBtn")}
          </button>
        </div>
      )}

      {/* 確認シート（出金専用） */}
      <ConfirmSheet
        open={confirmOpen}
        title={t("confirmSheetTitle")}
        executeLabel={t("confirmExecuteBtn")}
        cancelLabel={t("confirmCancelBtn")}
        rows={withdrawRows}
        onConfirm={handleWithdrawConfirm}
        onCancel={() => setConfirmOpen(false)}
        busy={confirmBusy}
        error={confirmError}
      />
    </div>
  )
}
