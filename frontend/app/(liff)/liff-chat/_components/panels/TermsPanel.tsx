// Copyright (c) Ultra AutoTrade. All rights reserved.
"use client"

import { ExternalLink, FileText, Shield } from "lucide-react"
import { useTranslations } from "next-intl"
import { useRouter } from "next/navigation"

// 法的文書ページから liff-chat に戻すための return パラメータ。
// 各文書ページの useSmartBack がこれを最優先で読み「戻る」で /liff-chat へ戻す。
const RETURN_TO = "/liff-chat"

// 利用規約/プライバシーポリシーへの遷移。
// - LINE (LIFF webview): 外部ブラウザで開く。LIFF webview 内で SPA を置換すると
//   liff-chat の履歴が汚れ「戻る」で /liff-approve に飛ぶため liff.openWindow({external:true})。
// - PWA / 通常ブラウザ: 同一タブで router.push する。新規タブ (window.open) は
//   認証セッション・履歴を引き継げず「戻る」が fallback `/` → 未認証で /connect に
//   飛ぶ不具合があったため、同一タブ遷移に変更し ?return=/liff-chat で戻り先を明示する。
//
// path は同一オリジン相対 ("/terms" 等) で保持。LINE 経路のみ window.location.origin を
// 前置して絶対 URL 化する (prod ドメインのハードコードは環境跨ぎバグの元なので避ける)。
function openDoc(router: ReturnType<typeof useRouter>, path: string) {
  const href = `${path}?return=${encodeURIComponent(RETURN_TO)}`
  const liff =
    typeof window !== "undefined"
      ? (window as Window & { liff?: { openWindow: (opts: { url: string; external: boolean }) => void } }).liff
      : undefined
  if (liff) {
    liff.openWindow({ url: `${window.location.origin}${href}`, external: true })
  } else {
    router.push(href)
  }
}

export function TermsPanel() {
  const t = useTranslations("Liff.panels.terms")
  const router = useRouter()

  const links = [
    {
      href: "/terms",
      label: t("termsLabel"),
      desc: t("termsDesc"),
      icon: FileText,
    },
    {
      // 実ルートは /privacy-policy (frontend/app/(user)/privacy-policy/page.tsx)。
      // 旧 href ".../privacy" は 404 のため修正。
      href: "/privacy-policy",
      label: t("privacyLabel"),
      desc: t("privacyDesc"),
      icon: Shield,
    },
  ]
  return (
    <div className="space-y-3 py-2">
      {links.map(({ href, label, desc, icon: Icon }) => (
        <button
          key={href}
          type="button"
          onClick={() => openDoc(router, href)}
          className="flex items-center gap-3 w-full ax-card-warm hover:bg-black/5 px-4 py-4 rounded-xl transition-colors text-left"
        >
          <Icon className="w-5 h-5 text-[#1D9E75] flex-shrink-0" />
          <div className="flex-1">
            <div className="text-[#1c1a27] text-sm font-medium">{label}</div>
            <div className="text-[#736f7e] text-xs">{desc}</div>
          </div>
          <ExternalLink className="w-4 h-4 text-[#736f7e] flex-shrink-0" />
        </button>
      ))}
      <p className="text-[#736f7e] text-xs text-center pt-2">
        {t("footer")}
      </p>
    </div>
  )
}
