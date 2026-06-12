// Copyright (c) Ultra AutoTrade. All rights reserved.
// frontend/app/(liff)/liff-chat/layout.tsx
// liff-chat 専用 NextIntlClientProvider + LanguageProvider。
// 既存の (liff)/layout.tsx は SSR/auth guard 担当のため変更しない。
// この layout はその配下に挿入され、liff-chat 以下のみを対象とする。
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

export default function LiffChatLayout({ children }: { children: ReactNode }) {
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
