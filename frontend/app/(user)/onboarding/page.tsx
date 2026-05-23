// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.
"use client";

import { useState } from "react";
import { logUserAction } from "@/lib/api/user_actions";

// P5 onboarding flow: welcome → login 確認 → 入金確認 (USDC >= $200) → manual UI 説明 → main
// 仕様: 各ステップは「次へ」で進む。step state は useState。
// 入金確認は P2-onramp の UsdcOnrampCard を呼ぶ前提だが、未 merge の現状は placeholder。
const steps = [
  {
    id: 1,
    title: "ようこそ Ultra AutoTrade へ",
    emoji: "👋",
    description: "AI が DeFi 運用を全自動で実行します。まずは 4 つのステップで準備を整えましょう。",
    details: [
      { text: "AI が市場・リスク・マクロ・行動の 4 観点を常時監視" },
      { text: "提案 → 実行はスケジューラが全自動で処理" },
      { text: "あなたは進捗を確認するだけ" },
    ],
    tip: "本オンボーディングは約 3 分で完了します。",
  },
  {
    id: 2,
    title: "ログイン状態を確認",
    emoji: "🔐",
    description: "Privy 経由でログインが完了していることを確認します。",
    details: [
      { text: "ログイン済みであれば次へ進めます" },
      { text: "未ログインの場合は /login へリダイレクト" },
      { text: "ウォレット連携も Privy が代行（秘密鍵は当社で扱いません）" },
    ],
    tip: "依存: P1 (Privy MVP)。本ステップは Privy セッションが有効である前提です。",
  },
  {
    id: 3,
    title: "USDC を入金（最低 $200）",
    emoji: "💵",
    description: "運用元本となる USDC を Ultra AutoTrade ウォレットに入金します。残高 ≥ $200 で次へ進めます。",
    details: [
      { text: "オンランプ経由でクレジットカード等から USDC を購入" },
      { text: "既存ウォレットからの直接送金にも対応" },
      { text: "入金確認は P2-onramp の UsdcOnrampCard コンポーネントで実施" },
    ],
    tip: "依存: P2-onramp (UsdcOnrampCard)。未 merge の現状は placeholder を表示します。",
  },
  {
    id: 4,
    title: "Manual UI の使い方（display-only）",
    emoji: "🧭",
    description: "/approve ページの説明です。実取引は AI が全自動で行うため、本画面は display-only(機能説明用)です。",
    details: [
      { text: "AI の提案カードを確認できます" },
      { text: "「承認 / 却下」ボタンは UI 操作のログにのみ記録されます" },
      { text: "実取引はスケジューラが自動執行（あなたの署名は不要）" },
      { text: "本機能は機能説明用です。実取引は全自動で実行されます。", warning: "実取引 API は本画面から呼ばれません" },
    ],
    tip: "/approve に進むと提案一覧が確認できます。",
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
    a: "いいえ。AIは「提案」するだけです。実際の預け入れ・引き出しには、必ずあなたのMetaMaskでの署名（承認）が必要です。署名しない限り資産は動きません。",
  },
  {
    q: "やめたいときはどうすればいいですか？",
    a: "いつでも資産をAaveから引き出せます。Ultra AutoTradeを解除した後も、資産はあなたのウォレットに残ります。引き出しに必要なのはガス代のみです。",
  },
];

interface StepDetail {
  text: string;
  link?: string;
  warning?: string;
}

interface Step {
  id: number;
  title: string;
  emoji: string;
  description: string;
  details: StepDetail[];
  tip?: string;
}

