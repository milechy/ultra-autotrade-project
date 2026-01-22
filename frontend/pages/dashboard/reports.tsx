import Head from "next/head";
import React from "react";
import AppShell from "../../components/layout/AppShell";
import ReportSummaryPanel from "../../components/dashboard/ReportSummaryPanel";
import { fetchLatestReport } from "../../lib/api/automation";
import type { AutomationReportSummary } from "../../lib/types";

export default function ReportsPage() {
  const [report, setReport] = React.useState<AutomationReportSummary | null>(null);
  const [error, setError] = React.useState<string | null>(null);
  const [loading, setLoading] = React.useState<boolean>(false);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const r = await fetchLatestReport();
      setReport(r);
    } catch (e: any) {
      setError(e?.message || String(e));
    } finally {
      setLoading(false);
    }
  }

  React.useEffect(() => { load(); }, []);

  return (
    <AppShell>
      <Head>
        <title>Reports - Ultra AutoTrade</title>
      </Head>

      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", gap: 12, flexWrap: "wrap" }}>
        <div>
          <h1 style={{ marginBottom: 6 }}>Latest Report</h1>
          <p style={{ marginTop: 0, color: "#555" }}>
            Summary view aligned with runbook reporting checks.
          </p>
        </div>

        <button
          onClick={() => load()}
          disabled={loading}
          style={{ padding: "6px 10px", borderRadius: 10, border: "1px solid #ddd", background: "#fff", cursor: "pointer" }}
        >
          {loading ? "Loading..." : "Refresh"}
        </button>
      </div>

      {error ? (
        <div style={{ marginTop: 12, padding: 12, border: "1px solid #f1c0c0", background: "#fff5f5", borderRadius: 12 }}>
          <strong>Failed to load</strong>
          <div style={{ marginTop: 6, fontFamily: "ui-monospace, Menlo, monospace", fontSize: 12 }}>{error}</div>
        </div>
      ) : null}

      {report ? <ReportSummaryPanel report={report} /> : null}

      <section style={{ marginTop: 16, border: "1px dashed #ddd", borderRadius: 12, padding: 14 }}>
        <h2 style={{ margin: 0, fontSize: 14 }}>Operational actions (runbook)</h2>
        <ul style={{ marginTop: 10, marginBottom: 0, color: "#555" }}>
          <li>Review <code>highlights</code> and confirm no unresolved warnings.</li>
          <li>If report generation fails, check ReportingService logs and dependencies.</li>
        </ul>
      </section>
    </AppShell>
  );
}
