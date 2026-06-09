// Copyright (c) Ultra AutoTrade. All rights reserved.
"use client"

import { ExternalLink, FileText, Shield } from "lucide-react"

// 利用規約/プライバシーポリシーは外部ブラウザ (新コンテキスト) で開く。
// LIFF webview 内で SPA を置換すると liff-chat の履歴が汚れ「戻る」で
// /liff-approve (パートナートップ) に戻ってしまうため、target=_blank の
// 素の <a> ではなく liff.openWindow({external:true}) を優先して使用する。
// liff が無い (通常ブラウザ等) 場合は window.open へフォールバック。
//
// path は同一オリジン相対 ("/terms" 等) で保持し、openExternal で
// window.location.origin を前置して絶対 URL 化する。prod ドメインを
// ハードコードすると staging で開いても本番 (app.ultra-auto-trade.com) に
// 飛んでしまうため (環境跨ぎバグ)、必ず現在のオリジン基準で解決する。
function openExternal(path: string) {
  const url = typeof window !== "undefined" ? `${window.location.origin}${path}` : path
  if (
    typeof window !== "undefined" &&
    (window as Window & { liff?: { openWindow: (opts: { url: string; external: boolean }) => void } }).liff
  ) {
    (window as Window & { liff?: { openWindow: (opts: { url: string; external: boolean }) => void } }).liff?.openWindow({ url, external: true })
  } else {
    window.open(url, "_blank", "noopener,noreferrer")
  }
}

export function TermsPanel() {
  const links = [
    {
      href: "/terms",
      label: "利用規約",
      desc: "サービス利用条件・免責事項",
      icon: FileText,
    },
    {
      // 実ルートは /privacy-policy (frontend/app/(user)/privacy-policy/page.tsx)。
      // 旧 href ".../privacy" は 404 のため修正。
      href: "/privacy-policy",
      label: "プライバシーポリシー",
      desc: "個人情報の取り扱い",
      icon: Shield,
    },
  ]
  return (
    <div className="space-y-3 py-2">
      {links.map(({ href, label, desc, icon: Icon }) => (
        <button
          key={href}
          type="button"
          onClick={() => openExternal(href)}
          className="flex items-center gap-3 w-full bg-zinc-800 hover:bg-zinc-700 px-4 py-4 rounded-xl transition-colors text-left"
        >
          <Icon className="w-5 h-5 text-[#4ade9a] flex-shrink-0" />
          <div className="flex-1">
            <div className="text-white text-sm font-medium">{label}</div>
            <div className="text-zinc-500 text-xs">{desc}</div>
          </div>
          <ExternalLink className="w-4 h-4 text-zinc-500 flex-shrink-0" />
        </button>
      ))}
      <p className="text-zinc-600 text-xs text-center pt-2">
        UAT App v1.0 | © 2026 UAT Co., Ltd.
      </p>
    </div>
  )
}
