// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.
"use client";

import { useState } from "react";
import { useAuth } from "@/lib/auth";
import { useAuthFetch } from "@/hooks/useAuthFetch";
import { useRouter } from "next/navigation";
import { useEffect } from "react";

interface AuditLogEntry {
  id: number;
  user_id: number;
  actor_id: number | null;
  action: string;
  old_value: string | null;
  new_value: string | null;
  created_at: string;
  user_email: string | null;
  actor_email: string | null;
}

interface AuditLogResponse {
  entries: AuditLogEntry[];
  total: number;
}

const RISK_MODE_LABEL: Record<string, string> = {
  conservative: "ローリスク",
  balanced: "ミドルリスク",
  aggressive: "ハイリスク",
  custom: "カスタム",
};

function modeLabel(value: string | null): string {
  if (!value) return "—";
  return RISK_MODE_LABEL[value] ?? value;
}

function formatDate(iso: string): string {
  try {
    return new Date(iso).toLocaleString("ja-JP", {
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

export default function CustomRiskModeAuditPage() {
  const { isAdmin } = useAuth();
  const router = useRouter();
  const [page, setPage] = useState(0);
  const limit = 20;

  const { data, loading, error } = useAuthFetch<AuditLogResponse>(
    `/auth/admin/risk-modes/custom-audit?limit=${limit}&offset=${page * limit}`,
  );

  useEffect(() => {
    if (isAdmin === false) {
      router.replace("/admin/dashboard");
    }
  }, [isAdmin, router]);

  if (!isAdmin) {
    return (
      <div className="p-8 text-zinc-400">アクセス権限がありません。</div>
    );
  }

  const totalPages = data ? Math.ceil(data.total / limit) : 0;

  return (
    <div className="p-6 space-y-6 max-w-6xl mx-auto">
      <div>
        <h1 className="text-2xl font-bold text-zinc-100">
          CUSTOMリスクモード 変更履歴
        </h1>
        <p className="text-sm text-zinc-400 mt-1">
          パートナーによるカスタムリスクモード変更の監査ログです。
          {data && (
            <span className="ml-2 text-zinc-500">（合計: {data.total}件）</span>
          )}
        </p>
      </div>

      {loading && (
        <div className="animate-pulse space-y-2">
          {[...Array(5)].map((_, i) => (
            <div key={i} className="h-12 bg-zinc-800 rounded-lg" />
          ))}
        </div>
      )}

      {error && (
        <div className="rounded-lg border border-red-800 bg-red-950/30 p-4 text-red-400">
          ❌ データの取得に失敗しました: {error.message}
        </div>
      )}

      {data && data.entries.length === 0 && !loading && (
        <div className="rounded-lg border border-zinc-700 bg-zinc-900/40 p-8 text-center text-zinc-500">
          変更履歴はありません。
        </div>
      )}

      {data && data.entries.length > 0 && (
        <>
          <div className="overflow-x-auto rounded-xl border border-zinc-700">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-zinc-700 bg-zinc-900/60">
                  <th className="text-left px-4 py-3 text-zinc-400 font-medium">
                    日時
                  </th>
                  <th className="text-left px-4 py-3 text-zinc-400 font-medium">
                    対象ユーザー
                  </th>
                  <th className="text-left px-4 py-3 text-zinc-400 font-medium">
                    操作者
                  </th>
                  <th className="text-left px-4 py-3 text-zinc-400 font-medium">
                    変更前
                  </th>
                  <th className="text-left px-4 py-3 text-zinc-400 font-medium">
                    変更後
                  </th>
                </tr>
              </thead>
              <tbody>
                {data.entries.map((entry) => (
                  <tr
                    key={entry.id}
                    className="border-b border-zinc-800 hover:bg-zinc-800/30 transition-colors"
                  >
                    <td className="px-4 py-3 text-zinc-300 whitespace-nowrap">
                      {formatDate(entry.created_at)}
                    </td>
                    <td className="px-4 py-3 text-zinc-300">
                      <span className="text-xs text-zinc-500 mr-1">
                        #{entry.user_id}
                      </span>
                      {entry.user_email ?? "—"}
                    </td>
                    <td className="px-4 py-3 text-zinc-300">
                      {entry.actor_email ? (
                        <>
                          <span className="text-xs text-zinc-500 mr-1">
                            #{entry.actor_id}
                          </span>
                          {entry.actor_email}
                        </>
                      ) : (
                        "—"
                      )}
                    </td>
                    <td className="px-4 py-3">
                      <span
                        className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs ${
                          entry.old_value === "custom"
                            ? "bg-purple-900/40 text-purple-300"
                            : "bg-zinc-800 text-zinc-400"
                        }`}
                      >
                        {modeLabel(entry.old_value)}
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      <span
                        className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs ${
                          entry.new_value === "custom"
                            ? "bg-purple-900/40 text-purple-300 font-medium"
                            : "bg-zinc-800 text-zinc-400"
                        }`}
                      >
                        {modeLabel(entry.new_value)}
                        {entry.new_value === "custom" && " ⚙️"}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {totalPages > 1 && (
            <div className="flex items-center justify-between">
              <button
                onClick={() => setPage(Math.max(0, page - 1))}
                disabled={page === 0}
                className="px-4 py-2 rounded-lg border border-zinc-600 hover:border-zinc-500 disabled:opacity-40 text-zinc-400 hover:text-zinc-300 transition-colors"
              >
                ← 前へ
              </button>
              <span className="text-zinc-500 text-sm">
                {page + 1} / {totalPages}
              </span>
              <button
                onClick={() => setPage(Math.min(totalPages - 1, page + 1))}
                disabled={page >= totalPages - 1}
                className="px-4 py-2 rounded-lg border border-zinc-600 hover:border-zinc-500 disabled:opacity-40 text-zinc-400 hover:text-zinc-300 transition-colors"
              >
                次へ →
              </button>
            </div>
          )}
        </>
      )}
    </div>
  );
}
