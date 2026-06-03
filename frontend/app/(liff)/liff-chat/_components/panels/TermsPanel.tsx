// Copyright (c) Ultra AutoTrade. All rights reserved.
"use client"

import { ExternalLink } from "lucide-react"

export function TermsPanel() {
  return (
    <div className="space-y-3 py-4">
      <a
        href="https://ultra-auto-trade.com/terms"
        target="_blank"
        rel="noopener noreferrer"
        className="flex items-center justify-between w-full px-4 py-4 bg-zinc-800 rounded-xl hover:bg-zinc-700 transition-colors"
      >
        <span className="text-white text-sm font-medium">利用規約</span>
        <ExternalLink className="w-4 h-4 text-zinc-400" />
      </a>
      <a
        href="https://ultra-auto-trade.com/privacy"
        target="_blank"
        rel="noopener noreferrer"
        className="flex items-center justify-between w-full px-4 py-4 bg-zinc-800 rounded-xl hover:bg-zinc-700 transition-colors"
      >
        <span className="text-white text-sm font-medium">プライバシーポリシー</span>
        <ExternalLink className="w-4 h-4 text-zinc-400" />
      </a>
    </div>
  )
}
