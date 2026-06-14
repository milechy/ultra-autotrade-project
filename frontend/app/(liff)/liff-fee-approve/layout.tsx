// Copyright (c) Ultra AutoTrade. All rights reserved.
// frontend/app/(liff)/liff-fee-approve/layout.tsx
// liff-fee-approve 専用 NextIntlClientProvider + LanguageProvider。
// 共通 LiffIntlLayout を薄いラッパとして参照する。
"use client"

import type { ReactNode } from "react"
import { LiffIntlLayout } from "../_components/LiffIntlLayout"

export default function LiffFeeApproveLayout({ children }: { children: ReactNode }) {
  return <LiffIntlLayout>{children}</LiffIntlLayout>
}
