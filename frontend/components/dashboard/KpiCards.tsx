// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.
'use client'
import React from "react";
import { useTranslations } from "next-intl";
import type { AutomationStatus, DashboardSnapshot } from "../../lib/types";

export default function KpiCards({ status, snapshot }: { status: AutomationStatus; snapshot?: DashboardSnapshot }) {
  const t = useTranslations("DashboardKpiCards");
  const paused = status.is_trading_paused;
  const hf = status.last_health_factor ?? null;
  const change24h = status.last_price_change_24h ?? null;
  const level = status.last_event_level ?? null;

  return (
    <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))", gap: 12 }}>
      <Card title={t("tradingStatus")}>
        <div style={{ fontSize: 20, fontWeight: 700 }}>{paused ? t("stopped") : t("running")}</div>
        <div style={{ color: "#666", marginTop: 4 }}>is_trading_paused</div>
      </Card>

      <Card title={t("safetyScore")}>
        <div style={{ fontSize: 20, fontWeight: 700 }}>{hf === null ? "N/A" : String(hf)}</div>
        <div style={{ color: "#666", marginTop: 4 }}>last_health_factor</div>
      </Card>

      <Card title={t("portfolio24h")}>
        <div style={{ fontSize: 20, fontWeight: 700 }}>{change24h === null ? "N/A" : `${change24h}%`}</div>
        <div style={{ color: "#666", marginTop: 4 }}>last_price_change_24h</div>
      </Card>

      <Card title={t("latestEventLevel")}>
        <div style={{ fontSize: 20, fontWeight: 700 }}>{level ?? "N/A"}</div>
        <div style={{ color: "#666", marginTop: 4 }}>last_event_level</div>
      </Card>

      {snapshot?.generated_at ? (
        <Card title={t("snapshotGeneratedAt")}>
          <div style={{ fontSize: 14, fontWeight: 700 }}>{new Date(snapshot.generated_at).toISOString()}</div>
          <div style={{ color: "#666", marginTop: 4 }}>generated_at (UTC)</div>
        </Card>
      ) : null}
    </div>
  );
}

function Card({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div style={{ border: "1px solid #e5e5e5", borderRadius: 12, padding: 14, background: "#fff" }}>
      <div style={{ fontSize: 12, color: "#666", marginBottom: 8 }}>{title}</div>
      {children}
    </div>
  );
}
