// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.
"use client";

import { useState } from "react";

const steps = [
  {
    id: 1,
    title: "ウォレットを準備する",
    emoji: "👛",
    description: "MetaMaskをインストールして、ウォレットを作成します。",
    details: [
      { text: "MetaMask公式サイトにアクセス", link: "https://metamask.io/download/" },
      { text: "Chrome拡張機能をインストール" },
      { text: "「新しいウォレットを作成」を選択" },
      { text: "パスワードを設定（強力なものを使用）" },
      { text: "シードフレーズを安全な場所に保管", warning: "シードフレーズは絶対に誰にも教えないでください" },
    ],
    tip: "MetaMaskの代わりにRabby WalletやCoinbase Walletも使えます。",
  },
  {
    id: 2,
    title: "ネットワークを追加する",
    emoji: "🌐",
    description: "Base Sepoliaネットワークをウォレットに追加します。",
    details: [
      { text: "ChainListにアクセス", link: "https://chainlist.org/?search=base+sepolia&testnets=true" },
      { text: "「Base Sepolia」を検索して「Add to MetaMask」をクリック" },
      { text: "MetaMaskのポップアップで「承認」を選択" },
      { text: "MetaMaskの上部ネットワーク欄が「Base Sepolia」になっていることを確認" },
    ],
    tip: "ChainListを使うと、ネットワーク情報を手入力する必要がありません。",
  },
  {
    id: 3,
    title: "テスト用ETHを入手する",
    emoji: "💰",
    description: "ガス代用のテストETH（SepoliaETH）をウォレットに送金します。",
    details: [
      { text: "Coinbase Faucetにアクセス", link: "https://faucet.quicknode.com/base/sepolia" },
      { text: "ウォレットアドレスを入力してテストETHを受け取る" },
      { text: "MetaMaskに「Base Sepolia ETH」が届いたことを確認" },
    ],
    tip: "テストネットのため、実際の資産は不要です。フォーセットから無料でテストETHが取得できます。",
  },
  {
    id: 4,
    title: "Ultra AutoTradeに接続する",
    emoji: "🔗",
    description: "ウォレットをUltra AutoTradeに接続して運用を開始します。",
    details: [
      { text: "Ultra AutoTradeにログイン" },
      { text: "「ウォレット接続」ボタンをクリック" },
      { text: "MetaMaskのポップアップで接続を承認" },
      { text: "AIの提案を確認し、実行する場合は署名して承認" },
    ],
    tip: "接続はウォレットアドレスの読み取りのみです。当社が秘密鍵を聞くことは一切ありません。",
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

  return (
    <div className="min-h-screen bg-zinc-950 text-zinc-100 p-6">
      <div className="max-w-3xl mx-auto space-y-8">
        {/* Header */}
        <div className="text-center space-y-2">
          <h1 className="text-3xl font-bold">はじめに</h1>
          <p className="text-zinc-400">
            Ultra AutoTradeで資産運用を始めるための4つのステップ
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
            onClick={() => setActiveStep((s) => Math.max(1, s - 1))}
            disabled={activeStep === 1}
            className="px-4 py-2 text-sm rounded-lg bg-zinc-800 text-zinc-300 hover:bg-zinc-700 disabled:opacity-30 disabled:cursor-not-allowed"
          >
            ← 前のステップ
          </button>
          <button
            onClick={() => setActiveStep((s) => Math.min(steps.length, s + 1))}
            disabled={activeStep === steps.length}
            className="px-4 py-2 text-sm rounded-lg bg-blue-600 text-white hover:bg-blue-500 disabled:opacity-30 disabled:cursor-not-allowed"
          >
            次のステップ →
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

        {/* CTA */}
        <div className="text-center py-6">
          <a
            href="/user/wallet"
            className="inline-block rounded-lg bg-blue-600 px-8 py-3 text-sm font-bold text-white hover:bg-blue-500 transition-all"
          >
            ウォレットを接続して始める →
          </a>
        </div>
      </div>
    </div>
  );
}
