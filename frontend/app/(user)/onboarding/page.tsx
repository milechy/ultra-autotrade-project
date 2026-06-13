// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.
"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";

const STEP_KEYS = ["wallet", "network", "testEth", "connect"] as const;
type StepKey = (typeof STEP_KEYS)[number];

const FAQ_KEYS = ["minAmount", "lossRisk", "aiAutoTrade", "howToStop"] as const;

const STEP_DETAIL_KEYS: Record<StepKey, string[]> = {
  wallet: ["metamask", "chrome", "create", "password", "seed"],
  network: ["chainlist", "search", "approve", "confirm"],
  testEth: ["faucet", "input", "confirm"],
  connect: ["login", "click", "approve", "sign"],
};

const DETAIL_LINKS: Record<string, string> = {
  metamask: "https://metamask.io/download/",
  chainlist: "https://chainlist.org/?search=base+sepolia&testnets=true",
  faucet: "https://faucet.quicknode.com/base/sepolia",
};

const STEP_EMOJIS: Record<StepKey, string> = {
  wallet: "👛",
  network: "🌐",
  testEth: "💰",
  connect: "🔗",
};

function StepCard({
  stepKey,
  stepNum,
  isActive,
  onClick,
  t,
}: {
  stepKey: StepKey;
  stepNum: number;
  isActive: boolean;
  onClick: () => void;
  t: ReturnType<typeof useTranslations>;
}) {
  const detailKeys = STEP_DETAIL_KEYS[stepKey];
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
        <span className="text-3xl">{STEP_EMOJIS[stepKey]}</span>
        <div>
          <span
            className={`text-xs font-bold px-2 py-0.5 rounded ${
              isActive ? "bg-blue-600 text-white" : "bg-zinc-800 text-zinc-400"
            }`}
          >
            {t("stepBadge", { id: stepNum })}
          </span>
          <h3 className="text-lg font-bold text-zinc-100 mt-1">
            {t(`steps.${stepKey}.title`)}
          </h3>
        </div>
      </div>
      <p className="text-sm text-zinc-400 mb-4">
        {t(`steps.${stepKey}.description`)}
      </p>

      {isActive && (
        <div className="space-y-3">
          <div className="space-y-2">
            {detailKeys.map((dk) => {
              const text = t(`steps.${stepKey}.details.${dk}`);
              const link = DETAIL_LINKS[dk];
              const isWarning = dk === "seed";
              return (
                <div key={dk} className="flex items-start gap-2">
                  <span className="text-blue-400 text-sm mt-0.5">●</span>
                  <div>
                    {link ? (
                      <a
                        href={link}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-sm text-blue-400 hover:underline"
                      >
                        {text} ↗
                      </a>
                    ) : (
                      <span className="text-sm text-zinc-300">{text}</span>
                    )}
                    {isWarning && (
                      <p className="text-xs text-red-400 mt-1">
                        ⚠️ {t(`steps.${stepKey}.seedWarning`)}
                      </p>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
          <div className="rounded-lg bg-zinc-800/50 border border-zinc-700 p-3">
            <p className="text-xs text-zinc-400">
              💡 {t(`steps.${stepKey}.tip`)}
            </p>
          </div>
        </div>
      )}
    </div>
  );
}

export default function OnboardingPage() {
  const t = useTranslations("WalletOnboarding");
  const [activeStep, setActiveStep] = useState(1);
  const [openFaq, setOpenFaq] = useState<number | null>(null);

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
          {STEP_KEYS.map((_, i) => (
            <div
              key={i}
              className={`flex-1 h-1.5 rounded-full transition-all ${
                i + 1 <= activeStep ? "bg-blue-500" : "bg-zinc-800"
              }`}
            />
          ))}
        </div>

        {/* Steps */}
        <div className="space-y-4">
          {STEP_KEYS.map((stepKey, i) => (
            <StepCard
              key={stepKey}
              stepKey={stepKey}
              stepNum={i + 1}
              isActive={activeStep === i + 1}
              onClick={() => setActiveStep(i + 1)}
              t={t}
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
            {t("prevBtn")}
          </button>
          <button
            onClick={() =>
              setActiveStep((s) => Math.min(STEP_KEYS.length, s + 1))
            }
            disabled={activeStep === STEP_KEYS.length}
            className="px-4 py-2 text-sm rounded-lg bg-blue-600 text-white hover:bg-blue-500 disabled:opacity-30 disabled:cursor-not-allowed"
          >
            {t("nextBtn")}
          </button>
        </div>

        {/* Safety notice */}
        <div className="rounded-xl border border-emerald-800 bg-emerald-950/20 p-6">
          <h3 className="font-bold text-emerald-400 mb-3">
            {t("safety.title")}
          </h3>
          <div className="space-y-2 text-sm text-zinc-400">
            <p>
              ✅{" "}
              <strong className="text-zinc-300">
                {t("safety.nonCustodial")}
              </strong>{" "}
              {t("safety.nonCustodialDesc")}
            </p>
            <p>
              ✅{" "}
              <strong className="text-zinc-300">
                {t("safety.signRequired")}
              </strong>{" "}
              {t("safety.signRequiredDesc")}
            </p>
            <p>
              ✅{" "}
              <strong className="text-zinc-300">
                {t("safety.emergencyStop")}
              </strong>{" "}
              {t("safety.emergencyStopDesc")}
            </p>
            <p>
              ✅{" "}
              <strong className="text-zinc-300">
                {t("safety.fourAgents")}
              </strong>{" "}
              {t("safety.fourAgentsDesc")}
            </p>
          </div>
        </div>

        {/* FAQ */}
        <div>
          <h2 className="text-xl font-bold mb-4">{t("faq.title")}</h2>
          <div className="space-y-2">
            {FAQ_KEYS.map((faqKey, i) => (
              <div
                key={faqKey}
                className="rounded-lg border border-zinc-800 bg-zinc-900/40 overflow-hidden"
              >
                <button
                  onClick={() => setOpenFaq(openFaq === i ? null : i)}
                  className="w-full text-left px-4 py-3 flex items-center justify-between hover:bg-zinc-900/60 transition-colors"
                >
                  <span className="text-sm font-medium text-zinc-200">
                    {t(`faq.${faqKey}.q`)}
                  </span>
                  <span className="text-zinc-500 ml-4">
                    {openFaq === i ? "−" : "+"}
                  </span>
                </button>
                {openFaq === i && (
                  <div className="px-4 pb-4 border-t border-zinc-800">
                    <p className="text-sm text-zinc-400 leading-relaxed pt-3">
                      {t(`faq.${faqKey}.a`)}
                    </p>
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
            {t("ctaBtn")}
          </a>
        </div>
      </div>
    </div>
  );
}
