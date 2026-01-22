import Head from "next/head";
import React from "react";
import AppShell from "../../components/layout/AppShell";
import KpiCards from "../../components/dashboard/KpiCards";
import StatusPanel from "../../components/dashboard/StatusPanel";
import SnapshotCharts from "../../components/dashboard/SnapshotCharts";
import { fetchAutomationStatus, fetchDashboardSnapshot } from "../../lib/api/automation";
import type { AutomationStatus, DashboardSnapshot } from "../../lib/types";

export default function AutomationPage() {
  const [lookbackHours, setLookbackHours] = React.useState<number>(6);
  const [status, setStatus] = React.useState<AutomationStatus | null>(null);
  const [snapshot, setSnapshot] = React.useState<DashboardSnapshot | null>(null);
  const [error, setError] = React.useState<string | null>(null);
  const [loading, setLoading] = React.useState<boolean>(false);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const [s, snap] = await Promise.all([
        fetchAutomationStatus(),
        fetchDashboardSnapshot(lookbackHours),
      ]);
      setStatus(s);
      setSnapshot(snap);
    } catch (e: any) {
      setError(e?.message || String(e));
    } finally {
      setLoading(false);
    }
  }

  React.useEffect(() => { load(); /* eslint-disable-line */ }, [lookbackHours]);

  return (
    <AppShell>
      <Head>
        <title>Automation - Ultra AutoTrade</title>
      </Head>

      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", gap: 12, flexWrap: "wrap" }}>
        <div>
          <h1 style={{ marginBottom: 6 }}>Automation Health</h1>
          <p style={{ marginTop: 0, color: "#555" }}>
            Operational read-only view. Aligns with <code>docs/19_operations_runbook.md</code> §2.4.
          </p>
        </div>

        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <label style={{ fontSize: 12, color: "#666" }}>lookback_hours</label>
          <select
            value={lookbackHours}
            onChange={(e) => setLookbackHours(Number(e.target.value))}
            style={{ padding: "6px 10px", borderRadius: 10, border: "1px solid #ddd" }}
          >
            {[1, 6, 12, 24].map((v) => (
              <option key={v} value={v}>{v}</option>
            ))}
          </select>
          <button
            onClick={() => load()}
            disabled={loading}
            style={{ padding: "6px 10px", borderRadius: 10, border: "1px solid #ddd", background: "#fff", cursor: "pointer" }}
          >
            {loading ? "Loading..." : "Refresh"}
          </button>
        </div>
      </div>

      {error ? (
        <div style={{ marginTop: 12, padding: 12, border: "1px solid #f1c0c0", background: "#fff5f5", borderRadius: 12 }}>
          <strong>Failed to load</strong>
          <div style={{ marginTop: 6, fontFamily: "ui-monospace, Menlo, monospace", fontSize: 12 }}>{error}</div>
        </div>
      ) : null}

      {status ? <KpiCards status={status} snapshot={snapshot ?? undefined} /> : null}

      {status ? <StatusPanel status={status} /> : null}
      {snapshot ? <SnapshotCharts snapshot={snapshot} /> : null}

      <section style={{ marginTop: 16, border: "1px dashed #ddd", borderRadius: 12, padding: 14 }}>
        <h2 style={{ margin: 0, fontSize: 14 }}>Operational actions (runbook)</h2>
        <ul style={{ marginTop: 10, marginBottom: 0, color: "#555" }}>
          <li>If <code>is_trading_paused = true</code>, follow Runbook “Emergency stop state” checks.</li>
          <li>If <code>last_health_factor</code> is low, follow Runbook “Aave HF degradation” checks.</li>
          <li>If errors persist, confirm backend logs and dependency health.</li>
        </ul>
      </section>
    </AppShell>
  );
}
