import { getJson } from "./http";
import type { AutomationStatus, DashboardSnapshot, AutomationReportSummary } from "../types";

// API パスは Backend の実際のルートに合わせる
// - ローカル開発: /api/automation/* (新)
// - Hetzner Staging: /api/* (旧)
// NEXT_PUBLIC_BACKEND_BASE_URL が設定されている場合は直接 Backend にアクセス

export async function fetchAutomationStatus(token?: string): Promise<AutomationStatus> {
  const init = token ? { headers: { Authorization: `Bearer ${token}` } } : undefined;
  // 新旧両方のパスを試行
  try {
    return await getJson<AutomationStatus>("/api/automation/status", init);
  } catch (e: any) {
    if (e?.status === 404) {
      // フォールバック: 旧パス
      return await getJson<AutomationStatus>("/api/status", init);
    }
    throw e;
  }
}

export async function fetchDashboardSnapshot(lookbackHours: number, token?: string): Promise<DashboardSnapshot> {
  const q = new URLSearchParams({ lookback_hours: String(lookbackHours) });
  const init = token ? { headers: { Authorization: `Bearer ${token}` } } : undefined;
  try {
    return await getJson<DashboardSnapshot>(`/api/automation/dashboard?${q.toString()}`, init);
  } catch (e: any) {
    if (e?.status === 404) {
      // フォールバック: 旧パス
      return await getJson<DashboardSnapshot>(`/api/dashboard?${q.toString()}`, init);
    }
    throw e;
  }
}

export async function fetchLatestReport(token?: string): Promise<AutomationReportSummary> {
  const init = token ? { headers: { Authorization: `Bearer ${token}` } } : undefined;
  try {
    return await getJson<AutomationReportSummary>("/api/automation/reports/latest", init);
  } catch (e: any) {
    if (e?.status === 404) {
      // フォールバック: 旧パス
      return await getJson<AutomationReportSummary>("/api/reports/latest", init);
    }
    throw e;
  }
}
