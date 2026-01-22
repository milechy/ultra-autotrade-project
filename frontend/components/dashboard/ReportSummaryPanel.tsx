import React from "react";
import type { AutomationReportSummary } from "../../lib/types";

export default function ReportSummaryPanel({ report }: { report: AutomationReportSummary }) {
  return (
    <section style={sectionStyle}>
      <header style={headerStyle}>
        <h2 style={{ margin: 0, fontSize: 16 }}>AutomationReportSummary</h2>
        <span style={{ color: "#666", fontSize: 12 }}>Source: GET /api/automation/reports/latest</span>
      </header>

      <div style={{ marginTop: 10 }}>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))", gap: 12 }}>
          <Card title="period">{String(report.period ?? "N/A")}</Card>
          <Card title="generated_at">{String(report.generated_at ?? "N/A")}</Card>
        </div>
      </div>

      {Array.isArray(report.highlights) && report.highlights.length > 0 ? (
        <div style={{ marginTop: 12 }}>
          <div style={{ fontSize: 12, color: "#666", marginBottom: 6 }}>highlights</div>
          <ul style={{ marginTop: 0 }}>
            {report.highlights.map((h, idx) => (
              <li key={idx} style={{ marginBottom: 6 }}>{h}</li>
            ))}
          </ul>
        </div>
      ) : null}

      <details style={{ marginTop: 12 }}>
        <summary style={{ cursor: "pointer" }}>Raw JSON</summary>
        <pre style={preStyle}>{JSON.stringify(report, null, 2)}</pre>
      </details>
    </section>
  );
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
