'use client'
// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.

import React, { useState, useEffect, useCallback } from "react";
import AuthGuard from "@/components/AuthGuard";
import { useAuth } from "@/lib/auth";
import { getJson } from "@/lib/api/http";
import ConfidenceTrendChart, { ConfidencePoint } from "@/components/charts/ConfidenceTrendChart";
import ActionDistributionChart, { ActionRecord } from "@/components/charts/ActionDistributionChart";
import AccuracyChart, { AccuracyPoint } from "@/components/charts/AccuracyChart";

// ─── Types ───────────────────────────────────────────────────────────────────

type AiDecisionRecord = {
  id: number;
  timestamp: string;
  pair: string;
  phase_a: "BUY" | "SELL" | "HOLD";
  phase_b: "BUY" | "SELL" | "HOLD" | null;
  final_decision: "BUY" | "SELL" | "HOLD";
  confidence: number | null;
  executed: boolean;
  reason?: string;
};

// ─── Mock data (shown when API returns 404) ───────────────────────────────────

const MOCK_RECORDS: AiDecisionRecord[] = [
  {
    id: 1,
    timestamp: new Date(Date.now() - 1000 * 60 * 5).toISOString(),
    pair: "BTC/USDT",
    phase_a: "BUY",
    phase_b: "BUY",
    final_decision: "BUY",
    confidence: 0.87,
    executed: true,
    reason: "強気トレンド継続。RSI過熱なし。",
  },
  {
    id: 2,
    timestamp: new Date(Date.now() - 1000 * 60 * 35).toISOString(),
    pair: "ETH/USDT",
    phase_a: "HOLD",
    phase_b: null,
    final_decision: "HOLD",
    confidence: 0.72,
    executed: false,
    reason: "Health Factor 1.62 — 閾値接近のため保留。",
  },
  {
    id: 3,
    timestamp: new Date(Date.now() - 1000 * 60 * 65).toISOString(),
    pair: "BTC/USDT",
    phase_a: "SELL",
    phase_b: "HOLD",
    final_decision: "HOLD",
    confidence: 0.61,
    executed: false,
    reason: "フェーズ間で不一致。安全側のHOLDを採用。",
  },
];

// ─── Helpers ─────────────────────────────────────────────────────────────────

function formatDateTime(iso: string): string {
  try {
    return new Date(iso).toLocaleString("ja-JP", {
      timeZone: "Asia/Tokyo",
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
    });
  } catch {
    return iso;
  }
}

function decisionBadge(
  decision: "BUY" | "SELL" | "HOLD" | null
): { label: string; bg: string; color: string } {
  if (decision === "BUY")  return { label: "BUY",  bg: "#dcfce7", color: "#16a34a" };
  if (decision === "SELL") return { label: "SELL", bg: "#fee2e2", color: "#dc2626" };
  if (decision === "HOLD") return { label: "HOLD", bg: "#f3f4f6", color: "#6b7280" };
  return { label: "—", bg: "#f3f4f6", color: "#9ca3af" };
}

function DecisionBadge({ decision }: { decision: "BUY" | "SELL" | "HOLD" | null }) {
  if (!decision) {
    return <span style={{ color: "#9ca3af", fontSize: 12 }}>—</span>;
  }
  const { label, bg, color } = decisionBadge(decision);
  return (
    <span style={{
      display: "inline-block",
      padding: "2px 10px",
      borderRadius: 999,
      fontSize: 12,
      fontWeight: 600,
      background: bg,
      color,
      letterSpacing: "0.02em",
    }}>
      {label}
    </span>
  );
}

// ─── Main export ──────────────────────────────────────────────────────────────

export default function AiMonitorPage() {
  return (
    <AuthGuard adminOnly>
      <AiMonitorContent />
    </AuthGuard>
  );
}

// ─── Page content ─────────────────────────────────────────────────────────────

const POLL_INTERVAL_SEC = 30;

