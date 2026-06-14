// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.
"use client";

import { useEffect, useState } from "react";
import { useTranslations } from "next-intl";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";

interface RiskOption {
  mode: string;
  label: string;
  description: string;
  max_utilization: number;
  min_health_factor: string;
  allowed_assets: string[];
  min_confidence: number;
}

interface RiskModeData {
  mode: string;
  options: RiskOption[];
}

function getToken(): string {
  if (typeof window === "undefined") return "";
  return localStorage.getItem("ultra_auth_token") ?? "";
}

const modeEmoji: Record<string, string> = {
  conservative: "🛡️",
  balanced: "⚖️",
  aggressive: "🚀",
};

const modeColor: Record<string, string> = {
  conservative: "border-emerald-500 bg-emerald-950/20 ring-emerald-500",
  balanced: "border-blue-500 bg-blue-950/20 ring-blue-500",
  aggressive: "border-orange-500 bg-orange-950/20 ring-orange-500",
};

export default function RiskModeSelector() {
  const t = useTranslations("SettingsRiskMode");
  const [data, setData] = useState<RiskModeData | null>(null);
  const [saving, setSaving] = useState(false);
  const [success, setSuccess] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const token = getToken();
    if (!token) return;
    fetch(`${API_BASE}/auth/risk-mode`, {
      headers: { Authorization: `Bearer ${token}` },
    })
      .then((r) => r.json())
      .then(setData)
      .catch(() => {});
  }, []);

  const handleSelect = async (mode: string) => {
    if (!data || data.mode === mode || saving) return;
    setSaving(true);
    setSuccess(null);
    setError(null);

    const token = getToken();
    try {
      const res = await fetch(`${API_BASE}/auth/risk-mode`, {
        method: "PUT",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({ mode }),
      });
      if (!res.ok) throw new Error(`Failed: ${res.status}`);
      const label = data.options.find((o) => o.mode === mode)?.label ?? mode;
      setData({ ...data, mode });
      setSuccess(t("successMessage", { label }));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed");
    } finally {
      setSaving(false);
    }
  };

  if (!data) return <div className="animate-pulse h-40 bg-zinc-800 rounded-xl" />;

  return (
    <div className="space-y-4">
      <div>
        <h3 className="text-lg font-bold text-zinc-100">{t("title")}</h3>
        <p className="text-sm text-zinc-400 mt-1">{t("description")}</p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {data.options.map((opt) => {
          const isActive = data.mode === opt.mode;
          return (
            <button
              key={opt.mode}
              onClick={() => handleSelect(opt.mode)}
              disabled={saving}
              className={`text-left rounded-xl border-2 p-5 transition-all disabled:opacity-60 ${
                isActive
                  ? `${modeColor[opt.mode]} ring-2`
                  : "border-zinc-700 bg-zinc-900/40 hover:border-zinc-500"
              }`}
            >
              <div className="flex items-center gap-2 mb-2">
                <span className="text-2xl">{modeEmoji[opt.mode]}</span>
                <span className="font-bold text-zinc-100">{opt.label}</span>
                {isActive && (
                  <span className="ml-auto text-xs px-2 py-0.5 rounded bg-zinc-800 text-zinc-300">
                    {t("currentBadge")}
                  </span>
                )}
              </div>
              <p className="text-sm text-zinc-400 mb-3">{opt.description}</p>
              <div className="space-y-1 text-xs text-zinc-500">
                <div className="flex justify-between">
                  <span>{t("maxUtilization")}</span>
                  <span className="text-zinc-300">{opt.max_utilization}%</span>
                </div>
                <div className="flex justify-between">
                  <span>{t("minHealthFactor")}</span>
                  <span className="text-zinc-300">{opt.min_health_factor}</span>
                </div>
                <div className="flex justify-between">
                  <span>{t("minConfidence")}</span>
                  <span className="text-zinc-300">{opt.min_confidence}%</span>
                </div>
                <div className="flex justify-between">
                  <span>{t("allowedAssets")}</span>
                  <span className="text-zinc-300 text-right">{opt.allowed_assets.join(", ")}</span>
                </div>
              </div>
            </button>
          );
        })}
      </div>

      {success && (
        <div className="rounded-lg border border-emerald-800 bg-emerald-950/30 p-3 text-sm text-emerald-400">
          ✅ {success}
        </div>
      )}
      {error && (
        <div className="rounded-lg border border-red-800 bg-red-950/30 p-3 text-sm text-red-400">
          ❌ {error}
        </div>
      )}

      <div className="rounded-lg bg-zinc-800/50 border border-zinc-700 p-4">
        <p className="text-xs text-zinc-500">
          💡 {t("aggressiveNote")}
        </p>
      </div>
    </div>
  );
}
