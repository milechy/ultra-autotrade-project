// Copyright (c) Ultra AutoTrade. All rights reserved.
// _components/AssetChart.tsx — recharts AreaChart（dynamic import 経由で使用）
"use client"

import { useState, useEffect } from "react"
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
} from "recharts"
import { useTranslations } from "next-intl"

interface Props {
  period: "1M" | "3M" | "6M" | "1Y"
}

interface DataPoint {
  date: string
  value: number
}

// バックエンド GET /api/portfolio/history のレスポンス要素 (PortfolioSnapshotResponse)。
// Decimal は JSON では文字列で返るため value は Number() でラップする。
interface PortfolioSnapshot {
  total_value_usd: string | number
  recorded_at: string
}

interface PortfolioHistoryResponse {
  items?: PortfolioSnapshot[]
}

// UI の期間タブ (1M/3M/6M/1Y) を backend の period 値 (7d/30d/90d/all) に対応付ける。
// backend は 7d/30d/90d/all のみ受け付けるため、6M/1Y は "all" に丸める。
const PERIOD_MAP: Record<Props["period"], string> = {
  "1M": "30d",
  "3M": "90d",
  "6M": "all",
  "1Y": "all",
}

export default function AssetChart({ period }: Props) {
  const t = useTranslations("Liff.panels")
  const [data, setData] = useState<DataPoint[]>([])
  const [loaded, setLoaded] = useState(false)

  useEffect(() => {
    const token =
      typeof window !== "undefined"
        ? (localStorage.getItem("auth_token") ?? "")
        : ""
    const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? ""
    const backendPeriod = PERIOD_MAP[period]

    // 資産推移は PortfolioSnapshot の総資産額 (total_value_usd) を時系列で描く。
    // v3 (REBALANCE_SHADOW_MODE=true) では snapshot が無く items=[] が正 → 「データなし」表示。
    fetch(
      `${API_BASE}/api/portfolio/history?period=${backendPeriod}&interval=daily`,
      { headers: token ? { Authorization: `Bearer ${token}` } : {} },
    )
      .then((r) => (r.ok ? r.json() : null))
      .then((d: PortfolioHistoryResponse | null) => {
        const items = d?.items ?? []
        if (items.length > 0) {
          setData(
            items.map((it) => ({
              date: it.recorded_at,
              value: Number(it.total_value_usd),
            })),
          )
        } else {
          setData([])
        }
        setLoaded(true)
      })
      .catch(() => {
        setData([])
        setLoaded(true)
      })
  }, [period])

  if (loaded && data.length === 0) {
    return (
      <div className="h-[200px] w-full flex items-center justify-center">
        <p className="text-sm text-gray-400">{t("assetHistoryEmpty")}</p>
      </div>
    )
  }

  return (
    <div className="h-[200px] w-full">
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={data} margin={{ top: 4, right: 4, left: 0, bottom: 0 }}>
          <defs>
            <linearGradient id="assetGrad" x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor="#1D9E75" stopOpacity={0.3} />
              <stop offset="95%" stopColor="#1D9E75" stopOpacity={0} />
            </linearGradient>
          </defs>
          <XAxis dataKey="date" hide />
          <YAxis hide />
          <Tooltip
            contentStyle={{
              background: "#1a1a2e",
              border: "1px solid #333",
              borderRadius: "8px",
              fontSize: "12px",
            }}
            labelStyle={{ color: "#9ca3af" }}
            formatter={(v: number) => [`$${v.toLocaleString()}`, t("statsCurrent")]}
          />
          <Area
            type="monotone"
            dataKey="value"
            stroke="#1D9E75"
            strokeWidth={2}
            fill="url(#assetGrad)"
            dot={false}
            activeDot={{ r: 4, fill: "#4ade9a" }}
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  )
}
