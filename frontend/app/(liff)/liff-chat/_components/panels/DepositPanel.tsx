// Copyright (c) Ultra AutoTrade. All rights reserved.
"use client"

import { useState, useEffect, useCallback } from "react"
import { AlertTriangle, Copy, Check, Loader2 } from "lucide-react"
import { apiFetch, apiPost } from "@/lib/api/client"

// ---- 型定義 ---------------------------------------------------------------

interface UserSettingsResponse {
  balance?: string | number | null
  wallet_address?: string | null
}

type Tab = "deposit" | "withdraw"

// 出金ネットワーク手数料概算 (USDC)
const WITHDRAW_FEE = 0.08

// ---- 確認シート（出金用） ---------------------------------------------------

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

  // 残高・ウォレット
  const [balance, setBalance] = useState<number | null>(null)
  const [walletAddress, setWalletAddress] = useState<string | null>(null)
  const [balanceLoading, setBalanceLoading] = useState(true)

  // 入金: コピー状態
  const [copied, setCopied] = useState(false)

  // 出金フォーム
  const [withdrawAmount, setWithdrawAmount] = useState("")

  // 確認シート（出金のみ）
  const [confirmOpen, setConfirmOpen] = useState(false)
  const [confirmBusy, setConfirmBusy] = useState(false)
  const [confirmError, setConfirmError] = useState<string | null>(null)
  const [successMsg, setSuccessMsg] = useState<string | null>(null)

  // ---- 残高取得 ------------------------------------------------------------

  const fetchBalance = useCallback(async () => {
    setBalanceLoading(true)
    try {
      const res = await apiFetch<UserSettingsResponse>("/api/user/settings")
      setBalance(res.balance != null ? Number(res.balance) : null)
      setWalletAddress(res.wallet_address ?? null)
    } catch {
      setBalance(null)
    } finally {
      setBalanceLoading(false)
    }
  }, [])

  useEffect(() => {
    void fetchBalance()
  }, [fetchBalance])

  // ---- 出金可能額上限 -------------------------------------------------------

  const maxWithdraw = balance ?? 0
  const withdrawNum = parseFloat(withdrawAmount) || 0
  const receiveAmount = Math.max(0, withdrawNum - WITHDRAW_FEE)

  // ---- タブ切替 ------------------------------------------------------------

  const handleTabChange = (t: Tab) => {
    setTab(t)
    setConfirmOpen(false)
    setConfirmError(null)
    setSuccessMsg(null)
  }

  // ---- アドレスコピー -------------------------------------------------------

  const handleCopyAddress = useCallback(async () => {
    if (!walletAddress) return
    try {
      await navigator.clipboard.writeText(walletAddress)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    } catch {
      // clipboard API 非対応環境では無視
    }
  }, [walletAddress])

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
      await apiPost<{ status: string }>("/api/transactions/withdraw", {
        amount_usdc: withdrawNum,
      })
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
          {/* 説明 */}
          <p className="text-sm text-zinc-400">
            「入金する」を押すと入金用アドレスが表示されます。取引所（例: SBI VCトレード）や
            お持ちのウォレットから USDC を送金してください。
          </p>

          {/* アドレス表示カード */}
          {walletAddress ? (
            <div className="bg-zinc-800 border border-zinc-700 rounded-xl px-4 py-4 space-y-3">
              <p className="text-xs text-zinc-400">入金用アドレス（Base Mainnet）</p>
              <p className="text-xs font-mono text-zinc-200 break-all leading-relaxed">
                {walletAddress}
              </p>
              <button
                onClick={() => { void handleCopyAddress() }}
                className="flex items-center gap-2 w-full justify-center bg-[#1D9E75] hover:bg-[#1a8f6a]
                           text-white font-semibold py-3 rounded-xl transition-colors"
              >
                {copied ? (
                  <>
                    <Check className="w-4 h-4" />
                    コピーしました
                  </>
                ) : (
                  <>
                    <Copy className="w-4 h-4" />
                    アドレスをコピー
                  </>
                )}
              </button>
            </div>
          ) : balanceLoading ? null : (
            <div className="bg-zinc-800 border border-zinc-700 rounded-xl px-4 py-4">
              <p className="text-sm text-zinc-400 text-center">
                ウォレットアドレスが登録されていません
              </p>
            </div>
          )}

          {/* 注意事項 */}
          <div className="space-y-2 text-xs text-zinc-500">
            <p>・ Ethereum など別ネットワークの USDC も自動で Base に変換されて着金します</p>
            <p>・ 少額すぎると送金できない場合があります（目安: 数十ドル以上）</p>
            <p>・ 着金後、Aave への運用反映まで数分かかる場合があります</p>
          </div>
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

      {/* 確認シート（出金のみ） */}
      <ConfirmSheet
        open={confirmOpen}
        title="出金内容の確認"
        rows={withdrawRows}
        onConfirm={handleWithdrawConfirm}
        onCancel={() => setConfirmOpen(false)}
        busy={confirmBusy}
        error={confirmError}
      />
    </div>
  )
}
