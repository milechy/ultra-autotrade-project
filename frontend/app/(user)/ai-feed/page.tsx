'use client'

import React, { useState, useEffect, useCallback } from "react";
import AuthGuard from "@/components/AuthGuard";
import { useAuth } from "@/lib/auth";
import { getJson } from "@/lib/api/http";

type ConfidencePoint = {
  timestamp: string;
  action: "BUY" | "SELL" | "HOLD";
  confidence: number;
  prompt_version: string;
};

type TrendResponse = {
  data_points: ConfidencePoint[];
  is_mock: boolean;
  total_count: number;
};

const ACTION_COLORS = {
  BUY: { bg: "#dcfce7", text: "#16a34a", bar: "#16a34a" },
  SELL: { bg: "#fee2e2", text: "#dc2626", bar: "#dc2626" },
  HOLD: { bg: "#f3f4f6", text: "#6b7280", bar: "#6b7280" },
};

function computeDailyAverages(points: ConfidencePoint[]): Array<{
  label: string;
  avg: number;
  action: "BUY" | "SELL" | "HOLD";
  count: number;
}> {
  const byDay: Record<string, { sum: number; count: number; actions: Record<string, number> }> = {};
  const cutoff = new Date(Date.now() - 7 * 24 * 60 * 60 * 1000);
  for (const p of points) {
    if (new Date(p.timestamp) < cutoff) continue;
    const label = new Date(p.timestamp).toLocaleDateString("ja-JP", {
      month: "2-digit",
      day: "2-digit",
      timeZone: "Asia/Tokyo",
    });
    if (!byDay[label]) byDay[label] = { sum: 0, count: 0, actions: { BUY: 0, SELL: 0, HOLD: 0 } };
    byDay[label].sum += p.confidence;
    byDay[label].count++;
    byDay[label].actions[p.action]++;
  }
  return Object.entries(byDay).map(([label, { sum, count, actions }]) => ({
    label,
    avg: Math.round(sum / count),
    count,
    action: (Object.entries(actions).sort((a, b) => b[1] - a[1])[0][0]) as "BUY" | "SELL" | "HOLD",
  }));
}

export default function AiFeedPage() {
  return (
    <AuthGuard>
      <AiFeedContent />
    </AuthGuard>
  );
}

function AiFeedContent() {
  const { token } = useAuth();
  const [trend, setTrend] = useState<TrendResponse | null>(null);
  const [isLoading, setIsLoading] = useState(false);

  const fetchTrend = useCallback(async () => {
    if (!token) return;
    setIsLoading(true);
    try {
      const data = await getJson<TrendResponse>("/api/ai/trend/confidence?days=7", {
        headers: { Authorization: `Bearer ${token}` },
      });
      setTrend(data);
    } catch {
      // silent — show empty state
    } finally {
      setIsLoading(false);
    }
  }, [token]);

  useEffect(() => {
    fetchTrend();
  }, [fetchTrend]);

  const dailyAverages = trend ? computeDailyAverages(trend.data_points) : [];
  const overallAvg =
    trend && trend.data_points.length > 0
      ? Math.round(
          trend.data_points.reduce((s, p) => s + p.confidence, 0) / trend.data_points.length,
        )
      : null;

  return (
    <>
      <title>AIシグナルフィード - Ultra AutoTrade</title>

      <div style={{ marginBottom: 20 }}>
        <h1 style={{ margin: 0 }}>AIシグナルフィード</h1>
        <p style={{ margin: "4px 0 0", color: "#666", fontSize: 13 }}>
          AI判定の信頼度トレンド（直近7日間）
        </p>
      </div>

      {trend?.is_mock && (
        <div style={{
          padding: "10px 14px",
          background: "#fffbeb",
          border: "1px solid #fde68a",
          borderRadius: 8,
          color: "#92400e",
          fontSize: 12,
          marginBottom: 16,
        }}>
          サンプルデータを表示しています。
        </div>
      )}

      {isLoading && (
        <div style={{ color: "#9ca3af", fontSize: 13, padding: "24px 0" }}>読み込み中...</div>
      )}

      {!isLoading && overallAvg !== null && (
        <div style={{
          padding: "20px 24px",
          border: "1px solid #e5e7eb",
          borderRadius: 12,
          background: "#fff",
          boxShadow: "0 1px 3px rgba(0,0,0,0.06)",
          marginBottom: 20,
          display: "flex",
          alignItems: "center",
          gap: 20,
        }}>
          <div>
            <div style={{ fontSize: 11, color: "#888", marginBottom: 2 }}>7日間平均信頼度</div>
            <div style={{ fontSize: 36, fontWeight: 700, color: "#1d4ed8", lineHeight: 1 }}>
              {overallAvg}
              <span style={{ fontSize: 18, fontWeight: 400, color: "#6b7280" }}>%</span>
            </div>
          </div>
          <div style={{ flex: 1, maxWidth: 200 }}>
            <div style={{ height: 8, borderRadius: 999, background: "#e5e7eb", overflow: "hidden" }}>
              <div style={{
                height: "100%",
                width: `${overallAvg}%`,
                background: overallAvg >= 70 ? "#16a34a" : overallAvg >= 50 ? "#f59e0b" : "#dc2626",
                borderRadius: 999,
                transition: "width 0.5s ease",
              }} />
            </div>
          </div>
        </div>
      )}

      {!isLoading && dailyAverages.length > 0 && (
        <div style={{
          border: "1px solid #e5e7eb",
          borderRadius: 12,
          background: "#fff",
          boxShadow: "0 1px 3px rgba(0,0,0,0.06)",
          overflow: "hidden",
        }}>
          <div style={{ padding: "12px 16px", borderBottom: "1px solid #f3f4f6" }}>
            <span style={{ fontSize: 13, fontWeight: 600, color: "#374151" }}>
              日別平均信頼度
            </span>
          </div>
          {dailyAverages.map((day) => {
            const colors = ACTION_COLORS[day.action];
            return (
              <div key={day.label} style={{
                padding: "12px 16px",
                borderBottom: "1px solid #f9fafb",
                display: "flex",
                alignItems: "center",
                gap: 12,
              }}>
                <span style={{ fontSize: 12, color: "#888", minWidth: 50 }}>{day.label}</span>
                <span style={{
                  fontSize: 11,
                  fontWeight: 600,
                  padding: "2px 8px",
                  borderRadius: 999,
                  background: colors.bg,
                  color: colors.text,
                  minWidth: 36,
                  textAlign: "center",
                }}>
                  {day.action}
                </span>
                <div style={{ flex: 1, height: 6, borderRadius: 999, background: "#f3f4f6", overflow: "hidden" }}>
                  <div style={{
                    height: "100%",
                    width: `${day.avg}%`,
                    background: colors.bar,
                    borderRadius: 999,
                  }} />
                </div>
                <span style={{ fontSize: 13, fontWeight: 600, color: "#374151", minWidth: 40, textAlign: "right" }}>
                  {day.avg}%
                </span>
                <span style={{ fontSize: 11, color: "#9ca3af", minWidth: 32 }}>
                  {day.count}件
                </span>
              </div>
            );
          })}
        </div>
      )}

      {!isLoading && dailyAverages.length === 0 && (
        <div style={{ color: "#9ca3af", fontSize: 13, padding: "24px 0", textAlign: "center" }}>
          表示するデータがありません。
        </div>
      )}
    </>
  );
}
