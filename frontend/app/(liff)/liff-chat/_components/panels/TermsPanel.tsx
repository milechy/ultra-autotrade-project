// Copyright (c) Ultra AutoTrade. All rights reserved.
"use client"

import { ExternalLink, FileText, Shield } from "lucide-react"

export function TermsPanel() {
  const links = [
    {
      href: "https://ultra-auto-trade.com/terms",
      label: "利用規約",
      desc: "サービス利用条件・免責事項",
      icon: FileText,
    },
    {
      href: "https://ultra-auto-trade.com/privacy",
      label: "プライバシーポリシー",
      desc: "個人情報の取り扱い",
      icon: Shield,
    },
  ]
  return (
    <div className="space-y-3 py-2">
      {links.map(({ href, label, desc, icon: Icon }) => (
        <a
          key={href}
          href={href}
          target="_blank"
          rel="noopener noreferrer"
          className="flex items-center gap-3 w-full bg-zinc-800 hover:bg-zinc-700 px-4 py-4 rounded-xl transition-colors"
        >
          <Icon className="w-5 h-5 text-[#4ade9a] flex-shrink-0" />
          <div className="flex-1">
            <div className="text-white text-sm font-medium">{label}</div>
            <div className="text-zinc-500 text-xs">{desc}</div>
          </div>
          <ExternalLink className="w-4 h-4 text-zinc-500 flex-shrink-0" />
        </a>
      ))}
      <p className="text-zinc-600 text-xs text-center pt-2">
        UAT App v1.0 | © 2026 UAT Co., Ltd.
      </p>
    </div>
  )
}
