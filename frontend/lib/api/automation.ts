import { getJson } from "./http";
import type { AutomationStatus, DashboardSnapshot, AutomationReportSummary } from "../types";

export async function fetchAutomationStatus(): Promise<AutomationStatus> {
  return await getJson<AutomationStatus>("/api/automation/status");
}

export async function fetchDashboardSnapshot(lookbackHours: number): Promise<DashboardSnapshot> {
  const q = new URLSearchParams({ lookback_hours: String(lookbackHours) });
  return await getJson<DashboardSnapshot>(`/api/automation/dashboard?${q.toString()}`);
}

export async function fetchLatestReport(): Promise<AutomationReportSummary> {
  return await getJson<AutomationReportSummary>("/api/automation/reports/latest");
}
