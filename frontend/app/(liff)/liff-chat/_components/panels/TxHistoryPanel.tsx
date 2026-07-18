// Copyright (c) Ultra AutoTrade. All rights reserved.
"use client"

import { useEffect, useState } from "react"
import { ArrowDown, ArrowUp, ChevronLeft, Download, ExternalLink, Loader2 } from "lucide-react"
import { useTranslations } from "next-intl"
import { getAuthToken } from "@/lib/auth/token-key"

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? ""

interface Transaction {
  id: number
  operation: "SUPPLY" | "WITHDRAW"
  asset: string
  amount_usd: string
  tx_hash: string | null
  status: string
  created_at: string
  protocol?: string
  apy?: string
  gas_fee_usd?: string
  wallet_address?: string
}

interface CoinSummary {
  asset: string
  total_supply: string
  total_withdraw: string
}

type FilterType = "all" | "SUPPLY" | "WITHDRAW" | "USDC" | "ETH"

function formatDate(iso: string): string {
  const d = new Date(iso)
  return d.toLocaleDateString("ja-JP", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  })
}

function formatMonthHeader(iso: string): string {
  const d = new Date(iso)
  return d.toLocaleDateString("ja-JP", { year: "numeric", month: "long" })
}

function formatAmountUsd(amountUsd: string, operation: "SUPPLY" | "WITHDRAW"): string {
  const num = Number(amountUsd)
  const sign = operation === "SUPPLY" ? "+" : "-"
  return `${sign}$${num.toFixed(2)}`
}

function buildCoinSummaries(txs: Transaction[]): CoinSummary[] {
  const map = new Map<string, { supply: number; withdraw: number }>()
  for (const tx of txs) {
    const key = tx.asset
    const existing = map.get(key) ?? { supply: 0, withdraw: 0 }
    const amt = Number(tx.amount_usd)
    if (tx.operation === "SUPPLY") {
      existing.supply += amt
    } else {
      existing.withdraw += amt
    }
    map.set(key, existing)
  }
  return Array.from(map.entries()).map(([asset, { supply, withdraw }]) => ({
    asset,
    total_supply: supply.toFixed(2),
    total_withdraw: withdraw.toFixed(2),
  }))
}

function groupByMonth(txs: Transaction[]): Array<{ month: string; items: Transaction[] }> {
  const groups = new Map<string, Transaction[]>()
  for (const tx of txs) {
    const key = formatMonthHeader(tx.created_at)
    const arr = groups.get(key) ?? []
    arr.push(tx)
    groups.set(key, arr)
  }
  return Array.from(groups.entries()).map(([month, items]) => ({ month, items }))
}

// --- Detail Panel ---
interface TxDetailPanelProps {
  tx: Transaction
  onClose: () => void
}

