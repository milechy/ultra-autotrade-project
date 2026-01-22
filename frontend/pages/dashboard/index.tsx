import Head from "next/head";
import Link from "next/link";
import AppShell from "../../components/layout/AppShell";

export default function DashboardIndex() {
  return (
    <AppShell>
      <Head>
        <title>Dashboard - Ultra AutoTrade</title>
      </Head>

      <h1 style={{ marginBottom: 8 }}>Dashboard</h1>
      <p style={{ marginTop: 0, color: "#555" }}>
        Operations entry point. Choose a view aligned with the runbook.
      </p>

      <div style={{ display: "flex", gap: 12, flexWrap: "wrap", marginTop: 16 }}>
        <Link href="/dashboard/automation" style={cardStyle}>
          <strong>Automation Health</strong>
          <div style={{ color: "#555", marginTop: 6 }}>
            AutomationStatus + DashboardSnapshot
          </div>
        </Link>
        <Link href="/dashboard/reports" style={cardStyle}>
          <strong>Latest Report</strong>
          <div style={{ color: "#555", marginTop: 6 }}>
            AutomationReportSummary
          </div>
        </Link>
      </div>

      <section style={{ marginTop: 24 }}>
        <h2 style={{ fontSize: 16 }}>Runbook mapping</h2>
        <p style={{ color: "#555" }}>
          Each view includes an “Operational actions” section that links back to the corresponding runbook steps.
        </p>
      </section>
    </AppShell>
  );
}

const cardStyle: React.CSSProperties = {
  display: "block",
  padding: 16,
  border: "1px solid #ddd",
  borderRadius: 12,
  width: 320,
  textDecoration: "none",
  color: "inherit",
  background: "#fff",
};
