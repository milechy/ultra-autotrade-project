'use client'

import Link from "next/link";
import React from "react";
import AuthGuard from "@/components/AuthGuard";
import { useAuth } from "@/lib/auth";
import { postJson } from "@/lib/api/http";
import {
  fetchKnowledgeItems,
  createKnowledgeItem,
  type KnowledgeItem,
  type KnowledgeItemStatus,
  type KnowledgeItemType,
} from "@/lib/api/knowledge";

// ─── RAG search types ────────────────────────────────────────────────────────

type RagChunk = {
  content: string;
  similarity: number;
  source?: string;
};

type RagSearchResult = {
  chunks: RagChunk[];
  query: string;
  total: number;
};

const STATUS_COLORS: Record<KnowledgeItemStatus, { bg: string; color: string; label: string }> = {
  pending:  { bg: "#fff8e1", color: "#b45309", label: "待機中" },
  analyzed: { bg: "#e8f5e9", color: "#1b5e20", label: "完了" },
  skipped:  { bg: "#f3f4f6", color: "#6b7280", label: "スキップ" },
  error:    { bg: "#fff1f2", color: "#b91c1c", label: "エラー" },
};

function StatusBadge({ status }: { status: KnowledgeItemStatus }) {
  const s = STATUS_COLORS[status] ?? { bg: "#f3f4f6", color: "#374151", label: status };
  return (
    <span style={{
      display: "inline-block",
      padding: "2px 8px",
      borderRadius: 999,
      fontSize: 12,
      fontWeight: 600,
      background: s.bg,
      color: s.color,
    }}>
      {s.label}
    </span>
  );
}

function formatDate(iso: string): string {
  try {
    return new Date(iso).toLocaleString("ja-JP", {
      year: "numeric", month: "2-digit", day: "2-digit",
      hour: "2-digit", minute: "2-digit",
    });
  } catch {
    return iso;
  }
}