function StepCard({
  step,
  isActive,
  onClick,
}: {
  step: Step;
  isActive: boolean;
  onClick: () => void;
}) {
  return (
    <div
      onClick={onClick}
      className={`rounded-xl border p-5 cursor-pointer transition-all ${
        isActive
          ? "border-blue-500 bg-blue-950/20"
          : "border-zinc-800 bg-zinc-900/40 hover:border-zinc-600"
      }`}
    >
      <div className="flex items-center gap-3 mb-3">
        <span className="text-3xl">{step.emoji}</span>
        <div>
          <span
            className={`text-xs font-bold px-2 py-0.5 rounded ${
              isActive ? "bg-blue-600 text-white" : "bg-zinc-800 text-zinc-400"
            }`}
          >
            STEP {step.id}
          </span>
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
          {/* P5: step 3 (入金) は P2-onramp の UsdcOnrampCard を呼ぶ placeholder */}
          {step.id === 3 && (
            <div className="rounded-lg border border-dashed border-amber-700 bg-amber-950/20 p-4">
              <p className="text-xs text-amber-400 mb-1 font-semibold">
                [Placeholder] UsdcOnrampCard
              </p>
              <p className="text-xs text-zinc-400">
                TODO(P2-onramp): UsdcOnrampCard コンポーネント merge 後に差し替え。
                残高 ≥ $200 のチェックも同コンポーネント側で実装予定。
              </p>
            </div>
          )}
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
  const [activeStep, setActiveStep] = useState(1);
  const [openFaq, setOpenFaq] = useState<number | null>(null);

  const goNext = () => {
    setActiveStep((s) => {
      const next = Math.min(steps.length, s + 1);
      if (next !== s) {
        void logUserAction({
          action_type: "onboarding_step_advance",
          target_type: "onboarding_step",
          target_id: next,
          context_json: { from: s, to: next },
        });
      }
      if (next === steps.length && s !== steps.length) {
        void logUserAction({
          action_type: "onboarding_completed",
          target_type: "onboarding_step",
          target_id: steps.length,
        });
      }
      return next;
    });
  };
  const goPrev = () => setActiveStep((s) => Math.max(1, s - 1));

  return (
    <div className="min-h-screen bg-zinc-950 text-zinc-100 p-6">
      <div className="max-w-3xl mx-auto space-y-8">
        {/* Header */}
        <div className="text-center space-y-2">
          <h1 className="text-3xl font-bold">はじめに</h1>
          <p className="text-zinc-400">
            ログイン → 入金 → manual UI 説明 → メインアプリの 4 ステップで準備
          </p>
        </div>

        {/* Progress bar */}
        <div className="flex items-center gap-1">
          {steps.map((s) => (
            <div
              key={s.id}
              className={`flex-1 h-1.5 rounded-full transition-all ${
                s.id <= activeStep ? "bg-blue-500" : "bg-zinc-800"
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
              onClick={() => setActiveStep(step.id)}
            />
          ))}
        </div>

        {/* Navigation buttons */}
        <div className="flex justify-between">
          <button
            onClick={goPrev}
            disabled={activeStep === 1}
            className="px-4 py-2 text-sm rounded-lg bg-zinc-800 text-zinc-300 hover:bg-zinc-700 disabled:opacity-30 disabled:cursor-not-allowed"
          >
            ← 前へ
          </button>
          <button
            onClick={goNext}
            disabled={activeStep === steps.length}
            className="px-4 py-2 text-sm rounded-lg bg-blue-600 text-white hover:bg-blue-500 disabled:opacity-30 disabled:cursor-not-allowed"
          >
            次へ →
          </button>
        </div>

        {/* Safety notice */}
        <div className="rounded-xl border border-emerald-800 bg-emerald-950/20 p-6">
          <h3 className="font-bold text-emerald-400 mb-3">🛡️ あなたの資産を守る仕組み</h3>
          <div className="space-y-2 text-sm text-zinc-400">
            <p>
              ✅ <strong className="text-zinc-300">ノンカストディアル</strong>{" "}
              — あなたの秘密鍵は当社が管理しません
            </p>
            <p>
              ✅ <strong className="text-zinc-300">署名が必須</strong>{" "}
              — AIの提案を実行するにはあなたの承認が必要です
            </p>
            <p>
              ✅ <strong className="text-zinc-300">緊急停止</strong>{" "}
              — Health Factorが危険水準になると自動ブレーキが作動
            </p>
            <p>
              ✅ <strong className="text-zinc-300">4つのAIエージェント</strong>{" "}
              — 市場・リスク・マクロ・行動パターンを常時監視
            </p>
          </div>
        </div>

        {/* FAQ */}
        <div>
          <h2 className="text-xl font-bold mb-4">よくある質問</h2>
          <div className="space-y-2">
            {faqs.map((faq, i) => (
              <div key={i} className="rounded-lg border border-zinc-800 bg-zinc-900/40 overflow-hidden">
                <button
                  onClick={() => setOpenFaq(openFaq === i ? null : i)}
                  className="w-full text-left px-4 py-3 flex items-center justify-between hover:bg-zinc-900/60 transition-colors"
                >
                  <span className="text-sm font-medium text-zinc-200">{faq.q}</span>
                  <span className="text-zinc-500 ml-4">{openFaq === i ? "−" : "+"}</span>
                </button>
                {openFaq === i && (
                  <div className="px-4 pb-4 border-t border-zinc-800">
                    <p className="text-sm text-zinc-400 leading-relaxed pt-3">{faq.a}</p>
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>

        {/* CTA: 最終ステップ完了後はメインアプリ(/approve)へ */}
        <div className="text-center py-6">
          <a
            href="/user/approve"
            className="inline-block rounded-lg bg-blue-600 px-8 py-3 text-sm font-bold text-white hover:bg-blue-500 transition-all"
          >
            メインアプリへ進む →
          </a>
          {/* P5 display-only label */}
          <p className="text-xs text-zinc-500 mt-3">
            本機能は機能説明用です。実取引は全自動で実行されます。
          </p>
        </div>
      </div>
    </div>
  );
}
