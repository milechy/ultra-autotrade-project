// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.
// frontend/components/user/BrowserTermsGate.tsx
//
// ブラウザ wallet 経路の利用規約ゲート。
//
// 背景 (Asana 1215645261952731):
//   /user 配下の全ページを通じて、ブラウザ wallet ログインユーザーに対して
//   利用規約同意 (version="2.0") を fail-closed パターンで強制する。
//   (liff)/layout.tsx の useLiffTermsGate 適用と同じ考え方を /user レイアウトに展開する。
//
// 動作:
//   - 除外パス: /user/terms-accept 自身（無限ループ防止）
//   - token 無しの場合はゲート無効（未ログインは UserGuard → /login に委ねる）
//   - 判定中は children を描画せずローディング表示
//   - 未同意 → router.replace('/user/terms-accept')
//   - liff-v3 または 2.0 で同意済み → children をそのまま描画

"use client"

import { useEffect } from "react"
import { usePathname, useRouter } from "next/navigation"
import { useTranslations } from "next-intl"
import { useLiffTermsGate } from "@/hooks/useLiffTermsGate"
import { getAuthToken } from "@/lib/auth/token-key"

/** ゲートを適用しないパス。terms-accept 自身は除外（無限ループ防止）。 */
const GATE_EXEMPT_PATHS = ["/user/terms-accept"]

/** ブラウザ経路で「同意済み」とみなすバージョン一覧。
 *  liff-v4 (月額同意を含む LIFF 最新) も accepted。liff-v3 はブラウザ経路では grandfather。 */
const BROWSER_ACCEPTED_VERSIONS: readonly string[] = ["liff-v3", "liff-v4", "2.0"]

export function BrowserTermsGate({ children }: { children: React.ReactNode }) {
  const t = useTranslations("UserBrowserTermsGate")
  const pathname = usePathname()
  const router = useRouter()

  const isExempt = GATE_EXEMPT_PATHS.includes(pathname ?? "")
  const token = typeof window !== "undefined" ? getAuthToken() : null

  // token 無し（未ログイン）はゲート無効: UserGuard が /login へ誘導するため不要。
  // 除外パス / token 無しの場合は enabled=false で常に "accepted" を返す。
  const gateState = useLiffTermsGate(
    !isExempt && !!token,
    BROWSER_ACCEPTED_VERSIONS
  )

  useEffect(() => {
    if (gateState === "not-accepted") {
      router.replace("/user/terms-accept")
    }
  }, [gateState, router])

  if (gateState === "loading") {
    return (
      <div className="min-h-screen bg-zinc-950 text-zinc-100 flex items-center justify-center">
        <p className="text-zinc-400">{t("loading")}</p>
      </div>
    )
  }

  // "not-accepted" の場合は useEffect でリダイレクト中のため children を描画しない。
  if (gateState === "not-accepted") {
    return null
  }

  return <>{children}</>
}
