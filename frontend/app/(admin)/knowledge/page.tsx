'use client'
// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.

import Link from "next/link";
import React from "react";
import { useTranslations } from "next-intl";
import AuthGuard from "@/components/AuthGuard";
import { useAuth } from "@/lib/auth";
import {
  fetchKnowledgeItems,
  createKnowledgeItem,
  type KnowledgeItem,
  type KnowledgeItemStatus,
  type KnowledgeItemType,
} from "@/lib/api/knowledge";
import { getJson, postJson } from "@/lib/api/http";

// ─── RAG search types ────────────────────────────────────────────────────────

type SearchTestItem = {
  content: string;
  source: string | null;
  similarity_score: number;
  created_at: string | null;
};

type SearchTestResponse = {
  results: SearchTestItem[];
  count: number;
  query: string;
};

type WorkflowResult = {
  fetched_count: number;
  traded_count: number;
  skipped_count: number;
  hold_count: number;
  errors: { item_id: number; step: string; message: string }[];
  status: string;
};

const STATUS_COLORS: Record<KnowledgeItemStatus, { bg: string; color: string }> = {
  pending:  { bg: "#fff8e1", color: "#b45309" },
  analyzed: { bg: "#e8f5e9", color: "#1b5e20" },
  skipped:  { bg: "#f3f4f6", color: "#6b7280" },
  error:    { bg: "#fff1f2", color: "#b91c1c" },
};

