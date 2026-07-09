// Copyright (c) Ultra AutoTrade. All rights reserved.
"use client"

import { useEffect, useState } from "react"
import { FileDown, ChevronRight, Loader2, AlertCircle } from "lucide-react"
import { useTranslations } from "next-intl"
import { getAuthToken } from "@/lib/auth/token-key"
import { saveBlob } from "@/lib/saveBlob"

type TFn = ReturnType<typeof useTranslations>

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? ""

interface UserSettings {
  corporate_fiscal_month?: number | null
}

export function TaxPanel() {
  const t = useTranslations("Liff.panels.tax")
  const [settings, setSettings] = useState<UserSettings | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const now = new Date()
  const currentYear = now.getFullYear()
  const currentMonth = now.getMonth() + 1
  const [selectedYear, setSelectedYear] = useState<number>(currentYear)
  const [selectedMonth, setSelectedMonth] = useState<number>(currentMonth)

  useEffect(() => {
    const token = getAuthToken()
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
        setError(t("loadError"))
        setSettings({})
      })
      .finally(() => setLoading(false))
  }, [t])

  const hasCorpInfo = !!settings?.corporate_fiscal_month

  // filename に拡張子が無い場合は blob.type から付与する。
  // 月次レポートはサーバ側 reportlab の有無で PDF / CSV が切り替わるため、
  // クライアントでは Content-Type（CORS セーフリストヘッダ）から拡張子を判定する。
  async function downloadFile(url: string, filename: string) {
    const token = getAuthToken()
    const response = await fetch(url, {
      headers: { Authorization: "Bearer " + (token ?? "") },
    })
    if (response.status === 401) {
      window.location.href = "/liff-login"
      return
    }
    if (!response.ok) {
      throw new Error("Download failed: " + response.status)
    }
    const blob = await response.blob()
    let resolvedName = filename
    if (!filename.includes(".")) {
      const ext = blob.type.includes("pdf") ? "pdf" : "csv"
      resolvedName = `${filename}.${ext}`
    }
    await saveBlob(blob, resolvedName)
  }

  function buildDownloadUrl(path: string): string {
    return `${API_BASE}${path}`
  }

  if (loading) {
    return (
      <div className="flex flex-col items-center justify-center py-12 text-[#736f7e]">
        <Loader2 className="w-6 h-6 animate-spin mb-3 text-[#736f7e]" />
        <p className="text-sm">{t("loading")}</p>
      </div>
    )
  }

  const tabs = [t("tabPersonal"), t("tabCorporate")] as const

  const activeTabIsPersonal = !hasCorpInfo

  return (
    <div className="pb-4">
      {/* タブ */}
      <div className="flex border-b border-[#1c1a27]/15 mb-4">
        {tabs.map((tab, idx) => {
          const isPersonalTab = idx === 0
          const active = hasCorpInfo ? !isPersonalTab : isPersonalTab
          const disabled = hasCorpInfo ? isPersonalTab : !isPersonalTab
          return (
            <button
              key={tab}
              disabled={disabled}
              className={`flex-1 py-3 text-sm font-medium transition-colors ${
                disabled
                  ? "text-[#736f7e] cursor-not-allowed"
                  : active
                  ? "border-b-2 border-[#1D9E75] text-[#1D9E75]"
                  : "text-[#736f7e]"
              }`}
            >
              {tab}
            </button>
          )
        })}
      </div>

      {/* エラーバナー */}
      {error && (
        <div className="flex items-center gap-2 ax-card-warm rounded-xl px-4 py-3 mb-4 text-[#736f7e] text-sm">
          <AlertCircle className="w-4 h-4 text-[#736f7e] flex-shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {activeTabIsPersonal && (
        <PersonalTabContent
          selectedYear={selectedYear}
          onYearChange={setSelectedYear}
          selectedMonth={selectedMonth}
          onMonthChange={setSelectedMonth}
          currentYear={currentYear}
          buildDownloadUrl={buildDownloadUrl}
          downloadFile={downloadFile}
          t={t}
        />
      )}

      {!activeTabIsPersonal && settings?.corporate_fiscal_month && (
        <CorporateTabContent fiscalMonth={settings.corporate_fiscal_month} t={t} />
      )}

      {/* 注意書き */}
      <div className="mt-6 px-1">
        <p className="text-[#736f7e] text-xs leading-relaxed">
          {t("cryptactNote")}
        </p>
      </div>
    </div>
  )
}

interface YearSelectorProps {
  selectedYear: number
  onYearChange: (year: number) => void
  currentYear: number
  t: TFn
}

