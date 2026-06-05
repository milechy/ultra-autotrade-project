// Copyright (c) Ultra AutoTrade. All rights reserved.
"use client"

import { useEffect, useState } from "react"
import { ArrowDown, ArrowUp, ChevronLeft, Download, ExternalLink, Loader2 } from "lucide-react"

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

function getToken(): string {
  if (typeof window === "undefined") return ""
  return localStorage.getItem("auth_token") ?? ""
}

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

function statusLabel(status: string): string {
  if (status === "executed" || status === "completed") return "実行済み"
  if (status === "pending") return "保留中"
  if (status === "failed") return "失敗"
  return status
}

// --- Detail Panel ---
interface TxDetailPanelProps {
  tx: Transaction
  onClose: () => void
}

function TxDetailPanel({ tx, onClose }: TxDetailPanelProps) {
  const isSupply = tx.operation === "SUPPLY"
  const amountDisplay = formatAmountUsd(tx.amount_usd, tx.operation)

  const detailRows: Array<{ label: string; value: string }> = [
    { label: "操作", value: isSupply ? "SUPPLY (入金)" : "WITHDRAW (出金)" },
    { label: "アセット", value: tx.asset },
    { label: "日時", value: formatDate(tx.created_at) },
    { label: "ステータス", value: statusLabel(tx.status) },
  ]
  if (tx.protocol) detailRows.push({ label: "プロトコル", value: tx.protocol })
  if (tx.apy) detailRows.push({ label: "APY", value: `${tx.apy}%` })
  if (tx.gas_fee_usd) detailRows.push({ label: "ガス代", value: `$${Number(tx.gas_fee_usd).toFixed(4)}` })
  if (tx.wallet_address) detailRows.push({ label: "ウォレット", value: `${tx.wallet_address.slice(0, 6)}...${tx.wallet_address.slice(-4)}` })
  if (tx.tx_hash) detailRows.push({ label: "Tx Hash", value: `${tx.tx_hash.slice(0, 8)}...${tx.tx_hash.slice(-6)}` })

  return (
    <div className="fixed inset-0 z-[60] bg-zinc-900 flex flex-col animate-in slide-in-from-right duration-200 w-[375px] mx-auto">
      {/* ヘッダー */}
      <div className="flex items-center bg-[#1a3d2e] px-4 py-3 flex-shrink-0">
        <button onClick={onClose} className="text-white mr-2">
          <ChevronLeft className="w-5 h-5" />
        </button>
        <h2 className="text-white font-semibold text-base">取引詳細</h2>
      </div>

      <div className="flex-1 overflow-y-auto px-4 pb-8">
        {/* 金額カード */}
        <div className="bg-[#1a3d2e] rounded-2xl p-4 mt-4 mb-6">
          <div className={`text-3xl font-bold ${isSupply ? "text-[#4ade9a]" : "text-orange-400"}`}>
            {amountDisplay}
          </div>
          <div className="text-zinc-300 text-sm mt-1">
            {tx.operation} · {tx.asset}
          </div>
        </div>

        {/* 詳細行 */}
        <div className="space-y-0">
          {detailRows.map((row) => (
            <div key={row.label} className="flex justify-between items-start py-3 border-b border-zinc-800">
              <span className="text-zinc-500 text-sm">{row.label}</span>
              <span className="text-zinc-100 text-sm text-right max-w-[60%] break-all">{row.value}</span>
            </div>
          ))}
        </div>

        {/* Basescan リンク */}
        {tx.tx_hash && (
          <a
            href={`https://basescan.org/tx/${tx.tx_hash}`}
            target="_blank"
            rel="noopener noreferrer"
            className="mt-6 flex items-center justify-center gap-2 w-full py-3 rounded-xl border border-zinc-700 text-zinc-300 hover:bg-zinc-800 transition-colors text-sm"
          >
            <ExternalLink className="w-4 h-4" />
            Basescanで確認する
          </a>
        )}
      </div>
    </div>
  )
}

