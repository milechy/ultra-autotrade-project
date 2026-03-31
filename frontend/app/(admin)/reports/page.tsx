'use client'
// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.

import React from "react";
import { useAuth } from "@/lib/auth";
import { getJson, postJson } from "@/lib/api/http";

// ── Types ──────────────────────────────────────────────────────────────────

interface EventCounts {
  INFO: number;
  WARNING: number;
  ALERT: number;
  CRITICAL: number;
  EMERGENCY: number;
}

interface MetricAggregate {
  metric_id: string;
  count: number;
  min_value: number | null;
  max_value: number | null;
  avg_value: number | null;
  unit: string | null;
}

interface ReportDetail {
  id: string;
  period_type: "daily" | "weekly";
  period_start: string;
  period_end: string;
  event_counts: EventCounts;
  hf_min: number | null;
  hf_max: number | null;
  hf_last: number | null;
  emergency_occurred: boolean;
  notes: string | null;
  metric_aggregates: MetricAggregate[];
  created_at: string;
}

// ── Mock Data ──────────────────────────────────────────────────────────────

const MOCK_REPORTS: ReportDetail[] = [
  {
    id: "rpt-001",
    period_type: "daily",
    period_start: "2026-03-21T00:00:00+09:00",
    period_end: "2026-03-21T23:59:59+09:00",
    event_counts: { INFO: 42, WARNING: 3, ALERT: 1, CRITICAL: 0, EMERGENCY: 0 },
    hf_min: 1.72,
    hf_max: 2.15,
    hf_last: 2.01,
    emergency_occurred: false,
    notes: "通常運用。HFは安定して推移。",
    metric_aggregates: [
      { metric_id: "health_factor", count: 288, min_value: 1.72, max_value: 2.15, avg_value: 1.94, unit: null },
      { metric_id: "usdc_balance", count: 288, min_value: 9800.0, max_value: 10200.0, avg_value: 10020.5, unit: "USDC" },
    ],
    created_at: "2026-03-22T00:05:00+09:00",
  },
  {
    id: "rpt-002",
    period_type: "daily",
    period_start: "2026-03-20T00:00:00+09:00",
    period_end: "2026-03-20T23:59:59+09:00",
    event_counts: { INFO: 38, WARNING: 8, ALERT: 4, CRITICAL: 2, EMERGENCY: 1 },
    hf_min: 1.48,
    hf_max: 1.98,
    hf_last: 1.71,
    emergency_occurred: true,
    notes: "HFが1.6を下回り緊急停止が発動。03:14 JST に自動復旧。担当者への通知済み。",
    metric_aggregates: [
      { metric_id: "health_factor", count: 288, min_value: 1.48, max_value: 1.98, avg_value: 1.68, unit: null },
      { metric_id: "usdc_balance", count: 288, min_value: 9200.0, max_value: 10100.0, avg_value: 9710.3, unit: "USDC" },
      { metric_id: "aave_borrow_usd", count: 288, min_value: 4500.0, max_value: 5100.0, avg_value: 4820.0, unit: "USD" },
    ],
    created_at: "2026-03-21T00:05:00+09:00",
  },
  {
    id: "rpt-003",
    period_type: "weekly",
    period_start: "2026-03-14T00:00:00+09:00",
    period_end: "2026-03-20T23:59:59+09:00",
    event_counts: { INFO: 310, WARNING: 21, ALERT: 7, CRITICAL: 2, EMERGENCY: 1 },
    hf_min: 1.48,
    hf_max: 2.31,
    hf_last: 1.71,
    emergency_occurred: true,
    notes: "週次まとめ。3/20の緊急停止を含む。全体的なHFは良好。",
    metric_aggregates: [
      { metric_id: "health_factor", count: 2016, min_value: 1.48, max_value: 2.31, avg_value: 1.92, unit: null },
      { metric_id: "usdc_balance", count: 2016, min_value: 9200.0, max_value: 10500.0, avg_value: 10045.8, unit: "USDC" },
    ],
    created_at: "2026-03-21T01:00:00+09:00",
  },
];

