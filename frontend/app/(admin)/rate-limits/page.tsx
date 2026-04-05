'use client'
// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.

import React, { useState, useEffect, useCallback } from "react";
import dynamic from "next/dynamic";
import AuthGuard from "@/components/AuthGuard";
import { useAuth } from "@/lib/auth";
import { getJson } from "@/lib/api/http";

const RateLimitsBarChart = dynamic(
  () => import("./RateLimitsBarChart"),
  { ssr: false },
);

// ─── Types ───────────────────────────────────────────────────────────────────

type ApiRateLimitEntry = {
  api_name: string;
  display_name: string;
  current: number;
  limit: number;
  window_seconds: number;
  usage_pct: number;
  reset_in_seconds: number;
};

type RateLimitStatus = {
  generated_at: string;
  apis: ApiRateLimitEntry[];
};

// ─── Helpers ─────────────────────────────────────────────────────────────────

function formatResetTime(seconds: number): string {
  if (seconds <= 0) return "—";
  if (seconds < 60) return `${Math.ceil(seconds)}秒`;
  if (seconds < 3600) return `${Math.ceil(seconds / 60)}分`;
  return `${Math.ceil(seconds / 3600)}時間`;
}

function formatWindowName(seconds: number): string {
  if (seconds === 60) return "1分";
  if (seconds === 900) return "15分";
  if (seconds === 3600) return "1時間";
  if (seconds === 86400) return "24時間";
  return `${seconds}秒`;
}

function usageColor(pct: number): string {
  if (pct >= 90) return "#dc2626";
  if (pct >= 80) return "#ca8a04";
  return "#16a34a";
}

function usageBg(pct: number): string {
  if (pct >= 90) return "#fee2e2";
  if (pct >= 80) return "#fef9c3";
  return "#dcfce7";
}

// ─── Main export ──────────────────────────────────────────────────────────────

export default function RateLimitsPage() {
  return (
    <AuthGuard adminOnly>
      <RateLimitsContent />
    </AuthGuard>
  );
}

const POLL_INTERVAL_SEC = 15;

