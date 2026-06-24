// Copyright (c) Ultra AutoTrade. All rights reserved.
// frontend/app/(liff)/liff-chat/_components/DividendChartWrapper.tsx
// DividendChart を dynamic(ssr:false) で読み込む薄いラッパー。
// CLAUDE.md 必須ルール: recharts は別ファイル分離 + dynamic(ssr:false) で SSR クラッシュを防ぐ。
"use client"

import dynamic from "next/dynamic"

const DividendChart = dynamic(
  () => import("./DividendChart").then((m) => ({ default: m.DividendChart })),
  { ssr: false },
)

export function DividendChartWrapper({
  data,
}: {
  data: { month: string; value_jpy: number }[]
}) {
  return <DividendChart data={data} />
}
