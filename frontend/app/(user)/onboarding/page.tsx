// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.
"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";

const STEP_KEYS = ["wallet", "network", "testEth", "connect"] as const;
type StepKey = (typeof STEP_KEYS)[number];

const FAQ_KEYS = ["minAmount", "lossRisk", "aiAutoTrade", "howToStop"] as const;
type FaqKey = (typeof FAQ_KEYS)[number];

const STEP_EMOJIS: Record<StepKey, string> = {
  wallet: "👛",
  network: "🌐",
  testEth: "💰",
  connect: "🔗",
};

const STEP_DETAIL_KEYS: Record<StepKey, string[]> = {
  wallet: ["site", "ext", "create", "password", "seed"],
  network: ["chainlist", "search", "approve", "verify"],
  testEth: ["faucet", "input", "verify"],
  connect: ["login", "clickConnect", "approve", "sign"],
};

const STEP_DETAIL_LINKS: Record<string, string> = {
  "wallet.site": "https://metamask.io/download/",
  "network.chainlist": "https://chainlist.org/?search=base+sepolia&testnets=true",
  "testEth.faucet": "https://faucet.quicknode.com/base/sepolia",
};

const STEP_DETAIL_WARNINGS = new Set(["wallet.seed"]);

const SAFETY_KEYS = [
  "nonCustodial",
  "signRequired",
  "emergencyStop",
  "fourAgents",
] as const;
type SafetyKey = (typeof SAFETY_KEYS)[number];

interface StepDetail {
  text: string;
  link?: string;
  warning?: string;
}

interface Step {
  id: number;
  key: StepKey;
  title: string;
  emoji: string;
  description: string;
  details: StepDetail[];
  tip?: string;
}

interface Faq {
  q: string;
  a: string;
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
  const t = useTranslations("Onboarding");
  const [activeStep, setActiveStep] = useState(1);
  const [openFaq, setOpenFaq] = useState<number | null>(null);

  const steps: Step[] = STEP_KEYS.map((key, idx) => {
    const detailKeys = STEP_DETAIL_KEYS[key];
    const details: StepDetail[] = detailKeys.map((dk) => {
      const linkKey = `${key}.${dk}`;
      const isWarning = STEP_DETAIL_WARNINGS.has(linkKey);
      return {
        text: t(`steps.${key}.details.${dk}`),
        link: STEP_DETAIL_LINKS[linkKey],
        warning: isWarning ? t(`steps.${key}.seedWarning`) : undefined,
      };
    });

    const hasTip = key === "wallet" || key === "network" || key === "testEth" || key === "connect";

    return {
      id: idx + 1,
      key,
      title: t(`steps.${key}.title`),
      emoji: STEP_EMOJIS[key],
      description: t(`steps.${key}.description`),
      details,
      tip: hasTip ? t(`steps.${key}.tip`) : undefined,
    };
  });

  const faqs: Faq[] = FAQ_KEYS.map((key) => ({
    q: t(`faqs.${key}.q`),
    a: t(`faqs.${key}.a`),
  }));

  const safetyItems: { key: SafetyKey; label: string; desc: string }[] = SAFETY_KEYS.map(
    (key) => ({
      key,
      label: t(`safety.${key}.label`),
      desc: t(`safety.${key}.desc`),
    })
  );

  return (
    <div className="min-h-screen bg-zinc-950 text-zinc-100 p-6">
      <div className="max-w-3xl mx-auto space-y-8">
        {/* Header */}
        <div className="text-center space-y-2">
          <h1 className="text-3xl font-bold">{t("headerTitle")}</h1>
          <p className="text-zinc-400">{t("headerSubtitle")}</p>
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
            {t("prevStep")}
          </button>
          <button
            onClick={() => setActiveStep((s) => Math.min(steps.length, s + 1))}
            disabled={activeStep === steps.length}
            className="px-4 py-2 text-sm rounded-lg bg-blue-600 text-white hover:bg-blue-500 disabled:opacity-30 disabled:cursor-not-allowed"
          >
            {t("nextStep")}
          </button>
        </div>

        {/* Safety notice */}
        <div className="rounded-xl border border-emerald-800 bg-emerald-950/20 p-6">
          <h3 className="font-bold text-emerald-400 mb-3">🛡️ {t("safety.title")}</h3>
          <div className="space-y-2 text-sm text-zinc-400">
            {safetyItems.map(({ key, label, desc }) => (
              <p key={key}>
                ✅ <strong className="text-zinc-300">{label}</strong>{" "}
                — {desc}
              </p>
            ))}
          </div>
        </div>

        {/* FAQ */}
        <div>
          <h2 className="text-xl font-bold mb-4">{t("faqTitle")}</h2>
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
            {t("cta")}
          </a>
        </div>
      </div>
    </div>
  );
}
