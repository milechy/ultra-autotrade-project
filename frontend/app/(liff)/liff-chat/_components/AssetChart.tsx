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

    fetch(`${API_BASE}/api/user/asset-history?period=${period}`, {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    })
      .then((r) => (r.ok ? r.json() : null))
      .then((d: { data?: DataPoint[] } | null) => {
        if (d?.data && d.data.length > 0) {
          setData(d.data)
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