function AiMonitorContent() {
  const { token } = useAuth();
  const [records, setRecords] = useState<AiDecisionRecord[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [isFeatureReady, setIsFeatureReady] = useState(true);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);
  const [countdown, setCountdown] = useState(POLL_INTERVAL_SEC);
  const [trendData, setTrendData] = useState<ConfidencePoint[]>([]);
  const [isTrendMock, setIsTrendMock] = useState(false);

  const fetchHistory = useCallback(async () => {
    if (!token) return;
    setIsLoading(true);
    setError(null);
    try {
      const data = await getJson<AiDecisionRecord[]>("/api/ai/history", {
        headers: { Authorization: `Bearer ${token}` },
      });
      setRecords(data);
      setIsFeatureReady(true);
      setLastUpdated(new Date());
      setCountdown(POLL_INTERVAL_SEC);
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : String(e);
      // 404 → feature not yet available, show mock data
      if (msg.includes("404") || msg.toLowerCase().includes("not found")) {
        setIsFeatureReady(false);
        setRecords(MOCK_RECORDS);
        setLastUpdated(new Date());
        setCountdown(POLL_INTERVAL_SEC);
      } else {
        setError(`データ取得エラー: ${msg}`);
      }
    } finally {
      setIsLoading(false);
    }
  }, [token]);

  const fetchTrend = useCallback(async () => {
    if (!token) return;
    try {
      const data = await getJson<{ data_points: ConfidencePoint[]; is_mock: boolean }>(
        "/api/ai/trend/confidence?days=7",
        { headers: { Authorization: `Bearer ${token}` } },
      );
      setTrendData(data.data_points);
      setIsTrendMock(data.is_mock);
    } catch {
      // silent fail — charts show empty state
    }
  }, [token]);

  useEffect(() => {
    fetchTrend();
  }, [fetchTrend]);

  // Initial fetch + polling
  useEffect(() => {
    fetchHistory();
    const interval = setInterval(fetchHistory, POLL_INTERVAL_SEC * 1000);
    return () => clearInterval(interval);
  }, [fetchHistory]);

  // Countdown ticker
  useEffect(() => {
    const ticker = setInterval(() => {
      setCountdown((prev) => (prev <= 1 ? POLL_INTERVAL_SEC : prev - 1));
    }, 1000);
    return () => clearInterval(ticker);
  }, []);

  const handleManualRefresh = () => {
    setCountdown(POLL_INTERVAL_SEC);
    fetchHistory();
  };

  return (
    <>
      <title>AI判定モニター - Ultra AutoTrade</title>

      {/* Header */}
      <div style={{
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        marginBottom: 8,
        flexWrap: "wrap",
        gap: 12,
      }}>
        <div>
          <h1 style={{ margin: 0 }}>AI判定モニター</h1>
          <p style={{ margin: "4px 0 0", color: "#666", fontSize: 13 }}>
            マルチLLMによるリアルタイム売買判定の履歴
          </p>
        </div>

        <div style={{ display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
          {lastUpdated && (
            <span style={{ fontSize: 12, color: "#888" }}>
              最終更新: {lastUpdated.toLocaleTimeString("ja-JP")}
              {" "}（{countdown}秒後に自動更新）
            </span>
          )}
          <button
            onClick={handleManualRefresh}
            disabled={isLoading}
            style={outlineBtnStyle}
          >
            {isLoading ? "読み込み中..." : "今すぐ更新"}
          </button>
        </div>
      </div>

      {/* Feature not ready banner */}
      {!isFeatureReady && (
        <div style={{
          padding: "12px 16px",
          background: "#fffbeb",
          border: "1px solid #fde68a",
          borderRadius: 10,
          color: "#92400e",
          fontSize: 13,
          marginBottom: 16,
          display: "flex",
          alignItems: "center",
          gap: 8,
        }}>
          <span style={{ fontSize: 16 }}>🚧</span>
          <span>
            <strong>準備中:</strong>{" "}
            AI判定履歴APIは現在実装中です。以下はサンプルデータです。
          </span>
        </div>
      )}

      {/* Error banner */}
      {error && (
        <div style={errorBoxStyle}>{error}</div>
      )}

      {/* Stats row */}
      {records.length > 0 && (
        <div style={{ display: "flex", gap: 12, flexWrap: "wrap", marginBottom: 20 }}>
          <StatCard
            label="総判定数"
            value={String(records.length)}
            subColor="#374151"
          />
          <StatCard
            label="BUY"
            value={String(records.filter((r) => r.final_decision === "BUY").length)}
            subColor="#16a34a"
          />
          <StatCard
            label="SELL"
            value={String(records.filter((r) => r.final_decision === "SELL").length)}
            subColor="#dc2626"
          />
          <StatCard
            label="HOLD"
            value={String(records.filter((r) => r.final_decision === "HOLD").length)}
            subColor="#6b7280"
          />
          <StatCard
            label="実行済み"
            value={String(records.filter((r) => r.executed).length)}
            subColor="#2563eb"
          />
        </div>
      )}

      {/* Table */}
      <section>
        <h2 style={{ fontSize: 15, marginBottom: 10, marginTop: 0 }}>
          判定履歴
          <span style={{ fontWeight: 400, color: "#888", fontSize: 12, marginLeft: 8 }}>
            全 {records.length} 件
          </span>
        </h2>

        {isLoading && records.length === 0 && (
          <div style={{ color: "#9ca3af", fontSize: 14, padding: "24px 0" }}>読み込み中...</div>
        )}

        {!isLoading && !error && records.length === 0 && (
          <div style={{ color: "#9ca3af", fontSize: 14, padding: "24px 0" }}>
            判定履歴がありません。
          </div>
        )}

        {records.length > 0 && (
          <div style={{ overflowX: "auto" }}>
            <table style={tableStyle}>
              <thead>
                <tr>
                  {["時刻", "ペア", "フェーズA判定", "フェーズB判定", "最終判定", "信頼度", "実行済み"].map((h) => (
                    <th key={h} style={thStyle}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {records.map((record, i) => (
                  <tr
                    key={record.id}
                    style={{ background: i % 2 === 0 ? "#fff" : "#fafafa" }}
                    title={record.reason ?? ""}
                  >
                    <td style={{ ...tdStyle, fontSize: 12, color: "#555", whiteSpace: "nowrap" }}>
                      {formatDateTime(record.timestamp)}
                    </td>
                    <td style={{ ...tdStyle, fontWeight: 600, whiteSpace: "nowrap" }}>
                      {record.pair}
                    </td>
                    <td style={tdStyle}>
                      <DecisionBadge decision={record.phase_a} />
                    </td>
                    <td style={tdStyle}>
                      <DecisionBadge decision={record.phase_b} />
                    </td>
                    <td style={tdStyle}>
                      <DecisionBadge decision={record.final_decision} />
                    </td>
                    <td style={{ ...tdStyle, textAlign: "right", whiteSpace: "nowrap" }}>
                      {record.confidence != null
                        ? (
                          <span style={{ fontVariantNumeric: "tabular-nums" }}>
                            {(record.confidence * 100).toFixed(0)}
                            <span style={{ fontSize: 11, color: "#888" }}>%</span>
                          </span>
                        )
                        : <span style={{ color: "#9ca3af", fontSize: 12 }}>—</span>
                      }
                    </td>
                    <td style={{ ...tdStyle, textAlign: "center" }}>
                      <span style={{
                        display: "inline-block",
                        padding: "2px 8px",
                        borderRadius: 999,
                        fontSize: 12,
                        fontWeight: 600,
                        background: record.executed ? "#dbeafe" : "#f3f4f6",
                        color: record.executed ? "#1d4ed8" : "#9ca3af",
                      }}>
                        {record.executed ? "済" : "未"}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        <p style={{ marginTop: 10, fontSize: 12, color: "#aaa" }}>
          ※ 行にカーソルを当てると判断理由が表示されます。
        </p>
      </section>

      {/* Charts section */}
      <section style={{ marginTop: 32 }}>
        <h2 style={{ fontSize: 15, marginBottom: 16, marginTop: 0 }}>
          トレンド分析
          {isTrendMock && (
            <span style={{ fontWeight: 400, color: "#f59e0b", fontSize: 11, marginLeft: 8 }}>
              サンプルデータ
            </span>
          )}
        </h2>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(320px, 1fr))", gap: 20 }}>
          <div style={chartCardStyle}>
            <h3 style={chartTitleStyle}>信頼度トレンド（直近7日）</h3>
            <ConfidenceTrendChart data={trendData} />
          </div>
          <div style={chartCardStyle}>
            <h3 style={chartTitleStyle}>判定アクション分布</h3>
            <ActionDistributionChart
              data={(records as AiDecisionRecord[]).map((r) => ({ timestamp: r.timestamp, action: r.final_decision } as ActionRecord))}
            />
          </div>
          <div style={chartCardStyle}>
            <h3 style={chartTitleStyle}>Two-Phase一致率</h3>
            <AccuracyChart
              data={(records as AiDecisionRecord[]).map((r) => ({
                timestamp: r.timestamp,
                phase_a: r.phase_a,
                phase_b: r.phase_b,
                agreed: r.phase_b != null && r.phase_a === r.phase_b,
              } as AccuracyPoint))}
            />
          </div>
        </div>
      </section>
    </>
  );
}

// ─── Sub-components ───────────────────────────────────────────────────────────

function StatCard({
  label,
  value,
  subColor,
}: {
  label: string;
  value: string;
  subColor: string;
}) {
  return (
    <div style={{
      padding: "12px 20px",
      border: "1px solid #e5e7eb",
      borderRadius: 10,
      background: "#fff",
      boxShadow: "0 1px 3px rgba(0,0,0,0.06)",
      minWidth: 90,
      textAlign: "center" as const,
    }}>
      <div style={{ fontSize: 22, fontWeight: 700, color: subColor, lineHeight: 1.2 }}>
        {value}
      </div>
      <div style={{ fontSize: 11, color: "#888", marginTop: 2 }}>{label}</div>
    </div>
  );
}

// ─── Styles ───────────────────────────────────────────────────────────────────

const outlineBtnStyle: React.CSSProperties = {
  padding: "6px 14px",
  background: "#fff",
  color: "#374151",
  border: "1px solid #d1d5db",
  borderRadius: 8,
  fontSize: 13,
  cursor: "pointer",
  textDecoration: "none",
  display: "inline-block",
};

const errorBoxStyle: React.CSSProperties = {
  padding: "10px 14px",
  background: "#fff1f2",
  border: "1px solid #fecaca",
  borderRadius: 8,
  color: "#b91c1c",
  fontSize: 13,
  marginBottom: 16,
};

const tableStyle: React.CSSProperties = {
  width: "100%",
  borderCollapse: "collapse",
  fontSize: 13,
  border: "1px solid #e5e7eb",
  borderRadius: 8,
  overflow: "hidden",
};

const thStyle: React.CSSProperties = {
  background: "#f9fafb",
  padding: "10px 12px",
  textAlign: "left",
  fontWeight: 600,
  borderBottom: "1px solid #e5e7eb",
  color: "#374151",
  whiteSpace: "nowrap",
};

const tdStyle: React.CSSProperties = {
  padding: "10px 12px",
  borderBottom: "1px solid #f3f4f6",
  verticalAlign: "middle",
};

const chartCardStyle: React.CSSProperties = {
  padding: "16px 20px",
  border: "1px solid #e5e7eb",
  borderRadius: 10,
  background: "#fff",
  boxShadow: "0 1px 3px rgba(0,0,0,0.06)",
};

const chartTitleStyle: React.CSSProperties = {
  fontSize: 13,
  fontWeight: 600,
  color: "#374151",
  marginTop: 0,
  marginBottom: 12,
};