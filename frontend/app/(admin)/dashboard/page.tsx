"use client";

import { useEffect, useState } from "react";
import AuthGuard from "@/components/AuthGuard";
import { useAuth } from "@/lib/auth";
import { fetchExchangeStatus } from "@/lib/api/exchange";

export default function DashboardPage() {
  const { token } = useAuth();
  const [status, setStatus] = useState<string>("読み込み中...");
  const [hf, setHf] = useState<string>("—");
  const [trades, setTrades] = useState<string>("—");

  useEffect(() => {
    if (!token) return;

    fetch("/api/automation/status", {
      headers: { Authorization: `Bearer ${token}` },
    })
      .then((r) => r.json())
      .then((d) => setStatus(d.is_trading_paused ? "停止中" : "稼働中"))
      .catch(() => setStatus("取得失敗"));

    fetch("/api/aave/status", {
      headers: { Authorization: `Bearer ${token}` },
    })
      .then((r) => r.json())
      .then((d) => setHf(d.health_factor ?? "—"))
      .catch(() => setHf("取得失敗"));

    fetchExchangeStatus(token)
      .then((d) => setTrades(`${d.daily_trades_used ?? 0}件`))
      .catch(() => setTrades("取得失敗"));
  }, [token]);

  return (
    <AuthGuard adminOnly>
      <div style={{ padding: "2rem" }}>
        <h1 style={{ fontSize: "1.5rem", fontWeight: "bold", marginBottom: "1.5rem" }}>
          運用ダッシュボード
        </h1>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))", gap: "1rem" }}>
          <Card label="システムステータス" value={status} />
          <Card label="Health Factor" value={hf} />
          <Card label="本日の取引" value={trades} />
          <Card label="総AUM" value="$15,000" />
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
