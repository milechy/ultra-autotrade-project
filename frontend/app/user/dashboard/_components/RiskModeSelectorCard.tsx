// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.
"use client";

import { useState } from "react";
import { useAuth } from "@/lib/auth";
import { useAuthFetch } from "@/hooks/useAuthFetch";
import { apiPut } from "@/lib/api/client";

type RiskModeValue =
  | "conservative"
  | "balanced"
  | "aggressive"
  | "custom";

interface CustomRiskParams {
  hf_lower_bound: number;
  supply_ratio: number;
  max_position_size_usd: number;
}

interface RiskOption {
  mode: RiskModeValue;
  label: string;
  description: string;
  max_utilization: number;
  min_health_factor: string;
  allowed_assets: string[];
  min_confidence: number;
}

interface RiskModeData {
  mode: RiskModeValue;
  options: RiskOption[];
}

interface UpdateRiskModeResponse {
  mode: string;
  label: string;
  message: string;
}

const MODE_EMOJI: Record<RiskModeValue, string> = {
  conservative: "🛡️",
  balanced: "⚖️",
  aggressive: "🚀",
  custom: "⚙️",
};

const MODE_COLOR: Record<RiskModeValue, string> = {
  conservative: "border-emerald-500 bg-emerald-950/20 ring-emerald-500",
  balanced: "border-blue-500 bg-blue-950/20 ring-blue-500",
  aggressive: "border-orange-500 bg-orange-950/20 ring-orange-500",
  custom: "border-purple-500 bg-purple-950/20 ring-purple-500",
};

const DEFAULT_CUSTOM_PARAMS: CustomRiskParams = {
  hf_lower_bound: 1.8,
  supply_ratio: 0.5,
  max_position_size_usd: 1000,
};

