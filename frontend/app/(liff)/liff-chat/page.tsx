// Copyright (c) Ultra AutoTrade. All rights reserved.
// frontend/app/(liff)/liff-chat/page.tsx
// LIFF チャット ホーム v3 — /liff-chat
"use client"

import { useState, useEffect } from "react"
import dynamic from "next/dynamic"
import { Menu, User } from "lucide-react"
import { useTranslations } from "next-intl"
import { useLanguage } from "@/lib/useLanguage"
import { useUsdcBalance } from "@/hooks/useUsdcBalance"
import { useEffectiveWalletAddress } from "@/hooks/useEffectiveWalletAddress"
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
import { ProposalActionCard } from "./_components/ProposalActionCard"
import { AwaitingFundsCard } from "./_components/AwaitingFundsCard"
import { ProposalSignSheet, type ChatProposal } from "./_components/ProposalSignSheet"
import { awaitFundsProposal } from "@/lib/api/admin-proposals"
import { DividendChartWrapper } from "./_components/DividendChartWrapper"

// recharts は SSR クラッシュ防止のため dynamic import
const AssetChart = dynamic(() => import("./_components/AssetChart"), {
  ssr: false,
  loading: () => (
    <div className="h-[200px] w-full flex items-center justify-center">
      <span className="text-[#736f7e] text-xs" id="chart-loading-placeholder" />
    </div>
  ),
})

// ────────────────────────────────────────────
// 型定義
// ────────────────────────────────────────────

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

// GET /api/portfolio/current の positions_json 要素 (バックエンドは List[Any] = 非構造)。
// v4 で実投資 (Aave リバランス) が動いた際に snapshot へ書かれる想定。
// producer が確定するまでフィールド名揺れを許容して defensive にマッピングする。
interface PortfolioPositionRaw {
  asset?: string
  symbol?: string
  protocol?: string
  amount_usd?: number | string
  value_usd?: number | string
  supply_usd?: number | string
  apy_pct?: number | string
  apy?: number | string
}

interface PortfolioCurrentResponse {
  positions_json?: PortfolioPositionRaw[] | null
  has_data?: boolean
  total_value_usd?: string
  weighted_avg_apy?: string
}

// positions_json (非構造) を CoinHolding[] に正規化する。
// asset を欠く要素は捨てる。金額/APY は Decimal 文字列で来ても Number() で数値化する。
function mapPositionsToHoldings(
  positions: PortfolioPositionRaw[] | null | undefined,
): CoinHolding[] {
  if (!Array.isArray(positions)) return []
  return positions
    .map((p) => {
      const asset = p.asset ?? p.symbol ?? ""
      const amount = p.amount_usd ?? p.value_usd ?? p.supply_usd ?? 0
      const apy = p.apy_pct ?? p.apy ?? 0
      return {
        asset,
        protocol: p.protocol ?? "Aave V3",
        amount_usd: Number(amount),
        apy_pct: Number(apy),
      }
    })
    .filter((c) => c.asset !== "" && Number.isFinite(c.amount_usd))
}

// fetch 失敗 (非2xx レスポンス / 例外) を観測可能化する。
// 従来は `.catch(() => {})` と `r.ok ? json : null` で 500 等が無言で握りつぶされ、
// 提案カードや AI 判定が「出ない」障害が長期間表面化しなかった
// (例: /api/proposals/pending の 500 = protocol カラム欠落)。
// 消費者 UX は変えず (データ無し表示は従来通り)、console.warn + PostHog で早期検知する。
function reportFetchError(endpoint: string, detail: unknown): null {
  console.warn(`[liff-chat] ${endpoint} の取得に失敗`, detail)
  try {
    track(EV.DATA_FETCH_ERROR, {
      endpoint,
      detail: detail instanceof Error ? detail.message : String(detail),
    })
  } catch {
    // posthog 未初期化でも握りつぶさない (console.warn は出ている)
  }
  return null
}

