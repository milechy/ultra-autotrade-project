// Copyright (c) Ultra AutoTrade. All rights reserved.
// frontend/app/(liff)/liff-chat/page.tsx
// LIFF チャット ホーム v3 — /liff-chat
"use client"

import { useState, useEffect } from "react"
import dynamic from "next/dynamic"
import { Menu, User, MessageCircle } from "lucide-react"
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
      <span className="text-zinc-600 text-xs">グラフを読み込み中...</span>
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
// ハンバーガーパネル定義（既存維持）
// ────────────────────────────────────────────

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

// ────────────────────────────────────────────
// ページ本体
// ────────────────────────────────────────────

export default function LiffChatPage() {
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
    fetch(`${API_BASE}/api/user/settings`, { headers })
      .then((r) => (r.ok ? r.json() : null))
      .then((d: Record<string, string> | null) => {
        if (d) {
          const current = parseFloat(d.balance ?? "0")
          const initial = parseFloat(d.initial_balance ?? d.balance ?? "0")
          const pnlUsd = current - initial
          const pnlPct = initial > 0 ? (pnlUsd / initial) * 100 : 0
          setAssetData({ current_usd: current, initial_usd: initial, pnl_usd: pnlUsd, pnl_pct: pnlPct })
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
    setAiJudgment(null)
  }
  function handleReject() {
    setAiJudgment(null)
  }

  // ── AI カード色設定
  const action = aiJudgment?.action ?? "HOLD"
  const confidence = aiJudgment?.confidence ?? 0
  const isBuy = action === "BUY"
  const isSell = action === "SELL"

  return (
    <div className="w-[375px] mx-auto h-dvh bg-zinc-950 text-zinc-100 flex flex-col overflow-hidden relative">

      {/* ── ヘッダー */}
      <header className="h-14 bg-[#1a3d2e] flex items-center justify-between px-4 flex-shrink-0">
        <button
          onClick={() => setMenuOpen(true)}
          className="text-white p-1 hover:bg-white/10 rounded-lg transition-colors"
          aria-label="メニューを開く"
        >
          <Menu className="w-6 h-6" />
        </button>
        <span
          className="font-bold text-xl tracking-wider bg-clip-text text-transparent
                     bg-[length:300%_100%] animate-logo-shine motion-reduce:animate-none
                     bg-[linear-gradient(100deg,#4ade9a_0%,#4ade9a_45%,#ffffff_50%,#4ade9a_55%,#4ade9a_100%)]"
        >
          UAT
        </span>
        <button
          onClick={() => setActivePanel("account")}
          className="text-white p-1 hover:bg-white/10 rounded-lg transition-colors"
          aria-label="アカウント"
        >
          <User className="w-6 h-6" />
        </button>
      </header>

      {/* ── メインコンテンツ */}
      <main className="flex-1 overflow-y-auto pb-24">

        {/* CURRENT ASSET カード（タップでグラフパネル） */}
        <button
          onClick={() => setGraphOpen(true)}
          className="bg-[#1a3d2e] rounded-2xl mx-4 mt-4 p-4 text-left w-[calc(100%-2rem)]
                     active:brightness-90 transition-all"
        >
          <div className="text-zinc-400 text-xs mb-1">CURRENT ASSET</div>
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
            <span className="text-zinc-500 ml-2">先月比</span>
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
              AI JUDGMENT
            </span>
            {confidence > 0 && (
              <span className="ml-auto text-zinc-500 text-xs">{confidence}% 信頼度</span>
            )}
          </div>

          {/* アクション表示 */}
          <div
            className={`font-bold text-2xl ${
              isBuy ? "text-[#4ade9a]" : isSell ? "text-red-400" : "text-white"
            }`}
          >
            {action}
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
                承認する
              </button>
              <button
                onClick={handleReject}
                className="flex-1 py-3 border border-zinc-600 text-zinc-300 rounded-xl font-semibold"
              >
                見送る
              </button>
            </div>
          )}

          {/* なぜ{action}？理由トグル（BUY/SELL/HOLD 共通） */}
          <button
            onClick={() => setReasonOpen((v) => !v)}
            className="mt-2 text-zinc-500 text-xs underline"
            aria-expanded={reasonOpen}
          >
            なぜ{action}？
          </button>
          {reasonOpen && (
            <p className="mt-2 text-zinc-400 text-xs leading-relaxed whitespace-pre-wrap">
              {aiJudgment?.reason ?? "理由データがありません"}
            </p>
          )}
        </div>

        {/* 運用中コイン一覧 */}
        <div className="mx-4 mt-4">
          <h3 className="text-zinc-400 text-xs font-semibold mb-3">運用中コイン</h3>
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
                運用中のコインがありません
              </div>
            )}
          </div>
        </div>
      </main>

      {/* ── FAB（右下固定） */}
      <button
        onClick={() => setChatOpen(true)}
        className="fixed bottom-6 right-6 z-30 w-14 h-14 rounded-full shadow-lg
                   flex items-center justify-center active:scale-95 transition-transform
                   bg-gradient-to-br from-[#b9a4f2] via-[#ecaccd] to-[#fbd9a0]"
        aria-label="チャットを開く"
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
        title="資産推移"
      >
        {/* 期間切替タブ */}
        <div className="flex gap-2 mb-4">
          {(["1M", "3M", "6M", "1Y"] as const).map((p) => (
            <button
              key={p}
              onClick={() => setGraphPeriod(p)}
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
              label: "開始額",
              value: `$${assetData?.initial_usd?.toLocaleString() ?? "—"}`,
            },
            {
              label: "現在",
              value: `$${assetData?.current_usd?.toLocaleString() ?? "—"}`,
            },
            {
              label: "利益",
              value: `$${assetData?.pnl_usd?.toLocaleString() ?? "—"}`,
            },
            {
              label: "利回り",
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
        onPanelOpen={(id) => setActivePanel(id)}
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
