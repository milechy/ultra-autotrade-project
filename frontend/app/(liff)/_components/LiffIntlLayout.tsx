// Copyright (c) Ultra AutoTrade. All rights reserved.
// frontend/app/(liff)/_components/LiffIntlLayout.tsx
// 共通 NextIntlClientProvider + LanguageProvider ラッパ。
// liff-confirm / liff-chat-history / liff-approve の各 layout.tsx から参照する。
// liff-chat/layout.tsx はこの共通版を使わず独立（#652 の構造維持）。
"use client"

import { useState, useEffect, type ReactNode } from "react"
import { NextIntlClientProvider } from "next-intl"
import { LanguageProvider, useLanguage } from "@/lib/useLanguage"
import jaMessages from "@/messages/ja.json"
import enMessages from "@/messages/en.json"

// IntlWrapper: LanguageProvider 内側で language を参照し NextIntlClientProvider を設定する
function IntlWrapper({ children }: { children: ReactNode }) {
  const { language } = useLanguage()
  const messages = language === "en" ? enMessages : jaMessages
  return (
    <NextIntlClientProvider locale={language} messages={messages}>
      {children}
    </NextIntlClientProvider>
  )
}

export function LiffIntlLayout({ children }: { children: ReactNode }) {
  // SSR hydration: mounted フラグで hydration mismatch を防ぐ
  const [mounted, setMounted] = useState(false)
  useEffect(() => {
    setMounted(true)
  }, [])

  if (!mounted) {
    // SSR / hydration 前は ja で描画（後から正しい言語に切り替わる）
    return (
      <LanguageProvider>
        <NextIntlClientProvider locale="ja" messages={jaMessages}>
          {children}
        </NextIntlClientProvider>
      </LanguageProvider>
    )
  }

  return (
    <LanguageProvider>
      <IntlWrapper>{children}</IntlWrapper>
    </LanguageProvider>
  )
}