// --- Main Panel ---
export function TxHistoryPanel() {
  const [txs, setTxs] = useState<Transaction[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [filter, setFilter] = useState<FilterType>("all")
  const [selectedTx, setSelectedTx] = useState<Transaction | null>(null)

  useEffect(() => {
    const token = getToken()
    setLoading(true)
    setError(null)
    fetch(`${API_BASE}/api/transactions?limit=50&offset=0`, {
      headers: { Authorization: `Bearer ${token}` },
    })
      .then((r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`)
        return r.json() as Promise<Transaction[] | { items: Transaction[] }>
      })
      .then((data) => {
        const items = Array.isArray(data) ? data : data.items
        setTxs(items)
      })
      .catch((err: unknown) => {
        setError(err instanceof Error ? err.message : "データ取得に失敗しました")
      })
      .finally(() => setLoading(false))
  }, [])

  const handleCsvDownload = () => {
    const token = getToken()
    const url = `${API_BASE}/api/proposals/tax/cryptact-csv`
    const link = document.createElement("a")
    // トークンをクエリに渡す（シンプルな download リンク用）
    link.href = `${url}?token=${encodeURIComponent(token)}`
    link.download = "uata_tax_report.csv"
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
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

  const FILTERS: Array<{ id: FilterType; label: string }> = [
    { id: "all", label: "すべて" },
    { id: "SUPPLY", label: "SUPPLY" },
    { id: "WITHDRAW", label: "WITHDRAW" },
    { id: "USDC", label: "USDC" },
    { id: "ETH", label: "ETH" },
  ]

  if (loading) {
    return (
      <div className="flex flex-col items-center justify-center py-12 text-zinc-500">
        <Loader2 className="w-6 h-6 mb-3 text-zinc-600 animate-spin" />
        <p className="text-sm">読み込み中...</p>
      </div>
    )
  }

  if (error) {
    return (
      <div className="flex flex-col items-center justify-center py-12 text-zinc-500">
        <p className="text-sm text-red-400">{error}</p>
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-4">
      {/* CSV ダウンロードボタン */}
      <div className="flex justify-end">
        <button
          onClick={handleCsvDownload}
          className="flex items-center gap-1.5 bg-zinc-800 hover:bg-zinc-700 text-zinc-300 text-xs px-3 py-1.5 rounded-lg transition-colors"
        >
          <Download className="w-3.5 h-3.5" />
          CSV
        </button>
      </div>

      {/* コイン別サマリーバー */}
      {coinSummaries.length > 0 && (
        <div className="flex gap-2 overflow-x-auto pb-2 scrollbar-hide">
          {coinSummaries.map((coin) => (
            <div
              key={coin.asset}
              className="flex-shrink-0 bg-zinc-800 rounded-xl px-3 py-2 min-w-[100px]"
            >
              <div className="text-xs text-zinc-400 font-medium mb-0.5">{coin.asset}</div>
              <div className="text-[#4ade9a] text-xs">+${coin.total_supply}</div>
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
                : "bg-zinc-800 text-zinc-400 hover:bg-zinc-700"
            }`}
          >
            {f.label}
          </button>
        ))}
      </div>

      {/* 取引リスト */}
      {filteredTxs.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-12 text-zinc-500">
          <p className="text-sm">取引履歴がありません</p>
        </div>
      ) : (
        <div className="flex flex-col">
          {grouped.map(({ month, items }) => (
            <div key={month}>
              {/* 月ヘッダー */}
              <div className="text-zinc-500 text-xs font-semibold py-2 pt-4">
                {month}
              </div>
              {/* 行 */}
              {items.map((tx) => {
                const isSupply = tx.operation === "SUPPLY"
                return (
                  <button
                    key={tx.id}
                    onClick={() => setSelectedTx(tx)}
                    className="flex items-center w-full py-3 border-b border-zinc-800 text-left hover:bg-zinc-800/50 transition-colors -mx-1 px-1 rounded"
                  >
                    {/* 種別アイコン */}
                    <div className="mr-3 w-8 h-8 rounded-full flex items-center justify-center bg-zinc-800 flex-shrink-0">
                      {isSupply ? (
                        <ArrowDown className="w-4 h-4 text-[#4ade9a]" />
                      ) : (
                        <ArrowUp className="w-4 h-4 text-orange-400" />
                      )}
                    </div>
                    {/* 情報 */}
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-1.5">
                        <span className="text-white text-sm font-medium">
                          {tx.operation}
                        </span>
                        <span className="bg-zinc-700 text-zinc-300 text-xs px-1.5 py-0.5 rounded">
                          {tx.asset}
                        </span>
                      </div>
                      <div className="text-zinc-500 text-xs mt-0.5">{formatDate(tx.created_at)}</div>
                    </div>
                    {/* 金額 */}
                    <div className="text-right flex-shrink-0 ml-2">
                      <div className={`font-medium text-sm ${isSupply ? "text-[#4ade9a]" : "text-orange-400"}`}>
                        {formatAmountUsd(tx.amount_usd, tx.operation)}
                      </div>
                      <div className="text-zinc-500 text-xs mt-0.5">{statusLabel(tx.status)}</div>
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