function StatusBadge({ status, label }: { status: KnowledgeItemStatus; label: string }) {
  const s = STATUS_COLORS[status] ?? { bg: "#f3f4f6", color: "#374151" };
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
      {label}
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
  const t = useTranslations("AdminKnowledge");
  const { token, isAdmin } = useAuth();
  const [items, setItems] = React.useState<KnowledgeItem[]>([]);
  const [loadError, setLoadError] = React.useState<string | null>(null);
  const [isLoading, setIsLoading] = React.useState(false);

  // form
  const [itemType, setItemType] = React.useState<KnowledgeItemType>("url");
  const [title, setTitle] = React.useState("");
  const [sourceUrl, setSourceUrl] = React.useState("");
  const [rawText, setRawText] = React.useState("");
  const [submitting, setSubmitting] = React.useState(false);
  const [submitError, setSubmitError] = React.useState<string | null>(null);
  const [submitSuccess, setSubmitSuccess] = React.useState<string | null>(null);

  // RAG search
  const [ragQuery, setRagQuery] = React.useState("");
  const [ragTopK, setRagTopK] = React.useState("3");
  const [ragSearching, setRagSearching] = React.useState(false);
  const [ragResult, setRagResult] = React.useState<SearchTestResponse | null>(null);
  const [ragError, setRagError] = React.useState<string | null>(null);

  // workflow
  const [workflowRunning, setWorkflowRunning] = React.useState(false);
  const [workflowResult, setWorkflowResult] = React.useState<WorkflowResult | null>(null);
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
      setSubmitSuccess(t("registered", { id: created.id }));
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
      const params = new URLSearchParams({
        query: ragQuery.trim(),
        top_k: ragTopK,
      });
      // backend prefix は /knowledge（/api なし）。getJson が base URL を解決するため
      // /api を付けた raw fetch（必ず 404）ではなくラッパ経由で叩く。
      const data = await getJson<SearchTestResponse>(
        `/knowledge/search/test?${params}`,
        { headers: token ? { Authorization: `Bearer ${token}` } : {} },
      );
      setRagResult(data);
    } catch (e: unknown) {
      const msg = (e as { message?: string })?.message ?? String(e);
      setRagError(msg);
    } finally {
      setRagSearching(false);
    }
  }

  async function handleWorkflowRun() {
    if (!window.confirm(t("workflowConfirm"))) {
      return;
    }
    setWorkflowRunning(true);
    setWorkflowResult(null);
    setWorkflowIsError(false);
    try {
      // backend prefix は /knowledge（/api なし）。postJson が base URL を解決する。
      const data = await postJson<WorkflowResult>(
        "/knowledge/workflow/trigger",
        {},
        { headers: token ? { Authorization: `Bearer ${token}` } : {} },
      );
      setWorkflowResult(data);
      setWorkflowIsError(false);
      loadItems();
    } catch (e: unknown) {
      const msg = (e as { message?: string })?.message ?? String(e);
      setWorkflowResult({ fetched_count: 0, traded_count: 0, skipped_count: 0, hold_count: 0, errors: [], status: "error" });
      setWorkflowIsError(true);
      console.error("Workflow error:", msg);
    } finally {
      setWorkflowRunning(false);
    }
  }

  const statusLabelMap: Record<KnowledgeItemStatus, string> = {
    pending:  t("statusPending"),
    analyzed: t("statusAnalyzed"),
    skipped:  t("statusSkipped"),
    error:    t("statusError"),
  };

  return (
    <AuthGuard adminOnly>
      <>
        <title>{t("pageTitle")}</title>

        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", flexWrap: "wrap", gap: 12 }}>
          <div>
            <h1 style={{ marginBottom: 4 }}>{t("pageHeading")}</h1>
            <p style={{ marginTop: 0, color: "#666" }}>
              {t("pageDescription")}
            </p>
          </div>
          <div style={{ display: "flex", gap: 8 }}>
            <Link href="/knowledge/search" style={outlineBtnStyle}>{t("navRagSearch")}</Link>
            <button onClick={loadItems} disabled={isLoading} style={outlineBtnStyle}>
              {isLoading ? t("navLoading") : t("navRefresh")}
            </button>
          </div>
        </div>

        {/* registration form */}
        <section style={cardStyle}>
          <h2 style={{ marginTop: 0, fontSize: 16 }}>{t("formSection")}</h2>

          <form onSubmit={handleSubmit}>
            {/* item_type toggle */}
            <div style={{ display: "flex", gap: 0, marginBottom: 16, border: "1px solid #ddd", borderRadius: 8, overflow: "hidden", width: "fit-content" }}>
              {(["url", "text"] as KnowledgeItemType[]).map((typ) => (
                <button
                  key={typ}
                  type="button"
                  onClick={() => setItemType(typ)}
                  style={{
                    padding: "6px 20px",
                    border: "none",
                    background: itemType === typ ? "#1a1a2e" : "#fff",
                    color: itemType === typ ? "#fff" : "#444",
                    fontWeight: itemType === typ ? 600 : 400,
                    cursor: "pointer",
                    fontSize: 14,
                    transition: "background 0.15s",
                  }}
                >
                  {typ === "url" ? t("typeUrl") : t("typeText")}
                </button>
              ))}
            </div>

            {/* title (optional) */}
            <div style={{ marginBottom: 12 }}>
              <label style={labelStyle}>{t("labelTitleOptional")}</label>
              <input
                type="text"
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                placeholder={t("placeholderTitle")}
                style={inputStyle}
              />
            </div>

            {/* URL or text */}
            {itemType === "url" ? (
              <div style={{ marginBottom: 12 }}>
                <label style={labelStyle}>{t("labelUrl")} <span style={{ color: "#e53e3e" }}>*</span></label>
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
                <label style={labelStyle}>{t("labelText")} <span style={{ color: "#e53e3e" }}>*</span></label>
                <textarea
                  value={rawText}
                  onChange={(e) => setRawText(e.target.value)}
                  placeholder={t("placeholderText")}
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
              {submitting ? t("btnRegistering") : t("btnRegister")}
            </button>
          </form>
        </section>

        {/* item list table */}
        <section style={{ marginTop: 24 }}>
          <h2 style={{ fontSize: 16, marginBottom: 12 }}>
            {t("tableSection")}
            <span style={{ fontWeight: 400, color: "#888", fontSize: 13, marginLeft: 8 }}>
              {t("tableCount", { count: items.length })}{t("tableAutoUpdate")}
            </span>
          </h2>

          {loadError && (
            <div style={errorBoxStyle}>{loadError}</div>
          )}

          {!loadError && items.length === 0 && !isLoading && (
            <p style={{ color: "#888" }}>{t("noItems")}</p>
          )}

          {items.length > 0 && (
            <div style={{ overflowX: "auto" }}>
              <table style={tableStyle}>
                <thead>
                  <tr>
                    {([
                      t("colId"),
                      t("colTitleUrl"),
                      t("colType"),
                      t("colStatus"),
                      t("colChunks"),
                      t("colCreatedAt"),
                    ]).map((h) => (
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
                          {item.title ?? <span style={{ color: "#aaa" }}>{t("noTitle")}</span>}
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
                          {item.item_type === "url" ? t("typeUrl") : t("typeText")}
                        </span>
                      </td>
                      <td style={tdStyle}>
                        <StatusBadge status={item.status} label={statusLabelMap[item.status] ?? item.status} />
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

        {/* ─── RAG Search Test ─────────────────────────────────────────── */}
        <section className="mt-8">
          <h2 className="text-base font-semibold mb-3 text-gray-900 dark:text-gray-100">
            {t("ragSection")}
          </h2>
          <div className="border border-gray-200 dark:border-gray-700 rounded-xl p-5 bg-white dark:bg-gray-900">
            <form onSubmit={handleRagSearch} className="space-y-3">
              <div>
                <label className="block text-xs font-medium text-gray-600 dark:text-gray-400 mb-1">
                  {t("ragQueryLabel")}
                </label>
                <textarea
                  value={ragQuery}
                  onChange={(e) => setRagQuery(e.target.value)}
                  placeholder={t("ragQueryPlaceholder")}
                  rows={3}
                  required
                  className="w-full px-3 py-2 text-sm border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 resize-y focus:outline-none focus:ring-2 focus:ring-blue-500"
                />
              </div>
              <div className="flex items-center gap-4">
                <div>
                  <label className="block text-xs font-medium text-gray-600 dark:text-gray-400 mb-1">
                    {t("ragTopKLabel")}
                  </label>
                  <select
                    value={ragTopK}
                    onChange={(e) => setRagTopK(e.target.value)}
                    className="px-3 py-1.5 text-sm border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 focus:outline-none focus:ring-2 focus:ring-blue-500"
                  >
                    <option value="3">{t("countUnit", { n: 3 })}</option>
                    <option value="5">{t("countUnit", { n: 5 })}</option>
                    <option value="10">{t("countUnit", { n: 10 })}</option>
                  </select>
                </div>
                <div className="flex-1" />
                <button
                  type="submit"
                  disabled={ragSearching || !ragQuery.trim()}
                  className="px-4 py-2 text-sm bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors font-medium flex items-center gap-2"
                >
                  {ragSearching && (
                    <svg className="animate-spin h-4 w-4 text-white" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                    </svg>
                  )}
                  {ragSearching ? t("ragSearching") : t("ragSearchBtn")}
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
                  {t("ragResultPrefix")}<span className="font-medium text-gray-700 dark:text-gray-300">{ragResult.query}</span>
                  {" "}{t("ragResultFetched", { count: ragResult.results.length })}
                </p>
                <div className="space-y-2">
                  {ragResult.results.length === 0 && (
                    <div className="py-8 text-center text-gray-400 dark:text-gray-600">
                      <p className="text-sm">{t("ragNoResults")}</p>
                      <p className="text-xs mt-1">{t("ragRetry")}</p>
                    </div>
                  )}
                  {ragResult.results.map((item, i) => (
                    <div
                      key={i}
                      className="p-3 border border-gray-200 dark:border-gray-700 rounded-lg bg-gray-50 dark:bg-gray-800"
                    >
                      <div className="flex items-center justify-between mb-1.5">
                        <span className="text-xs font-medium text-gray-500 dark:text-gray-400">
                          #{i + 1}{item.source ? ` — ${item.source}` : ""}
                        </span>
                        <span className={`text-xs font-semibold px-2 py-0.5 rounded-full ${
                          item.similarity_score >= 0.8
                            ? "bg-green-100 text-green-700 dark:bg-green-900 dark:text-green-300"
                            : item.similarity_score >= 0.6
                            ? "bg-yellow-100 text-yellow-700 dark:bg-yellow-900 dark:text-yellow-300"
                            : "bg-gray-100 dark:bg-gray-800 text-gray-600 dark:bg-gray-700 dark:text-gray-400"
                        }`}>
                          {(item.similarity_score * 100).toFixed(1)}%
                        </span>
                      </div>
                      <div className="mb-2">
                        <div className="w-full bg-gray-200 dark:bg-gray-700 rounded-full h-1">
                          <div
                            className="h-1 rounded-full bg-blue-500"
                            style={{ width: `${Math.min(item.similarity_score * 100, 100)}%` }}
                          />
                        </div>
                      </div>
                      <p className="text-sm text-gray-700 dark:text-gray-300 leading-relaxed whitespace-pre-wrap">
                        {item.content}
                      </p>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        </section>

        {/* ─── Manual Workflow Execution ──────────────────────────────────── */}
        {isAdmin && (
          <section className="mt-6 mb-8">
            <h2 className="text-base font-semibold mb-3 text-gray-900 dark:text-gray-100">
              {t("workflowSection")}
            </h2>
            <div className="border border-gray-200 dark:border-gray-700 rounded-xl p-5 bg-white dark:bg-gray-900">
              <p className="text-sm text-gray-600 dark:text-gray-400 mb-4">
                {t("workflowDescription")}
              </p>
              <button
                onClick={handleWorkflowRun}
                disabled={workflowRunning}
                className="px-5 py-2 text-sm bg-gray-900 dark:bg-gray-100 dark:bg-gray-800 text-white dark:text-gray-900 dark:text-gray-100 rounded-lg hover:bg-gray-700 dark:hover:bg-gray-200 disabled:opacity-50 disabled:cursor-not-allowed transition-colors font-semibold"
              >
                {workflowRunning ? t("workflowRunning") : t("workflowRun")}
              </button>
              {workflowResult && (
                <div className={`mt-3 p-3 rounded-lg text-sm ${
                  workflowIsError
                    ? "bg-red-50 dark:bg-red-950 border border-red-200 dark:border-red-800 text-red-700 dark:text-red-300"
                    : "bg-green-50 dark:bg-green-950 border border-green-200 dark:border-green-800 text-green-700 dark:text-green-300"
                }`}>
                  <p className="font-medium mb-1">{t("workflowStatusLabel", { status: workflowResult.status })}</p>
                  <div className="flex gap-4 text-xs flex-wrap">
                    <span>{t("workflowFetched", { count: workflowResult.fetched_count })}</span>
                    <span>{t("workflowTraded", { count: workflowResult.traded_count })}</span>
                    <span>{t("workflowSkipped", { count: workflowResult.skipped_count })}</span>
                    <span>{t("workflowHold", { count: workflowResult.hold_count })}</span>
                    {workflowResult.errors.length > 0 && (
                      <span className="text-red-600">{t("workflowErrors", { count: workflowResult.errors.length })}</span>
                    )}
                  </div>
                </div>
              )}
            </div>
          </section>
        )}
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
