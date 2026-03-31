'use client'
// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.

import React from "react";
import KpiCards from "@/components/dashboard/KpiCards";
import StatusPanel from "@/components/dashboard/StatusPanel";
import SnapshotCharts from "@/components/dashboard/SnapshotCharts";
import { fetchAutomationStatus, fetchDashboardSnapshot } from "@/lib/api/automation";
import { useAuth } from "@/lib/auth";
import type { AutomationStatus, DashboardSnapshot } from "@/lib/types";

export default function AutomationPage() {
  const { token } = useAuth();
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
        fetchAutomationStatus(token ?? undefined),
        fetchDashboardSnapshot(lookbackHours, token ?? undefined),
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
    <>
      <title>自動売買 - Ultra AutoTrade</title>

      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", gap: 12, flexWrap: "wrap" }}>
        <div>
          <h1 style={{ marginBottom: 6 }}>自動売買ステータス</h1>
          <p style={{ marginTop: 0, color: "#555" }}>
            運用読み取り専用ビュー。<code>docs/19_operations_runbook.md</code> §2.4 に準拠。
          </p>
        </div>

        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <label style={{ fontSize: 12, color: "#666" }}>参照時間</label>
          <select
            value={lookbackHours}
            onChange={(e) => setLookbackHours(Number(e.target.value))}
            style={{ padding: "6px 10px", borderRadius: 10, border: "1px solid #ddd" }}
          >
            {[1, 6, 12, 24].map((v) => (
              <option key={v} value={v}>{v}時間</option>
            ))}
          </select>
          <button
            onClick={() => load()}
            disabled={loading}
            style={{ padding: "6px 10px", borderRadius: 10, border: "1px solid #ddd", background: "#fff", cursor: "pointer" }}
          >
            {loading ? "読み込み中..." : "更新"}
          </button>
        </div>
      </div>

      {error ? (
        <div style={{ marginTop: 12, padding: 12, border: "1px solid #f1c0c0", background: "#fff5f5", borderRadius: 12 }}>
          <strong>読み込み失敗</strong>
          <div style={{ marginTop: 6, fontFamily: "ui-monospace, Menlo, monospace", fontSize: 12 }}>{error}</div>
        </div>
      ) : null}

      {status ? <KpiCards status={status} snapshot={snapshot ?? undefined} /> : null}

      {status ? <StatusPanel status={status} /> : null}
      {snapshot ? <SnapshotCharts snapshot={snapshot} /> : null}

      <section style={{ marginTop: 16, border: "1px dashed #ddd", borderRadius: 12, padding: 14 }}>
        <h2 style={{ margin: 0, fontSize: 14 }}>運用アクション（Runbook）</h2>
        <ul style={{ marginTop: 10, marginBottom: 0, color: "#555" }}>
          <li><code>is_trading_paused = true</code> の場合、Runbook「緊急停止状態」の確認手順に従う。</li>
          <li><code>last_health_factor</code> が低い場合、Runbook「Aave HF 低下」の確認手順に従う。</li>
          <li>エラーが継続する場合、バックエンドログと依存関係の状態を確認。</li>
        </ul>
      </section>
    </>
  );
}