// ── Helpers ────────────────────────────────────────────────────────────────

function formatJst(iso: string): string {
  return new Date(iso).toLocaleString("ja-JP", { timeZone: "Asia/Tokyo" });
}

function formatDateJst(iso: string): string {
  return new Date(iso).toLocaleDateString("ja-JP", {
    timeZone: "Asia/Tokyo",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  });
}

function hfColor(val: number | null): string {
  if (val == null) return "#6b7280";
  if (val >= 1.8) return "#16a34a";
  if (val >= 1.6) return "#ca8a04";
  return "#dc2626";
}

// ── Sub-components ─────────────────────────────────────────────────────────

function EventBadge({ level, count }: { level: string; count: number }) {
  const palette: Record<string, { bg: string; color: string }> = {
    INFO:      { bg: "#dbeafe", color: "#1d4ed8" },
    WARNING:   { bg: "#fef9c3", color: "#92400e" },
    ALERT:     { bg: "#ffedd5", color: "#c2410c" },
    CRITICAL:  { bg: "#fee2e2", color: "#dc2626" },
    EMERGENCY: { bg: "#fce7f3", color: "#9d174d" },
  };
  const p = palette[level] ?? { bg: "#f3f4f6", color: "#374151" };
  return (
    <span style={{
      display: "inline-flex", alignItems: "center", gap: 4,
      padding: "2px 8px", borderRadius: 999, fontSize: 12, fontWeight: 600,
      background: p.bg, color: p.color,
    }}>
      {level} {count}
    </span>
  );
}

function HfStat({ label, value }: { label: string; value: number | null }) {
  return (
    <span style={{ fontSize: 13, color: "#555" }}>
      {label}:{" "}
      <strong style={{ color: hfColor(value) }}>
        {value != null ? value.toFixed(2) : "—"}
      </strong>
    </span>
  );
}

