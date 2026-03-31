// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.
import React from "react";
import type { AutomationStatus } from "../../lib/types";

export default function StatusPanel({ status }: { status: AutomationStatus }) {
  return (
    <section style={sectionStyle}>
      <header style={headerStyle}>
        <h2 style={{ margin: 0, fontSize: 16 }}>AutomationStatus</h2>
        <span style={{ color: "#666", fontSize: 12 }}>Source: GET /api/automation/status</span>
      </header>

      <div style={{ marginTop: 10 }}>
        <Field label="emergency_reason" value={status.emergency_reason ?? "—"} />
      </div>

      <details style={{ marginTop: 12 }}>
        <summary style={{ cursor: "pointer" }}>生データ（JSON）</summary>
        <pre style={preStyle}>{JSON.stringify(status, null, 2)}</pre>
      </details>
    </section>
  );
}

function Field({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div style={{ display: "flex", gap: 10, padding: "6px 0" }}>
      <div style={{ width: 180, color: "#666", fontSize: 12 }}>{label}</div>
      <div style={{ fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace", fontSize: 12 }}>{value}</div>
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