function YearSelector({ selectedYear, onYearChange, currentYear, t }: YearSelectorProps) {
  return (
    <div className="flex items-center gap-3 mb-5">
      <span className="text-[#736f7e] text-sm">{t("yearLabel")}</span>
      <div className="flex gap-2">
        {[currentYear, currentYear - 1].map((year) => (
          <button
            key={year}
            onClick={() => onYearChange(year)}
            className={`px-4 py-1.5 rounded-full text-sm font-medium transition-colors ${
              selectedYear === year
                ? "bg-[#1D9E75] text-white"
                : "ax-card-warm text-[#736f7e] hover:bg-black/5"
            }`}
          >
            {year}
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
      className={`w-full flex items-center justify-between ax-card-warm px-4 py-4 rounded-xl transition-colors ${
        disabled
          ? "opacity-40 cursor-not-allowed"
          : "hover:bg-black/5 active:bg-black/10"
      }`}
    >
      <div className="flex items-center gap-3">
        <FileDown className={`w-5 h-5 ${disabled ? "text-[#736f7e]" : "text-[#1D9E75]"}`} />
        <div className="text-left">
          <div className="text-[#1c1a27] text-sm font-medium">{label}</div>
          <div className="text-[#736f7e] text-xs">{description}</div>
        </div>
      </div>
      <ChevronRight className="w-4 h-4 text-[#736f7e]" />
    </button>
  )
}

interface PersonalTabContentProps {
  selectedYear: number
  onYearChange: (year: number) => void
  selectedMonth: number
  onMonthChange: (month: number) => void
  currentYear: number
  buildDownloadUrl: (path: string) => string
  downloadFile: (url: string, filename: string) => Promise<void>
  t: TFn
}

function PersonalTabContent({
  selectedYear,
  onYearChange,
  selectedMonth,
  onMonthChange,
  currentYear,
  buildDownloadUrl,
  downloadFile,
  t,
}: PersonalTabContentProps) {
  return (
    <div className="space-y-3">
      <YearSelector
        selectedYear={selectedYear}
        onYearChange={onYearChange}
        currentYear={currentYear}
        t={t}
      />
      <DownloadButton
        label={t("cryptactCsvLabel")}
        description={t("cryptactCsvDesc")}
        onClick={() => {
          const url = buildDownloadUrl(
            `/api/proposals/tax/cryptact-csv?year=${selectedYear}`
          )
          void downloadFile(url, `cryptact_${selectedYear}.csv`)
        }}
      />
      <DownloadButton
        label={t("txCsvLabel")}
        description={t("txCsvDesc")}
        onClick={() => {
          const url = buildDownloadUrl(
            `/api/transactions/export?year=${selectedYear}`
          )
          void downloadFile(url, `transactions_${selectedYear}.csv`)
        }}
      />

      <MonthlyReportSection
        selectedYear={selectedYear}
        selectedMonth={selectedMonth}
        onMonthChange={onMonthChange}
        buildDownloadUrl={buildDownloadUrl}
        downloadFile={downloadFile}
        t={t}
      />
    </div>
  )
}

interface MonthlyReportSectionProps {
  selectedYear: number
  selectedMonth: number
  onMonthChange: (month: number) => void
  buildDownloadUrl: (path: string) => string
  downloadFile: (url: string, filename: string) => Promise<void>
  t: TFn
}

function MonthlyReportSection({
  selectedYear,
  selectedMonth,
  onMonthChange,
  buildDownloadUrl,
  downloadFile,
  t,
}: MonthlyReportSectionProps) {
  const [downloading, setDownloading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function handleDownload() {
    if (downloading) return
    setDownloading(true)
    setError(null)
    try {
      const url = buildDownloadUrl(
        `/api/reports/monthly?year=${selectedYear}&month=${selectedMonth}`
      )
      // 拡張子は downloadFile が Content-Type から判定する（PDF / CSV 両対応）
      const mm = String(selectedMonth).padStart(2, "0")
      await downloadFile(url, `monthly_report_${selectedYear}_${mm}`)
    } catch {
      setError(t("monthlyReportError"))
    } finally {
      setDownloading(false)
    }
  }

  return (
    <div className="pt-4 mt-2 border-t border-[#1c1a27]/15">
      <div className="flex items-center gap-3 mb-3">
        <span className="text-[#736f7e] text-sm">{t("monthLabel")}</span>
        <select
          aria-label={t("monthLabel")}
          value={selectedMonth}
          onChange={(e) => onMonthChange(Number(e.target.value))}
          className="ax-card-warm text-[#1c1a27] text-sm rounded-full px-4 py-1.5 focus:outline-none focus:ring-1 focus:ring-[#1D9E75]"
        >
          {Array.from({ length: 12 }, (_, i) => i + 1).map((m) => (
            <option key={m} value={m}>
              {t("monthUnit", { month: m })}
            </option>
          ))}
        </select>
      </div>

      <DownloadButton
        label={t("monthlyReportLabel")}
        description={t("monthlyReportDesc")}
        onClick={() => void handleDownload()}
        disabled={downloading}
      />

      {downloading && (
        <div className="flex items-center gap-2 mt-2 px-1 text-[#736f7e] text-xs">
          <Loader2 className="w-3 h-3 animate-spin" />
          <span>{t("monthlyReportLoading")}</span>
        </div>
      )}

      {error && (
        <div className="flex items-center gap-2 mt-2 px-1 text-[#736f7e] text-xs">
          <AlertCircle className="w-3 h-3 flex-shrink-0" />
          <span>{error}</span>
        </div>
      )}
    </div>
  )
}

interface CorporateTabContentProps {
  fiscalMonth: number
  t: TFn
}

function CorporateTabContent({ fiscalMonth, t }: CorporateTabContentProps) {
  return (
    <div className="space-y-3">
      {/* 決算月表示 */}
      <div className="flex items-center justify-between ax-card-warm rounded-xl px-4 py-3 mb-2">
        <span className="text-[#736f7e] text-sm">{t("corpFiscalMonthLabel")}</span>
        <span className="text-[#1c1a27] text-sm font-semibold">{t("corpFiscalMonthUnit", { month: fiscalMonth })}</span>
      </div>

      {/* 準備中: freee/弥生 CSV は税理士承認の仕訳マッピング適用後に提供する。
          個人データを法人フォーマットと偽って返さないため、ここでは DL を出さない。 */}
      <div className="flex items-start gap-2 ax-card-warm border border-[#1c1a27]/15 rounded-xl px-4 py-3 text-sm">
        <AlertCircle className="w-4 h-4 text-[#1D9E75] flex-shrink-0 mt-0.5" />
        <div className="text-[#736f7e] leading-relaxed">
          <p className="font-medium text-[#1c1a27] mb-1">{t("corpCsvPendingTitle")}</p>
          <p className="text-[#736f7e] text-xs">
            {t("corpCsvPendingDesc")}
          </p>
        </div>
      </div>
    </div>
  )
}
