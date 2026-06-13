// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.
"use client";

/**
 * Active ToS Consent (MVP-P0-14 / Asana GID 1215082217739006).
 *
 * 要件 (消費者契約法上の active consent):
 * - スクロール追跡で全文読了するまで checkbox を disable
 * - checkbox の default は uncheck 必須
 * - 「これはデモ運用であり、実資金は動かさない」明示同意
 * - 同意ログを POST /api/v1/tos/consent (tos_consents + user_actions に永続化)
 */

import { useEffect, useRef, useState } from "react";
import { useTranslations } from "next-intl";
import { getAuthToken } from "@/lib/auth/token-key";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";
const TOS_VERSION = "demo-1.0";
const SCROLL_TOLERANCE_PX = 16;

export interface DemoConsentModalProps {
  /** 同意が完了したときに呼ばれる。親側でモーダルを閉じる用途。 */
  onAccepted: () => void;
  /**
   * 任意: localStorage の token key を明示的に上書きする。
   * 未指定時は token-key.ts の getAuthToken() 移行シム
   * (auth_token → ultra_auth_token フォールバック) を使う。
   */
  tokenKey?: string;
}

export default function DemoConsentModal({
  onAccepted,
  tokenKey,
}: DemoConsentModalProps) {
  const t = useTranslations("DemoConsent");
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const [hasReadAll, setHasReadAll] = useState(false);
  const [demoAck, setDemoAck] = useState(false);
  const [feeAck, setFeeAck] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const checkScroll = () => {
    const el = scrollRef.current;
    if (!el) return;
    const remaining = el.scrollHeight - el.scrollTop - el.clientHeight;
    if (remaining <= SCROLL_TOLERANCE_PX) {
      setHasReadAll(true);
    }
  };

  useEffect(() => {
    const el = scrollRef.current;
    if (!el) return;
    if (el.scrollHeight <= el.clientHeight + SCROLL_TOLERANCE_PX) {
      setHasReadAll(true);
    }
  }, []);

  const canSubmit = hasReadAll && demoAck && feeAck && !submitting;

  const submit = async () => {
    if (!canSubmit) return;
    setSubmitting(true);
    setError(null);
    const token =
      (tokenKey !== undefined
        ? typeof window !== "undefined"
          ? window.localStorage.getItem(tokenKey)
          : null
        : getAuthToken()) || "";
    try {
      const res = await fetch(`${API_BASE}/api/v1/tos/consent`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({
          tos_version: TOS_VERSION,
          is_demo_ack: demoAck,
          fully_read: hasReadAll,
        }),
      });
      if (!res.ok) {
        const detail = await safeDetail(res);
        throw new Error(detail ?? t("recordErrorHttp", { status: res.status }));
      }
      onAccepted();
    } catch (e) {
      setError(e instanceof Error ? e.message : t("recordError"));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm"
      role="dialog"
      aria-modal="true"
      aria-labelledby="demo-consent-title"
    >
      <div className="mx-4 w-full max-w-xl rounded-2xl border border-zinc-700 bg-zinc-900 p-8 shadow-2xl">
        <h2
          id="demo-consent-title"
          className="mb-2 text-xl font-bold text-zinc-100"
        >
          {t("title")}
        </h2>
        <p className="mb-4 text-sm text-zinc-400">
          {t("subtitle")}
        </p>

        <div
          ref={scrollRef}
          onScroll={checkScroll}
          data-testid="tos-scroll-area"
          className="mb-4 h-64 overflow-y-auto rounded-lg border border-zinc-700 bg-zinc-950 p-4 text-sm leading-relaxed text-zinc-300"
        >
          <h3 className="font-semibold text-zinc-100">{t("article1Title")}</h3>
          <p className="mb-3">
            {t("article1Content")}
          </p>
          <h3 className="font-semibold text-zinc-100">{t("article2Title")}</h3>
          <p className="mb-3">
            {t("article2Content")}
          </p>
          <h3 className="font-semibold text-zinc-100">{t("article3Title")}</h3>
          <p className="mb-3">
            {t("article3Content")}
          </p>
          <h3 className="font-semibold text-zinc-100">{t("article4Title")}</h3>
          <p className="mb-3">
            {t("article4Content")}
          </p>
          <h3 className="font-semibold text-zinc-100">{t("article5Title")}</h3>
          <p className="mb-3">
            {t("article5Content")}
          </p>
          <p className="text-xs text-zinc-500">{t("versionFooter", { version: TOS_VERSION })}</p>
        </div>

        {!hasReadAll && (
          <p className="mb-3 text-xs text-amber-400" data-testid="tos-scroll-hint">
            {t("scrollHint")}
          </p>
        )}

        <div className="space-y-3">
          <label className="flex items-start gap-3 cursor-pointer">
            <input
              type="checkbox"
              data-testid="consent-demo-ack"
              checked={demoAck}
              disabled={!hasReadAll}
              onChange={(e) => setDemoAck(e.target.checked)}
              className="mt-0.5 w-5 h-5 rounded border-zinc-600 bg-zinc-800 text-blue-500 disabled:opacity-40"
            />
            <span className="text-sm text-zinc-200">
              {t("consent1Prefix")} <strong>{t("consent1Emphasis")}</strong>{" "}
              {t("consent1Suffix")}
            </span>
          </label>

          <label className="flex items-start gap-3 cursor-pointer">
            <input
              type="checkbox"
              data-testid="consent-fee-ack"
              checked={feeAck}
              disabled={!hasReadAll}
              onChange={(e) => setFeeAck(e.target.checked)}
              className="mt-0.5 w-5 h-5 rounded border-zinc-600 bg-zinc-800 text-blue-500 disabled:opacity-40"
            />
            <span className="text-sm text-zinc-200">
              {t("consent2Label")}
            </span>
          </label>
        </div>

        {error && (
          <div
            className="mt-4 rounded-lg border border-red-800 bg-red-950/30 p-3 text-sm text-red-400"
            role="alert"
          >
            {error}
          </div>
        )}

        <button
          type="button"
          data-testid="consent-submit"
          onClick={submit}
          disabled={!canSubmit}
          className={`mt-6 w-full rounded-lg py-3 text-sm font-bold transition-all ${
            canSubmit
              ? "bg-blue-600 text-white hover:bg-blue-500"
              : "bg-zinc-800 text-zinc-500 cursor-not-allowed"
          }`}
        >
          {submitting ? t("submittingButton") : t("submitButton")}
        </button>

        <p className="mt-4 text-center text-xs text-zinc-600">
          {t("pageFooter", { version: TOS_VERSION })}
        </p>
      </div>
    </div>
  );
}

async function safeDetail(res: Response): Promise<string | null> {
  try {
    const body = await res.json();
    if (typeof body?.detail === "string") return body.detail;
  } catch {
    /* noop */
  }
  return null;
}
