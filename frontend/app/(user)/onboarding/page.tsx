// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.
"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth";
import { logUserAction } from "@/lib/api/user_actions";
import { LegalGate } from "@/components/onboarding/LegalGate";

// P5 onboarding flow: welcome → login 確認 → 入金確認 (USDC >= $200) → manual UI 説明 → main
//
// 仕様:
//  - 各ステップは「完了条件」を持ち、満たすまで「次へ」は disabled。
//  - 完了状態は localStorage(`uata.onboarding.completed`) に保存。タブを閉じても残る。
//  - 既完了 user は main アプリ(/user/approve) へ自動遷移。
//  - USDC 入金ステップは P2-onramp の UsdcOnrampCard 未 merge のため placeholder + TODO。
//  - manual UI 説明ステップは「機能説明用」を繰り返し提示 + 法務文言の確認チェックを必須化。
//  - 法務 sign-off 前 banner (LegalGate) を画面上部に常設。
const ONBOARDING_STORAGE_KEY = "uata.onboarding.completed";
const ONBOARDING_PROGRESS_KEY = "uata.onboarding.progress"; // 各ステップの完了 flag を保存

type StepId = 1 | 2 | 3 | 4;

interface StepProgress {
  step1_welcome_read: boolean;
  step2_logged_in: boolean;
  step3_deposit_ok: boolean;
  step4_legal_ack: boolean;
  step4_manual_ui_read: boolean;
}

const DEFAULT_PROGRESS: StepProgress = {
  step1_welcome_read: false,
  step2_logged_in: false,
  step3_deposit_ok: false,
  step4_legal_ack: false,
  step4_manual_ui_read: false,
};

interface StepDetail {
  text: string;
  link?: string;
  warning?: string;
}

interface StepDef {
  id: StepId;
  title: string;
  emoji: string;
  description: string;
  details: StepDetail[];
  tip?: string;
  /** このステップを完了とみなすラベル（UI に表示） */
  completionLabel: string;
}

const steps: StepDef[] = [
  {
    id: 1,
    title: "ようこそ Ultra AutoTrade へ",
    emoji: "👋",
    description:
      "AI が DeFi 運用を全自動で実行します。まずは 4 つのステップで準備を整えましょう。",
    details: [
      { text: "AI が市場・リスク・マクロ・行動の 4 観点を常時監視" },
      { text: "提案 → 実行はスケジューラが全自動で処理" },
      { text: "あなたは進捗を確認するだけ" },
    ],
    tip: "本オンボーディングは約 3 分で完了します。",
    completionLabel: "イントロを読了したら次へ",
  },
  {
    id: 2,
    title: "ログイン状態を確認",
    emoji: "🔐",
    description: "Privy 経由でログインが完了していることを確認します。",
    details: [
      { text: "ログイン済みであれば次へ進めます" },
      { text: "未ログインの場合は /login へリダイレクト" },
      {
        text: "ウォレット連携も Privy が代行（秘密鍵は当社で扱いません）",
      },
    ],
    tip: "依存: P1 (Privy MVP)。本ステップは Privy セッションが有効である前提です。",
    completionLabel: "Privy login 済が確認できれば自動で完了",
  },
  {
    id: 3,
    title: "USDC を入金（最低 $200）",
    emoji: "💵",
    description:
      "運用元本となる USDC を Ultra AutoTrade ウォレットに入金します。残高 ≥ $200 で次へ進めます。",
    details: [
      { text: "オンランプ経由でクレジットカード等から USDC を購入" },
      { text: "既存ウォレットからの直接送金にも対応" },
      {
        text: "入金確認は P2-onramp の UsdcOnrampCard コンポーネントで実施",
      },
    ],
    tip: "依存: P2-onramp (UsdcOnrampCard)。未 merge の現状は placeholder を表示します。",
    completionLabel: "USDC 残高 ≥ $200 を満たすと完了",
  },
  {
    id: 4,
    title: "Manual UI の使い方（display-only）",
    emoji: "🧭",
    description:
      "/approve ページの説明です。実取引は AI が全自動で行うため、本画面は display-only(機能説明用)です。",
    details: [
      { text: "AI の提案カードを確認できます" },
      { text: "「承認 / 却下」ボタンは UI 操作のログにのみ記録されます" },
      { text: "実取引はスケジューラが自動執行（あなたの署名は不要）" },
      {
        text: "本機能は機能説明用です。実取引は全自動で実行されます。",
        warning: "実取引 API は本画面から呼ばれません",
      },
    ],
    tip: "/approve に進むと提案一覧が確認できます。",
    completionLabel: "法務文言の確認 + manual UI 説明の読了で完了",
  },
];

