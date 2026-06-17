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

// IntlWrapper: LanguageProvider 内側で language を参照し NextIntlClientProvider を設定する。
// mounted フラグをここで管理することで LanguageProvider を安定させ、
// 「ボタンは JP（language=en）なのに表示は日本語」という不整合を防ぐ。
function IntlWrapper({ children }: { children: ReactNode }) {
  const { language } = useLanguage()
  const [mounted, setMounted] = useState(false)

  useEffect(() => {
    setMounted(true)
  }, [])

  // mount 前は ja 固定（SSR hydration safe）
  // mount 後は LanguageProvider の実際の言語を使う
  const locale = mounted ? language : "ja"
  const messages = locale === "en" ? enMessages : jaMessages

  return (
    <NextIntlClientProvider locale={locale} messages={messages}>
      {children}
    </NextIntlClientProvider>
  )
}

export default function LiffChatLayout({ children }: { children: ReactNode }) {
  return (
    <LanguageProvider>
      <IntlWrapper>{children}</IntlWrapper>
    </LanguageProvider>
  )
}
