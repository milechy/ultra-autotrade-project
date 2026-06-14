'use client'
// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.

import React from "react";
import { useTranslations } from "next-intl";
import AuthGuard from "@/components/AuthGuard";
import ReportSummaryPanel from "@/components/dashboard/ReportSummaryPanel";
import { fetchLatestReport } from "@/lib/api/automation";
import { useAuth } from "@/lib/auth";
import type { AutomationReportSummary } from "@/lib/types";

export default function ReportsPage() {
  const t = useTranslations("AdminDashboardReports");
  const { token } = useAuth();
  const [report, setReport] = React.useState<AutomationReportSummary | null>(null);
  const [error, setError] = React.useState<string | null>(null);
  const [loading, setLoading] = React.useState<boolean>(false);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const r = await fetchLatestReport(token ?? undefined);
      setReport(r);
    } catch (e: any) {
      setError(e?.message || String(e));
    } finally {
      setLoading(false);
    }
  }

  React.useEffect(() => { load(); }, []);

  return (
    <AuthGuard adminOnly>
      <>
      <title>{t("browserTitle")}</title>

      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", gap: 12, flexWrap: "wrap" }}>
        <div>
          <h1 style={{ marginBottom: 6 }}>{t("pageTitle")}</h1>
          <p style={{ marginTop: 0, color: "#555" }}>
            {t("pageSubtitle")}
          </p>
        </div>

        <button
          onClick={() => load()}
          disabled={loading}
          style={{ padding: "6px 10px", borderRadius: 10, border: "1px solid #ddd", background: "#fff", cursor: "pointer" }}
        >
          {loading ? t("loading") : t("refreshButton")}
        </button>
      </div>

      {error ? (
        <div style={{ marginTop: 12, padding: 12, border: "1px solid #f1c0c0", background: "#fff5f5", borderRadius: 12 }}>
          <strong>{t("fetchFailed")}</strong>
          <div style={{ marginTop: 6, fontFamily: "ui-monospace, Menlo, monospace", fontSize: 12 }}>{error}</div>
        </div>
      ) : null}

      {report ? <ReportSummaryPanel report={report} /> : null}

      <section style={{ marginTop: 16, border: "1px dashed #ddd", borderRadius: 12, padding: 14 }}>
        <h2 style={{ margin: 0, fontSize: 14 }}>{t("runbookHeading")}</h2>
        <ul style={{ marginTop: 10, marginBottom: 0, color: "#555" }}>
          <li>{t("runbookItem1")}</li>
          <li>{t("runbookItem2")}</li>
        </ul>
      </section>
      </>
    </AuthGuard>
  );
}
