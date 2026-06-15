// Copyright (c) Ultra AutoTrade. All rights reserved.
// frontend/app/(liff)/liff-chat/page.tsx
// LIFF チャット ホーム v3 — /liff-chat
"use client"

import { useState, useEffect } from "react"
import dynamic from "next/dynamic"
import { Menu, User, MessageCircle } from "lucide-react"
import { useTranslations } from "next-intl"
import { useLanguage } from "@/lib/useLanguage"
import { track, EV } from "@/lib/posthog"
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
import { ChatPanel } from "./_components/ChatPanel"

// recharts は SSR クラッシュ防止のため dynamic import
const AssetChart = dynamic(() => import("./_components/AssetChart"), {
  ssr: false,
  loading: () => (
    <div className="h-[200px] w-full flex items-center justify-center">
      <span className="text-zinc-600 text-xs" id="chart-loading-placeholder" />
    </div>
  ),
})

// ────────────────────────────────────────────
// 型定義
// ────────────────────────────────────────────

interface AssetData {
  current_usd: number
  initial_usd: number
  pnl_usd: number
  pnl_pct: number
}

interface AiJudgment {
  action: "BUY" | "SELL" | "HOLD"
  confidence: number
  reason?: string
}

interface CoinHolding {
  asset: string
  protocol: string
  amount_usd: number
  apy_pct: number
}

// ────────────────────────────────────────────
// ページ本体
// ────────────────────────────────────────────