function TxDetailPanel({ tx, onClose }: TxDetailPanelProps) {
  const t = useTranslations("Liff.panels.txHistory")
  const isSupply = tx.operation === "SUPPLY"
  const amountDisplay = formatAmountUsd(tx.amount_usd, tx.operation)

  function statusLabel(status: string): string {
    if (status === "executed" || status === "completed") return t("statusExecuted")
    if (status === "pending") return t("statusPending")
    if (status === "failed") return t("statusFailed")
    return status
  }

  const detailRows: Array<{ label: string; value: string }> = [
    { label: t("detailOperation"), value: isSupply ? t("operationSupply") : t("operationWithdraw") },
    { label: t("detailAsset"), value: tx.asset },
    { label: t("detailDate"), value: formatDate(tx.created_at) },
    { label: t("detailStatus"), value: statusLabel(tx.status) },
  ]
  if (tx.apy) detailRows.push({ label: t("detailApy"), value: `${tx.apy}%` })
  if (tx.gas_fee_usd) detailRows.push({ label: t("detailGas"), value: `$${Number(tx.gas_fee_usd).toFixed(4)}` })
  if (tx.wallet_address) detailRows.push({ label: t("detailWallet"), value: `${tx.wallet_address.slice(0, 6)}...${tx.wallet_address.slice(-4)}` })
  if (tx.tx_hash) detailRows.push({ label: t("detailTxHash"), value: `${tx.tx_hash.slice(0, 8)}...${tx.tx_hash.slice(-6)}` })

  return (
    <div className="fixed inset-0 z-[60] ax-bg-app flex flex-col animate-in slide-in-from-right duration-200 w-[375px] mx-auto">
      {/* ヘッダー */}
      <div className="flex items-center bg-gradient-to-br from-[#b9a4f2] via-[#ecaccd] to-[#fbd9a0] px-4 py-3 flex-shrink-0">
        <button onClick={onClose} className="text-[#1c1a27] mr-2">
          <ChevronLeft className="w-5 h-5" />
        </button>
        <h2 className="text-[#1c1a27] font-semibold text-base">{t("detailTitle")}</h2>
      </div>

      <div className="flex-1 overflow-y-auto px-4 pb-8">
        {/* 金額カード */}
        <div className="ax-card-warm rounded-2xl p-4 mt-4 mb-6">
          <div className={`text-3xl font-bold ${isSupply ? "text-[#1D9E75]" : "text-orange-400"}`}>
            {amountDisplay}
          </div>
          <div className="text-[#736f7e] text-sm mt-1">
            {tx.operation} · {tx.asset}
          </div>
        </div>

        {/* 詳細行 */}
        <div className="space-y-0">
          {detailRows.map((row) => (
            <div key={row.label} className="flex justify-between items-start py-3 border-b border-[#1c1a27]/15">
              <span className="text-[#736f7e] text-sm">{row.label}</span>
              <span className="text-[#1c1a27] text-sm text-right max-w-[60%] break-all">{row.value}</span>
            </div>
          ))}
        </div>

        {/* Basescan リンク */}
        {tx.tx_hash && (
          <a
            href={`https://basescan.org/tx/${tx.tx_hash}`}
            target="_blank"
            rel="noopener noreferrer"
            className="mt-6 flex items-center justify-center gap-2 w-full py-3 rounded-xl border border-[#1c1a27]/15 text-[#736f7e] hover:bg-black/5 transition-colors text-sm"
          >
            <ExternalLink className="w-4 h-4" />
            {t("detailBasescanBtn")}
          </a>
        )}
      </div>
    </div>
  )
}

