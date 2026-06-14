// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.
// frontend/app/(liff)/liff-sign-poc/page.tsx
//
// PoC: LIFF内 Privy 署名の技術検証ページ
// URL: /liff-sign-poc
//
// 検証手順:
//   1. LIFF 初期化 + isInClient / isLoggedIn 確認
//   2. Privy embedded wallet 初期化確認
//   3. eth_signMessage (ガス不要) でiFrame通信確認
//   4. 結果をUIに表示 (実機テスト用)
//
// 注意: 本番導入前に LINE アプリ実機でこのページを開いて全ステップが PASS になることを確認すること。
// このファイルは PoC 専用 — 本実装は liff-approve/page.tsx に統合する。
"use client";

import { useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import { usePrivy, useWallets } from "@privy-io/react-auth";
import { useLiff } from "@/hooks/useLiff";

type StepResult = {
  step: string;
  status: "pending" | "running" | "pass" | "fail";
  detail?: string;
};

function statusColor(s: StepResult["status"]) {
  switch (s) {
    case "pass":
      return "text-green-400";
    case "fail":
      return "text-red-400";
    case "running":
      return "text-yellow-400";
    default:
      return "text-zinc-500";
  }
}

function statusIcon(s: StepResult["status"]) {
  switch (s) {
    case "pass":
      return "✅";
    case "fail":
      return "❌";
    case "running":
      return "⏳";
    default:
      return "⬜";
  }
}

export default function LiffSignPocPage() {
  const t = useTranslations("LiffSignPoc");
  const { isReady, isLoggedIn, isInClient, error: liffError } = useLiff();
  const { ready: privyReady, authenticated } = usePrivy();
  const { wallets } = useWallets();

  const STEPS: StepResult[] = [
    { step: t("step1"), status: "pending" },
    { step: t("step2"), status: "pending" },
    { step: t("step3"), status: "pending" },
    { step: t("step4"), status: "pending" },
    { step: t("step5"), status: "pending" },
  ];

  const [steps, setSteps] = useState<StepResult[]>(STEPS.map((s) => ({ ...s })));
  const [running, setRunning] = useState(false);
  const [userAgent, setUserAgent] = useState("");
  const [privyWalletAddress, setPrivyWalletAddress] = useState("");

  useEffect(() => {
    setUserAgent(navigator.userAgent);
  }, []);

  function updateStep(
    index: number,
    status: StepResult["status"],
    detail?: string
  ) {
    setSteps((prev) =>
      prev.map((s, i) => (i === index ? { ...s, status, detail } : s))
    );
  }

  async function runPoc() {
    if (running) return;
    setRunning(true);
    setSteps(STEPS.map((s) => ({ ...s })));

    // Step 1: LIFF init
    updateStep(0, "running");
    if (!isReady) {
      updateStep(0, "fail", t("step1FailDetail", { error: liffError ?? "timeout" }));
      setRunning(false);
      return;
    }
    updateStep(0, "pass", t("step1PassDetail", { isLoggedIn: String(isLoggedIn) }));

    // Step 2: isInClient
    updateStep(1, "running");
    if (!isInClient) {
      updateStep(
        1,
        "fail",
        t("step2FailDetail")
      );
      // Continue anyway for browser testing
    } else {
      updateStep(1, "pass", t("step2PassDetail"));
    }

    // Step 3: Privy init
    updateStep(2, "running");
    if (!privyReady) {
      updateStep(2, "fail", t("step3FailDetail"));
      setRunning(false);
      return;
    }
    updateStep(2, "pass", t("step3PassDetail", { authenticated: String(authenticated) }));

    // Step 4: Embedded wallet
    updateStep(3, "running");
    const privyWallet = wallets.find((w) => w.walletClientType === "privy");
    if (!privyWallet) {
      if (!authenticated) {
        updateStep(
          3,
          "fail",
          t("step4FailNotAuth")
        );
      } else {
        updateStep(
          3,
          "fail",
          t("step4FailNoWallet")
        );
      }
      setRunning(false);
      return;
    }
    setPrivyWalletAddress(privyWallet.address);
    updateStep(3, "pass", t("step4PassDetail", { address: privyWallet.address.slice(0, 8) }));

    // Step 5: eth_signMessage
    updateStep(4, "running");
    try {
      const eip1193 = await privyWallet.getEthereumProvider();
      const message = `LIFF Privy PoC sign test\nTimestamp: ${new Date().toISOString()}\nAddress: ${privyWallet.address}`;
      // personal_sign: 0xHex message, address
      const msgHex =
        "0x" +
        Array.from(new TextEncoder().encode(message))
          .map((b) => b.toString(16).padStart(2, "0"))
          .join("");
      const signature = (await eip1193.request({
        method: "personal_sign",
        params: [msgHex, privyWallet.address],
      })) as string;
      if (!signature || !signature.startsWith("0x")) {
        updateStep(4, "fail", t("step5FailInvalid", { signature }));
      } else {
        updateStep(
          4,
          "pass",
          t("step5PassDetail", { signature: signature.slice(0, 16) })
        );
      }
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : String(e);
      if (msg.includes("User rejected") || msg.includes("user rejected")) {
        updateStep(4, "fail", t("step5FailCancelled"));
      } else {
        updateStep(4, "fail", t("step5FailError", { msg }));
      }
    }

    setRunning(false);
  }

  return (
    <div className="min-h-screen bg-zinc-950 text-zinc-100 px-4 py-6 max-w-md mx-auto">
      <h1 className="text-lg font-bold mb-2 text-center">
        {t("title")}
      </h1>
      <p className="text-xs text-zinc-500 text-center mb-6">
        {t("subtitle")}
      </p>

      {/* Environment info */}
      <div className="bg-zinc-900 rounded-lg p-3 mb-4 space-y-1 text-xs">
        <div className="text-zinc-400 font-medium mb-1">{t("envInfo")}</div>
        <div>
          <span className="text-zinc-500">{t("envUserAgent")}: </span>
          <span className="text-zinc-300 break-all">{userAgent.slice(0, 80)}...</span>
        </div>
        <div>
          <span className="text-zinc-500">{t("envLiffReady")}: </span>
          <span className={isReady ? "text-green-400" : "text-yellow-400"}>
            {isReady ? "true" : "false"}
          </span>
        </div>
        <div>
          <span className="text-zinc-500">{t("envIsInClient")}: </span>
          <span className={isInClient ? "text-green-400" : "text-red-400"}>
            {isReady ? String(isInClient) : "—"}
          </span>
        </div>
        <div>
          <span className="text-zinc-500">{t("envPrivyReady")}: </span>
          <span className={privyReady ? "text-green-400" : "text-yellow-400"}>
            {privyReady ? "true" : "false"}
          </span>
        </div>
        <div>
          <span className="text-zinc-500">{t("envPrivyAuth")}: </span>
          <span className={authenticated ? "text-green-400" : "text-zinc-400"}>
            {authenticated ? "true" : "false"}
          </span>
        </div>
        {privyWalletAddress && (
          <div>
            <span className="text-zinc-500">{t("envWallet")}: </span>
            <span className="text-blue-400 font-mono">
              {privyWalletAddress.slice(0, 8)}...{privyWalletAddress.slice(-4)}
            </span>
          </div>
        )}
      </div>

      {/* Privy login button if not authenticated */}
      {privyReady && !authenticated && (
        <PrivyLoginButton />
      )}

      {/* Steps */}
      <div className="bg-zinc-900 rounded-lg p-3 mb-4 space-y-3">
        <div className="text-zinc-400 font-medium text-xs mb-2">{t("stepsTitle")}</div>
        {steps.map((s, i) => (
          <div key={i} className="flex gap-2 items-start">
            <span className="text-base leading-tight">{statusIcon(s.status)}</span>
            <div className="flex-1">
              <div className={`text-xs font-medium ${statusColor(s.status)}`}>
                {s.step}
              </div>
              {s.detail && (
                <div className="text-xs text-zinc-500 mt-0.5 break-words">
                  {s.detail}
                </div>
              )}
            </div>
          </div>
        ))}
      </div>

      {/* Run button */}
      <button
        onClick={() => void runPoc()}
        disabled={running || !isReady}
        className="w-full bg-blue-600 hover:bg-blue-500 disabled:opacity-50 disabled:cursor-not-allowed
                   text-white font-semibold py-3 rounded-lg transition-colors text-sm mb-3"
      >
        {running ? t("runButtonRunning") : isReady ? t("runButton") : t("runButtonInitializing")}
      </button>

      <p className="text-xs text-zinc-600 text-center">
        {t("hint")}
      </p>
    </div>
  );
}

// Privy login button — rendered only when not authenticated
function PrivyLoginButton() {
  const t = useTranslations("LiffSignPoc");
  const { login } = usePrivy();
  return (
    <button
      onClick={() => login()}
      className="w-full bg-violet-700 hover:bg-violet-600 text-white font-semibold py-2.5 rounded-lg text-sm mb-4"
    >
      {t("privyLoginButton")}
    </button>
  );
}
