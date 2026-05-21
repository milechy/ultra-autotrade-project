'use client'
// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.

import Link from "next/link";
import React from "react";
import AuthGuard from "@/components/AuthGuard";
import {
  searchKnowledge,
  type KnowledgeSearchResult,
  type KnowledgeSearchResponse,
} from "@/lib/api/knowledge";

const SIMILARITY_THRESHOLDS = [0.5, 0.6, 0.7, 0.8] as const;
const TOP_K_OPTIONS = [3, 5, 10, 20, 50] as const;
const MAX_HISTORY = 5;

interface QueryHistoryEntry {
  query: string;
  topK: number;
  threshold: number;
  resultCount: number;
  responseMs: number;
  timestamp: string;
}

interface DebugMeta {
  requestedAt: string;
  respondedAt: string;
  responseMs: number;
  topK: number;
  threshold: number;
  rawResponse: KnowledgeSearchResponse;
}

export default function RagTestPage() {
  const [query, setQuery] = React.useState("");
  const [topK, setTopK] = React.useState<number>(5);
  const [threshold, setThreshold] = React.useState<number>(0.7);
  const [results, setResults] = React.useState<KnowledgeSearchResult[]>([]);
  const [lastQuery, setLastQuery] = React.useState<string | null>(null);
  const [searching, setSearching] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const [debugMeta, setDebugMeta] = React.useState<DebugMeta | null>(null);
  const [showRaw, setShowRaw] = React.useState(false);
  const [history, setHistory] = React.useState<QueryHistoryEntry[]>([]);

  async function handleSearch(e: React.FormEvent) {
    e.preventDefault();
    const q = query.trim();
    if (!q) return;

    setSearching(true);
    setError(null);
    setShowRaw(false);

    const requestedAt = new Date().toISOString();
    const t0 = performance.now();

    try {
      const res = await searchKnowledge({ query: q, top_k: topK });
      const t1 = performance.now();
      const responseMs = Math.round(t1 - t0);
      const respondedAt = new Date().toISOString();

      const filtered = res.results.filter((r) => r.similarity >= threshold);
      setResults(filtered);
      setLastQuery(res.query);
      setDebugMeta({
        requestedAt,
        respondedAt,
        responseMs,
        topK,
        threshold,
        rawResponse: res,
      });

      const entry: QueryHistoryEntry = {
        query: q,
        topK,
        threshold,
        resultCount: filtered.length,
        responseMs,
        timestamp: respondedAt,
      };
      setHistory((prev) => [entry, ...prev].slice(0, MAX_HISTORY));
    } catch (err: unknown) {
      const msg = (err as { message?: string })?.message ?? String(err);
      setError(msg);
    } finally {
      setSearching(false);
    }
  }

  function handleHistoryRerun(entry: QueryHistoryEntry) {
    setQuery(entry.query);
    setTopK(entry.topK);
    setThreshold(entry.threshold);
  }

  function similarityColor(sim: number): string {
    if (sim >= 0.8) return "#15803d";
    if (sim >= 0.6) return "#b45309";
    return "#6b7280";
  }

  function similarityBg(sim: number): string {
    if (sim >= 0.8) return "#f0fdf4";
    if (sim >= 0.6) return "#fffbeb";
    return "#f9fafb";
  }

  function formatTime(iso: string): string {
    return new Date(iso).toLocaleTimeString("ja-JP", { hour12: false });
  }

  return (
    <AuthGuard adminOnly>
      <>
        <title>RAG 検索テスト (Admin) - Ultra AutoTrade</title>

        {/* ページヘッダー */}
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "baseline",
            flexWrap: "wrap",
            gap: 12,
          }}
        >
          <div>
            <h1 style={{ marginBottom: 4 }}>RAG 検索テスト</h1>
            <p style={{ marginTop: 0, color: "#666", fontSize: 14 }}>
              ベクトル検索の動作確認・デバッグ用ページです。応答時間・生レスポンス・クエリ履歴を確認できます。
            </p>
          </div>
          <div style={{ display: "flex", gap: 8 }}>
            <Link href="/knowledge/search" style={outlineBtnStyle}>
              通常検索
            </Link>
            <Link href="/knowledge" style={outlineBtnStyle}>
              ← ナレッジ一覧
            </Link>
          </div>
        </div>

        {/* 検索フォームカード */}
        <section style={cardStyle}>
          <form onSubmit={handleSearch}>
            <div
              style={{
                display: "flex",
                gap: 8,
                alignItems: "flex-end",
                flexWrap: "wrap",
              }}
            >
              {/* クエリ入力 */}
              <div style={{ flex: 1, minWidth: 260 }}>
                <label style={labelStyle}>検索クエリ</label>
                <input
                  type="text"
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  placeholder="例: BTC の強気サインを教えて"
                  required
                  style={inputStyle}
                  autoFocus
                />
              </div>

              {/* top_k */}
              <div>
                <label style={labelStyle}>件数 (top_k)</label>
                <select
                  value={topK}
                  onChange={(e) => setTopK(Number(e.target.value))}
                  style={{ ...inputStyle, width: 90 }}
                >
                  {TOP_K_OPTIONS.map((n) => (
                    <option key={n} value={n}>
                      {n} 件
                    </option>
                  ))}
                </select>
              </div>

              {/* 類似度閾値 */}
              <div>
                <label style={labelStyle}>類似度閾値</label>
                <select
                  value={threshold}
                  onChange={(e) => setThreshold(Number(e.target.value))}
                  style={{ ...inputStyle, width: 90 }}
                >
                  {SIMILARITY_THRESHOLDS.map((t) => (
                    <option key={t} value={t}>
                      {t}
                    </option>
                  ))}
                </select>
              </div>

              <button
                type="submit"
                disabled={searching || !query.trim()}
                style={{
                  ...primaryBtnStyle,
                  opacity: searching || !query.trim() ? 0.5 : 1,
                  cursor:
                    searching || !query.trim() ? "not-allowed" : "pointer",
                }}
              >
                {searching ? "検索中..." : "検索"}
              </button>
            </div>
          </form>
        </section>

        {/* エラー */}
        {error && <div style={errorBoxStyle}>{error}</div>}

        {/* 検索後の結果エリア */}
        {lastQuery !== null && !error && debugMeta && (
          <>
            {/* タイミング・サマリーバー */}
            <div
              style={{
                display: "flex",
                alignItems: "center",
                gap: 12,
                flexWrap: "wrap",
                marginTop: 20,
              }}
            >
              <h2 style={{ fontSize: 16, margin: 0 }}>
                検索結果
                <span
                  style={{
                    fontWeight: 400,
                    color: "#888",
                    fontSize: 13,
                    marginLeft: 8,
                  }}
                >
                  「{lastQuery}」— {results.length} 件
                  {results.length !== debugMeta.rawResponse.results.length && (
                    <span style={{ color: "#b45309" }}>
                      {" "}
                      (閾値フィルタ後 / 全{" "}
                      {debugMeta.rawResponse.results.length} 件)
                    </span>
                  )}
                </span>
              </h2>
              {/* 応答時間バッジ */}
              <span
                style={{
                  padding: "3px 12px",
                  borderRadius: 999,
                  fontSize: 12,
                  fontWeight: 700,
                  background:
                    debugMeta.responseMs < 500
                      ? "#f0fdf4"
                      : debugMeta.responseMs < 2000
                        ? "#fffbeb"
                        : "#fff1f2",
                  color:
                    debugMeta.responseMs < 500
                      ? "#15803d"
                      : debugMeta.responseMs < 2000
                        ? "#b45309"
                        : "#b91c1c",
                  border:
                    "1px solid " +
                    (debugMeta.responseMs < 500
                      ? "#bbf7d0"
                      : debugMeta.responseMs < 2000
                        ? "#fde68a"
                        : "#fecaca"),
                }}
              >
                応答時間: {debugMeta.responseMs}ms
              </span>

              {/* 生JSON トグル */}
              <button
                type="button"
                onClick={() => setShowRaw((v) => !v)}
                style={outlineBtnStyle}
              >
                {showRaw ? "生JSONを隠す" : "生JSONを表示"}
              </button>
            </div>

            {/* 生JSON */}
            {showRaw && (
              <div
                style={{
                  ...cardStyle,
                  background: "#0f172a",
                  borderColor: "#334155",
                  overflowX: "auto",
                }}
              >
                <pre
                  style={{
                    margin: 0,
                    fontSize: 12,
                    lineHeight: 1.6,
                    color: "#e2e8f0",
                    whiteSpace: "pre-wrap",
                    wordBreak: "break-all",
                  }}
                >
                  {JSON.stringify(debugMeta.rawResponse, null, 2)}
                </pre>
              </div>
            )}

            {/* Debug Info セクション */}
            <div
              style={{
                ...cardStyle,
                background: "#f8fafc",
                borderColor: "#cbd5e1",
                marginTop: 12,
              }}
            >
              <div
                style={{
                  fontSize: 11,
                  fontWeight: 700,
                  textTransform: "uppercase",
                  letterSpacing: "0.08em",
                  color: "#64748b",
                  marginBottom: 8,
                }}
              >
                Debug Info
              </div>
              <div
                style={{
                  display: "grid",
                  gridTemplateColumns: "repeat(auto-fill, minmax(180px, 1fr))",
                  gap: "6px 24px",
                  fontSize: 12,
                  color: "#475569",
                }}
              >
                <div>
                  <span style={{ color: "#94a3b8" }}>リクエスト時刻: </span>
                  {formatTime(debugMeta.requestedAt)}
                </div>
                <div>
                  <span style={{ color: "#94a3b8" }}>レスポンス時刻: </span>
                  {formatTime(debugMeta.respondedAt)}
                </div>
                <div>
                  <span style={{ color: "#94a3b8" }}>応答時間: </span>
                  {debugMeta.responseMs}ms
                </div>
                <div>
                  <span style={{ color: "#94a3b8" }}>top_k: </span>
                  {debugMeta.topK}
                </div>
                <div>
                  <span style={{ color: "#94a3b8" }}>類似度閾値: </span>
                  {debugMeta.threshold}
                </div>
                <div>
                  <span style={{ color: "#94a3b8" }}>APIヒット数: </span>
                  {debugMeta.rawResponse.count}
                </div>
                <div>
                  <span style={{ color: "#94a3b8" }}>フィルタ後件数: </span>
                  {results.length}
                </div>
              </div>
            </div>

            {/* 結果リスト */}
            {results.length === 0 ? (
              <p style={{ color: "#888", marginTop: 16 }}>
                該当するナレッジが見つかりませんでした。類似度閾値を下げるか、クエリを変えてお試しください。
              </p>
            ) : (
              <div
                style={{
                  display: "flex",
                  flexDirection: "column",
                  gap: 12,
                  marginTop: 16,
                }}
              >
                {results.map((r, i) => (
                  <div
                    key={r.chunk_id}
                    style={{
                      border: "1px solid #e5e7eb",
                      borderRadius: 12,
                      padding: 16,
                      background: "#fff",
                    }}
                  >
                    {/* ランク・タイトル・類似度 */}
                    <div
                      style={{
                        display: "flex",
                        justifyContent: "space-between",
                        alignItems: "flex-start",
                        gap: 8,
                        marginBottom: 10,
                      }}
                    >
                      <div
                        style={{
                          display: "flex",
                          alignItems: "center",
                          gap: 8,
                        }}
                      >
                        <span
                          style={{
                            display: "inline-flex",
                            alignItems: "center",
                            justifyContent: "center",
                            width: 26,
                            height: 26,
                            borderRadius: "50%",
                            background: "#1a1a2e",
                            color: "#fff",
                            fontSize: 11,
                            fontWeight: 700,
                            flexShrink: 0,
                          }}
                        >
                          {i + 1}
                        </span>
                        <span style={{ fontWeight: 600, color: "#111" }}>
                          {r.title ?? (
                            <span style={{ color: "#aaa", fontWeight: 400 }}>
                              （タイトルなし）
                            </span>
                          )}
                        </span>
                      </div>
                      <span
                        style={{
                          display: "inline-block",
                          padding: "2px 10px",
                          borderRadius: 999,
                          fontSize: 12,
                          fontWeight: 700,
                          background: similarityBg(r.similarity),
                          color: similarityColor(r.similarity),
                          whiteSpace: "nowrap",
                          flexShrink: 0,
                        }}
                      >
                        類似度 {(r.similarity * 100).toFixed(1)}%
                      </span>
                    </div>

                    {/* ソースURL */}
                    {r.source_url && (
                      <div style={{ marginBottom: 8 }}>
                        <a
                          href={r.source_url?.startsWith("http") ? r.source_url : "#"}
                          target="_blank"
                          rel="noopener noreferrer"
                          style={{
                            fontSize: 12,
                            color: "#3b82f6",
                            wordBreak: "break-all",
                          }}
                        >
                          {r.source_url}
                        </a>
                      </div>
                    )}

                    {/* コンテンツ */}
                    <p
                      style={{
                        margin: 0,
                        fontSize: 13,
                        lineHeight: 1.7,
                        color: "#374151",
                        background: "#f9fafb",
                        borderRadius: 8,
                        padding: "10px 14px",
                        whiteSpace: "pre-wrap",
                        wordBreak: "break-word",
                      }}
                    >
                      {r.content}
                    </p>

                    {/* デバッグ行: chunk_id / document_id */}
                    <div
                      style={{
                        marginTop: 8,
                        padding: "6px 10px",
                        background: "#f1f5f9",
                        borderRadius: 6,
                        fontSize: 11,
                        color: "#64748b",
                        display: "flex",
                        gap: 16,
                        flexWrap: "wrap",
                      }}
                    >
                      <span>
                        <span style={{ color: "#94a3b8" }}>chunk_id: </span>
                        <span style={{ fontFamily: "monospace" }}>
                          {r.chunk_id}
                        </span>
                      </span>
                      <span>
                        <span style={{ color: "#94a3b8" }}>document_id: </span>
                        <span style={{ fontFamily: "monospace" }}>
                          {r.document_id}
                        </span>
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </>
        )}

        {/* クエリ履歴 */}
        {history.length > 0 && (
          <section style={{ ...cardStyle, marginTop: 32 }}>
            <div
              style={{
                fontSize: 13,
                fontWeight: 600,
                color: "#374151",
                marginBottom: 10,
              }}
            >
              クエリ履歴（直近 {MAX_HISTORY} 件）
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
              {history.map((entry, idx) => (
                <div
                  key={idx}
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: 10,
                    padding: "6px 10px",
                    borderRadius: 8,
                    background: "#f8fafc",
                    border: "1px solid #e2e8f0",
                    flexWrap: "wrap",
                  }}
                >
                  <span
                    style={{
                      fontSize: 11,
                      color: "#94a3b8",
                      whiteSpace: "nowrap",
                    }}
                  >
                    {formatTime(entry.timestamp)}
                  </span>
                  <span
                    style={{
                      fontSize: 13,
                      color: "#1e293b",
                      flex: 1,
                      minWidth: 100,
                    }}
                  >
                    {entry.query}
                  </span>
                  <span style={{ fontSize: 11, color: "#64748b" }}>
                    top_k={entry.topK} / 閾値={entry.threshold} /{" "}
                    {entry.resultCount}件 / {entry.responseMs}ms
                  </span>
                  <button
                    type="button"
                    onClick={() => handleHistoryRerun(entry)}
                    style={{
                      ...outlineBtnStyle,
                      fontSize: 11,
                      padding: "3px 10px",
                    }}
                  >
                    再実行
                  </button>
                </div>
              ))}
            </div>
          </section>
        )}
      </>
    </AuthGuard>
  );
}

// ── スタイル定数 ──────────────────────────────────────────────────────────────

const cardStyle: React.CSSProperties = {
  border: "1px solid #e5e7eb",
  borderRadius: 12,
  padding: 20,
  background: "#fff",
  marginTop: 16,
};

const labelStyle: React.CSSProperties = {
  display: "block",
  fontSize: 13,
  fontWeight: 500,
  marginBottom: 4,
  color: "#374151",
};

const inputStyle: React.CSSProperties = {
  width: "100%",
  padding: "8px 12px",
  border: "1px solid #d1d5db",
  borderRadius: 8,
  fontSize: 14,
  outline: "none",
  boxSizing: "border-box",
};

const primaryBtnStyle: React.CSSProperties = {
  padding: "8px 20px",
  background: "#1a1a2e",
  color: "#fff",
  border: "none",
  borderRadius: 8,
  fontSize: 14,
  fontWeight: 600,
  cursor: "pointer",
  whiteSpace: "nowrap",
  alignSelf: "flex-end",
};

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
  marginTop: 12,
};