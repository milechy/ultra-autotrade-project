'use client'

import { useEffect, useState } from "react";
import Head from "next/head";
import AuthGuard from "@/components/AuthGuard";
import { useAuth } from "@/lib/auth";
import { fetchAutomationStatus } from "@/lib/api/automation";
import { fetchExchangeStatus } from "@/lib/api/exchange";
import type { AutomationStatus } from "@/lib/types";
import type { ExchangeStatusResponse } from "@/lib/api/exchange";

function getHfColor(hf: number): string {
  if (hf >= 1.8) return "#16a34a"; // green-600
  if (hf >= 1.6) return "#ca8a04"; // yellow-600
  return "#dc2626"; // red-600
}

function getHfBadge(hf: number): { label: string; bg: string; color: string } {
  if (hf >= 1.8) return { label: "安全", bg: "#dcfce7", color: "#16a34a" };
  if (hf >= 1.6) return { label: "注意", bg: "#fef9c3", color: "#ca8a04" };
  return { label: "危険", bg: "#fee2e2", color: "#dc2626" };
}

function formatDateTime(iso: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleString("ja-JP", { timeZone: "Asia/Tokyo" });
}

function DashboardContent() {
  const { token } = useAuth();
  const [automationStatus, setAutomationStatus] = useState<AutomationStatus | null>(null);
  const [exchangeStatus, setExchangeStatus] = useState<ExchangeStatusResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);

  const fetchData = async () => {
    if (!token) return;
    try {
      const [auto, exchange] = await Promise.all([
        fetchAutomationStatus(token ?? undefined),
        fetchExchangeStatus(token),
      ]);
      setAutomationStatus(auto);
      setExchangeStatus(exchange);
      setLastUpdated(new Date());
      setError(null);
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : String(e);
      setError(`データ取得エラー: ${msg}`);
    }
  };

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 30_000);
    return () => clearInterval(interval);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token]);

  const hfRaw = automationStatus?.last_health_factor;
  const hfNum = hfRaw != null ? parseFloat(String(hfRaw)) : null;

  const balanceUsdt = exchangeStatus?.balance_usdt
    ? parseFloat(exchangeStatus.balance_usdt).toFixed(2)
    : null;

  return (
    <>
      {/* ヘッダー */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 8 }}>
        <h1 style={{ margin: 0 }}>運用ダッシュボード</h1>
        {lastUpdated && (
          <span style={{ fontSize: 12, color: "#888" }}>
            最終更新: {lastUpdated.toLocaleTimeString("ja-JP")}（30秒自動更新）
          </span>
        )}
      </div>

      {error && (
        <div style={{ background: "#fee2e2", color: "#dc2626", padding: "8px 16px", borderRadius: 8, marginBottom: 16, fontSize: 14 }}>
          {error}
        </div>
      )}

      {/* カードグリッド */}
      <div style={{ display: "flex", gap: 16, flexWrap: "wrap", marginTop: 16 }}>

        {/* 2-1. Aave Health Factor カード */}
        <div style={cardStyle}>
          <div style={{ fontSize: 13, color: "#666", marginBottom: 8 }}>Aave Health Factor</div>
          {hfNum != null && !isNaN(hfNum) ? (
            <>
              <div style={{ fontSize: 40, fontWeight: 700, color: getHfColor(hfNum), lineHeight: 1.1 }}>
                {hfNum.toFixed(2)}
              </div>
              <span style={{
                display: "inline-block",
                marginTop: 8,
                padding: "2px 10px",
                borderRadius: 999,
                fontSize: 12,
                fontWeight: 600,
                background: getHfBadge(hfNum).bg,
                color: getHfBadge(hfNum).color,
              }}>
                {getHfBadge(hfNum).label}
              </span>
            </>
          ) : (
            <div style={{ fontSize: 24, color: "#9ca3af" }}>取得中...</div>
          )}
        </div>

        {/* 2-2. PnL（残高）カード */}
        <div style={cardStyle}>
          <div style={{ fontSize: 13, color: "#666", marginBottom: 8 }}>残高 (USDT)</div>
          <div style={{ fontSize: 36, fontWeight: 700, color: "#111" }}>
            {balanceUsdt != null ? `$${balanceUsdt}` : <span style={{ color: "#9ca3af", fontSize: 24 }}>取得中...</span>}
          </div>
          <div style={{ marginTop: 8, display: "flex", gap: 8, flexWrap: "wrap" }}>
            {exchangeStatus != null && (
              <span style={{
                display: "inline-block",
                padding: "2px 10px",
                borderRadius: 999,
                fontSize: 12,
                fontWeight: 600,
                background: exchangeStatus.connected ? "#dcfce7" : "#fee2e2",
                color: exchangeStatus.connected ? "#16a34a" : "#dc2626",
              }}>
                {exchangeStatus.connected ? "接続中" : "切断"}
              </span>
            )}
            {exchangeStatus?.sandbox_mode && (
              <span style={{
                display: "inline-block",
                padding: "2px 10px",
                borderRadius: 999,
                fontSize: 12,
                fontWeight: 600,
                background: "#fef3c7",
                color: "#92400e",
              }}>
                SANDBOX
              </span>
            )}
          </div>
        </div>

        {/* 2-3. システムステータスカード */}
        <div style={cardStyle}>
          <div style={{ fontSize: 13, color: "#666", marginBottom: 8 }}>システムステータス</div>
          {automationStatus != null ? (
            <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
              <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <span style={{ fontSize: 13, color: "#555" }}>緊急停止フラグ:</span>
                <span style={{
                  display: "inline-block",
                  padding: "2px 10px",
                  borderRadius: 999,
                  fontSize: 12,
                  fontWeight: 600,
                  background: automationStatus.is_trading_paused ? "#fee2e2" : "#dcfce7",
                  color: automationStatus.is_trading_paused ? "#dc2626" : "#16a34a",
                }}>
                  {automationStatus.is_trading_paused ? "停止中" : "稼働中"}
                </span>
              </div>
              {exchangeStatus != null && (
                <div style={{ fontSize: 13, color: "#555" }}>
                  本日の取引:{" "}
                  <strong>{exchangeStatus.daily_trades_used}</strong>
                  {" / "}
                  {exchangeStatus.daily_trade_limit} 件
                </div>
              )}
              {exchangeStatus?.last_trade_at && (
                <div style={{ fontSize: 13, color: "#555" }}>
                  最終取引: <strong>{formatDateTime(exchangeStatus.last_trade_at)}</strong>
                </div>
              )}
              {automationStatus.emergency_reason && (
                <div style={{ fontSize: 13, color: "#dc2626", fontWeight: 600 }}>
                  理由: {automationStatus.emergency_reason}
                </div>
              )}
            </div>
          ) : (
            <div style={{ fontSize: 14, color: "#9ca3af" }}>取得中...</div>
          )}
        </div>
      </div>

      {/* 2-4. 取引情報テーブル */}
      <section style={{ marginTop: 32 }}>
        <h2 style={{ fontSize: 16, marginBottom: 12 }}>取引情報</h2>
        {exchangeStatus != null ? (
          <table style={tableStyle}>
            <thead>
              <tr>
                <th style={thStyle}>項目</th>
                <th style={thStyle}>値</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td style={tdStyle}>本日の取引数</td>
                <td style={tdStyle}>{exchangeStatus.daily_trades_used} 件</td>
              </tr>
              <tr>
                <td style={tdStyle}>1日の取引上限</td>
                <td style={tdStyle}>{exchangeStatus.daily_trade_limit} 件</td>
              </tr>
              <tr>
                <td style={tdStyle}>最終取引日時</td>
                <td style={tdStyle}>{formatDateTime(exchangeStatus.last_trade_at)}</td>
              </tr>
              <tr>
                <td style={tdStyle}>サンドボックスモード</td>
                <td style={tdStyle}>{exchangeStatus.sandbox_mode ? "有効" : "無効"}</td>
              </tr>
              <tr>
                <td style={tdStyle}>接続状態</td>
                <td style={tdStyle}>{exchangeStatus.connected ? "接続中" : "切断"}</td>
              </tr>
            </tbody>
          </table>
        ) : (
          <div style={{ color: "#9ca3af", fontSize: 14 }}>取得中...</div>
        )}
        <p style={{ marginTop: 12, fontSize: 13, color: "#888" }}>
          ※ 詳細な取引履歴は今後のアップデートで実装予定
        </p>
      </section>
    </>
  );
}

export default function DashboardIndex() {
  return (
    <AuthGuard>
      <>
        <title>運用ダッシュボード - Ultra AutoTrade</title>
        <DashboardContent />
      </>
    </AuthGuard>
  );
}

const cardStyle: React.CSSProperties = {
  padding: 20,
  border: "1px solid #e5e7eb",
  borderRadius: 12,
  minWidth: 240,
  background: "#fff",
  boxShadow: "0 1px 3px rgba(0,0,0,0.08)",
};

const tableStyle: React.CSSProperties = {
  width: "100%",
  maxWidth: 600,
  borderCollapse: "collapse",
  fontSize: 14,
};

const thStyle: React.CSSProperties = {
  textAlign: "left",
  padding: "8px 12px",
  background: "#f9fafb",
  borderBottom: "1px solid #e5e7eb",
  color: "#374151",
  fontWeight: 600,
};

const tdStyle: React.CSSProperties = {
  padding: "8px 12px",
  borderBottom: "1px solid #f3f4f6",
  color: "#374151",
};
