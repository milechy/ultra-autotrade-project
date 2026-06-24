// PostHog クライアント & イベント定数
import posthog from "posthog-js"

export const POSTHOG_KEY = process.env.NEXT_PUBLIC_POSTHOG_KEY ?? ""
export const POSTHOG_HOST = process.env.NEXT_PUBLIC_POSTHOG_HOST ?? "https://us.i.posthog.com"
// デプロイごとの版識別子（デプロイ時に git short SHA を埋め込む。未設定時は "dev"）。
// 全イベントに super property として付与し、バージョン間の行動比較を可能にする。
export const APP_VERSION = process.env.NEXT_PUBLIC_APP_VERSION ?? "dev"

export function initPostHog() {
  if (typeof window === "undefined" || !POSTHOG_KEY) return
  if (posthog.__loaded) return
  posthog.init(POSTHOG_KEY, {
    api_host: POSTHOG_HOST,
    capture_pageview: true,
    capture_pageleave: true,
    autocapture: false,
    persistence: "localStorage",
  })
  // 以降の全イベントに app_version を付与（UI改善・バージョンアップ時の版間比較用）。
  posthog.register({ app_version: APP_VERSION })
}

// ── イベント名定数 ────────────────────────────────
export const EV = {
  MENU_OPEN:           "liff_menu_open",
  PANEL_OPEN:          "liff_panel_open",
  ASSET_GRAPH_OPEN:    "liff_asset_graph_open",
  GRAPH_PERIOD_CHANGE: "liff_graph_period_change",
  REASON_TOGGLE:       "liff_reason_toggle",
  JUDGMENT_APPROVE:    "liff_judgment_approve",
  JUDGMENT_REJECT:     "liff_judgment_reject",
  EMERGENCY_STOP:      "liff_emergency_stop",
  CHAT_OPEN:           "liff_chat_open",
  CHAT_QUESTION:       "liff_chat_question",
  LANGUAGE_TOGGLE:     "liff_language_toggle",
  ACCOUNT_OPEN:        "liff_account_open",
  OPMODE_CHANGE:       "liff_opmode_change",
  DEPOSIT_FUND:        "liff_deposit_fund",
  WITHDRAW_SUBMIT:     "liff_withdraw_submit",
  // データ取得失敗 (非2xx / 例外)。silent な握りつぶしを観測可能化し、
  // 提案・AI判定・残高などが「出ない」障害を早期検知する。
  DATA_FETCH_ERROR:    "liff_data_fetch_error",
} as const

export type EventName = typeof EV[keyof typeof EV]

export function track(event: EventName, props?: Record<string, unknown>) {
  if (typeof window === "undefined" || !POSTHOG_KEY) return
  posthog.capture(event, props)
}

export function identifyUser(userId: string | number, traits?: Record<string, unknown>) {
  if (typeof window === "undefined" || !POSTHOG_KEY) return
  posthog.identify(String(userId), traits)
}