export default function RiskModeSelectorCard() {
  const { isPartner } = useAuth();
  const { data, refetch } = useAuthFetch<RiskModeData>("/auth/risk-mode");

  const [saving, setSaving] = useState(false);
  const [success, setSuccess] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [showCustomForm, setShowCustomForm] = useState(false);
  const [customParams, setCustomParams] =
    useState<CustomRiskParams>(DEFAULT_CUSTOM_PARAMS);

  if (!data) {
    return <div className="animate-pulse h-40 bg-zinc-800 rounded-xl" />;
  }

  const visibleOptions = isPartner
    ? data.options
    : data.options.filter((o) => o.mode !== "custom");

  const handleSelect = async (mode: RiskModeValue) => {
    if (data.mode === mode || saving) return;

    if (mode === "custom") {
      setShowCustomForm(true);
      return;
    }
    setShowCustomForm(false);
    await submitMode(mode, undefined);
  };

  const submitMode = async (
    mode: RiskModeValue,
    params: CustomRiskParams | undefined,
  ) => {
    setSaving(true);
    setSuccess(null);
    setError(null);

    try {
      const body: { mode: string; custom_params?: CustomRiskParams } = {
        mode,
      };
      if (params) body.custom_params = params;

      await apiPut<UpdateRiskModeResponse>("/auth/risk-mode", body);
      await refetch();
      const label = data.options.find((o) => o.mode === mode)?.label ?? mode;
      setSuccess(`リスクモードを「${label}」に変更しました`);
      setShowCustomForm(false);
    } catch (e) {
      setError(e instanceof Error ? e.message : "変更に失敗しました");
    } finally {
      setSaving(false);
    }
  };

  const handleCustomSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    await submitMode("custom", customParams);
  };

  return (
    <div className="space-y-4">
      <div>
        <h3 className="text-lg font-bold text-zinc-100">リスクモード設定</h3>
        <p className="text-sm text-zinc-400 mt-1">
          運用スタイルに合わせてAIの判定基準が変わります。
          {isPartner && (
            <span className="ml-1 text-purple-400">
              パートナー向けカスタムモードが利用可能です。
            </span>
          )}
        </p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {visibleOptions.map((opt) => {
          const mode = opt.mode as RiskModeValue;
          const isActive = data.mode === mode;
          const isCustom = mode === "custom";

          return (
            <button
              key={mode}
              onClick={() => handleSelect(mode)}
              disabled={saving}
              className={`text-left rounded-xl border-2 p-5 transition-all disabled:opacity-60 ${
                isActive
                  ? `${MODE_COLOR[mode]} ring-2`
                  : "border-zinc-700 bg-zinc-900/40 hover:border-zinc-500"
              }`}
            >
              <div className="flex items-center gap-2 mb-2">
                <span className="text-2xl">{MODE_EMOJI[mode]}</span>
                <span className="font-bold text-zinc-100">{opt.label}</span>
                {isActive && (
                  <span className="ml-auto text-xs px-2 py-0.5 rounded bg-zinc-800 text-zinc-300">
                    現在
                  </span>
                )}
                {isCustom && (
                  <span className="text-xs px-2 py-0.5 rounded bg-purple-900/50 text-purple-300 border border-purple-700">
                    Partner限定
                  </span>
                )}
              </div>
              <p className="text-sm text-zinc-400 mb-3">
                {isCustom
                  ? "パートナー専用のカスタムパラメータで運用します"
                  : opt.description}
              </p>
              {!isCustom && (
                <div className="space-y-1 text-xs text-zinc-500">
                  <div className="flex justify-between">
                    <span>最大利用率</span>
                    <span className="text-zinc-300">{opt.max_utilization}%</span>
                  </div>
                  <div className="flex justify-between">
                    <span>最小 Health Factor</span>
                    <span className="text-zinc-300">{opt.min_health_factor}</span>
                  </div>
                  <div className="flex justify-between">
                    <span>必要信頼度</span>
                    <span className="text-zinc-300">{opt.min_confidence}%</span>
                  </div>
                </div>
              )}
              {isCustom && isActive && data.mode === "custom" && (
                <p className="text-xs text-purple-300 mt-2">
                  ⚙️ カスタムパラメータが適用中
                </p>
              )}
            </button>
          );
        })}
      </div>

      {/* CUSTOM モードパラメータ入力フォーム */}
      {showCustomForm && isPartner && (
        <form
          onSubmit={handleCustomSubmit}
          className="rounded-xl border-2 border-purple-700 bg-purple-950/20 p-5 space-y-4"
        >
          <h4 className="font-bold text-purple-300">
            ⚙️ カスタムモード パラメータ設定
          </h4>

          <div className="grid grid-cols-1 gap-4">
            <div>
              <label className="block text-sm text-zinc-400 mb-1">
                最小ヘルスファクター (1.3 〜 3.0)
              </label>
              <input
                type="number"
                step="0.1"
                min="1.3"
                max="3.0"
                value={customParams.hf_lower_bound}
                onChange={(e) =>
                  setCustomParams({
                    ...customParams,
                    hf_lower_bound: Number(e.target.value),
                  })
                }
                className="w-full bg-zinc-900 border border-zinc-600 rounded-lg px-3 py-2 text-zinc-100 focus:outline-none focus:border-purple-500"
                required
              />
            </div>

            <div>
              <label className="block text-sm text-zinc-400 mb-1">
                供給比率 (0.1 〜 0.9)
              </label>
              <input
                type="number"
                step="0.05"
                min="0.1"
                max="0.9"
                value={customParams.supply_ratio}
                onChange={(e) =>
                  setCustomParams({
                    ...customParams,
                    supply_ratio: Number(e.target.value),
                  })
                }
                className="w-full bg-zinc-900 border border-zinc-600 rounded-lg px-3 py-2 text-zinc-100 focus:outline-none focus:border-purple-500"
                required
              />
            </div>

            <div>
              <label className="block text-sm text-zinc-400 mb-1">
                最大ポジションサイズ USD (100 〜 100,000)
              </label>
              <input
                type="number"
                step="100"
                min="100"
                max="100000"
                value={customParams.max_position_size_usd}
                onChange={(e) =>
                  setCustomParams({
                    ...customParams,
                    max_position_size_usd: Number(e.target.value),
                  })
                }
                className="w-full bg-zinc-900 border border-zinc-600 rounded-lg px-3 py-2 text-zinc-100 focus:outline-none focus:border-purple-500"
                required
              />
            </div>
          </div>

          <div className="flex gap-3">
            <button
              type="submit"
              disabled={saving}
              className="flex-1 py-2 rounded-lg bg-purple-600 hover:bg-purple-500 disabled:opacity-60 text-white font-medium transition-colors"
            >
              {saving ? "保存中..." : "カスタムモードを適用"}
            </button>
            <button
              type="button"
              onClick={() => setShowCustomForm(false)}
              className="px-4 py-2 rounded-lg border border-zinc-600 hover:border-zinc-500 text-zinc-400 hover:text-zinc-300 transition-colors"
            >
              キャンセル
            </button>
          </div>

          <p className="text-xs text-zinc-500">
            ※ カスタムパラメータは森先生の法的レビュー後に本番適用されます。
          </p>
        </form>
      )}

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
    </div>
  );
}
