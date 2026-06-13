"use client";

import { useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import AuthGuard from "@/components/AuthGuard";
import { useAuth } from "@/lib/auth";
import { fetchExchangeStatus } from "@/lib/api/exchange";

export default function DashboardPage() {
  const t = useTranslations("AdminDashboard");
  const { token } = useAuth();
  const [status, setStatus] = useState<string>(t("loading"));
  const [hf, setHf] = useState<string>("—");
  const [trades, setTrades] = useState<string>("—");

  useEffect(() => {
    if (!token) return;

    fetch("/api/automation/status", {
      headers: { Authorization: `Bearer ${token}` },
    })
      .then((r) => r.json())
      .then((d) => setStatus(d.is_trading_paused ? t("statusStopped") : t("statusRunning")))
      .catch(() => setStatus(t("fetchFailed")));

    fetch("/api/aave/status", {
      headers: { Authorization: `Bearer ${token}` },
    })
      .then((r) => r.json())
      .then((d) => setHf(d.health_factor ?? "—"))
      .catch(() => setHf(t("fetchFailed")));

    fetchExchangeStatus(token)
      .then((d) => setTrades(t("tradeCount", { count: d.daily_trades_used ?? 0 })))
      .catch(() => setTrades(t("fetchFailed")));
  }, [token, t]);

  return (
    <AuthGuard adminOnly>
      <div style={{ padding: "2rem" }}>
        <h1 style={{ fontSize: "1.5rem", fontWeight: "bold", marginBottom: "1.5rem" }}>
          {t("pageTitle")}
        </h1>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))", gap: "1rem" }}>
          <Card label={t("cardSystemStatus")} value={status} />
          <Card label={t("cardHealthFactor")} value={hf} />
          <Card label={t("cardDailyTrades")} value={trades} />
          <Card label={t("cardTotalAum")} value="$15,000" />
        </div>
      </div>
    </AuthGuard>
  );
}

function Card({ label, value }: { label: string; value: string }) {
  return (
    <div style={{ padding: "1.5rem", border: "1px solid #e5e7eb", borderRadius: "0.5rem", background: "#fff" }}>
      <p style={{ color: "#6b7280", fontSize: "0.875rem", margin: 0 }}>{label}</p>
      <p style={{ fontSize: "1.25rem", fontWeight: "bold", margin: "0.5rem 0 0" }}>{value}</p>
    </div>
  );
}
