'use client'
// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.

import React, { useState, useEffect, useCallback } from "react";
import AuthGuard from "@/components/AuthGuard";
import { useAuth } from "@/lib/auth";
import { getJson, postJson } from "@/lib/api/http";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from "@/components/ui/dialog";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Slider } from "@/components/ui/slider";
import { PieChart, Pie, Cell, Tooltip, Legend, ResponsiveContainer } from "recharts";
import { type AiDecision, MOCK_DECISIONS } from "./mock-data";

// ─── Types ────────────────────────────────────────────────────────────────────

type ActionFilter = "ALL" | "BUY" | "SELL" | "HOLD";

// ─── Helpers ──────────────────────────────────────────────────────────────────

function formatDateTime(iso: string): string {
  try {
    return new Date(iso).toLocaleString("ja-JP", {
      timeZone: "Asia/Tokyo",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return iso;
  }
}

const ACTION_COLORS: Record<"BUY" | "SELL" | "HOLD", { bg: string; color: string }> = {
  BUY:  { bg: "#dcfce7", color: "#16a34a" },
  SELL: { bg: "#fee2e2", color: "#dc2626" },
  HOLD: { bg: "#f3f4f6", color: "#6b7280" },
};

function ActionBadge({ action }: { action?: "BUY" | "SELL" | "HOLD" }) {
  if (!action) return <span className="text-gray-400 text-xs">—</span>;
  const { bg, color } = ACTION_COLORS[action];
  return (
    <span style={{ display: "inline-block", padding: "2px 10px", borderRadius: 999, fontSize: 12, fontWeight: 600, background: bg, color }}>
      {action}
    </span>
  );
}

function StatCard({ label, value, color }: { label: string; value: string; color: string }) {
  return (
    <div className="px-5 py-3 border border-gray-200 dark:border-gray-700 rounded-xl bg-white dark:bg-gray-900 shadow-sm text-center min-w-[80px]">
      <div style={{ fontSize: 22, fontWeight: 700, color, lineHeight: 1.2 }}>{value}</div>
      <div className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">{label}</div>
    </div>
  );
}

const PIE_COLORS = ["#16a34a", "#dc2626", "#6b7280"];

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

// ─── Main export ──────────────────────────────────────────────────────────────

export default function AiDecisionsPage() {
  return (
    <AuthGuard adminOnly>
      <AiDecisionsContent />
    </AuthGuard>
  );
}

// ─── Page content ─────────────────────────────────────────────────────────────

function AiDecisionsContent() {
  const { token } = useAuth();
  const [decisions, setDecisions] = useState<AiDecision[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [isMock, setIsMock] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [triggering, setTriggering] = useState(false);
  const [triggerMsg, setTriggerMsg] = useState<string | null>(null);

  // Filters
  const [actionFilter, setActionFilter] = useState<ActionFilter>("ALL");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [confidenceThreshold, setConfidenceThreshold] = useState(0);

  // Detail dialog
  const [selectedDecision, setSelectedDecision] = useState<AiDecision | null>(null);

  const fetchDecisions = useCallback(async () => {
    if (!token) return;
    setIsLoading(true);
    setError(null);
    try {
      const data = await getJson<AiDecision[]>("/api/ai/history", {
        headers: { Authorization: `Bearer ${token}` },
      });
      setDecisions(data);
      setIsMock(false);
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : String(e);
      if (msg.includes("404") || msg.toLowerCase().includes("not found")) {
        setDecisions(MOCK_DECISIONS);
        setIsMock(true);
      } else {
        setError(`データ取得エラー: ${msg}`);
      }
    } finally {
      setIsLoading(false);
    }
  }, [token]);

  useEffect(() => {
    fetchDecisions();
  }, [fetchDecisions]);

  async function handleManualTrigger() {
    if (!token) return;
    setTriggering(true);
    setTriggerMsg(null);
    try {
      await postJson("/api/ai/analyze", {}, { headers: { Authorization: `Bearer ${token}` } });
      setTriggerMsg("AI分析を開始しました。しばらく後に更新してください。");
      setTimeout(() => fetchDecisions(), 3000);
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : String(e);
      setTriggerMsg(`エラー: ${msg}`);
    } finally {
      setTriggering(false);
    }
  }

  // Filtered decisions
  const filtered = decisions.filter((d) => {
    if (actionFilter !== "ALL" && d.final_action !== actionFilter) return false;
    if (confidenceThreshold > 0 && d.final_confidence * 100 < confidenceThreshold) return false;
    if (dateFrom && new Date(d.timestamp).getTime() < new Date(dateFrom).getTime()) return false;
    if (dateTo && new Date(d.timestamp).getTime() > new Date(dateTo).getTime() + 86400000) return false;
    return true;
  });

  const buyCount  = decisions.filter((d) => d.final_action === "BUY").length;
  const sellCount = decisions.filter((d) => d.final_action === "SELL").length;
  const holdCount = decisions.filter((d) => d.final_action === "HOLD").length;

  const pieData = [
    { name: "BUY",  value: buyCount },
    { name: "SELL", value: sellCount },
    { name: "HOLD", value: holdCount },
  ].filter((d) => d.value > 0);

  return (
    <>
      <title>AI決定モニター - Ultra AutoTrade</title>

      {/* Header */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 8, flexWrap: "wrap", gap: 12 }}>
        <div>
          <h1 style={{ margin: 0 }}>AI決定モニター</h1>
          <p style={{ margin: "4px 0 0", color: "#666", fontSize: 13 }}>マルチLLMによるAI判定の詳細履歴・フィルタリング</p>
        </div>
        <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
          {triggerMsg && (
            <span style={{ fontSize: 12, color: triggerMsg.startsWith("エラー") ? "#dc2626" : "#16a34a" }}>
              {triggerMsg}
            </span>
          )}
          <button
            onClick={handleManualTrigger}
            disabled={triggering}
            className="px-3 py-1.5 text-sm bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 transition-colors"
          >
            {triggering ? "分析中..." : "手動でAI分析を実行"}
          </button>
          <button onClick={fetchDecisions} disabled={isLoading} style={outlineBtnStyle}>
            {isLoading ? "読み込み中..." : "更新"}
          </button>
        </div>
      </div>

      {/* Mock banner */}
      {isMock && (
        <div className="p-3 mb-4 bg-amber-50 border border-amber-200 rounded-lg text-amber-800 text-sm dark:bg-amber-950 dark:border-amber-800 dark:text-amber-200">
          準備中: AI判定履歴APIは現在実装中です。以下はサンプルデータです。
        </div>
      )}

      {error && <div style={errorBoxStyle}>{error}</div>}

      {/* Stats */}
      {decisions.length > 0 && (
        <div className="flex gap-3 flex-wrap mb-5">
          <StatCard label="総判定数"       value={String(decisions.length)}                                   color="#374151" />
          <StatCard label="BUY"           value={String(buyCount)}                                            color="#16a34a" />
          <StatCard label="SELL"          value={String(sellCount)}                                           color="#dc2626" />
          <StatCard label="HOLD"          value={String(holdCount)}                                           color="#6b7280" />
          <StatCard label="Claude/GPT一致" value={String(decisions.filter((d) => d.agreed).length)}           color="#2563eb" />
          <StatCard label="実行済み"       value={String(decisions.filter((d) => d.executed).length)}         color="#7c3aed" />
        </div>
      )}

      {/* Chart + Filter */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-6">
        <div className="border border-gray-200 dark:border-gray-700 rounded-xl p-4 bg-white dark:bg-gray-900">
          <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-3">判定アクション分布</h3>
          {pieData.length > 0 ? (
            <ResponsiveContainer width="100%" height={200}>
              <PieChart>
                <Pie data={pieData} cx="50%" cy="50%" outerRadius={70} dataKey="value"
                  label={({ name, percent }) => `${name} ${(percent * 100).toFixed(0)}%`} labelLine={false}>
                  {pieData.map((_, i) => <Cell key={i} fill={PIE_COLORS[i % PIE_COLORS.length]} />)}
                </Pie>
                <Tooltip />
                <Legend />
              </PieChart>
            </ResponsiveContainer>
          ) : (
            <div className="h-48 flex items-center justify-center text-gray-400 text-sm">データなし</div>
          )}
        </div>

        <div className="border border-gray-200 dark:border-gray-700 rounded-xl p-4 bg-white dark:bg-gray-900">
          <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-3">フィルター</h3>
          <div className="space-y-3">
            <div>
              <label className="text-xs font-medium text-gray-600 dark:text-gray-400 block mb-1">アクション</label>
              <Select value={actionFilter} onValueChange={(v) => setActionFilter(v as ActionFilter)}>
                <SelectTrigger className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="ALL">すべて</SelectItem>
                  <SelectItem value="BUY">BUY</SelectItem>
                  <SelectItem value="SELL">SELL</SelectItem>
                  <SelectItem value="HOLD">HOLD</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="grid grid-cols-2 gap-2">
              <div>
                <label className="text-xs font-medium text-gray-600 dark:text-gray-400 block mb-1">開始日</label>
                <input type="date" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)}
                  className="w-full px-2 py-1.5 text-sm border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100" />
              </div>
              <div>
                <label className="text-xs font-medium text-gray-600 dark:text-gray-400 block mb-1">終了日</label>
                <input type="date" value={dateTo} onChange={(e) => setDateTo(e.target.value)}
                  className="w-full px-2 py-1.5 text-sm border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100" />
              </div>
            </div>
            <div>
              <label className="text-xs font-medium text-gray-600 dark:text-gray-400 block mb-1">
                最低信頼度: <span className="font-semibold text-gray-800 dark:text-gray-200">{confidenceThreshold}%</span>
              </label>
              <Slider min={0} max={100} step={5} value={[confidenceThreshold]}
                onValueChange={(vals) => setConfidenceThreshold(vals[0])} className="w-full" />
            </div>
            <button onClick={() => { setActionFilter("ALL"); setDateFrom(""); setDateTo(""); setConfidenceThreshold(0); }}
              className="text-xs text-blue-600 dark:text-blue-400 hover:underline">
              フィルターをリセット
            </button>
          </div>
        </div>
      </div>

      {/* Decision table */}
      <section>
        <h2 style={{ fontSize: 15, marginBottom: 10, marginTop: 0 }}>
          判定履歴
          <span style={{ fontWeight: 400, color: "#888", fontSize: 12, marginLeft: 8 }}>
            {filtered.length} / {decisions.length} 件
          </span>
        </h2>

        {isLoading && decisions.length === 0 && (
          <div style={{ color: "#9ca3af", fontSize: 14, padding: "24px 0" }}>読み込み中...</div>
        )}
        {!isLoading && !error && decisions.length === 0 && (
          <div style={{ color: "#9ca3af", fontSize: 14, padding: "24px 0" }}>判定履歴がありません。</div>
        )}

        {filtered.length > 0 && (
          <div className="border border-gray-200 dark:border-gray-700 rounded-xl overflow-hidden">
            <Table>
              <TableHeader>
                <TableRow className="bg-gray-50 dark:bg-gray-800">
                  <TableHead className="text-gray-700 dark:text-gray-300">日時</TableHead>
                  <TableHead className="text-gray-700 dark:text-gray-300">クエリ</TableHead>
                  <TableHead className="text-gray-700 dark:text-gray-300">判定</TableHead>
                  <TableHead className="text-gray-700 dark:text-gray-300">信頼度</TableHead>
                  <TableHead className="text-gray-700 dark:text-gray-300">Claude</TableHead>
                  <TableHead className="text-gray-700 dark:text-gray-300">GPT-4o</TableHead>
                  <TableHead className="text-gray-700 dark:text-gray-300">一致</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {filtered.map((d) => (
                  <TableRow key={d.id} onClick={() => setSelectedDecision(d)}
                    className="cursor-pointer hover:bg-blue-50 dark:hover:bg-blue-950 transition-colors">
                    <TableCell className="text-xs text-gray-500 dark:text-gray-400 whitespace-nowrap">
                      {formatDateTime(d.timestamp)}
                    </TableCell>
                    <TableCell className="max-w-[200px]">
                      <span className="block overflow-hidden text-ellipsis whitespace-nowrap text-sm text-gray-800 dark:text-gray-200" title={d.query}>
                        {d.query.length > 40 ? d.query.slice(0, 40) + "…" : d.query}
                      </span>
                    </TableCell>
                    <TableCell><ActionBadge action={d.final_action} /></TableCell>
                    <TableCell className="text-right whitespace-nowrap font-mono text-sm text-gray-800 dark:text-gray-200">
                      {(d.final_confidence * 100).toFixed(0)}%
                    </TableCell>
                    <TableCell><ActionBadge action={d.claude_action} /></TableCell>
                    <TableCell><ActionBadge action={d.gpt4o_action} /></TableCell>
                    <TableCell>
                      <span className={`inline-block px-2 py-0.5 rounded-full text-xs font-semibold ${
                        d.agreed
                          ? "bg-green-100 text-green-700 dark:bg-green-900 dark:text-green-300"
                          : "bg-red-100 text-red-700 dark:bg-red-900 dark:text-red-300"
                      }`}>
                        {d.agreed ? "一致" : "不一致"}
                      </span>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        )}
        <p className="mt-2 text-xs text-gray-400 dark:text-gray-600">※ 行をクリックすると詳細が表示されます。</p>
      </section>

      {/* Detail dialog */}
      <DecisionDetailDialog decision={selectedDecision} onClose={() => setSelectedDecision(null)} />
    </>
  );
}

// ─── Detail dialog ────────────────────────────────────────────────────────────

function DecisionDetailDialog({ decision, onClose }: { decision: AiDecision | null; onClose: () => void }) {
  function formatDateTime(iso: string): string {
    try {
      return new Date(iso).toLocaleString("ja-JP", { timeZone: "Asia/Tokyo", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" });
    } catch { return iso; }
  }

  return (
    <Dialog open={decision !== null} onOpenChange={(open) => { if (!open) onClose(); }}>
      <DialogContent className="max-w-2xl max-h-[80vh] overflow-y-auto bg-white dark:bg-gray-900 border-gray-200 dark:border-gray-700">
        <DialogHeader>
          <DialogTitle className="text-gray-900 dark:text-gray-100">
            AI判定詳細 — {decision && formatDateTime(decision.timestamp)}
          </DialogTitle>
          <DialogDescription className="text-gray-600 dark:text-gray-400">
            {decision?.query}
          </DialogDescription>
        </DialogHeader>

        {decision && (
          <div className="space-y-4 text-sm">
            <div className="flex items-center gap-3 p-3 rounded-lg bg-gray-50 dark:bg-gray-800 flex-wrap">
              <div>
                <span className="text-xs text-gray-500 dark:text-gray-400 block">最終判定</span>
                <ActionBadge action={decision.final_action} />
              </div>
              <div>
                <span className="text-xs text-gray-500 dark:text-gray-400 block">信頼度</span>
                <span className="font-mono font-semibold text-gray-800 dark:text-gray-200">
                  {(decision.final_confidence * 100).toFixed(0)}%
                </span>
              </div>
              <div>
                <span className="text-xs text-gray-500 dark:text-gray-400 block">実行</span>
                <span className={`font-semibold ${decision.executed ? "text-blue-600" : "text-gray-400"}`}>
                  {decision.executed ? "済" : "未実行"}
                </span>
              </div>
            </div>

            {/* Claude */}
            <div className="border border-gray-200 dark:border-gray-700 rounded-lg p-3">
              <div className="flex items-center gap-2 mb-2">
                <span className="text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wide">Claude</span>
                <ActionBadge action={decision.claude_action} />
                <span className="text-xs text-gray-500 dark:text-gray-400 ml-auto">
                  信頼度 {(decision.claude_confidence * 100).toFixed(0)}%
                </span>
              </div>
              <p className="text-gray-700 dark:text-gray-300">{decision.claude_reason}</p>
              {decision.claude_raw_response && (
                <details className="mt-2">
                  <summary className="text-xs text-gray-400 cursor-pointer hover:text-gray-600">生レスポンス</summary>
                  <pre className="mt-1 text-xs bg-gray-100 dark:bg-gray-800 p-2 rounded overflow-x-auto text-gray-600 dark:text-gray-400">
                    {decision.claude_raw_response}
                  </pre>
                </details>
              )}
            </div>

            {/* GPT-4o */}
            {decision.gpt4o_action && (
              <div className="border border-gray-200 dark:border-gray-700 rounded-lg p-3">
                <div className="flex items-center gap-2 mb-2">
                  <span className="text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wide">GPT-4o</span>
                  <ActionBadge action={decision.gpt4o_action} />
                  {decision.gpt4o_confidence != null && (
                    <span className="text-xs text-gray-500 dark:text-gray-400 ml-auto">
                      信頼度 {(decision.gpt4o_confidence * 100).toFixed(0)}%
                    </span>
                  )}
                </div>
                {decision.gpt4o_reason && (
                  <p className="text-gray-700 dark:text-gray-300">{decision.gpt4o_reason}</p>
                )}
                {decision.gpt4o_raw_response && (
                  <details className="mt-2">
                    <summary className="text-xs text-gray-400 cursor-pointer hover:text-gray-600">生レスポンス</summary>
                    <pre className="mt-1 text-xs bg-gray-100 dark:bg-gray-800 p-2 rounded overflow-x-auto text-gray-600 dark:text-gray-400">
                      {decision.gpt4o_raw_response}
                    </pre>
                  </details>
                )}
              </div>
            )}

            {/* Agreement */}
            <div className={`p-2 rounded text-xs font-medium ${
              decision.agreed
                ? "bg-green-50 text-green-700 dark:bg-green-950 dark:text-green-300"
                : "bg-red-50 text-red-700 dark:bg-red-950 dark:text-red-300"
            }`}>
              {decision.agreed ? "Claude と GPT-4o の判定が一致しました。" : "Claude と GPT-4o の判定が不一致です。安全側の判定を採用。"}
            </div>

            {/* RAG context */}
            {decision.rag_context && (
              <div className="border border-gray-200 dark:border-gray-700 rounded-lg p-3">
                <span className="text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wide block mb-2">
                  RAGコンテキスト（ソース数: {decision.rag_context.source_count}）
                </span>
                <p className="text-xs text-gray-500 dark:text-gray-400 mb-2">検索クエリ: {decision.rag_context.query}</p>
                <ul className="space-y-1">
                  {decision.rag_context.chunks.map((chunk, i) => (
                    <li key={i} className="text-xs bg-gray-50 dark:bg-gray-800 p-2 rounded text-gray-600 dark:text-gray-400">
                      {chunk}
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}