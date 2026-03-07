// frontend/pages/knowledge/search.tsx
import Head from "next/head";
import Link from "next/link";
import React from "react";
import AppShell from "../../components/layout/AppShell";
import AuthGuard from "../../components/AuthGuard";
import {
  searchKnowledge,
  type KnowledgeSearchResult,
} from "../../lib/api/knowledge";

export default function KnowledgeSearchPage() {
  const [query, setQuery] = React.useState("");
  const [topK, setTopK] = React.useState(5);
  const [results, setResults] = React.useState<KnowledgeSearchResult[]>([]);
  const [lastQuery, setLastQuery] = React.useState<string | null>(null);
  const [searching, setSearching] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);

  async function handleSearch(e: React.FormEvent) {
    e.preventDefault();
    const q = query.trim();
    if (!q) return;

    setSearching(true);
    setError(null);

    try {
      const res = await searchKnowledge({ query: q, top_k: topK });
      setResults(res.results);
      setLastQuery(res.query);
    } catch (err: unknown) {
      const msg = (err as { message?: string })?.message ?? String(err);
      setError(msg);
    } finally {
      setSearching(false);
    }
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

  return (
    <AuthGuard>
      <AppShell>
        <Head>
          <title>RAG検索 - ナレッジ Hub - Ultra AutoTrade</title>
        </Head>

        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", flexWrap: "wrap", gap: 12 }}>
          <div>
            <h1 style={{ marginBottom: 4 }}>RAG検索</h1>
            <p style={{ marginTop: 0, color: "#666" }}>
              登録済みナレッジをベクトル検索で照会します。
            </p>
          </div>
          <Link href="/knowledge" style={outlineBtnStyle}>← ナレッジ一覧</Link>
        </div>

        {/* 検索フォーム */}
        <section style={cardStyle}>
          <form onSubmit={handleSearch}>
            <div style={{ display: "flex", gap: 8, alignItems: "flex-end", flexWrap: "wrap" }}>
              <div style={{ flex: 1, minWidth: 240 }}>
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
              <div>
                <label style={labelStyle}>件数</label>
                <select
                  value={topK}
                  onChange={(e) => setTopK(Number(e.target.value))}
                  style={{ ...inputStyle, width: 80 }}
                >
                  {[3, 5, 10, 20].map((n) => (
                    <option key={n} value={n}>{n}件</option>
                  ))}
                </select>
              </div>
              <button type="submit" disabled={searching || !query.trim()} style={primaryBtnStyle}>
                {searching ? "検索中..." : "検索"}
              </button>
            </div>
          </form>
        </section>

        {/* エラー */}
        {error && (
          <div style={errorBoxStyle}>{error}</div>
        )}

        {/* 検索結果 */}
        {lastQuery !== null && !error && (
          <section style={{ marginTop: 20 }}>
            <h2 style={{ fontSize: 16, marginBottom: 12 }}>
              検索結果
              <span style={{ fontWeight: 400, color: "#888", fontSize: 13, marginLeft: 8 }}>
                「{lastQuery}」— {results.length} 件
              </span>
            </h2>

            {results.length === 0 ? (
              <p style={{ color: "#888" }}>該当するナレッジが見つかりませんでした。</p>
            ) : (
              <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
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
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 8, marginBottom: 10 }}>
                      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                        <span style={{
                          display: "inline-flex",
                          alignItems: "center",
                          justifyContent: "center",
                          width: 24,
                          height: 24,
                          borderRadius: "50%",
                          background: "#1a1a2e",
                          color: "#fff",
                          fontSize: 11,
                          fontWeight: 700,
                          flexShrink: 0,
                        }}>
                          {i + 1}
                        </span>
                        <span style={{ fontWeight: 600, color: "#111" }}>
                          {r.title ?? <span style={{ color: "#aaa", fontWeight: 400 }}>（タイトルなし）</span>}
                        </span>
                      </div>
                      <span style={{
                        display: "inline-block",
                        padding: "2px 10px",
                        borderRadius: 999,
                        fontSize: 12,
                        fontWeight: 700,
                        background: similarityBg(r.similarity),
                        color: similarityColor(r.similarity),
                        whiteSpace: "nowrap",
                        flexShrink: 0,
                      }}>
                        類似度 {(r.similarity * 100).toFixed(1)}%
                      </span>
                    </div>

                    {r.source_url && (
                      <div style={{ marginBottom: 8 }}>
                        <a
                          href={r.source_url}
                          target="_blank"
                          rel="noopener noreferrer"
                          style={{ fontSize: 12, color: "#3b82f6", wordBreak: "break-all" }}
                        >
                          {r.source_url}
                        </a>
                      </div>
                    )}

                    <p style={{
                      margin: 0,
                      fontSize: 13,
                      lineHeight: 1.7,
                      color: "#374151",
                      background: "#f9fafb",
                      borderRadius: 8,
                      padding: "10px 14px",
                      whiteSpace: "pre-wrap",
                      wordBreak: "break-word",
                    }}>
                      {r.content}
                    </p>

                    <div style={{ marginTop: 8, fontSize: 11, color: "#9ca3af" }}>
                      チャンク ID: {r.chunk_id} / ドキュメント ID: {r.document_id}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </section>
        )}
      </AppShell>
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
