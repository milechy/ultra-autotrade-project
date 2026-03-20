import { getJson } from "./http";
import type { AutomationStatus, DashboardSnapshot, AutomationReportSummary } from "../types";

// API paths match the actual backend routes.
// - Local dev: /api/automation/* (new)
// - Staging: /api/* (legacy)
// If NEXT_PUBLIC_BACKEND_BASE_URL is set, requests go directly to the backend.

export async function fetchAutomationStatus(token?: string): Promise<AutomationStatus> {
  const init = token ? { headers: { Authorization: `Bearer ${token}` } } : undefined;
  // Try both new and legacy paths
  try {
    return await getJson<AutomationStatus>("/api/automation/status", init);
  } catch (e: any) {
    if (e?.status === 404) {
      // Fallback: legacy path
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
      // Fallback: legacy path
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
      // Fallback: legacy path
      return await getJson<AutomationReportSummary>("/api/reports/latest", init);
    }
    throw e;
  }
}
