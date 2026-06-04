// Copyright (c) Ultra AutoTrade. All rights reserved.
// frontend/app/(liff)/liff-chat/page.tsx
// LIFF チャット ホーム — /liff-chat
"use client"

import { useState } from "react"
import { Menu, User } from "lucide-react"
import { HamburgerMenu } from "./_components/HamburgerMenu"
import { SlideUpPanel } from "./_components/SlideUpPanel"
import { MyWalletPanel } from "./_components/panels/MyWalletPanel"
import { DepositPanel } from "./_components/panels/DepositPanel"
import { ReferralPanel } from "./_components/panels/ReferralPanel"
import { OpModePanel } from "./_components/panels/OpModePanel"
import { TxHistoryPanel } from "./_components/panels/TxHistoryPanel"
import { TaxPanel } from "./_components/panels/TaxPanel"
import { NotificationPanel } from "./_components/panels/NotificationPanel"
import { AccountPanel } from "./_components/panels/AccountPanel"
import { TermsPanel } from "./_components/panels/TermsPanel"

const PANEL_TITLES: Record<string, string> = {
  myWallet:     "MY WALLET",
  deposit:      "入金/出金",
  referral:     "紹介キャンペーン",
  opMode:       "運用モード切替",
  txHistory:    "取引履歴",
  tax:          "TAX & REPORTS",
  notification: "通知設定",
  account:      "アカウント",
  terms:        "利用規約",
}

export default function LiffChatPage() {
  const [menuOpen, setMenuOpen] = useState(false)
  const [activePanel, setActivePanel] = useState<string | null>(null)

  return (
    <div className="w-[375px] mx-auto h-dvh bg-zinc-950 text-zinc-100 flex flex-col overflow-hidden relative">
      {/* ヘッダー */}
      <header className="h-14 bg-[#1a3d2e] flex items-center justify-between px-4 flex-shrink-0">
        <button
          onClick={() => setMenuOpen(true)}
          className="text-white hover:bg-white/10 rounded-lg p-1 transition-colors"
          aria-label="メニューを開く"
        >
          <Menu className="w-6 h-6" />
        </button>
        <span className="text-[#4ade9a] font-bold text-xl">UAT</span>
        <button
          className="text-white hover:bg-white/10 rounded-lg p-1 transition-colors"
          aria-label="アカウント"
        >
          <User className="w-6 h-6" />
        </button>
      </header>

      {/* メインコンテンツ（暫定） */}
      <main className="flex-1 flex items-center justify-center">
        <p className="text-zinc-600 text-sm">ホーム画面は別タスクで実装</p>
      </main>

      {/* ハンバーガーメニュー */}
      <HamburgerMenu
        open={menuOpen}
        onClose={() => setMenuOpen(false)}
        onPanelOpen={(id) => setActivePanel(id)}
      />

      {/* 各パネル */}
      {Object.keys(PANEL_TITLES).map((id) => (
        <SlideUpPanel
          key={id}
          open={activePanel === id}
          onClose={() => setActivePanel(null)}
          title={PANEL_TITLES[id]}
        >
          {id === "myWallet"     && <MyWalletPanel />}
          {id === "deposit"      && <DepositPanel />}
          {id === "referral"     && <ReferralPanel />}
          {id === "opMode"       && <OpModePanel />}
          {id === "txHistory"    && <TxHistoryPanel />}
          {id === "tax"          && <TaxPanel />}
          {id === "notification" && <NotificationPanel />}
          {id === "account"      && <AccountPanel />}
          {id === "terms"        && <TermsPanel />}
        </SlideUpPanel>
      ))}
    </div>
  )
}
