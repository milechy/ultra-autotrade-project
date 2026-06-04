// Copyright (c) Ultra AutoTrade. All rights reserved.
"use client"

import {
  Wallet,
  ArrowDownUp,
  Users,
  Settings2,
  Clock,
  FileText,
  Bell,
  User,
  BookOpen,
  ChevronRight,
} from "lucide-react"

interface HamburgerMenuProps {
  open: boolean
  onClose: () => void
  onPanelOpen: (id: string) => void
}

const MENU_ITEMS = [
  { id: "myWallet",     label: "MY WALLET",      sub: "ウォレットアドレス・QRコード",   icon: Wallet },
  { id: "deposit",      label: "入金/出金",        sub: "USDCの入出金",                 icon: ArrowDownUp },
  { id: "referral",     label: "紹介キャンペーン", sub: "お友達を紹介して報酬を獲得",    icon: Users },
  { id: "opMode",       label: "運用モード切替",   sub: "おまかせ / アクティブ",         icon: Settings2 },
  { id: "txHistory",    label: "取引履歴",         sub: "過去の取引を確認",              icon: Clock },
  { id: "tax",          label: "TAX & REPORTS",   sub: "税務レポート・CSV出力",          icon: FileText },
  { id: "notification", label: "通知設定",         sub: "LINE・プッシュ通知の設定",      icon: Bell },
  { id: "account",      label: "アカウント",       sub: "プロフィール・ログアウト",       icon: User },
  { id: "terms",        label: "利用規約",         sub: "利用規約・プライバシーポリシー", icon: BookOpen },
]

export function HamburgerMenu({ open, onClose, onPanelOpen }: HamburgerMenuProps) {
  return (
    <>
      {/* バックドロップ */}
      {open && (
        <div
          className="fixed inset-0 z-40 bg-black/60"
          onClick={onClose}
        />
      )}

      {/* サイドパネル本体 */}
      <div
        className={`fixed top-0 left-0 h-full z-50 w-72 bg-[#1a3d2e] flex flex-col
                    transform transition-transform duration-300 ease-in-out
                    ${open ? "translate-x-0" : "-translate-x-full"}`}
      >
        {/* ヘッダー */}
        <div className="flex items-center justify-between px-4 py-4 border-b border-white/10">
          <span className="text-[#4ade9a] font-bold text-lg">UAT</span>
          <button
            onClick={onClose}
            className="text-white text-xl leading-none w-8 h-8 flex items-center justify-center hover:bg-white/10 rounded-full transition-colors"
            aria-label="メニューを閉じる"
          >
            ×
          </button>
        </div>

        {/* メニュー項目 */}
        <div className="flex-1 overflow-y-auto">
          {MENU_ITEMS.map((item) => (
            <button
              key={item.id}
              onClick={() => { onPanelOpen(item.id); onClose() }}
              className="flex items-center w-full px-4 py-4 border-b border-white/10 hover:bg-white/5 active:bg-white/10 transition-colors"
            >
              <item.icon className="w-5 h-5 text-[#4ade9a] mr-3 flex-shrink-0" />
              <div className="flex-1 text-left">
                <div className="text-white font-medium text-sm">{item.label}</div>
                <div className="text-zinc-400 text-xs mt-0.5">{item.sub}</div>
              </div>
              <ChevronRight className="w-4 h-4 text-zinc-600 flex-shrink-0" />
            </button>
          ))}
        </div>

        {/* フッター */}
        <div className="mt-auto px-4 py-4">
          <p className="text-zinc-600 text-xs text-center">UAT App v1.0 | © 2026 UAT Co., Ltd.</p>
        </div>
      </div>
    </>
  )
}
