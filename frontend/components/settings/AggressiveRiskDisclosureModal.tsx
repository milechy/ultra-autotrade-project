// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.
"use client";

// [Phase-D D5b] aggressive ティア(Pendle stablecoin PT / yoUSD)のリスク開示/同意モーダル。
// 満期ロック(即時出金不可) / yoUSD 裏付け / スリッページ・薄い流動性リスク の 3 項目を全同意
// (all-checkbox required)してはじめて aggressive を選択できる。TermsModal の踏襲。同意は
// POST /api/user/aggressive-consent で backend に永続する。

import { useState } from "react";
import { useTranslations } from "next-intl";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";

// 3 つの必須確認項目。id は i18n キー(AggressiveDisclosure.items.<id>.{title,detail})に対応。
const ITEM_IDS = ["funds_locked", "pt_backed", "slippage"] as const;
type ItemId = (typeof ITEM_IDS)[number];

interface Props {
  onConsented: () => void;
  onCancel: () => void;
}

function getToken(): string {
  if (typeof window === "undefined") return "";
  return localStorage.getItem("ultra_auth_token") ?? "";
}

export default function AggressiveRiskDisclosureModal({ onConsented, onCancel }: Props) {
  const t = useTranslations("AggressiveDisclosure");
  const [checked, setChecked] = useState<Record<ItemId, boolean>>({
    funds_locked: false,
    pt_backed: false,
    slippage: false,
  });
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const allChecked = ITEM_IDS.every((id) => checked[id]);

  const handleConsent = async () => {
    if (!allChecked || submitting) return;
    setSubmitting(true);
    setError(null);
    try {
      const res = await fetch(`${API_BASE}/api/user/aggressive-consent`, {
        method: "POST",
        headers: { Authorization: `Bearer ${getToken()}` },
      });
      if (!res.ok) throw new Error(`Failed: ${res.status}`);
      onConsented();
    } catch (e) {
      setError(e instanceof Error ? e.message : t("error"));
    } finally {
      setSubmitting(false);
    }
  };

  const checkboxClass =
    "mt-0.5 w-5 h-5 rounded border-zinc-600 bg-zinc-800 text-orange-500 focus:ring-orange-500 focus:ring-offset-zinc-900 cursor-pointer";

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm">
      <div className="mx-4 w-full max-w-lg rounded-2xl border border-orange-800/60 bg-zinc-900 p-8 shadow-2xl">
        <h2 className="mb-2 text-xl font-bold text-zinc-100">🚀 {t("title")}</h2>
        <p className="mb-6 text-sm text-zinc-400">{t("subtitle")}</p>

        <div className="space-y-4">
          {ITEM_IDS.map((id) => (
            <label key={id} className="flex items-start gap-3 cursor-pointer group">
              <input
                type="checkbox"
                checked={checked[id]}
                onChange={(e) => setChecked({ ...checked, [id]: e.target.checked })}
                className={checkboxClass}
              />
              <div>
                <span className="text-sm font-medium text-zinc-200 group-hover:text-white">
                  {t(`items.${id}.title`)}
                </span>
                <p className="mt-1 text-xs text-zinc-500">{t(`items.${id}.detail`)}</p>
              </div>
            </label>
          ))}
        </div>

        {error && (
          <div className="mt-4 rounded-lg border border-red-800 bg-red-950/30 p-3 text-sm text-red-400">
            {error}
          </div>
        )}

        <div className="mt-6 flex gap-3">
          <button
            onClick={onCancel}
            disabled={submitting}
            className="flex-1 rounded-lg border border-zinc-700 py-3 text-sm font-medium text-zinc-300 hover:bg-zinc-800 disabled:opacity-60"
          >
            {t("cancelBtn")}
          </button>
          <button
            onClick={handleConsent}
            disabled={!allChecked || submitting}
            className={`flex-1 rounded-lg py-3 text-sm font-bold transition-all ${
              allChecked
                ? "bg-orange-600 text-white hover:bg-orange-500"
                : "bg-zinc-800 text-zinc-500 cursor-not-allowed"
            }`}
          >
            {submitting ? t("submitting") : t("submitBtn")}
          </button>
        </div>
      </div>
    </div>
  );
}
