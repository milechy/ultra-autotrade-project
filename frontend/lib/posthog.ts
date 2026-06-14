// PostHog クライアント & イベント定数
import posthog from "posthog-js"

export const POSTHOG_KEY = process.env.NEXT_PUBLIC_POSTHOG_KEY ?? ""
export const POSTHOG_HOST = process.env.NEXT_PUBLIC_POSTHOG_HOST ?? "https://us.i.posthog.com"

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
  LANGUAGE_TOGGLE:     "liff_language_toggle",
  ACCOUNT_OPEN:        "liff_account_open",
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
