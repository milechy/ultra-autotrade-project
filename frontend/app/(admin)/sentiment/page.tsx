'use client'
// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.

import React, { useState, useEffect, useCallback } from "react";
import AuthGuard from "@/components/AuthGuard";
import { useAuth } from "@/lib/auth";
import { getJson } from "@/lib/api/http";
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer,
  ScatterChart, Scatter, ReferenceLine,
} from "recharts";

// ─── Types ───────────────────────────────────────────────────────────────────

type SentimentLabel = "positive" | "negative" | "neutral";

type XPost = {
  post_id: string;
  text: string;
  sentiment: SentimentLabel;
  score: number;
  created_at: string;
  likes: number;
};

type SentimentDataPoint = {
  timestamp: string;
  score: number;
  label: SentimentLabel;
  post_count: number;
  ai_action: "BUY" | "SELL" | "HOLD" | null;
};

type SentimentHistoryResponse = {
  data_points: SentimentDataPoint[];
  latest_posts: XPost[];
  current_score: number;
  current_label: SentimentLabel;
  is_mock: boolean;
  hours: number;
};

// ─── Helpers ─────────────────────────────────────────────────────────────────

function formatDateTime(iso: string): string {
  try {
    return new Date(iso).toLocaleString("ja-JP", {
      timeZone: "Asia/Tokyo",
      month: "2-digit", day: "2-digit",
      hour: "2-digit", minute: "2-digit",
    });
  } catch { return iso; }
}

function sentimentColor(label: SentimentLabel): string {
  if (label === "positive") return "#16a34a";
  if (label === "negative") return "#dc2626";
  return "#6b7280";
}

function sentimentBg(label: SentimentLabel): string {
  if (label === "positive") return "#dcfce7";
  if (label === "negative") return "#fee2e2";
  return "#f3f4f6";
}

function sentimentLabel(label: SentimentLabel): string {
  if (label === "positive") return "ポジティブ";
  if (label === "negative") return "ネガティブ";
  return "ニュートラル";
}

function scoreToGaugeAngle(score: number): number {
  // -1.0 → -90deg, 0 → 0deg, +1.0 → +90deg
  return score * 90;
}

// ─── Gauge Component ─────────────────────────────────────────────────────────

function SentimentGauge({ score, label }: { score: number; label: SentimentLabel }) {
  const angle = scoreToGaugeAngle(score);
  const color = sentimentColor(label);
  const pct = Math.round((score + 1) / 2 * 100);

  return (
    <div style={{ textAlign: "center" as const, padding: "16px 0" }}>
      <div style={{ position: "relative" as const, display: "inline-block" }}>
        <svg width={180} height={100} viewBox="0 0 180 100">
          {/* Background arc */}
          <path d="M 20 90 A 70 70 0 0 1 160 90" fill="none" stroke="#e5e7eb" strokeWidth={14} strokeLinecap="round" />
          {/* Colored arc - use dasharray trick */}
          <path d="M 20 90 A 70 70 0 0 1 160 90" fill="none" stroke={color}
            strokeWidth={14} strokeLinecap="round"
            strokeDasharray={`${pct * 2.2} 220`} />
          {/* Needle */}
          <line
            x1={90} y1={90}
            x2={90 + 60 * Math.cos((angle - 90) * Math.PI / 180)}
            y2={90 + 60 * Math.sin((angle - 90) * Math.PI / 180)}
            stroke="#374151" strokeWidth={3} strokeLinecap="round"
          />
          <circle cx={90} cy={90} r={6} fill="#374151" />
        </svg>
      </div>
      <div style={{ fontSize: 32, fontWeight: 700, color, lineHeight: 1.1 }}>
        {score >= 0 ? "+" : ""}{score.toFixed(3)}
      </div>
      <div style={{
        display: "inline-block",
        padding: "4px 16px",
        borderRadius: 999,
        background: sentimentBg(label),
        color,
        fontSize: 14,
        fontWeight: 600,
        marginTop: 6,
      }}>
        {sentimentLabel(label)}
      </div>
    </div>
  );
}

// ─── Main export ──────────────────────────────────────────────────────────────

export default function SentimentPage() {
  return (
    <AuthGuard adminOnly>
      <SentimentContent />
    </AuthGuard>
  );
}

const POLL_INTERVAL_SEC = 60;