function MetricsTable({ rows }: { rows: MetricAggregate[] }) {
  if (rows.length === 0) return <p style={{ fontSize: 13, color: "#9ca3af" }}>メトリクスデータなし</p>;
  return (
    <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
      <thead>
        <tr style={{ background: "#f9fafb" }}>
          {["メトリクスID", "件数", "最小", "最大", "平均", "単位"].map((h) => (
            <th key={h} style={thS}>{h}</th>
          ))}
        </tr>
      </thead>
      <tbody>
        {rows.map((r) => (
          <tr key={r.metric_id} style={{ borderBottom: "1px solid #f3f4f6" }}>
            <td style={tdS}><code style={{ fontSize: 12 }}>{r.metric_id}</code></td>
            <td style={tdS}>{r.count}</td>
            <td style={tdS}>{r.min_value != null ? r.min_value.toFixed(2) : "—"}</td>
            <td style={tdS}>{r.max_value != null ? r.max_value.toFixed(2) : "—"}</td>
            <td style={tdS}>{r.avg_value != null ? r.avg_value.toFixed(2) : "—"}</td>
            <td style={tdS}>{r.unit ?? "—"}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function ReportCard({
  report,
  expanded,
  onToggle,
}: {
  report: ReportDetail;
  expanded: boolean;
  onToggle: () => void;
}) {
  const periodLabel = report.period_type === "weekly" ? "週次" : "日次";
  const periodColor = report.period_type === "weekly" ? "#6d28d9" : "#0284c7";
  const periodBg   = report.period_type === "weekly" ? "#ede9fe" : "#e0f2fe";

  return (
    <div style={{
      border: report.emergency_occurred ? "1.5px solid #fca5a5" : "1px solid #e5e7eb",
      borderRadius: 12,
      background: "#fff",
      boxShadow: "0 1px 4px rgba(0,0,0,0.07)",
      overflow: "hidden",
      transition: "box-shadow 0.15s",
    }}>
      {/* Card Header */}
      <button
        onClick={onToggle}
        style={{
          width: "100%", textAlign: "left", background: "none",
          border: "none", padding: "16px 20px", cursor: "pointer",
          display: "flex", alignItems: "flex-start", gap: 12,
        }}
      >
        {/* Period badge */}
        <span style={{
          flexShrink: 0, padding: "2px 10px", borderRadius: 999, fontSize: 12,
          fontWeight: 700, background: periodBg, color: periodColor,
        }}>
          {periodLabel}
        </span>

        {/* Main info */}
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ fontSize: 14, fontWeight: 600, color: "#111", marginBottom: 4 }}>
            {formatDateJst(report.period_start)} 〜 {formatDateJst(report.period_end)}
          </div>
          <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginBottom: 8 }}>
            {(["INFO", "WARNING", "ALERT", "CRITICAL", "EMERGENCY"] as const).map((lv) =>
              report.event_counts[lv] > 0
                ? <EventBadge key={lv} level={lv} count={report.event_counts[lv]} />
                : null
            )}
          </div>
          <div style={{ display: "flex", gap: 16, flexWrap: "wrap" }}>
            <HfStat label="HF最小" value={report.hf_min} />
            <HfStat label="HF最大" value={report.hf_max} />
            <HfStat label="HF最終" value={report.hf_last} />
          </div>
        </div>

        {/* Emergency flag */}
        {report.emergency_occurred && (
          <span style={{
            flexShrink: 0, padding: "2px 10px", borderRadius: 999,
            fontSize: 12, fontWeight: 700,
            background: "#fee2e2", color: "#dc2626",
          }}>
            緊急停止
          </span>
        )}

        {/* Expand arrow */}
        <span style={{ flexShrink: 0, fontSize: 14, color: "#9ca3af", paddingTop: 2 }}>
          {expanded ? "▲" : "▼"}
        </span>
      </button>

      {/* Expanded Detail */}
      {expanded && (
        <div style={{ borderTop: "1px solid #f3f4f6", padding: "16px 20px" }}>
          {/* Emergency banner */}
          {report.emergency_occurred && (
            <div style={{
              marginBottom: 16, padding: "12px 16px",
              background: "#fef2f2", border: "1px solid #fca5a5", borderRadius: 8,
              display: "flex", alignItems: "center", gap: 10,
            }}>
              <span style={{ fontSize: 18 }}>⚠️</span>
              <div>
                <strong style={{ color: "#dc2626", fontSize: 13 }}>緊急停止が発生しました</strong>
                <p style={{ margin: 0, fontSize: 13, color: "#b91c1c", marginTop: 2 }}>
                  このレポート期間中に緊急停止（EMERGENCY）イベントが記録されています。ログを確認し、原因を調査してください。
                </p>
              </div>
            </div>
          )}

          {/* Metric aggregates table */}
          <h3 style={{ fontSize: 13, fontWeight: 700, color: "#374151", marginBottom: 10, marginTop: 0 }}>
            メトリクス集計
          </h3>
          <MetricsTable rows={report.metric_aggregates} />

          {/* Notes */}
          {report.notes && (
            <div style={{ marginTop: 16 }}>
              <h3 style={{ fontSize: 13, fontWeight: 700, color: "#374151", marginBottom: 6, marginTop: 0 }}>
                メモ
              </h3>
              <p style={{ fontSize: 13, color: "#555", margin: 0, lineHeight: 1.6 }}>{report.notes}</p>
            </div>
          )}

          {/* Footer meta */}
          <div style={{ marginTop: 16, fontSize: 12, color: "#9ca3af" }}>
            レポートID: {report.id} ／ 生成日時: {formatJst(report.created_at)}
          </div>
        </div>
      )}
    </div>
  );
}

// ── Confirmation Dialog ────────────────────────────────────────────────────

function ConfirmDialog({
  open,
  onCancel,
  onConfirm,
  loading,
}: {
  open: boolean;
  onCancel: () => void;
  onConfirm: () => void;
  loading: boolean;
}) {
  if (!open) return null;
  return (
    <div style={{
      position: "fixed", inset: 0, zIndex: 1000,
      background: "rgba(0,0,0,0.35)", display: "flex",
      alignItems: "center", justifyContent: "center",
    }}>
      <div style={{
        background: "#fff", borderRadius: 14, padding: 32,
        maxWidth: 440, width: "90%", boxShadow: "0 8px 32px rgba(0,0,0,0.18)",
      }}>
        <h2 style={{ margin: "0 0 12px", fontSize: 18, fontWeight: 700 }}>レポートを生成しますか？</h2>
        <p style={{ fontSize: 14, color: "#555", margin: "0 0 24px" }}>
          最新データを元に新しいレポートを生成します。
          生成には数秒かかる場合があります。
        </p>
        <div style={{ display: "flex", gap: 10, justifyContent: "flex-end" }}>
          <button
            onClick={onCancel}
            disabled={loading}
            style={{
              padding: "8px 20px", borderRadius: 8, border: "1px solid #e5e7eb",
              background: "#fff", cursor: "pointer", fontSize: 14, color: "#374151",
            }}
          >
            キャンセル
          </button>
          <button
            onClick={onConfirm}
            disabled={loading}
            style={{
              padding: "8px 20px", borderRadius: 8, border: "none",
              background: loading ? "#93c5fd" : "#2563eb",
              color: "#fff", cursor: loading ? "not-allowed" : "pointer",
              fontSize: 14, fontWeight: 600,
            }}
          >
            {loading ? "生成中..." : "生成する"}
          </button>
        </div>
      </div>
    </div>
  );
}

// ── Toast ──────────────────────────────────────────────────────────────────

function Toast({ message, type, onClose }: { message: string; type: "success" | "error"; onClose: () => void }) {
  React.useEffect(() => {
    const t = setTimeout(onClose, 4000);
    return () => clearTimeout(t);
  }, [onClose]);

  return (
    <div style={{
      position: "fixed", bottom: 24, right: 24, zIndex: 2000,
      padding: "12px 20px", borderRadius: 10,
      background: type === "success" ? "#166534" : "#991b1b",
      color: "#fff", fontSize: 14, fontWeight: 600,
      boxShadow: "0 4px 16px rgba(0,0,0,0.18)",
      display: "flex", alignItems: "center", gap: 10,
    }}>
      <span>{type === "success" ? "✓" : "✗"}</span>
      <span>{message}</span>
      <button
        onClick={onClose}
        style={{ marginLeft: 8, background: "none", border: "none", color: "#fff", cursor: "pointer", fontSize: 16 }}
      >
        ×
      </button>
    </div>
  );
}

// ── Main Page ──────────────────────────────────────────────────────────────

function ReportViewerContent() {
  const { token, isAdmin } = useAuth();
  const [reports, setReports] = React.useState<ReportDetail[]>([]);
  const [loading, setLoading] = React.useState(false);
  const [fetchError, setFetchError] = React.useState<string | null>(null);
  const [expandedId, setExpandedId] = React.useState<string | null>(null);
  const [showConfirm, setShowConfirm] = React.useState(false);
  const [generating, setGenerating] = React.useState(false);
  const [toast, setToast] = React.useState<{ message: string; type: "success" | "error" } | null>(null);

  const loadReports = React.useCallback(async () => {
    setLoading(true);
    setFetchError(null);
    try {
      const init = token ? { headers: { Authorization: `Bearer ${token}` } } : undefined;
      const data = await getJson<ReportDetail[]>("/api/reports", init);
      setReports(data);
    } catch {
      // Fallback to mock data
      setReports(MOCK_REPORTS);
      setFetchError("APIからの取得に失敗しました。モックデータを表示しています。");
    } finally {
      setLoading(false);
    }
  }, [token]);

  React.useEffect(() => {
    loadReports();
  }, [loadReports]);

  const handleGenerate = async () => {
    setGenerating(true);
    try {
      const init = token ? { headers: { Authorization: `Bearer ${token}` } } : undefined;
      await postJson("/api/reports/generate", {}, init);
      setShowConfirm(false);
      setToast({ message: "レポートを生成しました", type: "success" });
      await loadReports();
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : (e as { message?: string })?.message ?? "生成に失敗しました";
      setShowConfirm(false);
      setToast({ message: `エラー: ${msg}`, type: "error" });
    } finally {
      setGenerating(false);
    }
  };

  const toggleExpand = (id: string) => {
    setExpandedId((prev) => (prev === id ? null : id));
  };

  return (
    <>
      <title>レポートビューア - Ultra AutoTrade</title>

      {/* Page Header */}
      <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 12, flexWrap: "wrap", marginBottom: 24 }}>
        <div>
          <h1 style={{ margin: 0, fontSize: 22, fontWeight: 700 }}>レポートビューア</h1>
          <p style={{ margin: "6px 0 0", color: "#6b7280", fontSize: 14 }}>
            自動化レポートの確認・管理。カードをクリックして詳細を展開できます。
          </p>
        </div>
        <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
          <button
            onClick={loadReports}
            disabled={loading}
            style={{
              padding: "7px 14px", borderRadius: 8, border: "1px solid #e5e7eb",
              background: "#fff", cursor: loading ? "not-allowed" : "pointer",
              fontSize: 13, color: "#374151",
            }}
          >
            {loading ? "読み込み中..." : "更新"}
          </button>
          {isAdmin && (
            <button
              onClick={() => setShowConfirm(true)}
              disabled={loading || generating}
              style={{
                padding: "7px 16px", borderRadius: 8, border: "none",
                background: "#2563eb", color: "#fff",
                cursor: loading || generating ? "not-allowed" : "pointer",
                fontSize: 13, fontWeight: 600,
              }}
            >
              レポート生成
            </button>
          )}
        </div>
      </div>

      {/* Fetch error notice */}
      {fetchError && (
        <div style={{
          marginBottom: 16, padding: "10px 16px", borderRadius: 8,
          background: "#fffbeb", border: "1px solid #fcd34d", fontSize: 13, color: "#92400e",
        }}>
          {fetchError}
        </div>
      )}

      {/* Report list */}
      {reports.length === 0 && !loading ? (
        <div style={{ textAlign: "center", padding: "48px 0", color: "#9ca3af", fontSize: 14 }}>
          レポートがありません
        </div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          {reports.map((r) => (
            <ReportCard
              key={r.id}
              report={r}
              expanded={expandedId === r.id}
              onToggle={() => toggleExpand(r.id)}
            />
          ))}
        </div>
      )}

      {/* Confirmation Dialog */}
      <ConfirmDialog
        open={showConfirm}
        onCancel={() => setShowConfirm(false)}
        onConfirm={handleGenerate}
        loading={generating}
      />

      {/* Toast */}
      {toast && (
        <Toast
          message={toast.message}
          type={toast.type}
          onClose={() => setToast(null)}
        />
      )}
    </>
  );
}

export default function ReportsPage() {
  return <ReportViewerContent />;
}

// ── Style constants ────────────────────────────────────────────────────────

const thS: React.CSSProperties = {
  textAlign: "left",
  padding: "7px 12px",
  borderBottom: "1px solid #e5e7eb",
  color: "#374151",
  fontWeight: 600,
  fontSize: 12,
};

const tdS: React.CSSProperties = {
  padding: "7px 12px",
  color: "#374151",
  verticalAlign: "middle",
};