// レスポンスを JSON 化する。非2xx は reportFetchError で記録して null を返す。
async function jsonOrReport(endpoint: string, r: Response): Promise<unknown> {
  if (!r.ok) return reportFetchError(endpoint, `HTTP ${r.status}`)
  return r.json()
}

// ────────────────────────────────────────────
// ページ本体
// ────────────────────────────────────────────

export default function LiffChatPage() {
  const t = useTranslations("Liff")
  const { language, setLanguage } = useLanguage()

  // 現在資産 = 実効アドレス（smart_wallet_address 優先、無ければ EOA）の USDC
  // オンチェーン残高（非カストディアル）。backend B1 の build-tx 残高ガード
  // （smart_wallet_address 優先）とフロント表示を一致させる
  // （2026-07-04 資金迷子バグ修正）。refetch は S2 の着金検知ポーリングで使う。
  const { address: effectiveWalletAddress } = useEffectiveWalletAddress()
  const { balanceUsd, refetch: refetchBalance } = useUsdcBalance(effectiveWalletAddress)

  // ── 既存 state（ハンバーガー）
  const [menuOpen, setMenuOpen] = useState(false)
  const [activePanel, setActivePanel] = useState<string | null>(null)
  // パネルがハンバーガーメニュー由来で開かれたか（戻るでメニューに復帰するため）
  const [panelFromMenu, setPanelFromMenu] = useState(false)

  // ── 新規 state（ホームコンテンツ）
  const [aiJudgment, setAiJudgment] = useState<AiJudgment | null>(null)
  const [coins, setCoins] = useState<CoinHolding[]>([])

  // ── 半自動実行 state（保留中提案の承認→自己署名→submit-tx / Asana 1215743441691795）
  const [pendingProposal, setPendingProposal] = useState<ChatProposal | null>(null)
  const [signSheetOpen, setSignSheetOpen] = useState(false)
  const [rejecting, setRejecting] = useState(false)
  const authToken =
    typeof window !== "undefined" ? (localStorage.getItem("auth_token") ?? "") : ""
  const [graphPeriod, setGraphPeriod] = useState<"1M" | "3M" | "6M" | "1Y">("3M")
  const [graphOpen, setGraphOpen] = useState(false)
  const [chatOpen, setChatOpen] = useState(false)
  const [unreadCount] = useState(0)
  const [reasonOpen, setReasonOpen] = useState(false)

  // ── KPI 表示 state（KPI-C: 運用残高 + 加重平均APY / KPI-D: 月次手取りグラフ）
  const [portfolio, setPortfolio] = useState<PortfolioCurrentResponse | null>(null)
  const [dividends, setDividends] = useState<{ month: string; value_jpy: number }[]>([])

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

    // 運用停止状態（is_active=false）を読んで緊急停止バーの初期状態に反映する。
    // 現在資産はオンチェーン残高（useUsdcBalance）で取得するため、ここでは balance を読まない。
    fetch(`${API_BASE}/api/user/settings`, { headers })
      .then((r) => jsonOrReport("user/settings", r))
      .then((d) => {
        const s = d as { is_active?: boolean } | null
        if (s?.is_active === false) setPaused(true)
      })
      .catch((e) => reportFetchError("user/settings", e))

    // AI 判定（最新 1 件）
    fetch(`${API_BASE}/api/ai/decisions?limit=1`, { headers })
      .then((r) => jsonOrReport("ai/decisions", r))
      .then((d) => {
        const j = d as { items?: AiJudgment[] } | null
        if (j?.items?.[0]) setAiJudgment(j.items[0])
      })
      .catch((e) => reportFetchError("ai/decisions", e))

    // 運用中コイン: 最新ポートフォリオ snapshot の positions_json を表示する。
    // /api/user/holdings は不在のため /api/portfolio/current を使う (Asana 1215723024139228)。
    // v3 (shadow mode) は positions_json が空 → 「運用中のコインがありません」が正。
    fetch(`${API_BASE}/api/portfolio/current`, { headers })
      .then((r) => jsonOrReport("portfolio/current", r))
      .then((d) => {
        setCoins(mapPositionsToHoldings((d as PortfolioCurrentResponse | null)?.positions_json))
      })
      .catch((e) => reportFetchError("portfolio/current", e))

  }, [])

  // ── KPI-C: 運用残高 + 加重平均APY を 30秒ポーリングで取得
  useEffect(() => {
    const token =
      typeof window !== "undefined" ? (localStorage.getItem("auth_token") ?? "") : ""
    const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? ""
    if (!token) return
    const headers = { Authorization: `Bearer ${token}` }
    const fetchPortfolio = () => {
      fetch(`${API_BASE}/api/portfolio/current`, { headers })
        .then((r) => jsonOrReport("portfolio/current", r))
        .then((d) => {
          if (d) setPortfolio(d as PortfolioCurrentResponse)
        })
        .catch((e) => reportFetchError("portfolio/current", e))
    }
    fetchPortfolio()
    const id = setInterval(fetchPortfolio, 30_000)
    return () => clearInterval(id)
  }, [])

  // ── 保留中の提案を30秒ごとに再取得する。期限切れ・承認/見送り後の消化・
  // 入金待ち(awaiting_funds)→承認済みへの遷移など、バックエンド側の状態変化を
  // ポーリングで検知して画面に反映する(以前は初回1回のみの取得だったため、
  // 期限切れ後もBOXがリロードまで残り続ける不具合があった)。
  // awaiting_funds 中は着金検知のため残高も合わせて再取得する。
  useEffect(() => {
    const token =
      typeof window !== "undefined" ? (localStorage.getItem("auth_token") ?? "") : ""
    const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? ""
    if (!token) return
    const headers = { Authorization: `Bearer ${token}` }
    const poll = () => {
      if (pendingProposal?.status === "awaiting_funds") refetchBalance()
      fetch(`${API_BASE}/api/proposals/pending`, { headers })
        .then((r) => jsonOrReport("proposals/pending", r))
        .then((d) => {
          const items = (d as { items?: ChatProposal[] } | null)?.items
          setPendingProposal(items?.[0] ?? null)
        })
        .catch((e) => reportFetchError("proposals/pending", e))
    }
    poll()
    const id = setInterval(poll, 30_000)
    return () => clearInterval(id)
  }, [pendingProposal?.status, refetchBalance])

  // ── KPI-D: 月次手取り（配当）を取得（月次データのため初回のみ）
  useEffect(() => {
    const token =
      typeof window !== "undefined" ? (localStorage.getItem("auth_token") ?? "") : ""
    const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? ""
    if (!token) return
    const headers = { Authorization: `Bearer ${token}` }
    fetch(`${API_BASE}/api/user/dividends`, { headers })
      .then((r) => jsonOrReport("user/dividends", r))
      .then((raw) => {
        const d = raw as { dividends?: { month: string; user_takehome_jpy: string }[] } | null
        if (!d?.dividends) return
        setDividends(
          d.dividends
            .map((item) => ({
              month: item.month.slice(0, 7),
              value_jpy: Number(item.user_takehome_jpy),
            }))
            .reverse(),
        )
      })
      .catch((e) => reportFetchError("user/dividends", e))
  }, [])

  // ── WebSocket: AI 判定リアルタイム受信
  useEffect(() => {
    const token =
      typeof window !== "undefined"
        ? (localStorage.getItem("auth_token") ?? "")
        : ""
    if (!token) return

    const WS_BASE = (process.env.NEXT_PUBLIC_API_URL ?? "").replace(
      /^https?/,
      (m) => (m === "https" ? "wss" : "ws"),
    )
    const ws = new WebSocket(`${WS_BASE}/api/ai/ws/decisions?token=${token}`)
    ws.onmessage = (ev) => {
      try {
        const data = JSON.parse(ev.data) as AiJudgment
        setAiJudgment(data)
      } catch {
        // parse 失敗は無視
      }
    }
    ws.onerror = (ev) => {
      reportFetchError("ai/ws/decisions", ev)
      ws.close()
    }
    return () => ws.close()
  }, [])

  // ── アプリアイコンバッジ（Badging API）: 保留中の提案がある間、ホーム画面に
  // 追加済みPWAのアイコンにネイティブアプリ同様の丸バッジを表示する。
  // ブラウザタブ表示時や未対応環境（iOS 16.3以下等）では navigator.setAppBadge
  // 自体が存在しないため何もしない（フォアグラウンドで開いている間のみ更新される。
  // バックグラウンドでの自動更新には Web Push 連携が別途必要）。
  useEffect(() => {
    const nav = navigator as Navigator & {
      setAppBadge?: (contents?: number) => Promise<void>
      clearAppBadge?: () => Promise<void>
    }
    if (!nav.setAppBadge || !nav.clearAppBadge) return
    if (pendingProposal) {
      nav.setAppBadge(1).catch(() => {})
    } else {
      nav.clearAppBadge().catch(() => {})
    }
  }, [pendingProposal])


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

  // ── 提案 見送り: POST /api/proposals/{id}/reject（VIEWER は自分の提案のみ可）
  async function handleRejectProposal() {
    if (!pendingProposal || !authToken) return
    const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? ""
    setRejecting(true)
    try {
      const res = await fetch(
        `${API_BASE}/api/proposals/${pendingProposal.id}/reject`,
        { method: "POST", headers: { Authorization: `Bearer ${authToken}` } },
      )
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      setPendingProposal(null)
      setToast(t("exec.rejected"))
    } catch {
      setToast(t("exec.rejectFailed"))
    } finally {
      setRejecting(false)
      setTimeout(() => setToast(null), 2800)
    }
  }

  // ── 提案 承認: 残高十分なら署名シート、残高不足なら入金待ち(awaiting_funds)化(S2)。
  // 「承認＝投資意図のキャプチャ」。await-funds で保持し、着金検知で署名可能になる。
  async function handleApproveProposal() {
    if (!pendingProposal || !authToken) return
    if (insufficientBalance) {
      try {
        await awaitFundsProposal(pendingProposal.id, authToken)
        setPendingProposal({ ...pendingProposal, status: "awaiting_funds" })
      } catch {
        setToast(t("exec.signFailed"))
        setTimeout(() => setToast(null), 2800)
      }
      return
    }
    setSignSheetOpen(true)
  }

  // ── 提案 実行完了（署名シートからの成功コールバック）
  function handleProposalExecuted() {
    setSignSheetOpen(false)
    setPendingProposal(null)
    setToast(t("exec.executeSuccess"))
    setTimeout(() => setToast(null), 2800)
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

  // F4: SUPPLY (USDC 入金) で wallet 残高 < 提案額なら署名前にブロック + 入金導線を出す。
  // backend B1 の build-tx 残高ガード (SUPPLY/USDC 限定) とフロント表示を一致させる。
  const insufficientBalance =
    pendingProposal?.operation === "SUPPLY" &&
    balanceUsd != null &&
    Number(pendingProposal.amount_usd) > balanceUsd

  return (
    <div className="w-[375px] mx-auto h-dvh ax-bg-app text-[#1c1a27] flex flex-col overflow-hidden relative">

      {/* ── ヘッダー（arobix グラデ） */}
      <header className="h-14 bg-gradient-to-r from-[#b9a4f2] via-[#ecaccd] to-[#fbd9a0] grid grid-cols-3 items-center px-4 flex-shrink-0">
        <button
          onClick={() => { setMenuOpen(true); track(EV.MENU_OPEN) }}
          className="text-[#1c1a27] p-1 hover:bg-black/5 rounded-lg transition-colors justify-self-start"
          aria-label={t("header.menuAriaLabel")}
        >
          <Menu className="w-6 h-6" />
        </button>
        {/* ヘッダー中央ロゴは非表示（QA AI FAB に集約）。grid-cols-3 維持のため空プレースホルダ */}
        <div aria-hidden="true" />
        <div className="flex items-center gap-1 justify-self-end">
          {/* JP/EN トグルボタン */}
          <button
            onClick={() => { const next = language === "ja" ? "en" : "ja"; setLanguage(next); track(EV.LANGUAGE_TOGGLE, { language: next }) }}
            aria-label={t("header.langToggleAriaLabel")}
            className="text-[#1c1a27] text-xs font-semibold px-2 py-1 rounded-md
                       hover:bg-black/5 transition-colors border border-[#1c1a27]/30"
          >
            {language === "ja" ? "EN" : "JP"}
          </button>
          <button
            onClick={() => { setActivePanel("account"); setPanelFromMenu(false); track(EV.ACCOUNT_OPEN) }}
            className="text-[#1c1a27] p-1 hover:bg-black/5 rounded-lg transition-colors"
            aria-label={t("header.accountAriaLabel")}
          >
            <User className="w-6 h-6" />
          </button>
        </div>
      </header>

      {/* ── メインコンテンツ */}
      <main className="flex-1 overflow-y-auto pb-24">

        {/* AI 判定 / 保留中の提案（ヘッダー直下=最優先表示。統合ボックス化により
            保留中の提案がある間は下の統合カードに一本化し、銘柄・金額のない
            汎用カードは表示しない。行動を促す情報を資産サマリーより先に出す） */}
        {!pendingProposal && (
          <div
            className={`rounded-2xl mx-4 mt-4 p-4 transition-all
              ${isBuy
                ? "ax-card-warm border-2 border-[#1D9E75] [animation:pulse_0.8s_ease-in-out_2]"
                : isSell
                ? "ax-card-warm border-2 border-red-500 [animation:pulse_0.8s_ease-in-out_2]"
                : "ax-card-warm"
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
                    : "bg-[#736f7e]"
                }`}
              />
              <span
                className={`text-xs font-medium ${
                  isBuy ? "text-[#1D9E75]" : isSell ? "text-red-600" : "text-[#736f7e]"
                }`}
              >
                {t("home.aiJudgment")}
              </span>
            </div>

            {/* アクション表示 */}
            <div
              className={`font-bold text-2xl ${
                isBuy ? "text-[#1D9E75]" : isSell ? "text-red-600" : "text-[#1c1a27]"
              }`}
            >
              {aiJudgment ? action : t("home.noSignal")}
            </div>

            {/* 確信度表示。HOLD は「シグナルが弱く様子見」と分かる文言、BUY/SELL は従来表記。 */}
            {aiJudgment && (
              <p className="mt-1 text-[#736f7e] text-xs" data-testid="confidence-label">
                {action === "HOLD"
                  ? t("home.holdWeakSignalLabel", { confidence })
                  : `${confidence}% ${t("home.confidenceLabel")}`}
              </p>
            )}

            {/* なぜ{action}？理由トグル（aiJudgment がある場合のみ表示） */}
            {aiJudgment && (
              <>
                <button
                  onClick={() => { const next = !reasonOpen; setReasonOpen(next); track(EV.REASON_TOGGLE, { action, open: next }) }}
                  className="mt-2 text-[#736f7e] text-xs underline"
                  aria-expanded={reasonOpen}
                >
                  {t("home.whyAction", { action })}
                </button>
                {reasonOpen && (
                  <p className="mt-2 text-[#736f7e] text-xs leading-relaxed whitespace-pre-wrap">
                    {aiJudgment.reason ?? t("home.noReason")}
                  </p>
                )}
              </>
            )}
          </div>
        )}

        {/* 保留中の提案（承認→自己署名→実行 / 見送り）。統合ボックス化により銘柄・金額・
            確信度・ウォレット残高をカード内に集約する（KPI-E の別行表示は廃止）。 */}
        {pendingProposal && (
          pendingProposal.status === "awaiting_funds" ? (
            <AwaitingFundsCard
              proposal={pendingProposal}
              balanceUsd={balanceUsd}
              rejecting={rejecting}
              onReject={handleRejectProposal}
              onDepositSettled={refetchBalance}
            />
          ) : (
            <ProposalActionCard
              proposal={pendingProposal}
              rejecting={rejecting}
              onApprove={handleApproveProposal}
              onReject={handleRejectProposal}
              insufficientBalance={insufficientBalance}
              confidence={aiJudgment?.confidence}
              balanceUsd={balanceUsd}
              onDepositSettled={refetchBalance}
            />
          )
        )}

        {/* CURRENT ASSET カード（タップでグラフパネル） */}
        <button
          onClick={() => { setGraphOpen(true); track(EV.ASSET_GRAPH_OPEN) }}
          className="bg-gradient-to-br from-[#b9a4f2] via-[#ecaccd] to-[#fbd9a0] rounded-2xl mx-4 mt-4 p-4 text-left w-[calc(100%-2rem)]
                     active:brightness-95 transition-all"
        >
          <div className="text-[#2a2440]/70 text-xs mb-1">{t("home.currentAsset")}</div>
          <div className="text-[#1c1a27] text-3xl font-bold">
            {balanceUsd != null
              ? `$${balanceUsd.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
              : "—"}
          </div>
        </button>

        {/* KPI-C: 運用残高 + 加重平均APY */}
        <div className="grid grid-cols-2 gap-3 mx-4 mt-3">
          <div className="ax-card-warm rounded-2xl p-3">
            <div className="text-xs text-[#736f7e]">{t("kpi.totalValue")}</div>
            <div className="text-lg font-bold text-[#1c1a27]">
              {portfolio
                ? `$${Number(portfolio.total_value_usd).toLocaleString("en-US", { maximumFractionDigits: 2 })}`
                : "—"}
            </div>
          </div>
          <div className="ax-card-warm rounded-2xl p-3">
            <div className="text-xs text-[#736f7e]">{t("kpi.avgApy")}</div>
            <div className="text-lg font-bold text-[#1D9E75]">
              {portfolio && Number(portfolio.weighted_avg_apy) > 0
                ? `${Number(portfolio.weighted_avg_apy).toFixed(2)}%`
                : "—"}
            </div>
          </div>
        </div>

        {/* KPI-D: 月次手取り（配当）グラフ */}
        <div className="mx-4 mt-3 ax-card-warm rounded-2xl p-4">
          <div className="text-xs text-[#736f7e] mb-2">{t("kpi.monthlyDividend")}</div>
          <DividendChartWrapper data={dividends} />
        </div>

        {/* 運用中コイン一覧 */}
        <div className="mx-4 mt-4">
          <h3 className="text-[#736f7e] text-xs font-semibold mb-3">{t("home.operatingCoins")}</h3>
          <div className="space-y-2">
            {coins.map((coin) => (
              <div
                key={coin.asset}
                className="flex items-center w-full ax-card-warm rounded-xl px-4 py-3"
              >
                {/* コインアバター */}
                <div
                  className="w-8 h-8 rounded-full bg-[#1D9E75]/15 text-[#1D9E75]
                               flex items-center justify-center text-xs font-bold mr-3 flex-shrink-0"
                >
                  {coin.asset.slice(0, 2)}
                </div>
                <div className="flex-1 text-left">
                  <div className="text-[#1c1a27] text-sm font-medium">{coin.asset}</div>
                </div>
                <div className="text-right">
                  <div className="text-[#1c1a27] text-sm">${coin.amount_usd.toLocaleString()}</div>
                  <div
                    className={`text-xs ${
                      coin.apy_pct >= 0 ? "text-[#1D9E75]" : "text-red-600"
                    }`}
                  >
                    {coin.apy_pct >= 0 ? "+" : ""}
                    {coin.apy_pct}% APY
                  </div>
                </div>
              </div>
            ))}
            {coins.length === 0 && (
              <div className="text-center py-6 text-[#736f7e] text-sm">
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
          <div className="relative w-[375px] mx-auto ax-card-warm rounded-t-2xl p-5 ax-safe-bottom">
            <h3 className="text-[#1c1a27] font-bold text-lg mb-1">{t("home.stopConfirmTitle")}</h3>
            <p className="text-[#736f7e] text-sm mb-4 leading-relaxed">
              {t("home.stopConfirmDesc")}
            </p>
            <div className="flex gap-3">
              <button
                onClick={() => setStopConfirmOpen(false)}
                disabled={stopLoading}
                className="flex-1 py-3 rounded-xl border border-[#1c1a27]/20 text-[#1c1a27] font-semibold disabled:opacity-40"
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
          className="fixed top-4 left-1/2 -translate-x-1/2 z-[60] px-4 py-2 rounded-xl bg-[#1b1a23]
                     text-[#fbf7f0] text-sm shadow-lg whitespace-nowrap"
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
        {/* QA AI ボタン = UAT アニメロゴ（ヘッダーと同一・カラータイマー点滅継続） */}
        <svg viewBox="0 0 100 100" className="w-12 h-12" aria-hidden="true">
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
        {unreadCount > 0 && (
          <span
            className="absolute -top-1 -right-1 w-5 h-5 rounded-full bg-red-500 text-white text-xs
                       flex items-center justify-center font-bold"
          >
            {unreadCount}
          </span>
        )}
      </button>

      {/* ── 提案 署名シート（承認→Privy 自己署名→submit-tx） */}
      {pendingProposal && (
        <ProposalSignSheet
          proposal={pendingProposal}
          token={authToken}
          open={signSheetOpen}
          onClose={() => setSignSheetOpen(false)}
          onExecuted={handleProposalExecuted}
          insufficientBalance={insufficientBalance}
          balanceUsd={balanceUsd}
          onDepositSettled={refetchBalance}
        />
      )}

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
                  : "bg-[#1c1a27]/5 text-[#736f7e]"
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
            // v3: 取得原価ベースの基準値が無いため初期額/損益/利回りは「—」。
            // 現在額のみオンチェーン残高（useUsdcBalance）で表示する。
            {
              label: t("panels.statsStart"),
              value: "—",
            },
            {
              label: t("panels.statsCurrent"),
              value:
                balanceUsd != null
                  ? `$${balanceUsd.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
                  : "—",
            },
            {
              label: t("panels.statsProfit"),
              value: "—",
            },
            {
              label: t("panels.statsYield"),
              value: "—",
            },
          ].map((s) => (
            <div key={s.label} className="ax-card-warm rounded-xl p-3">
              <div className="text-[#736f7e] text-xs">{s.label}</div>
              <div className="text-[#1c1a27] font-semibold mt-0.5">{s.value}</div>
            </div>
          ))}
        </div>
      </SlideUpPanel>

      {/* ── ハンバーガーメニュー（既存維持） */}
      <HamburgerMenu
        open={menuOpen}
        onClose={() => setMenuOpen(false)}
        onPanelOpen={(id) => { setActivePanel(id); setPanelFromMenu(true); track(EV.PANEL_OPEN, { panel: id }) }}
      />

      {/* ── 各パネル（既存維持） */}
      {Object.keys(PANEL_TITLES).map((id) => (
        <SlideUpPanel
          key={id}
          open={activePanel === id}
          onClose={() => { setActivePanel(null); if (panelFromMenu) { setMenuOpen(true); setPanelFromMenu(false) } }}
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