export default function LiffChatPage() {
  const t = useTranslations("Liff")
  const { language, setLanguage } = useLanguage()

  // ── 既存 state（ハンバーガー）
  const [menuOpen, setMenuOpen] = useState(false)
  const [activePanel, setActivePanel] = useState<string | null>(null)

  // ── 新規 state（ホームコンテンツ）
  const [assetData, setAssetData] = useState<AssetData | null>(null)
  const [aiJudgment, setAiJudgment] = useState<AiJudgment | null>(null)
  const [coins, setCoins] = useState<CoinHolding[]>([])
  const [graphPeriod, setGraphPeriod] = useState<"1M" | "3M" | "6M" | "1Y">("3M")
  const [graphOpen, setGraphOpen] = useState(false)
  const [chatOpen, setChatOpen] = useState(false)
  const [unreadCount] = useState(0)
  const [reasonOpen, setReasonOpen] = useState(false)

  // ── 緊急停止 state
  const [paused, setPaused] = useState(false)
  const [stopConfirmOpen, setStopConfirmOpen] = useState(false)
  const [stopLoading, setStopLoading] = useState(false)
  const [toast, setToast] = useState<string | null>(null)

  // ── データ取得
  useEffect(() => {
    const token =
      typeof window !== "undefined"
        ? (localStorage.getItem("auth_token") ?? "")
        : ""
    const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? ""
    if (!token) return

    const headers = { Authorization: `Bearer ${token}` }

    // 資産サマリー（/api/user/settings から balance を読む）
    // 併せて is_active=false（運用停止中）を読んで緊急停止バーの初期状態に反映する。
    fetch(`${API_BASE}/api/user/settings`, { headers })
      .then((r) => (r.ok ? r.json() : null))
      .then((d: (Record<string, string> & { is_active?: boolean }) | null) => {
        if (d) {
          const current = parseFloat(d.balance ?? "0")
          const initial = parseFloat(d.initial_balance ?? d.balance ?? "0")
          const pnlUsd = current - initial
          const pnlPct = initial > 0 ? (pnlUsd / initial) * 100 : 0
          setAssetData({ current_usd: current, initial_usd: initial, pnl_usd: pnlUsd, pnl_pct: pnlPct })
          if (d.is_active === false) setPaused(true)
        }
      })
      .catch(() => {})

    // AI 判定（最新 1 件）
    fetch(`${API_BASE}/api/ai/decisions?limit=1`, { headers })
      .then((r) => (r.ok ? r.json() : null))
      .then((d: { items?: AiJudgment[] } | null) => {
        if (d?.items?.[0]) setAiJudgment(d.items[0])
      })
      .catch(() => {})

    // 運用中コイン
    fetch(`${API_BASE}/api/user/holdings`, { headers })
      .then((r) => (r.ok ? r.json() : null))
      .then((d: { items?: CoinHolding[] } | null) => {
        if (Array.isArray(d?.items)) setCoins(d!.items!)
      })
      .catch(() => {})
  }, [])

  // ── 承認・見送りハンドラ（BUY/SELL）
  function handleApprove() {
    // liff-approve に遷移せずパネルで完結させる想定（Phase 5 以降）
    track(EV.JUDGMENT_APPROVE, { action: aiJudgment?.action })
    setAiJudgment(null)
  }
  function handleReject() {
    track(EV.JUDGMENT_REJECT, { action: aiJudgment?.action })
    setAiJudgment(null)
  }

  // ── 緊急停止: POST /api/user/pause（require_active_user / consumer 可）
  // backend の OR ロジック安全装置は変更せず、ユーザーの is_active フラグを落とすだけ。
  async function handleEmergencyStop() {
    const token =
      typeof window !== "undefined"
        ? (localStorage.getItem("auth_token") ?? "")
        : ""
    const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? ""
    if (!token) return
    setStopLoading(true)
    try {
      const res = await fetch(`${API_BASE}/api/user/pause`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
      })
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      setPaused(true)
      setStopConfirmOpen(false)
      track(EV.EMERGENCY_STOP)
      setToast(t("home.stopSuccess"))
    } catch {
      setToast(t("home.stopFailed"))
    } finally {
      setStopLoading(false)
      setTimeout(() => setToast(null), 2800)
    }
  }

  // ── AI カード色設定
  const action = aiJudgment?.action
  const confidence = aiJudgment?.confidence ?? 0
  const isBuy = action === "BUY"
  const isSell = action === "SELL"

  // ── パネルタイトル（i18n 化）
  const PANEL_TITLES: Record<string, string> = {
    myWallet:     t("menu.myWalletLabel"),
    deposit:      t("panels.deposit.title"),
    referral:     t("panels.referral.title"),
    opMode:       t("panels.opMode.title"),
    txHistory:    t("panels.txHistory.title"),
    tax:          t("panels.tax.title"),
    notification: t("panels.notification.title"),
    account:      t("panels.account.title"),
    terms:        t("panels.terms.title"),
  }

  return (
    <div className="w-[375px] mx-auto h-dvh bg-zinc-950 text-zinc-100 flex flex-col overflow-hidden relative">

      {/* ── ヘッダー */}
      <header className="h-14 bg-[#1a3d2e] flex items-center justify-between px-4 flex-shrink-0">
        <button
          onClick={() => { setMenuOpen(true); track(EV.MENU_OPEN) }}
          className="text-white p-1 hover:bg-white/10 rounded-lg transition-colors"
          aria-label={t("header.menuAriaLabel")}
        >
          <Menu className="w-6 h-6" />
        </button>
        <svg
          width="36"
          height="36"
          viewBox="0 0 100 100"
          aria-label={t("header.logoAriaLabel")}
          className="flex-shrink-0"
        >
          {/* ベゼル: フラットグレー */}
          <circle cx="50" cy="50" r="49" fill="#CCCCCC" />
          {/* 内面: 赤 — カラータイマー点滅 */}
          <circle
            cx="50"
            cy="50"
            r="41.5"
            fill="#E8341A"
            className="animate-color-timer motion-reduce:animate-none"
          />
          {/* U リング: 白 */}
          <g transform="translate(1.75,1.75) scale(0.965)">
            <path
              d="M 82.9 22.4 A 43 43 0 1 1 17.1 22.4 L 28.6 32.0 A 28 28 0 1 0 71.4 32.0 Z"
              fill="white"
            />
          </g>
        </svg>
        <div className="flex items-center gap-1">
          {/* JP/EN トグルボタン */}
          <button
            onClick={() => { const next = language === "ja" ? "en" : "ja"; setLanguage(next); track(EV.LANGUAGE_TOGGLE, { language: next }) }}
            aria-label={t("header.langToggleAriaLabel")}
            className="text-zinc-300 text-xs font-semibold px-2 py-1 rounded-md
                       hover:bg-white/10 transition-colors border border-zinc-600"
          >
            {language === "ja" ? "EN" : "JP"}
          </button>
          <button
            onClick={() => { setActivePanel("account"); track(EV.ACCOUNT_OPEN) }}
            className="text-white p-1 hover:bg-white/10 rounded-lg transition-colors"
            aria-label={t("header.accountAriaLabel")}
          >
            <User className="w-6 h-6" />
          </button>
        </div>
      </header>

      {/* ── メインコンテンツ */}
      <main className="flex-1 overflow-y-auto pb-24">

        {/* CURRENT ASSET カード（タップでグラフパネル） */}
        <button
          onClick={() => { setGraphOpen(true); track(EV.ASSET_GRAPH_OPEN) }}
          className="bg-[#1a3d2e] rounded-2xl mx-4 mt-4 p-4 text-left w-[calc(100%-2rem)]
                     active:brightness-90 transition-all"
        >
          <div className="text-zinc-400 text-xs mb-1">{t("home.currentAsset")}</div>
          <div className="text-white text-3xl font-bold">
            ${assetData?.current_usd?.toLocaleString() ?? "—"}
          </div>
          <div
            className={`text-sm mt-1 ${
              (assetData?.pnl_pct ?? 0) >= 0 ? "text-[#4ade9a]" : "text-red-400"
            }`}
          >
            {(assetData?.pnl_pct ?? 0) >= 0 ? "+" : ""}
            {assetData?.pnl_pct?.toFixed(2) ?? "—"}%
            <span className="text-zinc-500 ml-2">{t("home.lastMonthComparison")}</span>
          </div>
        </button>

        {/* AI 判定カード */}
        <div
          className={`rounded-2xl mx-4 mt-4 p-4 transition-all
            ${isBuy
              ? "bg-zinc-900 border-2 border-[#1D9E75] [animation:pulse_0.8s_ease-in-out_2]"
              : isSell
              ? "bg-zinc-900 border-2 border-red-500 [animation:pulse_0.8s_ease-in-out_2]"
              : "bg-zinc-900"
            }`}
        >
          {/* ヘッダー行 */}
          <div className="flex items-center gap-2 mb-2">
            <div
              className={`w-2 h-2 rounded-full ${
                isBuy
                  ? "bg-[#1D9E75] [animation:ping_0.5s_ease-in-out_4]"
                  : isSell
                  ? "bg-red-500"
                  : "bg-zinc-500"
              }`}
            />
            <span
              className={`text-xs font-medium ${
                isBuy ? "text-[#4ade9a]" : isSell ? "text-red-400" : "text-zinc-400"
              }`}
            >
              {t("home.aiJudgment")}
            </span>
            {confidence > 0 && (
              <span className="ml-auto text-zinc-500 text-xs">{confidence}% {t("home.confidenceLabel")}</span>
            )}
          </div>

          {/* アクション表示 */}
          <div
            className={`font-bold text-2xl ${
              isBuy ? "text-[#4ade9a]" : isSell ? "text-red-400" : "text-white"
            }`}
          >
            {aiJudgment ? action : t("home.noSignal")}
          </div>

          {/* BUY / SELL 時: 承認・見送りボタン */}
          {(isBuy || isSell) && (
            <div className="flex gap-3 mt-3">
              <button
                onClick={handleApprove}
                className={`flex-1 py-3 rounded-xl font-semibold text-white ${
                  isBuy ? "bg-[#1D9E75]" : "bg-red-500"
                }`}
              >
                {t("home.approve")}
              </button>
              <button
                onClick={handleReject}
                className="flex-1 py-3 border border-zinc-600 text-zinc-300 rounded-xl font-semibold"
              >
                {t("home.reject")}
              </button>
            </div>
          )}

          {/* なぜ{action}？理由トグル（aiJudgment がある場合のみ表示） */}
          {aiJudgment && (
            <>
              <button
                onClick={() => { const next = !reasonOpen; setReasonOpen(next); track(EV.REASON_TOGGLE, { action, open: next }) }}
                className="mt-2 text-zinc-500 text-xs underline"
                aria-expanded={reasonOpen}
              >
                {t("home.whyAction", { action })}
              </button>
              {reasonOpen && (
                <p className="mt-2 text-zinc-400 text-xs leading-relaxed whitespace-pre-wrap">
                  {aiJudgment.reason ?? t("home.noReason")}
                </p>
              )}
            </>
          )}
        </div>

        {/* 運用中コイン一覧 */}
        <div className="mx-4 mt-4">
          <h3 className="text-zinc-400 text-xs font-semibold mb-3">{t("home.operatingCoins")}</h3>
          <div className="space-y-2">
            {coins.map((coin) => (
              <button
                key={coin.asset}
                className="flex items-center w-full bg-zinc-900 rounded-xl px-4 py-3 active:brightness-75 transition-all"
              >
                {/* コインアバター */}
                <div
                  className="w-8 h-8 rounded-full bg-[#1D9E75]/20 text-[#4ade9a]
                               flex items-center justify-center text-xs font-bold mr-3 flex-shrink-0"
                >
                  {coin.asset.slice(0, 2)}
                </div>
                <div className="flex-1 text-left">
                  <div className="text-white text-sm font-medium">{coin.asset}</div>
                  <div className="text-zinc-500 text-xs">{coin.protocol}</div>
                </div>
                <div className="text-right">
                  <div className="text-white text-sm">${coin.amount_usd.toLocaleString()}</div>
                  <div
                    className={`text-xs ${
                      coin.apy_pct >= 0 ? "text-[#4ade9a]" : "text-red-400"
                    }`}
                  >
                    {coin.apy_pct >= 0 ? "+" : ""}
                    {coin.apy_pct}% APY
                  </div>
                </div>
              </button>
            ))}
            {coins.length === 0 && (
              <div className="text-center py-6 text-zinc-600 text-sm">
                {t("home.noCoins")}
              </div>
            )}
          </div>
        </div>
      </main>

      {/* ── 緊急停止バー（下部固定 / safe-area 対応）
          Arobix warm-light に馴染むよう、黒背景グラデーションは廃し、
          細めの赤アウトライン（薄赤フィル）にして主張を抑える。 */}
      <div className="fixed bottom-0 left-0 right-0 z-30 w-[375px] mx-auto px-4 pt-2 ax-safe-bottom">
        {paused ? (
          <div
            role="status"
            className="w-full py-2 rounded-lg border border-red-400/50 bg-red-500/10
                       text-red-500 text-xs font-medium flex items-center justify-center gap-1.5"
          >
            <span className="w-1.5 h-1.5 rounded-full bg-red-500" />
            {t("home.stoppedStatus")}
          </div>
        ) : (
          <button
            onClick={() => setStopConfirmOpen(true)}
            className="w-full py-2 rounded-lg border border-red-400 bg-red-500/10
                       text-red-600 text-sm font-semibold active:bg-red-500/20 transition-colors"
            aria-label={t("home.emergencyStopAriaLabel")}
          >
            {t("home.emergencyStop")}
          </button>
        )}
      </div>

      {/* 緊急停止 確認ダイアログ */}
      {stopConfirmOpen && (
        <div className="fixed inset-0 z-50 flex items-end justify-center">
          <div
            className="absolute inset-0 bg-black/60"
            onClick={() => !stopLoading && setStopConfirmOpen(false)}
          />
          <div className="relative w-[375px] mx-auto bg-zinc-900 rounded-t-2xl p-5 ax-safe-bottom">
            <h3 className="text-white font-bold text-lg mb-1">{t("home.stopConfirmTitle")}</h3>
            <p className="text-zinc-400 text-sm mb-4 leading-relaxed">
              {t("home.stopConfirmDesc")}
            </p>
            <div className="flex gap-3">
              <button
                onClick={() => setStopConfirmOpen(false)}
                disabled={stopLoading}
                className="flex-1 py-3 rounded-xl border border-zinc-600 text-zinc-300 font-semibold disabled:opacity-40"
              >
                {t("home.stopCancel")}
              </button>
              <button
                onClick={handleEmergencyStop}
                disabled={stopLoading}
                className="flex-1 py-3 rounded-xl bg-red-500 active:bg-red-600 text-white font-bold disabled:opacity-50"
              >
                {stopLoading ? t("home.stopping") : t("home.stopConfirm")}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* トースト */}
      {toast && (
        <div
          role="status"
          className="fixed top-4 left-1/2 -translate-x-1/2 z-[60] px-4 py-2 rounded-xl bg-zinc-800
                     border border-zinc-700 text-white text-sm shadow-lg whitespace-nowrap"
        >
          {toast}
        </div>
      )}

      {/* ── FAB（右下固定） */}
      <button
        onClick={() => { setChatOpen(true); track(EV.CHAT_OPEN) }}
        className="fixed bottom-24 right-6 z-40 w-14 h-14 rounded-full shadow-lg
                   flex items-center justify-center active:scale-95 transition-transform
                   bg-gradient-to-br from-[#b9a4f2] via-[#ecaccd] to-[#fbd9a0]"
        aria-label={t("home.openChatAriaLabel")}
      >
        <MessageCircle className="w-6 h-6 text-[#2a2440]" />
        {unreadCount > 0 && (
          <span
            className="absolute -top-1 -right-1 w-5 h-5 rounded-full bg-red-500 text-white text-xs
                       flex items-center justify-center font-bold"
          >
            {unreadCount}
          </span>
        )}
      </button>

      {/* ── チャットパネル */}
      {chatOpen && <ChatPanel onClose={() => setChatOpen(false)} />}

      {/* ── グラフパネル（資産推移） */}
      <SlideUpPanel
        open={graphOpen}
        onClose={() => setGraphOpen(false)}
        title={t("panels.assetHistory")}
      >
        {/* 期間切替タブ */}
        <div className="flex gap-2 mb-4">
          {(["1M", "3M", "6M", "1Y"] as const).map((p) => (
            <button
              key={p}
              onClick={() => { setGraphPeriod(p); track(EV.GRAPH_PERIOD_CHANGE, { period: p }) }}
              className={`px-3 py-1.5 rounded-full text-xs font-medium transition-colors ${
                graphPeriod === p
                  ? "bg-[#1D9E75] text-white"
                  : "bg-zinc-800 text-zinc-400"
              }`}
            >
              {p}
            </button>
          ))}
        </div>

        {/* AreaChart (recharts / dynamic import) */}
        <AssetChart period={graphPeriod} />

        {/* 統計グリッド */}
        <div className="grid grid-cols-2 gap-3 mt-4">
          {[
            {
              label: t("panels.statsStart"),
              value: `$${assetData?.initial_usd?.toLocaleString() ?? "—"}`,
            },
            {
              label: t("panels.statsCurrent"),
              value: `$${assetData?.current_usd?.toLocaleString() ?? "—"}`,
            },
            {
              label: t("panels.statsProfit"),
              value: `$${assetData?.pnl_usd?.toLocaleString() ?? "—"}`,
            },
            {
              label: t("panels.statsYield"),
              value: `${assetData?.pnl_pct?.toFixed(2) ?? "—"}%`,
            },
          ].map((s) => (
            <div key={s.label} className="bg-zinc-800 rounded-xl p-3">
              <div className="text-zinc-500 text-xs">{s.label}</div>
              <div className="text-white font-semibold mt-0.5">{s.value}</div>
            </div>
          ))}
        </div>
      </SlideUpPanel>

      {/* ── ハンバーガーメニュー（既存維持） */}
      <HamburgerMenu
        open={menuOpen}
        onClose={() => setMenuOpen(false)}
        onPanelOpen={(id) => { setActivePanel(id); track(EV.PANEL_OPEN, { panel: id }) }}
      />

      {/* ── 各パネル（既存維持） */}
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
