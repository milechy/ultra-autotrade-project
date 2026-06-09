// Copyright (c) Ultra AutoTrade. All rights reserved.
"use client"

import { useState, useEffect, useCallback } from "react"
import { AlertTriangle, Loader2 } from "lucide-react"
import { useFundWallet, useWallets } from "@privy-io/react-auth"
import { base } from "viem/chains"
import { liffFetch } from "@/lib/liff/liff-fetch"

// ---- 型定義 ---------------------------------------------------------------

interface UserSettingsResponse {
  balance?: string | number | null
  wallet_address?: string | null
}

type Tab = "deposit" | "withdraw"
type PaymentMethod = "card" | "apple" | "google"

// 入金用 JPY → USDC 変換レート（固定近似値）
const JPY_PER_USDC = 155

// 出金ネットワーク手数料概算 (USDC)
const WITHDRAW_FEE = 0.08

// ---- 確認シート ------------------------------------------------------------

interface ConfirmSheetProps {
  open: boolean
  title: string
  rows: { label: string; value: string }[]
  onConfirm: () => void | Promise<void>
  onCancel: () => void
  busy: boolean
  error: string | null
}

function ConfirmSheet({ open, title, rows, onConfirm, onCancel, busy, error }: ConfirmSheetProps) {
  if (!open) return null
  return (
    <>
      <div
        className="fixed inset-0 z-[60] bg-black/60"
        onClick={!busy ? onCancel : undefined}
      />
      <div className="fixed bottom-0 left-0 right-0 z-[70] bg-zinc-900 rounded-t-2xl border-t border-zinc-800 px-4 pb-8 pt-3 animate-in slide-in-from-bottom duration-300">
        <div className="mx-auto mb-4 h-1 w-8 rounded-full bg-zinc-700" />
        <h2 className="text-base font-semibold text-zinc-100 mb-4">{title}</h2>
        <div className="space-y-3 mb-6">
          {rows.map((r) => (
            <div key={r.label} className="flex justify-between items-baseline gap-2">
              <span className="text-xs text-zinc-500 shrink-0">{r.label}</span>
              <span className="text-sm text-zinc-100 text-right">{r.value}</span>
            </div>
          ))}
        </div>
        {error && (
          <div className="flex items-start gap-2 mb-3 text-red-400 text-xs">
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
          実行する
        </button>
        <button
          onClick={onCancel}
          disabled={busy}
          className="mt-2 w-full py-3 rounded-xl border border-zinc-600 text-zinc-300
                     hover:bg-zinc-800 disabled:opacity-50 disabled:cursor-not-allowed
                     text-sm font-medium transition-colors"
        >
          キャンセル
        </button>
      </div>
    </>
  )
}

// ---- メインコンポーネント ---------------------------------------------------

export function DepositPanel() {
  const [tab, setTab] = useState<Tab>("deposit")

  // 残高
  const [balance, setBalance] = useState<number | null>(null)
  const [walletAddress, setWalletAddress] = useState<string | null>(null)
  const [balanceLoading, setBalanceLoading] = useState(true)

  // 入金フォーム
  const [depositAmount, setDepositAmount] = useState("")
  const [paymentMethod, setPaymentMethod] = useState<PaymentMethod>("card")

  // 出金フォーム
  const [withdrawAmount, setWithdrawAmount] = useState("")

  // 確認シート
  const [confirmOpen, setConfirmOpen] = useState(false)
  const [confirmBusy, setConfirmBusy] = useState(false)
  const [confirmError, setConfirmError] = useState<string | null>(null)
  const [successMsg, setSuccessMsg] = useState<string | null>(null)

  // Privy
  const { fundWallet } = useFundWallet()
  const { wallets } = useWallets()

  // ---- 残高取得 ------------------------------------------------------------

  const fetchBalance = useCallback(async () => {
    setBalanceLoading(true)
    try {
      // (liff) パネルは liffFetch を使う。apiFetch は (user) 側 AuthProvider が
      // resolve する authReadyPromise を待つが、(liff) ツリーには AuthProvider が
      // 無く永久 pending → リクエストがハングして残高スピナーが止まらない
      // (Asana 1215524979521648)。兄弟パネルと同じ liffFetch に統一する。
      const res = await liffFetch("/api/user/settings")
      if (res.ok) {
        const data = (await res.json()) as UserSettingsResponse
        setBalance(data.balance != null ? Number(data.balance) : null)
        setWalletAddress(data.wallet_address ?? null)
      } else {
        setBalance(null)
      }
    } catch {
      setBalance(null)
    } finally {
      setBalanceLoading(false)
    }
  }, [])

  useEffect(() => {
    void fetchBalance()
  }, [fetchBalance])

  // ---- 出金可能額上限（全額ボタン用） ----------------------------------------

  const maxWithdraw = balance ?? 0

  // ---- 受取予定額計算 -------------------------------------------------------

  const withdrawNum = parseFloat(withdrawAmount) || 0
  const receiveAmount = Math.max(0, withdrawNum - WITHDRAW_FEE)

  // ---- タブ切替 ------------------------------------------------------------

  const handleTabChange = (t: Tab) => {
    setTab(t)
    setConfirmOpen(false)
    setConfirmError(null)
    setSuccessMsg(null)
  }

  // ---- 入金確認シート -------------------------------------------------------

  const depositNum = parseFloat(depositAmount) || 0
  const estimatedUsdc = depositNum > 0 ? (depositNum / JPY_PER_USDC).toFixed(2) : "0"

  const depositRows = [
    { label: "金額", value: `¥${depositNum.toLocaleString("ja-JP")}` },
    { label: "概算 USDC", value: `≈ $${estimatedUsdc} USDC` },
    { label: "支払い方法", value: paymentMethod === "card" ? "クレジット/デビット" : paymentMethod === "apple" ? "Apple Pay" : "Google Pay" },
    { label: "ネットワーク", value: "Base Mainnet" },
  ]

  const handleDepositConfirm = useCallback(async () => {
    setConfirmBusy(true)
    setConfirmError(null)
    try {
      // Privy useFundWallet でオンランプ起動
      const wallet = wallets.find((w) => w.walletClientType === "privy")
      const address = wallet?.address ?? walletAddress ?? ""
      if (!address) throw new Error("ウォレットアドレスが見つかりません")
      await fundWallet({
        address,
        options: {
          chain: base,
          asset: "USDC",
          amount: estimatedUsdc,
        },
      })
      setConfirmOpen(false)
      setSuccessMsg("入金フローを開始しました。完了後に残高が更新されます。")
      void fetchBalance()
    } catch (e) {
      if (e instanceof Error && e.message.toLowerCase().includes("exit")) {
        // ユーザーが途中でキャンセル — エラー扱いしない
        setConfirmOpen(false)
      } else {
        setConfirmError(e instanceof Error ? e.message : "入金処理に失敗しました")
      }
    } finally {
      setConfirmBusy(false)
    }
  }, [wallets, walletAddress, fundWallet, estimatedUsdc, fetchBalance])

  // ---- 出金確認シート -------------------------------------------------------

  const withdrawRows = [
    { label: "出金額", value: `$${withdrawNum.toFixed(2)} USDC` },
    { label: "ネットワーク手数料", value: `≈ $${WITHDRAW_FEE.toFixed(2)}` },
    { label: "受取予定額", value: `$${receiveAmount.toFixed(2)} USDC` },
    { label: "出金先", value: walletAddress ? `${walletAddress.slice(0, 6)}...${walletAddress.slice(-4)}` : "ウォレット" },
  ]

  const handleWithdrawConfirm = useCallback(async () => {
    setConfirmBusy(true)
    setConfirmError(null)
    try {
      const res = await liffFetch("/api/transactions/withdraw", {
        method: "POST",
        body: JSON.stringify({ amount_usdc: withdrawNum }),
      })
      if (!res.ok) {
        const detail = (await res.json().catch(() => null)) as { detail?: string } | null
        throw new Error(detail?.detail ?? "出金処理に失敗しました")
      }
      setConfirmOpen(false)
      setSuccessMsg("出金リクエストを送信しました。反映まで少々お待ちください。")
      setWithdrawAmount("")
      void fetchBalance()
    } catch (e) {
      setConfirmError(e instanceof Error ? e.message : "出金処理に失敗しました")
    } finally {
      setConfirmBusy(false)
    }
  }, [withdrawNum, fetchBalance])

  // ---- 残高ラベル（タブ依存） -----------------------------------------------

  const balanceLabel = tab === "deposit" ? "現在の残高" : "出金可能残高"

  // ---- レンダリング --------------------------------------------------------

  return (
    <div className="pb-2">
      {/* タブ */}
      <div className="flex border-b border-zinc-800 mb-4">
        {(["deposit", "withdraw"] as Tab[]).map((t) => (
          <button
            key={t}
            onClick={() => handleTabChange(t)}
            className={[
              "flex-1 py-2 text-sm font-medium transition-colors",
              tab === t
                ? "border-b-2 border-[#1D9E75] text-[#1D9E75]"
                : "text-zinc-400",
            ].join(" ")}
          >
            {t === "deposit" ? "入金" : "出金"}
          </button>
        ))}
      </div>

      {/* 残高カード */}
      <div className="bg-[#1a3d2e] rounded-xl px-4 py-4 mb-4">
        <p className="text-xs text-zinc-400 mb-1">{balanceLabel}</p>
        {balanceLoading ? (
          <div className="flex items-center gap-2">
            <Loader2 className="w-4 h-4 animate-spin text-zinc-400" />
            <span className="text-zinc-400 text-sm">取得中...</span>
          </div>
        ) : (
          <p className="text-2xl font-bold text-white">
            {balance != null ? `$${balance.toFixed(2)}` : "---"}
            <span className="text-sm font-normal text-zinc-400 ml-2">USDC</span>
          </p>
        )}
        <p className="text-xs text-zinc-500 mt-1">USDC · Base Mainnet</p>
      </div>

      {/* 成功メッセージ */}
      {successMsg && (
        <div className="bg-[#1a3d2e] border border-[#1D9E75] rounded-xl px-4 py-3 mb-4 text-sm text-[#4ade9a]">
          {successMsg}
        </div>
      )}

      {/* ====== 入金タブ ====== */}
      {tab === "deposit" && (
        <div className="space-y-4">
          {/* 金額入力 */}
          <div>
            <label className="block text-xs text-zinc-400 mb-1">金額を入力（円）</label>
            <div className="relative">
              <span className="absolute left-3 top-1/2 -translate-y-1/2 text-zinc-400 text-sm">¥</span>
              <input
                type="number"
                min="0"
                placeholder="金額を入力"
                value={depositAmount}
                onChange={(e) => setDepositAmount(e.target.value)}
                className="w-full bg-zinc-800 text-white text-lg pl-7 pr-4 py-3 rounded-xl
                           border border-zinc-700 focus:border-[#1D9E75] focus:outline-none
                           placeholder-zinc-600"
              />
            </div>
            {depositNum > 0 && (
              <p className="text-xs text-zinc-500 mt-1">
                ≈ ${(depositNum / JPY_PER_USDC).toFixed(2)} USDC
              </p>
            )}
          </div>

          {/* クイックボタン */}
          <div className="grid grid-cols-4 gap-2">
            {[10000, 30000, 50000, 100000].map((amt) => (
              <button
                key={amt}
                onClick={() => setDepositAmount(String(amt))}
                className="bg-zinc-800 hover:bg-zinc-700 text-zinc-200 text-xs py-2 rounded-lg
                           border border-zinc-700 transition-colors"
              >
                ¥{(amt / 10000).toFixed(0)}万
              </button>
            ))}
          </div>

          {/* 支払い方法 */}
          <div>
            <label className="block text-xs text-zinc-400 mb-2">支払い方法</label>
            <div className="space-y-2">
              {(
                [
                  { id: "card" as PaymentMethod, label: "クレジット/デビット" },
                  { id: "apple" as PaymentMethod, label: "Apple Pay" },
                  { id: "google" as PaymentMethod, label: "Google Pay" },
                ] as { id: PaymentMethod; label: string }[]
              ).map(({ id, label }) => (
                <label
                  key={id}
                  className={[
                    "flex items-center gap-3 px-3 py-3 rounded-xl border cursor-pointer transition-colors",
                    paymentMethod === id
                      ? "border-[#1D9E75] bg-[#1a3d2e]"
                      : "border-zinc-700 bg-zinc-800",
                  ].join(" ")}
                >
                  <input
                    type="radio"
                    name="payment"
                    value={id}
                    checked={paymentMethod === id}
                    onChange={() => setPaymentMethod(id)}
                    className="accent-[#1D9E75]"
                  />
                  <span className="text-sm text-zinc-200">{label}</span>
                </label>
              ))}
            </div>
          </div>

          {/* 入金ボタン */}
          <button
            disabled={!depositAmount || depositNum <= 0}
            onClick={() => {
              setConfirmError(null)
              setSuccessMsg(null)
              setConfirmOpen(true)
            }}
            className="w-full bg-[#1D9E75] hover:bg-[#1a8f6a]
                       disabled:opacity-40 disabled:cursor-not-allowed
                       text-white font-semibold py-3 rounded-xl transition-colors"
          >
            入金する
          </button>
        </div>
      )}

      {/* ====== 出金タブ ====== */}
      {tab === "withdraw" && (
        <div className="space-y-4">
          {/* 金額入力 */}
          <div>
            <label className="block text-xs text-zinc-400 mb-1">金額を入力（USDC）</label>
            <div className="relative">
              <span className="absolute left-3 top-1/2 -translate-y-1/2 text-zinc-400 text-sm">$</span>
              <input
                type="number"
                min="0"
                step="0.01"
                placeholder="金額を入力"
                value={withdrawAmount}
                onChange={(e) => setWithdrawAmount(e.target.value)}
                className="w-full bg-zinc-800 text-white text-lg pl-7 pr-4 py-3 rounded-xl
                           border border-zinc-700 focus:border-[#1D9E75] focus:outline-none
                           placeholder-zinc-600"
              />
            </div>
          </div>

          {/* クイックボタン */}
          <div className="grid grid-cols-4 gap-2">
            {[100, 500, 1000].map((amt) => (
              <button
                key={amt}
                onClick={() => setWithdrawAmount(String(amt))}
                className="bg-zinc-800 hover:bg-zinc-700 text-zinc-200 text-xs py-2 rounded-lg
                           border border-zinc-700 transition-colors"
              >
                ${amt}
              </button>
            ))}
            <button
              onClick={() => setWithdrawAmount(maxWithdraw > 0 ? maxWithdraw.toFixed(2) : "")}
              className="bg-zinc-800 hover:bg-zinc-700 text-zinc-200 text-xs py-2 rounded-lg
                         border border-zinc-700 transition-colors"
            >
              全額
            </button>
          </div>

          {/* 出金先（変更不可） */}
          <div>
            <label className="block text-xs text-zinc-400 mb-1">出金先</label>
            <div className="bg-zinc-800 border border-zinc-700 rounded-xl px-4 py-3">
              <p className="text-sm text-zinc-300 font-mono">
                {walletAddress
                  ? `${walletAddress.slice(0, 6)}...${walletAddress.slice(-4)}`
                  : "自分のウォレット"}
              </p>
              <p className="text-xs text-zinc-500 mt-0.5">変更不可</p>
            </div>
          </div>

          {/* 手数料・受取予定額 */}
          <div className="bg-zinc-800 border border-zinc-700 rounded-xl px-4 py-3 space-y-2">
            <div className="flex justify-between text-xs text-zinc-400">
              <span>ネットワーク手数料</span>
              <span>≈ ${WITHDRAW_FEE.toFixed(2)}</span>
            </div>
            <div className="flex justify-between text-sm font-semibold">
              <span className="text-zinc-300">受取予定額</span>
              <span className="text-white">
                {withdrawNum > 0 ? `$${receiveAmount.toFixed(2)} USDC` : "---"}
              </span>
            </div>
          </div>

          {/* 警告 */}
          <div className="flex items-start gap-2 text-yellow-400 text-xs">
            <AlertTriangle className="w-4 h-4 shrink-0 mt-0.5" />
            <p>
              出金後の資産はAave運用から外れます。再入金まで利回りは発生しません。
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
            出金する
          </button>
        </div>
      )}

      {/* 確認シート */}
      <ConfirmSheet
        open={confirmOpen}
        title={tab === "deposit" ? "入金内容の確認" : "出金内容の確認"}
        rows={tab === "deposit" ? depositRows : withdrawRows}
        onConfirm={tab === "deposit" ? handleDepositConfirm : handleWithdrawConfirm}
        onCancel={() => setConfirmOpen(false)}
        busy={confirmBusy}
        error={confirmError}
      />
    </div>
  )
}