const faqs = [
  {
    q: "最低いくらから始められますか？",
    a: "最低金額の制限はありませんが、ガス代を考慮すると100 USDC以上を推奨します。少額だとガス代の比率が高くなり、利回りが相殺される可能性があります。",
  },
  {
    q: "損失のリスクはありますか？",
    a: "はい。暗号資産のDeFi運用には元本を失うリスクがあります。AIが最適な判断を支援しますが、市場リスク・スマートコントラクトリスク・清算リスクなどがあります。詳しくはリスク開示書をお読みください。",
  },
  {
    q: "AIが勝手に取引しますか？",
    a: "本サービスはAIスケジューラが全自動で実行します。manual UI(/approve)はあくまで機能説明用の display-only であり、ボタン操作で実取引が発生することはありません。本機能は機能説明用です。",
  },
  {
    q: "やめたいときはどうすればいいですか？",
    a: "いつでも資産をAaveから引き出せます。Ultra AutoTradeを解除した後も、資産はあなたのウォレットに残ります。引き出しに必要なのはガス代のみです。",
  },
];

function loadProgress(): StepProgress {
  if (typeof window === "undefined") return DEFAULT_PROGRESS;
  try {
    const raw = window.localStorage.getItem(ONBOARDING_PROGRESS_KEY);
    if (!raw) return DEFAULT_PROGRESS;
    const parsed = JSON.parse(raw) as Partial<StepProgress>;
    return { ...DEFAULT_PROGRESS, ...parsed };
  } catch {
    return DEFAULT_PROGRESS;
  }
}

function persistProgress(p: StepProgress): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(ONBOARDING_PROGRESS_KEY, JSON.stringify(p));
  } catch {
    // QuotaExceeded などは無視
  }
}

function markCompletedFlag(): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(ONBOARDING_STORAGE_KEY, "true");
  } catch {
    // ignore
  }
}

function isAlreadyCompleted(): boolean {
  if (typeof window === "undefined") return false;
  try {
    return window.localStorage.getItem(ONBOARDING_STORAGE_KEY) === "true";
  } catch {
    return false;
  }
}

