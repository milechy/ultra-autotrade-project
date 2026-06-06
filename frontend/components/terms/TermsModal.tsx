// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.
"use client";

import { useState } from "react";
import { getAuthToken } from "@/lib/auth/token-key";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";
const CURRENT_VERSION = "2.0";

interface TermsModalProps {
  onAccepted: () => void;
}

export default function TermsModal({ onAccepted }: TermsModalProps) {
  const [checked, setChecked] = useState({
    terms: false,
    risk: false,
    privacy: false,
    age: false,
  });
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const allChecked = Object.values(checked).every(Boolean);

  const handleAccept = async () => {
    if (!allChecked) return;
    setSubmitting(true);
    setError(null);
    const token = getAuthToken() ?? "";
    try {
      const res = await fetch(`${API_BASE}/auth/terms/accept`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({ version: CURRENT_VERSION }),
      });
      if (!res.ok) throw new Error(`Failed: ${res.status}`);
      onAccepted();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to accept terms");
    } finally {
      setSubmitting(false);
    }
  };

  const checkboxClass =
    "w-5 h-5 rounded border-zinc-600 bg-zinc-800 text-blue-500 focus:ring-blue-500 focus:ring-offset-zinc-900 cursor-pointer";

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm">
      <div className="mx-4 w-full max-w-lg rounded-2xl border border-zinc-700 bg-zinc-900 p-8 shadow-2xl">
        <h2 className="mb-2 text-xl font-bold text-zinc-100">
          Ultra AutoTrade 利用規約への同意
        </h2>
        <p className="mb-6 text-sm text-zinc-400">
          サービスを利用するには、以下の全ての規約に同意する必要があります。
        </p>

        <div className="space-y-4">
          <label className="flex items-start gap-3 cursor-pointer group">
            <input
              type="checkbox"
              checked={checked.terms}
              onChange={(e) => setChecked({ ...checked, terms: e.target.checked })}
              className={checkboxClass}
            />
            <div>
              <span className="text-sm font-medium text-zinc-200 group-hover:text-white">
                利用規約に同意します
              </span>
              <a
                href="/docs/terms-of-service"
                target="_blank"
                className="ml-2 text-xs text-blue-400 hover:underline"
              >
                全文を読む →
              </a>
            </div>
          </label>

          <label className="flex items-start gap-3 cursor-pointer group">
            <input
              type="checkbox"
              checked={checked.risk}
              onChange={(e) => setChecked({ ...checked, risk: e.target.checked })}
              className={checkboxClass}
            />
            <div>
              <span className="text-sm font-medium text-zinc-200 group-hover:text-white">
                リスク開示書を理解し同意します
              </span>
              <a
                href="/docs/risk-disclosure"
                target="_blank"
                className="ml-2 text-xs text-blue-400 hover:underline"
              >
                全文を読む →
              </a>
              <p className="mt-1 text-xs text-zinc-500">
                暗号資産の取引には元本を失うリスクがあります
              </p>
            </div>
          </label>

          <label className="flex items-start gap-3 cursor-pointer group">
            <input
              type="checkbox"
              checked={checked.privacy}
              onChange={(e) => setChecked({ ...checked, privacy: e.target.checked })}
              className={checkboxClass}
            />
            <div>
              <span className="text-sm font-medium text-zinc-200 group-hover:text-white">
                プライバシーポリシーに同意します
              </span>
              <a
                href="/docs/privacy-policy"
                target="_blank"
                className="ml-2 text-xs text-blue-400 hover:underline"
              >
                全文を読む →
              </a>
            </div>
          </label>

          <label className="flex items-start gap-3 cursor-pointer group">
            <input
              type="checkbox"
              checked={checked.age}
              onChange={(e) => setChecked({ ...checked, age: e.target.checked })}
              className={checkboxClass}
            />
            <span className="text-sm font-medium text-zinc-200 group-hover:text-white">
              18歳以上であることを確認します
            </span>
          </label>
        </div>

        {error && (
          <div className="mt-4 rounded-lg border border-red-800 bg-red-950/30 p-3 text-sm text-red-400">
            {error}
          </div>
        )}

        <button
          onClick={handleAccept}
          disabled={!allChecked || submitting}
          className={`mt-6 w-full rounded-lg py-3 text-sm font-bold transition-all ${
            allChecked
              ? "bg-blue-600 text-white hover:bg-blue-500"
              : "bg-zinc-800 text-zinc-500 cursor-not-allowed"
          }`}
        >
          {submitting ? "処理中..." : "同意してサービスを利用する"}
        </button>

        <p className="mt-4 text-center text-xs text-zinc-600">
          v{CURRENT_VERSION} • 同意内容はサーバーに記録されます
        </p>
      </div>
    </div>
  );
}
