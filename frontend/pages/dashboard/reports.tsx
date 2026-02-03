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
        <title>レポート - Ultra AutoTrade</title>
      </Head>

      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", gap: 12, flexWrap: "wrap" }}>
        <div>
          <h1 style={{ marginBottom: 6 }}>最新レポート</h1>
          <p style={{ marginTop: 0, color: "#555" }}>
            Runbook のレポート確認に沿ったサマリービュー。
          </p>
        </div>

        <button
          onClick={() => load()}
          disabled={loading}
          style={{ padding: "6px 10px", borderRadius: 10, border: "1px solid #ddd", background: "#fff", cursor: "pointer" }}
        >
          {loading ? "読み込み中..." : "更新"}
        </button>
      </div>

      {error ? (
        <div style={{ marginTop: 12, padding: 12, border: "1px solid #f1c0c0", background: "#fff5f5", borderRadius: 12 }}>
          <strong>読み込み失敗</strong>
          <div style={{ marginTop: 6, fontFamily: "ui-monospace, Menlo, monospace", fontSize: 12 }}>{error}</div>
        </div>
      ) : null}

      {report ? <ReportSummaryPanel report={report} /> : null}

      <section style={{ marginTop: 16, border: "1px dashed #ddd", borderRadius: 12, padding: 14 }}>
        <h2 style={{ margin: 0, fontSize: 14 }}>運用アクション（Runbook）</h2>
        <ul style={{ marginTop: 10, marginBottom: 0, color: "#555" }}>
          <li><code>highlights</code> を確認し、未解決の警告がないことを確認。</li>
          <li>レポート生成が失敗した場合、ReportingService のログと依存関係を確認。</li>
        </ul>
      </section>
    </AppShell>
  );
}
