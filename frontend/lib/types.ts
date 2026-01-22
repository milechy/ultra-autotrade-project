// NOTE: We intentionally model these as minimally-typed objects.
// The source of truth is backend/app/automation/schemas.py.
// We avoid “inventing” fields (contract change prohibited). UI renders known fields when present, and falls back to JSON.

export type AutomationStatus = {
  is_trading_paused: boolean;
  last_health_factor?: string | number | null;
  last_price_change_24h?: number | null;
  last_event_level?: string | null;
  emergency_reason?: string | null;
  recent_events?: unknown[];
  [k: string]: unknown;
};

export type DashboardSnapshot = {
  generated_at: string;
  period_start: string;
  period_end: string;
  status: AutomationStatus;
  aggregates?: Record<string, unknown>;
  [k: string]: unknown;
};

export type AutomationReportSummary = {
  period: string;
  generated_at?: string;
  highlights?: string[];
  metrics?: unknown[];
  [k: string]: unknown;
};