export default function KnowledgeIndexPage() {
  const { token } = useAuth();
  const [items, setItems] = React.useState<KnowledgeItem[]>([]);
  const [loadError, setLoadError] = React.useState<string | null>(null);
  const [isLoading, setIsLoading] = React.useState(false);

  // フォーム
  const [itemType, setItemType] = React.useState<KnowledgeItemType>("url");
  const [title, setTitle] = React.useState("");
  const [sourceUrl, setSourceUrl] = React.useState("");
  const [rawText, setRawText] = React.useState("");
  const [submitting, setSubmitting] = React.useState(false);
  const [submitError, setSubmitError] = React.useState<string | null>(null);
  const [submitSuccess, setSubmitSuccess] = React.useState<string | null>(null);

  // RAG検索
  const [ragQuery, setRagQuery] = React.useState("");
  const [ragTopK, setRagTopK] = React.useState("3");
  const [ragSearching, setRagSearching] = React.useState(false);
  const [ragResult, setRagResult] = React.useState<RagSearchResult | null>(null);
  const [ragError, setRagError] = React.useState<string | null>(null);

  // ワークフロー実行
  const [workflowRunning, setWorkflowRunning] = React.useState(false);
  const [workflowMsg, setWorkflowMsg] = React.useState<string | null>(null);
  const [workflowIsError, setWorkflowIsError] = React.useState(false);

  async function loadItems() {
    setIsLoading(true);
    setLoadError(null);
    try {
      const data = await fetchKnowledgeItems();
      setItems(data);
    } catch (e: unknown) {
      const msg = (e as { message?: string })?.message ?? String(e);
      setLoadError(msg);
    } finally {
      setIsLoading(false);
    }
  }

  React.useEffect(() => {
    loadItems();
    const interval = setInterval(loadItems, 30_000);
    return () => clearInterval(interval);
  }, []);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    setSubmitError(null);
    setSubmitSuccess(null);

    try {
      const req = {
        item_type: itemType,
        title: title.trim() || undefined,
        source_url: itemType === "url" ? sourceUrl.trim() : undefined,
        raw_text: itemType === "text" ? rawText.trim() : undefined,
      };
      const created = await createKnowledgeItem(req);
      setSubmitSuccess(`登録しました（ID: ${created.id}）`);
      setTitle("");
      setSourceUrl("");
      setRawText("");
      loadItems();
    } catch (e: unknown) {
      const msg = (e as { message?: string })?.message ?? String(e);
      setSubmitError(msg);
    } finally {
      setSubmitting(false);
    }
  }

  async function handleRagSearch(e: React.FormEvent) {
    e.preventDefault();
    if (!ragQuery.trim()) return;
    setRagSearching(true);
    setRagError(null);
    setRagResult(null);
    try {
      const result = await postJson<RagSearchResult>(
        "/api/knowledge/search",
        { query: ragQuery.trim(), top_k: Number(ragTopK) },
        { headers: token ? { Authorization: `Bearer ${token}` } : {} }
      );
      setRagResult(result);
    } catch (e: unknown) {
      const msg = (e as { message?: string })?.message ?? String(e);
      setRagError(msg);
    } finally {
      setRagSearching(false);
    }
  }

  async function handleWorkflowRun() {
    setWorkflowRunning(true);
    setWorkflowMsg(null);
    setWorkflowIsError(false);
    try {
      const result = await postJson<{ status: string; message?: string }>(
        "/api/automation/workflow/run",
        { dry_run: false },
        { headers: token ? { Authorization: `Bearer ${token}` } : {} }
      );
      setWorkflowMsg(result.message ?? `完了しました (status: ${result.status})`);
      setWorkflowIsError(false);
      loadItems();
    } catch (e: unknown) {
      const msg = (e as { message?: string })?.message ?? String(e);
      setWorkflowMsg(`エラー: ${msg}`);
      setWorkflowIsError(true);
    } finally {
      setWorkflowRunning(false);
    }
  }

  return (
    <AuthGuard>
      <>
        <title>ナレッジ Hub - Ultra AutoTrade</title>

        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", flexWrap: "wrap", gap: 12 }}>
          <div>
            <h1 style={{ marginBottom: 4 }}>ナレッジ Hub</h1>
            <p style={{ marginTop: 0, color: "#666" }}>
              URL またはテキストを登録してRAG検索の知識ベースを構築します。
            </p>
          </div>
          <div style={{ display: "flex", gap: 8 }}>
            <Link href="/knowledge/search" style={outlineBtnStyle}>RAG検索 →</Link>
            <button onClick={loadItems} disabled={isLoading} style={outlineBtnStyle}>
              {isLoading ? "読み込み中..." : "更新"}
            </button>
          </div>
        </div>

        {/* 登録フォーム */}
        <section style={cardStyle}>
          <h2 style={{ marginTop: 0, fontSize: 16 }}>ナレッジ登録</h2>

          <form onSubmit={handleSubmit}>
            {/* item_type 切替 */}
            <div style={{ display: "flex", gap: 0, marginBottom: 16, border: "1px solid #ddd", borderRadius: 8, overflow: "hidden", width: "fit-content" }}>
              {(["url", "text"] as KnowledgeItemType[]).map((t) => (
                <button
                  key={t}
                  type="button"
                  onClick={() => setItemType(t)}
                  style={{
                    padding: "6px 20px",
                    border: "none",
                    background: itemType === t ? "#1a1a2e" : "#fff",
                    color: itemType === t ? "#fff" : "#444",
                    fontWeight: itemType === t ? 600 : 400,
                    cursor: "pointer",
                    fontSize: 14,
                    transition: "background 0.15s",
                  }}
                >
                  {t === "url" ? "URL" : "テキスト"}
                </button>
              ))}
            </div>

            {/* タイトル（任意） */}
            <div style={{ marginBottom: 12 }}>
              <label style={labelStyle}>タイトル（任意）</label>
              <input
                type="text"
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                placeholder="例: BTC相場分析 2026-03"
                style={inputStyle}
              />
            </div>

            {/* URL or テキスト */}
            {itemType === "url" ? (
              <div style={{ marginBottom: 12 }}>
                <label style={labelStyle}>URL <span style={{ color: "#e53e3e" }}>*</span></label>
                <input
                  type="url"
                  value={sourceUrl}
                  onChange={(e) => setSourceUrl(e.target.value)}
                  placeholder="https://example.com/article"
                  required
                  style={inputStyle}
                />
              </div>
            ) : (
              <div style={{ marginBottom: 12 }}>
                <label style={labelStyle}>テキスト <span style={{ color: "#e53e3e" }}>*</span></label>
                <textarea
                  value={rawText}
                  onChange={(e) => setRawText(e.target.value)}
                  placeholder="登録するテキストを入力してください..."
                  required
                  rows={5}
                  style={{ ...inputStyle, resize: "vertical", fontFamily: "inherit" }}
                />
              </div>
            )}

            {submitError && (
              <div style={errorBoxStyle}>{submitError}</div>
            )}
            {submitSuccess && (
              <div style={successBoxStyle}>{submitSuccess}</div>
            )}

            <button type="submit" disabled={submitting} style={primaryBtnStyle}>
              {submitting ? "登録中..." : "登録する"}
            </button>
          </form>
        </section>

        {/* アイテム一覧テーブル */}
        <section style={{ marginTop: 24 }}>
          <h2 style={{ fontSize: 16, marginBottom: 12 }}>
            登録済みアイテム
            <span style={{ fontWeight: 400, color: "#888", fontSize: 13, marginLeft: 8 }}>
              全 {items.length} 件（30秒自動更新）
            </span>
          </h2>

          {loadError && (
            <div style={errorBoxStyle}>{loadError}</div>
          )}

          {!loadError && items.length === 0 && !isLoading && (
            <p style={{ color: "#888" }}>アイテムがありません。上のフォームから登録してください。</p>
          )}

          {items.length > 0 && (
            <div style={{ overflowX: "auto" }}>
              <table style={tableStyle}>
                <thead>
                  <tr>
                    {["ID", "タイトル / URL", "種別", "ステータス", "チャンク数", "登録日時"].map((h) => (
                      <th key={h} style={thStyle}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {items.map((item, i) => (
                    <tr key={item.id} style={{ background: i % 2 === 0 ? "#fff" : "#fafafa" }}>
                      <td style={tdStyle}>{item.id}</td>
                      <td style={{ ...tdStyle, maxWidth: 300 }}>
                        <div style={{ fontWeight: 500, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                          {item.title ?? <span style={{ color: "#aaa" }}>（タイトルなし）</span>}
                        </div>
                        {item.source_url && (
                          <div style={{ fontSize: 11, color: "#888", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", marginTop: 2 }}>
                            <a href={item.source_url} target="_blank" rel="noopener noreferrer" style={{ color: "#3b82f6" }}>
                              {item.source_url}
                            </a>
                          </div>
                        )}
                      </td>
                      <td style={tdStyle}>
                        <span style={{ fontSize: 12, color: "#555" }}>
                          {item.item_type === "url" ? "URL" : "テキスト"}
                        </span>
                      </td>
                      <td style={tdStyle}>
                        <StatusBadge status={item.status} />
                      </td>
                      <td style={{ ...tdStyle, textAlign: "center" }}>{item.chunk_count}</td>
                      <td style={{ ...tdStyle, fontSize: 12, color: "#666", whiteSpace: "nowrap" }}>
                        {formatDate(item.created_at)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>
        {/* ─── RAG検索テスト ─────────────────────────────────────────── */}
        <section className="mt-8">
          <h2 className="text-base font-semibold mb-3 text-gray-900 dark:text-gray-100">
            RAG検索テスト
          </h2>
          <div className="border border-gray-200 dark:border-gray-700 rounded-xl p-5 bg-white dark:bg-gray-900">
            <form onSubmit={handleRagSearch} className="space-y-3">
              <div>
                <label className="block text-xs font-medium text-gray-600 dark:text-gray-400 mb-1">
                  検索クエリ
                </label>
                <textarea
                  value={ragQuery}
                  onChange={(e) => setRagQuery(e.target.value)}
                  placeholder="例: BTC/USDT の強気トレンドについて"
                  rows={3}
                  required
                  className="w-full px-3 py-2 text-sm border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 resize-y focus:outline-none focus:ring-2 focus:ring-blue-500"
                />
              </div>
              <div className="flex items-center gap-4">
                <div>
                  <label className="block text-xs font-medium text-gray-600 dark:text-gray-400 mb-1">
                    取得件数 (top_k)
                  </label>
                  <select
                    value={ragTopK}
                    onChange={(e) => setRagTopK(e.target.value)}
                    className="px-3 py-1.5 text-sm border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 focus:outline-none focus:ring-2 focus:ring-blue-500"
                  >
                    <option value="1">1件</option>
                    <option value="3">3件</option>
                    <option value="5">5件</option>
                    <option value="10">10件</option>
                  </select>
                </div>
                <div className="flex-1" />
                <button
                  type="submit"
                  disabled={ragSearching || !ragQuery.trim()}
                  className="px-4 py-2 text-sm bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors font-medium"
                >
                  {ragSearching ? "検索中..." : "RAG検索を実行"}
                </button>
              </div>
            </form>

            {ragError && (
              <div className="mt-3 p-3 bg-red-50 dark:bg-red-950 border border-red-200 dark:border-red-800 rounded-lg text-red-700 dark:text-red-300 text-sm">
                {ragError}
              </div>
            )}

            {ragResult && (
              <div className="mt-4">
                <p className="text-xs text-gray-500 dark:text-gray-400 mb-2">
                  検索クエリ: <span className="font-medium text-gray-700 dark:text-gray-300">{ragResult.query}</span>
                  　取得: {ragResult.chunks.length} チャンク
                </p>
                <div className="space-y-2">
                  {ragResult.chunks.length === 0 && (
                    <p className="text-sm text-gray-400 dark:text-gray-600">該当するチャンクが見つかりませんでした。</p>
                  )}
                  {ragResult.chunks.map((chunk, i) => (
                    <div
                      key={i}
                      className="p-3 border border-gray-200 dark:border-gray-700 rounded-lg bg-gray-50 dark:bg-gray-800"
                    >
                      <div className="flex items-center justify-between mb-1.5">
                        <span className="text-xs font-medium text-gray-500 dark:text-gray-400">
                          チャンク #{i + 1}{chunk.source ? ` — ${chunk.source}` : ""}
                        </span>
                        <span className={`text-xs font-semibold px-2 py-0.5 rounded-full ${
                          chunk.similarity >= 0.8
                            ? "bg-green-100 text-green-700 dark:bg-green-900 dark:text-green-300"
                            : chunk.similarity >= 0.6
                            ? "bg-yellow-100 text-yellow-700 dark:bg-yellow-900 dark:text-yellow-300"
                            : "bg-gray-100 text-gray-600 dark:bg-gray-700 dark:text-gray-400"
                        }`}>
                          類似度 {(chunk.similarity * 100).toFixed(1)}%
                        </span>
                      </div>
                      <p className="text-sm text-gray-700 dark:text-gray-300 leading-relaxed whitespace-pre-wrap">
                        {chunk.content}
                      </p>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        </section>

        {/* ─── 手動ワークフロー実行 ──────────────────────────────────── */}
        <section className="mt-6 mb-8">
          <h2 className="text-base font-semibold mb-3 text-gray-900 dark:text-gray-100">
            手動ワークフロー実行
          </h2>
          <div className="border border-gray-200 dark:border-gray-700 rounded-xl p-5 bg-white dark:bg-gray-900">
            <p className="text-sm text-gray-600 dark:text-gray-400 mb-4">
              Pendingステータスのナレッジアイテムをバックエンドで処理します（スクレイピング → チャンク化 → ベクトル化）。
            </p>
            <div className="flex items-center gap-4 flex-wrap">
              <button
                onClick={handleWorkflowRun}
                disabled={workflowRunning}
                className="px-5 py-2 text-sm bg-gray-900 dark:bg-gray-100 text-white dark:text-gray-900 rounded-lg hover:bg-gray-700 dark:hover:bg-gray-200 disabled:opacity-50 disabled:cursor-not-allowed transition-colors font-semibold"
              >
                {workflowRunning ? "処理中..." : "Pendingアイテムを処理"}
              </button>
              {workflowMsg && (
                <span className={`text-sm font-medium ${
                  workflowIsError
                    ? "text-red-600 dark:text-red-400"
                    : "text-green-600 dark:text-green-400"
                }`}>
                  {workflowMsg}
                </span>
              )}
            </div>
          </div>
        </section>
      </>
    </AuthGuard>
  );
}

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
  marginBottom: 12,
};

const successBoxStyle: React.CSSProperties = {
  padding: "10px 14px",
  background: "#f0fdf4",
  border: "1px solid #bbf7d0",
  borderRadius: 8,
  color: "#15803d",
  fontSize: 13,
  marginBottom: 12,
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
