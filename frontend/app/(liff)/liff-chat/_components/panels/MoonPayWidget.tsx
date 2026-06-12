// Copyright (c) Ultra AutoTrade. All rights reserved.
// frontend/app/(liff)/liff-chat/_components/panels/MoonPayWidget.tsx
// MoonPay 入金ウィジェット（EN モード時のみ表示）。
// @moonpay/moonpay-react 等の npm 依存を追加せず iframe/プレースホルダ実装。
// MoonPay 有効化は Privy ダッシュボード操作で行うため、ここは UI のみ。
"use client"

import { ExternalLink } from "lucide-react"
import { useTranslations } from "next-intl"

// MoonPay の公式購入 URL。実際の API キー統合は別途 Privy ダッシュボードで行う。
const MOONPAY_URL = "https://buy.moonpay.com"

export function MoonPayWidget() {
  const t = useTranslations("Liff.panels.deposit")

  const handleOpen = () => {
    if (typeof window !== "undefined") {
      window.open(MOONPAY_URL, "_blank", "noopener,noreferrer")
    }
  }

  return (
    <div className="bg-zinc-800 border border-zinc-700 rounded-xl px-4 py-4 space-y-3">
      {/* ヘッダー */}
      <div className="flex items-center gap-2">
        {/* MoonPay カラーアクセント */}
        <div className="w-6 h-6 rounded-full bg-gradient-to-br from-purple-500 to-blue-500 flex-shrink-0" />
        <p className="text-sm font-semibold text-white">{t("moonpayTitle")}</p>
      </div>

      <p className="text-xs text-zinc-400 leading-relaxed">
        {t("moonpayDesc")}
      </p>

      <button
        onClick={handleOpen}
        className="w-full flex items-center justify-center gap-2
                   bg-gradient-to-r from-purple-600 to-blue-600
                   hover:from-purple-500 hover:to-blue-500
                   text-white font-semibold py-3 rounded-xl
                   transition-all active:scale-[0.98]"
      >
        <span>{t("moonpayTitle")}</span>
        <ExternalLink className="w-4 h-4" />
      </button>
    </div>
  )
}
