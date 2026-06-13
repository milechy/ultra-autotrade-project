// Copyright (c) Ultra AutoTrade. All rights reserved.
// frontend/app/(liff)/liff-sign-poc/layout.tsx
// liff-sign-poc 専用 NextIntlClientProvider + LanguageProvider。
// 共通 LiffIntlLayout を薄いラッパとして参照する。
"use client"

import type { ReactNode } from "react"
import { LiffIntlLayout } from "../_components/LiffIntlLayout"

export default function LiffSignPocLayout({ children }: { children: ReactNode }) {
  return <LiffIntlLayout>{children}</LiffIntlLayout>
}
