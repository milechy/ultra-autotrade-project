// Copyright (c) Ultra AutoTrade. All rights reserved.
// frontend/app/(liff)/liff-chat/_components/DividendChart.tsx
// 月次手取り（配当）の推移を描く LineChart（recharts を直接 import）。
// SSR クラッシュ防止のため DividendChartWrapper の dynamic(ssr:false) 経由で読み込むこと。
"use client"

import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer } from "recharts"
import { useTranslations } from "next-intl"

interface DividendPoint {
  month: string
  value_jpy: number
}

export function DividendChart({ data }: { data: DividendPoint[] }) {
  const t = useTranslations("Liff")

  if (data.length === 0) {
    return (
      <div className="flex items-center justify-center h-32 text-[#736f7e] text-sm">
        {t("kpi.noDataYet")}
      </div>
    )
  }

  return (
    <ResponsiveContainer width="100%" height={120}>
      <LineChart data={data}>
        <XAxis dataKey="month" tick={{ fontSize: 10 }} />
        <YAxis tick={{ fontSize: 10 }} unit="円" />
        <Tooltip formatter={(value) => [`¥${Number(value).toLocaleString()}`, ""]} />
        <Line
          type="monotone"
          dataKey="value_jpy"
          stroke="#1D9E75"
          strokeWidth={2}
          dot={false}
        />
      </LineChart>
    </ResponsiveContainer>
  )
}
