// Copyright (c) Ultra AutoTrade. All rights reserved.
"use client"

// 「完全おまかせ」の運用方針（安全重視 = Aave のみ / 利回り重視 = Aave + Pendle PT）を
// ユーザーが選ぶシート。OpModePanel から「おまかせ」タップ時に開く。
//
// 満期ロック（Pendle PT は満期まで出金不可）は Aave USDC とリスクの質が異なるため、
// インラインのトグルではなく専用シートで対比してから選ばせる。「利回り重視」確定後に
// リスク開示モーダル（3 項目全同意）→ Privy 再署名 が続く。
//
// 表記の注意: 想定利回り / 月利の数値は載せない（森先生 法務判断で月利目安表記は抵触）。
// 差は「出金できるか」「元本保証の有無」で表現する。
// 配色の注意: arobix テーマが `.arobix-root .text-white` を暗紫で !important 上書きするため
// LIFF 面では text-white を使わない（memory: project_arobix_text_white_override）。

import { Shield, TrendingUp } from "lucide-react"
import { useTranslations } from "next-intl"
import { useState } from "react"
import type { ManagedScope } from "@/lib/api/delegation"

interface Props {
  /** 現在の実効方針（両ゲートが通っているときのみ "yield"）。 */
  currentScope: ManagedScope
  /** 方針変更に Privy 再署名が要るか（既に委譲済みの場合）。 */
  requiresResignature: boolean
  busy: boolean
  onConfirm: (scope: ManagedScope) => void
  onCancel: () => void
}

export function ManagedScopeSheet({
  currentScope,
  requiresResignature,
  busy,
  onConfirm,
  onCancel,
}: Props) {
  const t = useTranslations("Liff.panels.opMode")
  const [selected, setSelected] = useState<ManagedScope>(currentScope)

  const OPTIONS: {
    id: ManagedScope
    label: string
    protocols: string
    points: string[]
    caution: boolean
    icon: typeof Shield
  }[] = [
    {
      id: "safety",
      label: t("scopeSafetyLabel"),
      protocols: t("scopeSafetyProtocols"),
      points: [t("scopeSafetyPoint1"), t("scopeSafetyPoint2")],
      caution: false,
      icon: Shield,
    },
    {
      id: "yield",
      label: t("scopeYieldLabel"),
      protocols: t("scopeYieldProtocols"),
      points: [t("scopeYieldPoint1"), t("scopeYieldPoint2")],
      caution: true,
      icon: TrendingUp,
    },
  ]

  return (
    <div
      className="fixed inset-0 z-[70] flex items-end justify-center bg-black/50 sm:items-center"
      data-testid="managed-scope-sheet"
    >
      <div className="w-full max-w-md rounded-t-2xl bg-[#fbf7f0] p-5 sm:rounded-2xl">
        <h2 className="text-lg font-bold text-[#1c1a27]">{t("scopeSheetTitle")}</h2>
        <p className="mt-1 text-sm text-[#736f7e]">{t("scopeSheetSubtitle")}</p>

        <div className="mt-4 space-y-3">
          {OPTIONS.map((opt) => {
            const Icon = opt.icon
            const isSelected = selected === opt.id
            return (
              <button
                key={opt.id}
                type="button"
                data-testid={`managed-scope-option-${opt.id}`}
                aria-pressed={isSelected}
                disabled={busy}
                onClick={() => setSelected(opt.id)}
                className={[
                  "w-full rounded-2xl border-2 p-4 text-left transition-all",
                  opt.caution ? "bg-amber-500/10" : "bg-[#1D9E75]/10",
                  isSelected
                    ? opt.caution
                      ? "border-amber-500 opacity-100"
                      : "border-[#1D9E75] opacity-100"
                    : "border-[#1c1a27]/15 opacity-60",
                  busy ? "cursor-not-allowed" : "",
                ].join(" ")}
              >
                <div className="flex items-start gap-3">
                  <Icon
                    className={`mt-0.5 h-5 w-5 shrink-0 ${
                      opt.caution ? "text-amber-600" : "text-[#1D9E75]"
                    }`}
                  />
                  <div className="min-w-0">
                    <p className="text-base font-bold text-[#1c1a27]">{opt.label}</p>
                    <p className="mt-0.5 text-sm text-[#736f7e]">{opt.protocols}</p>
                    <ul className="mt-2 space-y-1">
                      {opt.points.map((point) => (
                        <li key={point} className="text-xs text-[#736f7e]">
                          {opt.caution ? "⚠ " : "・"}
                          {point}
                        </li>
                      ))}
                    </ul>
                  </div>
                </div>
              </button>
            )
          })}
        </div>

        {/* 段階A（dry-run）注記: セレクタは表示するが Pendle の実運用はまだ開始しない。
            選択は記録されるが「利回り重視で運用が始まっている」と誤認させないよう明示する。
            PENDLE_ENABLE_ONCHAIN_WRITE 有効化（段階B以降）でこの注記を外す。 */}
        {selected === "yield" && (
          <p
            className="mt-4 rounded-lg border border-amber-500/30 bg-amber-500/10 p-3 text-xs text-amber-700"
            data-testid="managed-scope-preparing-notice"
          >
            {t("scopeYieldPreparingNotice")}
          </p>
        )}

        {/* 委譲枠は consent 時点で固定されるため、範囲を変えるには Privy 再署名が要る。
            黙って古い枠のまま表示だけ変えない（TEE 側は旧 allowlist を enforce し続ける）。 */}
        {requiresResignature && selected !== currentScope && (
          <p
            className="mt-4 rounded-lg border border-[#1c1a27]/15 bg-[#1c1a27]/5 p-3 text-xs text-[#736f7e]"
            data-testid="managed-scope-resign-notice"
          >
            {t("scopeResignatureNotice")}
          </p>
        )}

        <div className="mt-5 flex gap-3">
          <button
            type="button"
            onClick={onCancel}
            disabled={busy}
            data-testid="managed-scope-cancel"
            className="flex-1 rounded-lg border border-[#1c1a27]/20 py-3 text-sm font-medium text-[#1c1a27] disabled:opacity-60"
          >
            {t("scopeCancelBtn")}
          </button>
          <button
            type="button"
            onClick={() => onConfirm(selected)}
            disabled={busy}
            data-testid="managed-scope-confirm"
            className="flex-1 rounded-lg bg-[#1D9E75] py-3 text-sm font-bold text-[#fbf7f0] disabled:opacity-60"
          >
            {busy ? t("scopeSubmitting") : t("scopeConfirmBtn")}
          </button>
        </div>
      </div>
    </div>
  )
}
