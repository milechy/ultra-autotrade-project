// Copyright (c) Ultra AutoTrade. All rights reserved.
"use client"

import { useEffect, useState } from "react"
import { FileDown, ChevronRight, Loader2, AlertCircle } from "lucide-react"

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? ""

function getToken(): string {
  if (typeof window === "undefined") return ""
  return localStorage.getItem("auth_token") ?? ""
}

interface UserSettings {
  corporate_fiscal_month?: number | null
}

export function TaxPanel() {
  const [settings, setSettings] = useState<UserSettings | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const currentYear = new Date().getFullYear()
  const [selectedYear, setSelectedYear] = useState<number>(currentYear)

  useEffect(() => {
    const token = getToken()
    fetch(`${API_BASE}/api/user/settings`, {
      headers: { Authorization: `Bearer ${token}` },
    })
      .then((r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`)
        return r.json() as Promise<UserSettings>
      })
      .then((data) => {
        setSettings(data)
        setError(null)
      })
      .catch(() => {
        setError("設定の読み込みに失敗しました")
        setSettings({})
      })
      .finally(() => setLoading(false))
  }, [])

  const hasCorpInfo = !!settings?.corporate_fiscal_month

  function downloadFile(url: string, filename: string) {
    const link = document.createElement("a")
    link.href = url
    link.download = filename
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
  }

  function buildDownloadUrl(path: string): string {
    const token = getToken()
    const sep = path.includes("?") ? "&" : "?"
    return `${API_BASE}${path}${sep}token=${encodeURIComponent(token)}`
  }

  if (loading) {
    return (
      <div className="flex flex-col items-center justify-center py-12 text-zinc-500">
        <Loader2 className="w-6 h-6 animate-spin mb-3 text-zinc-600" />
        <p className="text-sm">読み込み中...</p>
      </div>
    )
  }

  const tabs = ["個人", "法人"] as const
  type Tab = (typeof tabs)[number]

  const activeTab: Tab = hasCorpInfo ? "法人" : "個人"

  return (
    <div className="pb-4">
      {/* タブ */}
      <div className="flex border-b border-zinc-800 mb-4">
        {tabs.map((tab) => {
          const isPersonal = tab === "個人"
          const active = hasCorpInfo ? !isPersonal : isPersonal
          const disabled = hasCorpInfo ? isPersonal : !isPersonal
          return (
            <button
              key={tab}
              disabled={disabled}
              className={`flex-1 py-3 text-sm font-medium transition-colors ${
                disabled
                  ? "text-zinc-600 cursor-not-allowed"
                  : active
                  ? "border-b-2 border-[#1D9E75] text-[#1D9E75]"
                  : "text-zinc-400"
              }`}
            >
              {tab}
            </button>
          )
        })}
      </div>

      {/* エラーバナー */}
      {error && (
        <div className="flex items-center gap-2 bg-zinc-800 rounded-xl px-4 py-3 mb-4 text-zinc-400 text-sm">
          <AlertCircle className="w-4 h-4 text-zinc-500 flex-shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {activeTab === "個人" && (
        <PersonalTabContent
          selectedYear={selectedYear}
          onYearChange={setSelectedYear}
          currentYear={currentYear}
          buildDownloadUrl={buildDownloadUrl}
          downloadFile={downloadFile}
        />
      )}

      {activeTab === "法人" && settings?.corporate_fiscal_month && (
        <CorporateTabContent fiscalMonth={settings.corporate_fiscal_month} />
      )}

      {/* 注意書き */}
      <div className="mt-6 px-1">
        <p className="text-zinc-500 text-xs leading-relaxed">
          CSV ファイルは Cryptact（暗号資産税務ソフト）で直接インポートできます。
        </p>
      </div>
    </div>
  )
}

interface YearSelectorProps {
  selectedYear: number
  onYearChange: (year: number) => void
  currentYear: number
}

function YearSelector({ selectedYear, onYearChange, currentYear }: YearSelectorProps) {
  return (
    <div className="flex items-center gap-3 mb-5">
      <span className="text-zinc-400 text-sm">対象年度</span>
      <div className="flex gap-2">
        {[currentYear, currentYear - 1].map((year) => (
          <button
            key={year}
            onClick={() => onYearChange(year)}
            className={`px-4 py-1.5 rounded-full text-sm font-medium transition-colors ${
              selectedYear === year
                ? "bg-[#1D9E75] text-white"
                : "bg-zinc-800 text-zinc-400 hover:bg-zinc-700"
            }`}
          >
            {year}年
          </button>
        ))}
      </div>
    </div>
  )
}

interface DownloadButtonProps {
  label: string
  description: string
  onClick: () => void
  disabled?: boolean
}

function DownloadButton({ label, description, onClick, disabled = false }: DownloadButtonProps) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      className={`w-full flex items-center justify-between bg-zinc-800 px-4 py-4 rounded-xl transition-colors ${
        disabled
          ? "opacity-40 cursor-not-allowed"
          : "hover:bg-zinc-700 active:bg-zinc-600"
      }`}
    >
      <div className="flex items-center gap-3">
        <FileDown className={`w-5 h-5 ${disabled ? "text-zinc-600" : "text-[#4ade9a]"}`} />
        <div className="text-left">
          <div className="text-white text-sm font-medium">{label}</div>
          <div className="text-zinc-500 text-xs">{description}</div>
        </div>
      </div>
      <ChevronRight className="w-4 h-4 text-zinc-600" />
    </button>
  )
}

interface PersonalTabContentProps {
  selectedYear: number
  onYearChange: (year: number) => void
  currentYear: number
  buildDownloadUrl: (path: string) => string
  downloadFile: (url: string, filename: string) => void
}

function PersonalTabContent({
  selectedYear,
  onYearChange,
  currentYear,
  buildDownloadUrl,
  downloadFile,
}: PersonalTabContentProps) {
  return (
    <div className="space-y-3">
      <YearSelector
        selectedYear={selectedYear}
        onYearChange={onYearChange}
        currentYear={currentYear}
      />
      <DownloadButton
        label="Cryptact 用 CSV"
        description="暗号資産税務計算ツール対応"
        onClick={() => {
          const url = buildDownloadUrl(
            `/api/proposals/tax/cryptact-csv?year=${selectedYear}`
          )
          downloadFile(url, `cryptact_${selectedYear}.csv`)
        }}
      />
      <DownloadButton
        label="取引一覧 CSV"
        description="全取引データのエクスポート"
        onClick={() => {
          const url = buildDownloadUrl(
            `/api/transactions/export?year=${selectedYear}`
          )
          downloadFile(url, `transactions_${selectedYear}.csv`)
        }}
      />
    </div>
  )
}

interface CorporateTabContentProps {
  fiscalMonth: number
}

function CorporateTabContent({ fiscalMonth }: CorporateTabContentProps) {
  return (
    <div className="space-y-3">
      {/* 決算月表示 */}
      <div className="flex items-center justify-between bg-zinc-800 rounded-xl px-4 py-3 mb-2">
        <span className="text-zinc-400 text-sm">決算月</span>
        <span className="text-white text-sm font-semibold">{fiscalMonth}月</span>
      </div>

      {/* 準備中: freee/弥生 CSV は税理士承認の仕訳マッピング適用後に提供する。
          個人データを法人フォーマットと偽って返さないため、ここでは DL を出さない。 */}
      <div className="flex items-start gap-2 bg-zinc-800/60 border border-zinc-700 rounded-xl px-4 py-3 text-sm">
        <AlertCircle className="w-4 h-4 text-[#1D9E75] flex-shrink-0 mt-0.5" />
        <div className="text-zinc-300 leading-relaxed">
          <p className="font-medium text-white mb-1">法人向け CSV は準備中です</p>
          <p className="text-zinc-400 text-xs">
            freee / 弥生 形式の仕訳 CSV は、税理士監修の会計マッピング適用後に提供します。
            決算月の設定は保存済みです。
          </p>
        </div>
      </div>
    </div>
  )
}
