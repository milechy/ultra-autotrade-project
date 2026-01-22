import React from "react";
import type { DashboardSnapshot } from "../../lib/types";

/**
 * Contract-safe visualization strategy:
 * - We do NOT assume specific aggregate keys.
 * - If aggregates exist, we render a compact table.
 * - Otherwise we fall back to raw JSON.
 */
export default function SnapshotCharts({ snapshot }: { snapshot: DashboardSnapshot }) {
  const aggs = snapshot.aggregates;

  return (
    <section style={sectionStyle}>
      <header style={headerStyle}>
        <h2 style={{ margin: 0, fontSize: 16 }}>DashboardSnapshot</h2>
        <span style={{ color: "#666", fontSize: 12 }}>Source: GET /api/automation/dashboard</span>
      </header>

      <div style={{ marginTop: 10, display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(260px, 1fr))", gap: 12 }}>
        <Card title="period_start">{new Date(snapshot.period_start).toISOString()}</Card>
        <Card title="period_end">{new Date(snapshot.period_end).toISOString()}</Card>
      </div>

      {aggs && typeof aggs === "object" ? (
        <div style={{ marginTop: 12 }}>
          <div style={{ fontSize: 12, color: "#666", marginBottom: 6 }}>aggregates (metric_id → aggregate)</div>
          <div style={{ border: "1px solid #e5e5e5", borderRadius: 12, overflow: "hidden" }}>
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
              <thead>
                <tr style={{ background: "#fafafa" }}>
                  <th style={thStyle}>metric_id</th>
                  <th style={thStyle}>value</th>
                </tr>
              </thead>
              <tbody>
                {Object.entries(aggs).slice(0, 50).map(([k, v]) => (
                  <tr key={k}>
                    <td style={tdStyle}><code>{k}</code></td>
                    <td style={tdStyle}><code>{stringifyCompact(v)}</code></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div style={{ color: "#777", fontSize: 12, marginTop: 6 }}>
            Showing up to 50 items. Use Raw JSON for the full payload.
          </div>
        </div>
      ) : null}

      <details style={{ marginTop: 12 }}>
        <summary style={{ cursor: "pointer" }}>Raw JSON</summary>
        <pre style={preStyle}>{JSON.stringify(snapshot, null, 2)}</pre>
      </details>
    </section>
  );
}

function stringifyCompact(v: unknown): string {
  if (v === null || v === undefined) return String(v);
  if (typeof v === "string" || typeof v === "number" || typeof v === "boolean") return String(v);
  try { return JSON.stringify(v); } catch { return "[unserializable]"; }
}

function Card({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div style={{ border: "1px solid #e5e5e5", borderRadius: 12, padding: 14, background: "#fff" }}>
      <div style={{ fontSize: 12, color: "#666", marginBottom: 8 }}>{title}</div>
      <div style={{ fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace", fontSize: 12 }}>{children}</div>
    </div>
  );
}

const sectionStyle: React.CSSProperties = {
  marginTop: 16,
  border: "1px solid #eee",
  borderRadius: 12,
  padding: 14,
  background: "#fff",
};

const headerStyle: React.CSSProperties = {
  display: "flex",
  justifyContent: "space-between",
  alignItems: "baseline",
  gap: 10,
};

const preStyle: React.CSSProperties = {
  marginTop: 8,
  padding: 10,
  borderRadius: 10,
  background: "#f7f7f7",
  overflowX: "auto",
  fontSize: 12,
};

const thStyle: React.CSSProperties = { textAlign: "left", padding: "10px 10px", borderBottom: "1px solid #eee" };
const tdStyle: React.CSSProperties = { textAlign: "left", padding: "10px 10px", borderBottom: "1px solid #f0f0f0", verticalAlign: "top" };