function SentimentContent() {
  const { token } = useAuth();
  const [data, setData] = useState<SentimentHistoryResponse | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [hours, setHours] = useState(24);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);
  const [countdown, setCountdown] = useState(POLL_INTERVAL_SEC);

  const fetchData = useCallback(async () => {
    if (!token) return;
    setIsLoading(true);
    setError(null);
    try {
      const res = await getJson<SentimentHistoryResponse>(
        `/api/ai/sentiment/history?hours=${hours}`,
        { headers: { Authorization: `Bearer ${token}` } },
      );
      setData(res);
      setLastUpdated(new Date());
      setCountdown(POLL_INTERVAL_SEC);
    } catch (e: unknown) {
      setError(`データ取得エラー: ${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setIsLoading(false);
    }
  }, [token, hours]);

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

  // Chart data
  const chartData = (data?.data_points ?? []).map((dp) => ({
    label: formatDateTime(dp.timestamp),
    score: dp.score,
    post_count: dp.post_count,
  }));

  // Correlation data (sentiment score vs AI action)
  const correlationData = (data?.data_points ?? []).map((dp) => ({
    score: dp.score,
    action: dp.ai_action === "BUY" ? 1 : dp.ai_action === "SELL" ? -1 : 0,
    label: dp.ai_action ?? "HOLD",
  }));

  return (
    <>
      <title>Xセンチメント分析 - Ultra AutoTrade</title>

      {/* Header */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 8, flexWrap: "wrap" as const, gap: 12 }}>
        <div>
          <h1 style={{ margin: 0 }}>Xセンチメント分析</h1>
          <p style={{ margin: "4px 0 0", color: "#666", fontSize: 13 }}>
            X（Twitter）の暗号通貨関連投稿のセンチメント分析
          </p>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap" as const }}>
          <select
            value={hours}
            onChange={(e) => setHours(Number(e.target.value))}
            style={{ padding: "6px 10px", border: "1px solid #d1d5db", borderRadius: 8, fontSize: 13 }}
          >
            <option value={6}>直近6時間</option>
            <option value={24}>直近24時間</option>
            <option value={72}>直近3日</option>
            <option value={168}>直近1週間</option>
          </select>
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

      {data?.is_mock && (
        <div style={{ padding: "12px 16px", background: "#fffbeb", border: "1px solid #fde68a", borderRadius: 10, color: "#92400e", fontSize: 13, marginBottom: 16 }}>
          <strong>準備中:</strong> X API未設定のため、サンプルデータを表示しています。
        </div>
      )}

      {error && <div style={errorBoxStyle}>{error}</div>}

      {/* Current Sentiment + Stats */}
      {data && (
        <div style={{ display: "grid", gridTemplateColumns: "auto 1fr", gap: 20, marginBottom: 24, alignItems: "start" }}>
          {/* Gauge */}
          <div style={cardStyle}>
            <h2 style={sectionTitleStyle}>現在のセンチメント</h2>
            <SentimentGauge score={data.current_score} label={data.current_label} />
          </div>
          {/* Stats */}
          <div style={cardStyle}>
            <h2 style={sectionTitleStyle}>統計</h2>
            <div style={{ display: "flex", flexWrap: "wrap" as const, gap: 12, marginTop: 8 }}>
              {[
                { label: "データポイント", value: String(data.data_points.length), color: "#374151" },
                { label: "ポジティブ", value: String(data.data_points.filter(d => d.label === "positive").length), color: "#16a34a" },
                { label: "ネガティブ", value: String(data.data_points.filter(d => d.label === "negative").length), color: "#dc2626" },
                { label: "ニュートラル", value: String(data.data_points.filter(d => d.label === "neutral").length), color: "#6b7280" },
                { label: "平均スコア", value: data.data_points.length > 0 ? (data.data_points.reduce((s, d) => s + d.score, 0) / data.data_points.length).toFixed(3) : "—", color: "#374151" },
              ].map(({ label, value, color }) => (
                <div key={label} style={{ padding: "12px 20px", border: "1px solid #e5e7eb", borderRadius: 10, background: "#fafafa", textAlign: "center" as const, minWidth: 90 }}>
                  <div style={{ fontSize: 22, fontWeight: 700, color, lineHeight: 1.2 }}>{value}</div>
                  <div style={{ fontSize: 11, color: "#888", marginTop: 2 }}>{label}</div>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* Trend Chart */}
      <div style={{ ...cardStyle, marginBottom: 20 }}>
        <h2 style={sectionTitleStyle}>センチメントスコア推移（直近{hours}時間）</h2>
        {chartData.length === 0 ? (
          <div style={{ color: "#9ca3af", fontSize: 13, padding: "24px 0", textAlign: "center" as const }}>データがありません</div>
        ) : (
          <ResponsiveContainer width="100%" height={240}>
            <LineChart data={chartData} margin={{ top: 8, right: 16, left: 0, bottom: 4 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
              <XAxis dataKey="label" tick={{ fontSize: 11, fill: "#6b7280" }} interval="preserveStartEnd" />
              <YAxis domain={[-1, 1]} tick={{ fontSize: 11, fill: "#6b7280" }} tickFormatter={(v: number) => v.toFixed(1)} />
              <Tooltip formatter={(v: number) => [v.toFixed(3), "スコア"]} contentStyle={{ fontSize: 12 }} />
              <ReferenceLine y={0} stroke="#9ca3af" strokeDasharray="4 4" />
              <ReferenceLine y={0.2} stroke="#16a34a" strokeDasharray="2 4" strokeOpacity={0.5} />
              <ReferenceLine y={-0.2} stroke="#dc2626" strokeDasharray="2 4" strokeOpacity={0.5} />
              <Line type="monotone" dataKey="score" stroke="#2563eb" strokeWidth={2} dot={false} name="センチメントスコア" />
            </LineChart>
          </ResponsiveContainer>
        )}
      </div>

      {/* Correlation: Sentiment vs AI Action */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(300px, 1fr))", gap: 20, marginBottom: 20 }}>
        <div style={cardStyle}>
          <h2 style={sectionTitleStyle}>センチメント × AI判定 相関</h2>
          {correlationData.length === 0 ? (
            <div style={{ color: "#9ca3af", fontSize: 13, padding: "24px 0", textAlign: "center" as const }}>データがありません</div>
          ) : (
            <ResponsiveContainer width="100%" height={220}>
              <ScatterChart margin={{ top: 8, right: 16, left: 0, bottom: 4 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                <XAxis dataKey="score" type="number" domain={[-1, 1]} name="センチメントスコア" tick={{ fontSize: 11 }} tickFormatter={(v: number) => v.toFixed(1)} />
                <YAxis dataKey="action" type="number" domain={[-1.5, 1.5]} name="AI判定" tick={{ fontSize: 11 }}
                  tickFormatter={(v: number) => v === 1 ? "BUY" : v === -1 ? "SELL" : "HOLD"} />
                <Tooltip cursor={{ strokeDasharray: "3 3" }} contentStyle={{ fontSize: 12 }}
                  formatter={(v: number, name: string) => {
                    if (name === "AI判定") return [v === 1 ? "BUY" : v === -1 ? "SELL" : "HOLD", name];
                    return [typeof v === "number" ? v.toFixed(3) : v, name];
                  }} />
                <Scatter data={correlationData} fill="#2563eb" opacity={0.6} />
              </ScatterChart>
            </ResponsiveContainer>
          )}
        </div>

        {/* Latest X Posts */}
        <div style={cardStyle}>
          <h2 style={sectionTitleStyle}>最新Xポスト（直近10件）</h2>
          {(data?.latest_posts ?? []).length === 0 ? (
            <div style={{ color: "#9ca3af", fontSize: 13, padding: "24px 0", textAlign: "center" as const }}>データがありません</div>
          ) : (
            <div style={{ display: "flex", flexDirection: "column" as const, gap: 8, maxHeight: 280, overflowY: "auto" as const }}>
              {(data?.latest_posts ?? []).map((post) => (
                <div key={post.post_id} style={{ padding: "8px 12px", borderRadius: 8, background: "#fafafa", border: "1px solid #f3f4f6" }}>
                  <div style={{ fontSize: 13, color: "#374151", marginBottom: 4 }}>{post.text}</div>
                  <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
                    <span style={{
                      display: "inline-block", padding: "1px 8px", borderRadius: 999,
                      fontSize: 11, fontWeight: 600,
                      background: sentimentBg(post.sentiment),
                      color: sentimentColor(post.sentiment),
                    }}>
                      {post.score >= 0 ? "+" : ""}{post.score.toFixed(2)}
                    </span>
                    <span style={{ fontSize: 11, color: "#9ca3af" }}>
                      ♥ {post.likes.toLocaleString()} · {formatDateTime(post.created_at)}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </>
  );
}

// ─── Styles ───────────────────────────────────────────────────────────────────

const outlineBtnStyle: React.CSSProperties = {
  padding: "6px 14px", background: "#fff", color: "#374151",
  border: "1px solid #d1d5db", borderRadius: 8, fontSize: 13,
  cursor: "pointer",
};

const errorBoxStyle: React.CSSProperties = {
  padding: "10px 14px", background: "#fff1f2", border: "1px solid #fecaca",
  borderRadius: 8, color: "#b91c1c", fontSize: 13, marginBottom: 16,
};

const cardStyle: React.CSSProperties = {
  padding: "16px 20px", border: "1px solid #e5e7eb", borderRadius: 10,
  background: "#fff", boxShadow: "0 1px 3px rgba(0,0,0,0.06)",
};

const sectionTitleStyle: React.CSSProperties = {
  fontSize: 14, fontWeight: 600, color: "#374151", marginTop: 0, marginBottom: 8,
};