function RateLimitsContent() {
  const { token } = useAuth();
  const [status, setStatus] = useState<RateLimitStatus | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);
  const [countdown, setCountdown] = useState(POLL_INTERVAL_SEC);

  const fetchData = useCallback(async () => {
    if (!token) return;
    setIsLoading(true);
    setError(null);
    try {
      const res = await getJson<RateLimitStatus>(
        "/api/automation/rate-limits",
        { headers: { Authorization: `Bearer ${token}` } },
      );
      setStatus(res);
      setLastUpdated(new Date());
      setCountdown(POLL_INTERVAL_SEC);
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : String(e);
      if (msg.includes("404") || msg.toLowerCase().includes("not found")) {
        // Feature not yet wired — show empty state
        setError(null);
      } else {
        setError(`データ取得エラー: ${msg}`);
      }
    } finally {
      setIsLoading(false);
    }
  }, [token]);

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, POLL_INTERVAL_SEC * 1000);
    return () => clearInterval(interval);
  }, [fetchData]);

  useEffect(() => {
    const ticker = setInterval(() => {
      setCountdown((prev) => (prev <= 1 ? POLL_INTERVAL_SEC : prev - 1));
    }, 1000);
    return () => clearInterval(ticker);
  }, []);

  const hasAlert = (status?.apis ?? []).some((a) => a.usage_pct >= 80);
  const hasWarning = (status?.apis ?? []).some((a) => a.usage_pct >= 90);

  // Chart data
  const chartData = (status?.apis ?? []).map((api) => ({
    name: api.display_name.replace(" (", "\n("),
    usage_pct: api.usage_pct,
    current: api.current,
    limit: api.limit,
  }));

  return (
    <>
      <title>APIレート制限 - Ultra AutoTrade</title>

      {/* Header */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 8, flexWrap: "wrap" as const, gap: 12 }}>
        <div>
          <h1 style={{ margin: 0 }}>APIレート制限ダッシュボード</h1>
          <p style={{ margin: "4px 0 0", color: "#666", fontSize: 13 }}>
            各APIのレート制限使用状況（スライディングウィンドウ）
          </p>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap" as const }}>
          {lastUpdated && (
            <span style={{ fontSize: 12, color: "#888" }}>
              最終更新: {lastUpdated.toLocaleTimeString("ja-JP")} （{countdown}秒後に自動更新）
            </span>
          )}
          <button onClick={fetchData} disabled={isLoading} style={outlineBtnStyle}>
            {isLoading ? "読み込み中..." : "今すぐ更新"}
          </button>
        </div>
      </div>

      {/* Alert banners */}
      {hasWarning && (
        <div style={{ padding: "12px 16px", background: "#fff1f2", border: "1px solid #fecaca", borderRadius: 10, color: "#b91c1c", fontSize: 13, marginBottom: 12 }}>
          <strong>警告:</strong> 1つ以上のAPIが使用率90%を超えています。
        </div>
      )}
      {!hasWarning && hasAlert && (
        <div style={{ padding: "12px 16px", background: "#fef9c3", border: "1px solid #fde68a", borderRadius: 10, color: "#92400e", fontSize: 13, marginBottom: 12 }}>
          <strong>注意:</strong> 1つ以上のAPIが使用率80%を超えています。
        </div>
      )}

      {error && <div style={errorBoxStyle}>{error}</div>}

      {!status && !isLoading && !error && (
        <div style={{ padding: "24px", textAlign: "center" as const, color: "#9ca3af", fontSize: 13 }}>
          データを取得中...
        </div>
      )}

      {/* Progress bars */}
      {status && (
        <div style={{ display: "flex", flexDirection: "column" as const, gap: 16, marginBottom: 24 }}>
          {status.apis.map((api) => {
            const color = usageColor(api.usage_pct);
            const bg = usageBg(api.usage_pct);
            return (
              <div key={api.api_name} style={{ ...cardStyle }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
                  <div>
                    <span style={{ fontSize: 14, fontWeight: 600, color: "#374151" }}>{api.display_name}</span>
                    <span style={{ fontSize: 12, color: "#9ca3af", marginLeft: 8 }}>
                      ウィンドウ: {formatWindowName(api.window_seconds)}
                    </span>
                  </div>
                  <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
                    <span style={{
                      display: "inline-block", padding: "2px 10px", borderRadius: 999,
                      background: bg, color, fontSize: 13, fontWeight: 700,
                    }}>
                      {api.usage_pct.toFixed(1)}%
                    </span>
                    <span style={{ fontSize: 12, color: "#6b7280" }}>
                      リセット: {formatResetTime(api.reset_in_seconds)}
                    </span>
                  </div>
                </div>
                {/* Progress bar */}
                <div style={{ background: "#f3f4f6", borderRadius: 999, height: 10, overflow: "hidden" }}>
                  <div style={{
                    width: `${Math.min(100, api.usage_pct)}%`,
                    height: "100%",
                    background: color,
                    borderRadius: 999,
                    transition: "width 0.5s ease",
                  }} />
                </div>
                <div style={{ display: "flex", justifyContent: "space-between", marginTop: 4 }}>
                  <span style={{ fontSize: 11, color: "#9ca3af" }}>
                    {api.current.toLocaleString()} / {api.limit.toLocaleString()}
                  </span>
                  <span style={{ fontSize: 11, color: api.usage_pct >= 90 ? "#dc2626" : api.usage_pct >= 80 ? "#ca8a04" : "#9ca3af" }}>
                    {api.usage_pct >= 90 ? "CRITICAL" : api.usage_pct >= 80 ? "WARNING" : "OK"}
                  </span>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* Bar chart */}
      {status && chartData.length > 0 && (
        <div style={cardStyle}>
          <h2 style={{ fontSize: 14, fontWeight: 600, color: "#374151", marginTop: 0, marginBottom: 12 }}>
            使用率一覧（%）
          </h2>
          <RateLimitsBarChart data={chartData} />
        </div>
      )}
    </>
  );
}

// ─── Styles ───────────────────────────────────────────────────────────────────

const outlineBtnStyle: React.CSSProperties = {
  padding: "6px 14px", background: "#fff", color: "#374151",
  border: "1px solid #d1d5db", borderRadius: 8, fontSize: 13, cursor: "pointer",
};

const errorBoxStyle: React.CSSProperties = {
  padding: "10px 14px", background: "#fff1f2", border: "1px solid #fecaca",
  borderRadius: 8, color: "#b91c1c", fontSize: 13, marginBottom: 16,
};

const cardStyle: React.CSSProperties = {
  padding: "16px 20px", border: "1px solid #e5e7eb", borderRadius: 10,
  background: "#fff", boxShadow: "0 1px 3px rgba(0,0,0,0.06)",
};