// --- Main Panel ---
export function TxHistoryPanel() {
  const t = useTranslations("Liff.panels.txHistory")
  const [txs, setTxs] = useState<Transaction[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [filter, setFilter] = useState<FilterType>("all")
  const [selectedTx, setSelectedTx] = useState<Transaction | null>(null)
  // 401 (認証切れ) を一般エラーと区別し、再ログイン導線を出すためのフラグ。
  const [authExpired, setAuthExpired] = useState(false)

  useEffect(() => {
    // token-key 統一: 正準/旧キーの両方を救済する getAuthToken を使う
    // (旧キーで保存済みセッションの 401 取りこぼしを防ぐ)。
    const token = getAuthToken()
    setLoading(true)
    setError(null)
    setAuthExpired(false)

    // token が無い状態で Bearer null を投げると確定 401 になるため、
    // 先に fail-visible で再ログイン導線を出す (黒画面・無言失敗にしない)。
    if (!token) {
      setAuthExpired(true)
      setLoading(false)
      return
    }

    fetch(`${API_BASE}/api/transactions?limit=50&offset=0`, {
      headers: { Authorization: `Bearer ${token}` },
    })
      .then((r) => {
        if (r.status === 401) {
          setAuthExpired(true)
          throw new Error("auth_expired")
        }
        if (!r.ok) throw new Error(`HTTP ${r.status}`)
        return r.json() as Promise<Transaction[] | { items: Transaction[] }>
      })
      .then((data) => {
        const items = Array.isArray(data) ? data : data.items
        setTxs(items)
      })
      .catch((err: unknown) => {
        if (err instanceof Error && err.message !== "auth_expired") {
          setError(err.message)
        }
      })
      .finally(() => setLoading(false))
  }, [])

  const handleCsvDownload = () => {
    const token = getAuthToken()
    if (!token) {
      // 認証切れ: 黙ってダウンロードさせず再ログイン導線へ寄せる。
      setAuthExpired(true)
      return
    }
    const url = `${API_BASE}/api/proposals/tax/cryptact-csv`
    const link = document.createElement("a")
    // トークンをクエリに渡す（シンプルな download リンク用）
    link.href = `${url}?token=${encodeURIComponent(token)}`
    link.download = "uata_tax_report.csv"
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
  }

  function statusLabel(status: string): string {
    if (status === "executed" || status === "completed") return t("statusExecuted")
    if (status === "pending") return t("statusPending")
    if (status === "failed") return t("statusFailed")
    return status
  }

  // フィルタリング
  const filteredTxs = txs.filter((tx) => {
    if (filter === "all") return true
    if (filter === "SUPPLY") return tx.operation === "SUPPLY"
    if (filter === "WITHDRAW") return tx.operation === "WITHDRAW"
    if (filter === "USDC") return tx.asset === "USDC"
    if (filter === "ETH") return tx.asset === "ETH" || tx.asset === "WETH"
    return true
  })

  const coinSummaries = buildCoinSummaries(txs)
  const grouped = groupByMonth(filteredTxs)

  // 資産フィルタ（USDC / ETH）は **履歴に実在する資産だけ** 出す。
  // 以前は ETH タブを常時ハードコードしており、ETH 建て取引が 1 件も無くても表示され、
  // タップすると必ず空になっていた（テスター報告 2026-07-17「ETH が残ってます」）。
  const hasUsdc = txs.some((tx) => tx.asset === "USDC")
  const hasEth = txs.some((tx) => tx.asset === "ETH" || tx.asset === "WETH")

  // 選択中の資産フィルタが（ポーリング更新等で）実在しなくなったら "all" に戻す
  // （消えたタブが選ばれたまま空表示になるのを防ぐ）。
  useEffect(() => {
    if (filter === "USDC" && !hasUsdc) setFilter("all")
    if (filter === "ETH" && !hasEth) setFilter("all")
  }, [filter, hasUsdc, hasEth])

  const FILTERS: Array<{ id: FilterType; label: string }> = [
    { id: "all", label: t("filterAll") },
    { id: "SUPPLY", label: "SUPPLY" },
    { id: "WITHDRAW", label: "WITHDRAW" },
    ...(hasUsdc ? [{ id: "USDC" as FilterType, label: "USDC" }] : []),
    ...(hasEth ? [{ id: "ETH" as FilterType, label: "ETH" }] : []),
  ]

  if (loading) {
    return (
      <div className="flex flex-col items-center justify-center py-12 text-[#736f7e]">
        <Loader2 className="w-6 h-6 mb-3 text-[#736f7e] animate-spin" />
        <p className="text-sm">{t("loading")}</p>
      </div>
    )
  }

  // 認証切れ (401 / token 欠落): 黒画面・無言失敗にせず再ログイン導線を出す。
  if (authExpired) {
    return (
      <div className="flex flex-col items-center justify-center py-12 px-4 text-center">
        <p className="text-sm text-[#736f7e] mb-1">{t("authExpiredTitle")}</p>
        <p className="text-xs text-[#736f7e] mb-5">
          {t("authExpiredDesc")}
        </p>
        <button
          onClick={() => {
            if (typeof window !== "undefined") {
              window.location.href = "/liff-login"
            }
          }}
          className="bg-[#1D9E75] hover:bg-[#178a66] text-white text-sm font-semibold px-5 py-2.5 rounded-xl transition-colors"
        >
          {t("reloginBtn")}
        </button>
      </div>
    )
  }

  if (error) {
    return (
      <div className="flex flex-col items-center justify-center py-12 text-[#736f7e]">
        <p className="text-sm text-red-600">{error}</p>
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-4">
      {/* CSV ダウンロードボタン */}
      <div className="flex justify-end">
        <button
          onClick={handleCsvDownload}
          className="flex items-center gap-1.5 ax-card-warm hover:bg-black/5 text-[#736f7e] text-xs px-3 py-1.5 rounded-lg transition-colors"
        >
          <Download className="w-3.5 h-3.5" />
          {t("csvBtn")}
        </button>
      </div>

      {/* コイン別サマリーバー */}
      {coinSummaries.length > 0 && (
        <div className="flex gap-2 overflow-x-auto pb-2 scrollbar-hide">
          {coinSummaries.map((coin) => (
            <div
              key={coin.asset}
              className="flex-shrink-0 ax-card-warm rounded-xl px-3 py-2 min-w-[100px]"
            >
              <div className="text-xs text-[#736f7e] font-medium mb-0.5">{coin.asset}</div>
              <div className="text-[#1D9E75] text-xs">+${coin.total_supply}</div>
              <div className="text-orange-400 text-xs">-${coin.total_withdraw}</div>
            </div>
          ))}
        </div>
      )}

      {/* フィルターバー */}
      <div className="flex gap-2 overflow-x-auto pb-1 scrollbar-hide">
        {FILTERS.map((f) => (
          <button
            key={f.id}
            onClick={() => setFilter(f.id)}
            className={`flex-shrink-0 text-xs px-3 py-1.5 rounded-full transition-colors ${
              filter === f.id
                ? "bg-[#1D9E75] text-white"
                : "ax-card-warm text-[#736f7e] hover:bg-black/5"
            }`}
          >
            {f.label}
          </button>
        ))}
      </div>

      {/* 取引リスト */}
      {filteredTxs.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-12 text-[#736f7e]">
          <p className="text-sm">{t("noTxs")}</p>
        </div>
      ) : (
        <div className="flex flex-col">
          {grouped.map(({ month, items }) => (
            <div key={month}>
              {/* 月ヘッダー */}
              <div className="text-[#736f7e] text-xs font-semibold py-2 pt-4">
                {month}
              </div>
              {/* 行 */}
              {items.map((tx) => {
                const isSupply = tx.operation === "SUPPLY"
                return (
                  <button
                    key={tx.id}
                    onClick={() => setSelectedTx(tx)}
                    className="flex items-center w-full py-3 border-b border-[#1c1a27]/15 text-left hover:bg-black/5 transition-colors -mx-1 px-1 rounded"
                  >
                    {/* 種別アイコン */}
                    <div className="mr-3 w-8 h-8 rounded-full flex items-center justify-center ax-card-warm flex-shrink-0">
                      {isSupply ? (
                        <ArrowDown className="w-4 h-4 text-[#1D9E75]" />
                      ) : (
                        <ArrowUp className="w-4 h-4 text-orange-400" />
                      )}
                    </div>
                    {/* 情報 */}
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-1.5">
                        <span className="text-[#1c1a27] text-sm font-medium">
                          {tx.operation}
                        </span>
                        <span className="bg-[#1c1a27]/10 text-[#736f7e] text-xs px-1.5 py-0.5 rounded">
                          {tx.asset}
                        </span>
                      </div>
                      <div className="text-[#736f7e] text-xs mt-0.5">{formatDate(tx.created_at)}</div>
                    </div>
                    {/* 金額 */}
                    <div className="text-right flex-shrink-0 ml-2">
                      <div className={`font-medium text-sm ${isSupply ? "text-[#1D9E75]" : "text-orange-400"}`}>
                        {formatAmountUsd(tx.amount_usd, tx.operation)}
                      </div>
                      <div className="text-[#736f7e] text-xs mt-0.5">{statusLabel(tx.status)}</div>
                    </div>
                  </button>
                )
              })}
            </div>
          ))}
        </div>
      )}

      {/* 詳細パネル */}
      {selectedTx && (
        <TxDetailPanel tx={selectedTx} onClose={() => setSelectedTx(null)} />
      )}
    </div>
  )
}
