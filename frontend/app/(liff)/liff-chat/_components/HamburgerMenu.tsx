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
import { useTranslations } from "next-intl"
import { isAutoModeEnabled, isReferralEnabled } from "@/lib/flags"

interface HamburgerMenuProps {
  open: boolean
  onClose: () => void
  onPanelOpen: (id: string) => void
}

export function HamburgerMenu({ open, onClose, onPanelOpen }: HamburgerMenuProps) {
  const t = useTranslations("Liff.menu")

  const MENU_ITEMS = [
    { id: "myWallet",     label: t("myWalletLabel"),     sub: t("myWalletSub"),     icon: Wallet },
    { id: "deposit",      label: t("depositLabel"),      sub: t("depositSub"),      icon: ArrowDownUp },
    // 友達紹介（利益連動リワード）は LINE 審査リスクのため審査期間中はフラグで非表示。
    ...(isReferralEnabled()
      ? [{ id: "referral", label: t("referralLabel"), sub: t("referralSub"), icon: Users }]
      : []),
    // 運用モード切替（おまかせ/アクティブ）は、おまかせ非表示時はモードが
    // アクティブのみとなり切替が無意味なため、メニュー項目ごと隠す。
    ...(isAutoModeEnabled()
      ? [{ id: "opMode", label: t("opModeLabel"), sub: t("opModeSub"), icon: Settings2 }]
      : []),
    { id: "txHistory",    label: t("txHistoryLabel"),    sub: t("txHistorySub"),    icon: Clock },
    { id: "tax",          label: t("taxLabel"),          sub: t("taxSub"),          icon: FileText },
    { id: "notification", label: t("notificationLabel"), sub: t("notificationSub"), icon: Bell },
    { id: "account",      label: t("accountLabel"),      sub: t("accountSub"),      icon: User },
    { id: "terms",        label: t("termsLabel"),        sub: t("termsSub"),        icon: BookOpen },
  ]

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
        className={`fixed top-0 left-0 h-full z-50 w-72 bg-[#1b1a23] flex flex-col
                    transform transition-transform duration-300 ease-in-out
                    ${open ? "translate-x-0" : "-translate-x-full"}`}
      >
        {/* ヘッダー */}
        <div className="flex items-center justify-between px-4 py-4 border-b border-white/10">
          <span className="text-[#fbd9a0] font-bold text-lg">{t("title")}</span>
          <button
            onClick={onClose}
            className="text-white text-xl leading-none w-8 h-8 flex items-center justify-center hover:bg-white/10 rounded-full transition-colors"
            aria-label={t("closeAriaLabel")}
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
              <item.icon className="w-5 h-5 text-[#fbd9a0] mr-3 flex-shrink-0" />
              <div className="flex-1 text-left">
                <div className="text-white font-medium text-sm">{item.label}</div>
                <div className="text-white/55 text-xs mt-0.5">{item.sub}</div>
              </div>
              <ChevronRight className="w-4 h-4 text-white/40 flex-shrink-0" />
            </button>
          ))}
        </div>

        {/* フッター */}
        <div className="mt-auto px-4 py-4">
          <p className="text-white/40 text-xs text-center">{t("footer")}</p>
        </div>
      </div>
    </>
  )
}
