'use client'
// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.

import { useEffect, useState, useCallback } from "react";
import { useTranslations } from "next-intl";
import AuthGuard from "@/components/AuthGuard";
import { useAuth } from "@/lib/auth";
import { fetchExchangeStatus } from "@/lib/api/exchange";
import type { ExchangeStatusResponse } from "@/lib/api/exchange";

function formatDateTime(iso: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleString("ja-JP", { timeZone: "Asia/Tokyo" });
}

function ExchangeContent() {
  const { token } = useAuth();
  const t = useTranslations("AdminExchange");
  const [status, setStatus] = useState<ExchangeStatusResponse | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);

  const fetchData = useCallback(async () => {
    if (!token) return;
    setIsLoading(true);
    try {
      const data = await fetchExchangeStatus(token);
      setStatus(data);
      setLastUpdated(new Date());
      setError(null);
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : String(e);
      setError(t("fetchError", { msg }));
    } finally {
      setIsLoading(false);
    }
  }, [token, t]);

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 30_000);
    return () => clearInterval(interval);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token]);

  const dailyUsedPct =
    status && status.daily_trade_limit > 0
      ? Math.min(100, (status.daily_trades_used / status.daily_trade_limit) * 100)
      : 0;

  return (
    <>
      {/* ヘッダー */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 8 }}>
        <h1 style={{ margin: 0 }}>{t("pageTitle")}</h1>
        {lastUpdated && (
          <span style={{ fontSize: 12, color: "#888" }}>
            {t("lastUpdated", { time: lastUpdated.toLocaleTimeString("ja-JP") })}
          </span>
        )}
      </div>

      {error && (
        <div style={{ background: "#fee2e2", color: "#dc2626", padding: "8px 16px", borderRadius: 8, marginBottom: 16, fontSize: 14 }}>
          {error}
        </div>
      )}

      {/* ステータスセクション */}
      <section style={{ marginTop: 16 }}>
        <h2 style={{ fontSize: 16, marginBottom: 12 }}>{t("connectionSectionTitle")}</h2>
        <div style={{ display: "flex", gap: 16, flexWrap: "wrap" }}>

          {/* 接続状態カード */}
          <div style={cardStyle}>
            <div style={{ fontSize: 13, color: "#666", marginBottom: 8 }}>{t("cardConnectionLabel")}</div>
            {status ? (
              <>
                <span style={{
                  display: "inline-block",
                  padding: "4px 14px",
                  borderRadius: 999,
                  fontSize: 16,
                  fontWeight: 700,
                  background: status.connected ? "#dcfce7" : "#fee2e2",
                  color: status.connected ? "#16a34a" : "#dc2626",
                }}>
                  {status.connected ? t("statusConnected") : t("statusDisconnected")}
                </span>
                <div style={{ marginTop: 12 }}>
                  <span style={{
                    display: "inline-block",
                    padding: "2px 10px",
                    borderRadius: 999,
                    fontSize: 12,
                    fontWeight: 600,
                    background: status.sandbox_mode ? "#fef9c3" : "#dcfce7",
                    color: status.sandbox_mode ? "#ca8a04" : "#16a34a",
                  }}>
                    {status.sandbox_mode ? t("modeSandbox") : t("modeProduction")}
                  </span>
                </div>
              </>
            ) : (
              <div style={{ fontSize: 16, color: "#9ca3af" }}>{t("loading")}</div>
            )}
          </div>

          {/* 残高カード */}
          <div style={cardStyle}>
            <div style={{ fontSize: 13, color: "#666", marginBottom: 8 }}>{t("cardBalanceLabel")}</div>
            <div style={{ fontSize: 36, fontWeight: 700, color: "#111" }}>
              {status
                ? status.balance_usdt != null
                  ? `$${parseFloat(status.balance_usdt).toFixed(2)}`
                  : "—"
                : <span style={{ color: "#9ca3af", fontSize: 24 }}>{t("loading")}</span>
              }
            </div>
          </div>

          {/* 前回取引カード */}
          <div style={cardStyle}>
            <div style={{ fontSize: 13, color: "#666", marginBottom: 8 }}>{t("cardLastTradeLabel")}</div>
            <div style={{ fontSize: 14, fontWeight: 600, color: "#374151" }}>
              {status ? formatDateTime(status.last_trade_at) : <span style={{ color: "#9ca3af" }}>{t("loading")}</span>}
            </div>
          </div>
        </div>
      </section>

      {/* 日次取引制限セクション */}
      <section style={{ marginTop: 32 }}>
        <h2 style={{ fontSize: 16, marginBottom: 12 }}>{t("dailyLimitSectionTitle")}</h2>
        <div style={{ ...cardStyle, maxWidth: 480 }}>
          <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 8, fontSize: 14 }}>
            <span style={{ color: "#374151" }}>{t("dailyLimitUsedOver")}</span>
            <span style={{ fontWeight: 700, color: "#111" }}>
              {status ? `${status.daily_trades_used} / ${status.daily_trade_limit}` : "—"}
            </span>
          </div>
          {/* プログレスバー */}
          <div style={{ background: "#e5e7eb", borderRadius: 999, height: 10, overflow: "hidden" }}>
            <div style={{
              width: `${dailyUsedPct}%`,
              height: "100%",
              background: dailyUsedPct >= 90 ? "#dc2626" : dailyUsedPct >= 70 ? "#ca8a04" : "#16a34a",
              borderRadius: 999,
              transition: "width 0.4s ease",
            }} />
          </div>
          <div style={{ marginTop: 6, fontSize: 12, color: "#666", textAlign: "right" }}>
            {t("dailyLimitUsedPct", { pct: dailyUsedPct.toFixed(1) })}
          </div>
        </div>
      </section>

      {/* 取引所タイプセクション */}
      <section style={{ marginTop: 32 }}>
        <h2 style={{ fontSize: 16, marginBottom: 12 }}>{t("settingsSectionTitle")}</h2>
        <div style={{ ...cardStyle, maxWidth: 480 }}>
          <div style={{ fontSize: 13, color: "#666", marginBottom: 8 }}>{t("currentExchangeTypeLabel")}</div>
          <div style={{ marginBottom: 12 }}>
            <select
              disabled
              style={{
                padding: "8px 12px",
                borderRadius: 8,
                border: "1px solid #e5e7eb",
                fontSize: 14,
                color: "#374151",
                background: "#f9fafb",
                cursor: "not-allowed",
                width: "100%",
              }}
            >
              <option value="bybit">Bybit</option>
              <option value="okx">OKX</option>
              <option value="kraken">Kraken</option>
              <option value="dummy">{t("exchangeDummy")}</option>
            </select>
          </div>
          <div style={{
            background: "#fef9c3",
            border: "1px solid #fde047",
            borderRadius: 8,
            padding: "10px 14px",
            fontSize: 13,
            color: "#92400e",
          }}>
            {t("exchangeTypeChangeHint")}
          </div>
        </div>
      </section>

      {/* 接続テストセクション */}
      <section style={{ marginTop: 32 }}>
        <h2 style={{ fontSize: 16, marginBottom: 12 }}>{t("connectionTestSectionTitle")}</h2>
        <div style={{ display: "flex", alignItems: "center" }}>
          <button
            onClick={fetchData}
            disabled
            style={{
              padding: "10px 24px",
              borderRadius: 8,
              border: "none",
              background: "#9ca3af",
              color: "#fff",
              fontWeight: 600,
              fontSize: 14,
              cursor: "not-allowed",
            }}
          >
            {isLoading ? t("testButtonLoading") : t("testButton")}
          </button>
          <span className="text-xs bg-gray-200 text-gray-600 px-2 py-0.5 rounded-full ml-2">Coming Soon</span>
        </div>
        {status && !error && (
          <div style={{ marginTop: 12, color: "#16a34a", fontSize: 14, fontWeight: 600 }}>
            {status.connected ? t("testSuccessConnected") : t("testSuccessDisconnected")}
          </div>
        )}
      </section>
    </>
  );
}

export default function ExchangePage() {
  const t = useTranslations("AdminExchange");
  return (
    <AuthGuard adminOnly>
      <>
        <title>{t("htmlTitle")}</title>
        <ExchangeContent />
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