function StepCard({
  step,
  isActive,
  isComplete,
  onClick,
  children,
}: {
  step: StepDef;
  isActive: boolean;
  isComplete: boolean;
  onClick: () => void;
  children?: React.ReactNode;
}) {
  return (
    <div
      onClick={onClick}
      className={`rounded-xl border p-5 cursor-pointer transition-all ${
        isActive
          ? "border-blue-500 bg-blue-950/20"
          : isComplete
            ? "border-emerald-700 bg-emerald-950/10"
            : "border-zinc-800 bg-zinc-900/40 hover:border-zinc-600"
      }`}
      data-step-id={step.id}
      data-step-complete={isComplete}
    >
      <div className="flex items-center gap-3 mb-3">
        <span className="text-3xl">{step.emoji}</span>
        <div className="flex-1">
          <div className="flex items-center gap-2">
            <span
              className={`text-xs font-bold px-2 py-0.5 rounded ${
                isActive
                  ? "bg-blue-600 text-white"
                  : isComplete
                    ? "bg-emerald-600 text-white"
                    : "bg-zinc-800 text-zinc-400"
              }`}
            >
              STEP {step.id}
            </span>
            {isComplete && (
              <span className="text-xs text-emerald-400" aria-label="完了">
                ✓ 完了
              </span>
            )}
          </div>
          <h3 className="text-lg font-bold text-zinc-100 mt-1">{step.title}</h3>
        </div>
      </div>
      <p className="text-sm text-zinc-400 mb-4">{step.description}</p>

      {isActive && (
        <div className="space-y-3">
          <div className="space-y-2">
            {step.details.map((d, i) => (
              <div key={i} className="flex items-start gap-2">
                <span className="text-blue-400 text-sm mt-0.5">●</span>
                <div>
                  {d.link ? (
                    <a
                      href={d.link}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-sm text-blue-400 hover:underline"
                    >
                      {d.text} ↗
                    </a>
                  ) : (
                    <span className="text-sm text-zinc-300">{d.text}</span>
                  )}
                  {d.warning && (
                    <p className="text-xs text-red-400 mt-1">⚠️ {d.warning}</p>
                  )}
                </div>
              </div>
            ))}
          </div>
          {children}
          <div className="rounded-lg bg-zinc-800/40 border border-zinc-700 p-3">
            <p className="text-xs text-zinc-400">
              <span className="font-semibold text-zinc-300">完了条件:</span>{" "}
              {step.completionLabel}
            </p>
          </div>
          {step.tip && (
            <div className="rounded-lg bg-zinc-800/50 border border-zinc-700 p-3">
              <p className="text-xs text-zinc-400">💡 {step.tip}</p>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export default function OnboardingPage() {
  const router = useRouter();
  const auth = useAuth();
  const [activeStep, setActiveStep] = useState<StepId>(1);
  const [openFaq, setOpenFaq] = useState<number | null>(null);
  const [progress, setProgress] = useState<StepProgress>(DEFAULT_PROGRESS);
  const [hydrated, setHydrated] = useState(false);

  // hydration: localStorage 読み出し → 完了済なら即 redirect
  useEffect(() => {
    setHydrated(true);
    if (isAlreadyCompleted()) {
      router.replace("/user/approve");
      return;
    }
    setProgress(loadProgress());
  }, [router]);

  // Privy login 状態に応じて step2 を自動完了
  useEffect(() => {
    if (!hydrated) return;
    if (auth.isAuthenticated && !progress.step2_logged_in) {
      setProgress((p) => {
        const next = { ...p, step2_logged_in: true };
        persistProgress(next);
        return next;
      });
    }
  }, [hydrated, auth.isAuthenticated, progress.step2_logged_in]);

  const isStepComplete = useCallback(
    (id: StepId): boolean => {
      switch (id) {
        case 1:
          return progress.step1_welcome_read;
        case 2:
          return progress.step2_logged_in;
        case 3:
          return progress.step3_deposit_ok;
        case 4:
          return progress.step4_legal_ack && progress.step4_manual_ui_read;
      }
    },
    [progress],
  );

  const canAdvance = useMemo(
    () => isStepComplete(activeStep),
    [isStepComplete, activeStep],
  );

  const allComplete = useMemo(
    () => steps.every((s) => isStepComplete(s.id)),
    [isStepComplete],
  );

  const goNext = useCallback(() => {
    if (!canAdvance) return;
    setActiveStep((s) => {
      const next = Math.min(steps.length, s + 1) as StepId;
      if (next !== s) {
        void logUserAction({
          action_type: "onboarding_step_advance",
          target_type: "onboarding_step",
          target_id: next,
          context_json: { from: s, to: next },
        });
      }
      return next;
    });
  }, [canAdvance]);

  const goPrev = useCallback(() => {
    setActiveStep((s) => Math.max(1, s - 1) as StepId);
  }, []);

  // ステップ 1 を「読了」マークするボタン用
  const markStep1Read = useCallback(() => {
    setProgress((p) => {
      if (p.step1_welcome_read) return p;
      const next = { ...p, step1_welcome_read: true };
      persistProgress(next);
      return next;
    });
  }, []);

  // ステップ 3: TODO(P2-onramp) merge 前の暫定として「入金済(テスト)」ボタンで完了させる。
  // 本実装では UsdcOnrampCard の残高チェック onComplete callback に置き換える。
  const markStep3DepositOk = useCallback(() => {
    setProgress((p) => {
      if (p.step3_deposit_ok) return p;
      const next = { ...p, step3_deposit_ok: true };
      persistProgress(next);
      return next;
    });
  }, []);

  const toggleStep4LegalAck = useCallback(() => {
    setProgress((p) => {
      const next = { ...p, step4_legal_ack: !p.step4_legal_ack };
      persistProgress(next);
      return next;
    });
  }, []);

  const toggleStep4ManualUiRead = useCallback(() => {
    setProgress((p) => {
      const next = { ...p, step4_manual_ui_read: !p.step4_manual_ui_read };
      persistProgress(next);
      return next;
    });
  }, []);

  const onCompleteOnboarding = useCallback(() => {
    if (!allComplete) return;
    markCompletedFlag();
    void logUserAction({
      action_type: "onboarding_completed",
      target_type: "onboarding_step",
      target_id: steps.length,
    });
    router.replace("/user/approve");
  }, [allComplete, router]);

  // active step が変わるたびに step1_welcome_read を auto-mark（読んだ扱い）
  useEffect(() => {
    if (activeStep > 1 && !progress.step1_welcome_read) {
      markStep1Read();
    }
  }, [activeStep, progress.step1_welcome_read, markStep1Read]);

  return (
    <div className="min-h-screen bg-zinc-950 text-zinc-100 p-6">
      <div className="max-w-3xl mx-auto space-y-8">
        {/* 法務 sign-off 前 banner */}
        <LegalGate />

        {/* Header */}
        <div className="text-center space-y-2">
          <h1 className="text-3xl font-bold">はじめに</h1>
          <p className="text-zinc-400">
            ログイン → 入金 → manual UI 説明 → メインアプリの 4 ステップで準備
          </p>
        </div>

        {/* Progress bar */}
        <div className="flex items-center gap-1" aria-label="進捗">
          {steps.map((s) => (
            <div
              key={s.id}
              className={`flex-1 h-1.5 rounded-full transition-all ${
                isStepComplete(s.id)
                  ? "bg-emerald-500"
                  : s.id <= activeStep
                    ? "bg-blue-500"
                    : "bg-zinc-800"
              }`}
            />
          ))}
        </div>

        {/* Steps */}
        <div className="space-y-4">
          {steps.map((step) => (
            <StepCard
              key={step.id}
              step={step}
              isActive={activeStep === step.id}
              isComplete={isStepComplete(step.id)}
              onClick={() => setActiveStep(step.id)}
            >
              {/* Step 2: login 状態の表示 */}
              {step.id === 2 && activeStep === 2 && (
                <div
                  className={`rounded-lg border p-4 ${
                    auth.isAuthenticated
                      ? "border-emerald-700 bg-emerald-950/20"
                      : "border-amber-700 bg-amber-950/20"
                  }`}
                >
                  {auth.isLoading ? (
                    <p className="text-xs text-zinc-400">確認中...</p>
                  ) : auth.isAuthenticated ? (
                    <p className="text-xs text-emerald-400">
                      ✓ Privy login が確認できました
                    </p>
                  ) : (
                    <div className="space-y-2">
                      <p className="text-xs text-amber-400">
                        未ログインです。下のリンクからログインしてください。
                      </p>
                      <a
                        href="/login?redirect=/user/onboarding"
                        className="inline-block text-xs text-blue-400 underline"
                      >
                        /login へ →
                      </a>
                    </div>
                  )}
                </div>
              )}

              {/* Step 3: P2-onramp 未 merge の placeholder */}
              {step.id === 3 && activeStep === 3 && (
                <div className="rounded-lg border border-dashed border-amber-700 bg-amber-950/20 p-4 space-y-3">
                  <p className="text-xs text-amber-400 font-semibold">
                    [Placeholder] UsdcOnrampCard
                  </p>
                  <p className="text-xs text-zinc-400">
                    TODO(P2-onramp): UsdcOnrampCard コンポーネント merge 後に差し替え。
                    残高 ≥ $200 のチェックも同コンポーネント側で実装予定。
                  </p>
                  <button
                    type="button"
                    onClick={markStep3DepositOk}
                    disabled={progress.step3_deposit_ok}
                    className="px-3 py-1.5 text-xs rounded bg-zinc-700 text-zinc-200 hover:bg-zinc-600 disabled:opacity-40 disabled:cursor-not-allowed"
                  >
                    {progress.step3_deposit_ok
                      ? "入金確認済 (テスト)"
                      : "入金済としてマーク (テスト)"}
                  </button>
                </div>
              )}

              {/* Step 4: manual UI 説明 + 法務文言確認 */}
              {step.id === 4 && activeStep === 4 && (
                <div className="space-y-3">
                  <div className="rounded-lg border border-zinc-700 bg-zinc-900/60 p-4">
                    <p className="text-xs font-semibold text-zinc-200 mb-2">
                      📷 manual UI スクリーンショット（イメージ）
                    </p>
                    <div className="rounded border border-dashed border-zinc-700 bg-zinc-950 p-6 text-center">
                      <p className="text-xs text-zinc-500">
                        [/approve ページのスクリーンショット placeholder]
                      </p>
                      <p className="text-[10px] text-zinc-600 mt-2">
                        提案カード一覧 + 承認/却下ボタン（display-only）
                      </p>
                    </div>
                    <p className="text-xs text-zinc-400 mt-3 leading-relaxed">
                      上記の承認/却下ボタンは <strong>機能説明用</strong>{" "}
                      です。クリックは UI 操作ログに記録されるだけで、実取引は発生しません。
                      実取引は AI スケジューラが全自動で実行します。
                      <strong>本機能は機能説明用です。</strong>
                    </p>
                  </div>

                  <label className="flex items-start gap-2 cursor-pointer rounded-lg border border-zinc-700 bg-zinc-900/40 p-3 hover:border-zinc-600">
                    <input
                      type="checkbox"
                      checked={progress.step4_legal_ack}
                      onChange={toggleStep4LegalAck}
                      className="mt-0.5"
                      data-testid="onboarding-step4-legal-ack"
                    />
                    <span className="text-xs text-zinc-300">
                      本サービスはノンカストディアルであり、manual UI は機能説明用 (display-only)
                      であることを理解しました。実取引は AI スケジューラが全自動で執行することに同意します。
                    </span>
                  </label>

                  <label className="flex items-start gap-2 cursor-pointer rounded-lg border border-zinc-700 bg-zinc-900/40 p-3 hover:border-zinc-600">
                    <input
                      type="checkbox"
                      checked={progress.step4_manual_ui_read}
                      onChange={toggleStep4ManualUiRead}
                      className="mt-0.5"
                      data-testid="onboarding-step4-manual-ui-read"
                    />
                    <span className="text-xs text-zinc-300">
                      manual UI の使い方（display-only であること）を読了しました。本機能は機能説明用です。
                    </span>
                  </label>
                </div>
              )}
            </StepCard>
          ))}
        </div>

        {/* Navigation buttons */}
        <div className="flex justify-between items-center gap-3">
          <button
            onClick={goPrev}
            disabled={activeStep === 1}
            className="px-4 py-2 text-sm rounded-lg bg-zinc-800 text-zinc-300 hover:bg-zinc-700 disabled:opacity-30 disabled:cursor-not-allowed"
          >
            ← 前へ
          </button>

          {activeStep < steps.length ? (
            <button
              onClick={goNext}
              disabled={!canAdvance}
              title={
                canAdvance
                  ? "次のステップへ"
                  : "完了条件を満たしてください"
              }
              className="px-4 py-2 text-sm rounded-lg bg-blue-600 text-white hover:bg-blue-500 disabled:opacity-30 disabled:cursor-not-allowed"
            >
              次へ →
            </button>
          ) : (
            <button
              onClick={onCompleteOnboarding}
              disabled={!allComplete}
              title={
                allComplete
                  ? "オンボーディング完了"
                  : "すべてのステップを完了してください"
              }
              data-testid="onboarding-complete-button"
              className="px-4 py-2 text-sm rounded-lg bg-emerald-600 text-white hover:bg-emerald-500 disabled:opacity-30 disabled:cursor-not-allowed"
            >
              完了してメインアプリへ →
            </button>
          )}
        </div>

        {/* Safety notice */}
        <div className="rounded-xl border border-emerald-800 bg-emerald-950/20 p-6">
          <h3 className="font-bold text-emerald-400 mb-3">
            🛡️ あなたの資産を守る仕組み
          </h3>
          <div className="space-y-2 text-sm text-zinc-400">
            <p>
              ✅{" "}
              <strong className="text-zinc-300">ノンカストディアル</strong>{" "}
              — あなたの秘密鍵は当社が管理しません
            </p>
            <p>
              ✅{" "}
              <strong className="text-zinc-300">display-only manual UI</strong>{" "}
              — manual UI は機能説明用です。実取引は AI が全自動で実行
            </p>
            <p>
              ✅ <strong className="text-zinc-300">緊急停止</strong>{" "}
              — Health Factorが危険水準になると自動ブレーキが作動
            </p>
            <p>
              ✅{" "}
              <strong className="text-zinc-300">4つのAIエージェント</strong>{" "}
              — 市場・リスク・マクロ・行動パターンを常時監視
            </p>
          </div>
        </div>

        {/* FAQ */}
        <div>
          <h2 className="text-xl font-bold mb-4">よくある質問</h2>
          <div className="space-y-2">
            {faqs.map((faq, i) => (
              <div
                key={i}
                className="rounded-lg border border-zinc-800 bg-zinc-900/40 overflow-hidden"
              >
                <button
                  onClick={() => setOpenFaq(openFaq === i ? null : i)}
                  className="w-full text-left px-4 py-3 flex items-center justify-between hover:bg-zinc-900/60 transition-colors"
                >
                  <span className="text-sm font-medium text-zinc-200">
                    {faq.q}
                  </span>
                  <span className="text-zinc-500 ml-4">
                    {openFaq === i ? "−" : "+"}
                  </span>
                </button>
                {openFaq === i && (
                  <div className="px-4 pb-4 border-t border-zinc-800">
                    <p className="text-sm text-zinc-400 leading-relaxed pt-3">
                      {faq.a}
                    </p>
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>

        {/* CTA: 最終ステップ完了後はメインアプリ(/approve)へ */}
        <div className="text-center py-6">
          <p className="text-xs text-zinc-500">
            本機能は機能説明用です。実取引は全自動で実行されます。
          </p>
        </div>
      </div>
    </div>
  );
}
