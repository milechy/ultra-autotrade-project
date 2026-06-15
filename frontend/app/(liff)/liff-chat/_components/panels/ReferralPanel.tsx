// Copyright (c) Ultra AutoTrade. All rights reserved.
"use client"

import { useEffect, useState, useCallback } from "react"
import { Copy, Mail, Share2, CheckCircle, Users, Gift, TrendingUp, ChevronRight } from "lucide-react"
import { useTranslations } from "next-intl"
import { getReferralInfo, createReferralCode, type ReferralInfo } from "@/lib/api/referral"

type TFn = ReturnType<typeof useTranslations>
import { getAuthToken } from "@/lib/auth/token-key"

// SIGNUP URL: 専用の env/定数が無いため、sibling パネル (TermsPanel 等) と同じ
// app.ultra-auto-trade.com 系ドメインへハードコードでフォールバックする。
// NEXT_PUBLIC_LIFF_APP_URL が定義されればそちらを優先する。
const SIGNUP_URL = process.env.NEXT_PUBLIC_LIFF_APP_URL ?? "https://app.ultra-auto-trade.com/auth/register"

function getToken(): string {
  // 統一済み auth token getter (Asana 1215441139765963)。
  // 正準キー auth_token を優先し、旧キー ultra_auth_token をフォールバック読み。
  return getAuthToken() ?? ""
}

function buildShareText(code: string, template: string): string {
  // template uses {code} and {url} as placeholders (from i18n keys shareTextBody)
  return template
    .replace("{code}", code)
    .replace("{url}", `${SIGNUP_URL}?ref=${code}`)
}

/** フォールバック用のスケルトンデータ（ローディング中 or エラー時） */
const EMPTY_INFO: ReferralInfo = {
  referral_count: 0,
  current_month_reward_jpy: "0",
  total_payout_jpy: "0",
  campaign_rate: "0.10",
  referral_code: "",
  referred_users: [],
}

export function ReferralPanel() {
  const t = useTranslations("Liff.panels.referral")
  const [info, setInfo] = useState<ReferralInfo | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [toast, setToast] = useState<string | null>(null)
  const [creatingCode, setCreatingCode] = useState(false)

  const showToast = useCallback((msg: string) => {
    setToast(msg)
    setTimeout(() => setToast(null), 2500)
  }, [])

  useEffect(() => {
    const token = getToken()
    setLoading(true)
    getReferralInfo(token)
      .then((data) => {
        setInfo(data)
        setError(null)
      })
      .catch(() => {
        setError(t("dataError"))
        setInfo(EMPTY_INFO)
      })
      .finally(() => setLoading(false))
  }, [])

  const handleCreateCode = useCallback(async () => {
    const token = getToken()
    setCreatingCode(true)
    try {
      const res = await createReferralCode(token)
      setInfo((prev) =>
        prev ? { ...prev, referral_code: res.referral_code } : null
      )
      showToast(t("toastCodeCreated"))
    } catch {
      showToast(t("toastCodeCreateFailed"))
    } finally {
      setCreatingCode(false)
    }
  }, [showToast])

  const handleCopyCode = useCallback(async () => {
    const code = info?.referral_code
    if (!code) return
    try {
      await navigator.clipboard.writeText(code)
      showToast(t("toastCodeCopied"))
    } catch {
      showToast(t("toastCopyFailed"))
    }
  }, [info?.referral_code, showToast, t])

  const handleCopyLink = useCallback(async () => {
    const code = info?.referral_code
    if (!code) return
    const url = `${SIGNUP_URL}?ref=${code}`
    try {
      await navigator.clipboard.writeText(url)
      showToast(t("toastLinkCopied"))
    } catch {
      showToast(t("toastCopyFailed"))
    }
  }, [info?.referral_code, showToast, t])

  const handleLineShare = useCallback(async () => {
    const code = info?.referral_code
    if (!code) return
    const shareText = buildShareText(code, t("shareTextBody"))
    try {
      const { getLiff, isLiffConfigured } = await import("@/lib/liff/init")
      // ブラウザ PWA モード（LIFF 未設定）は SDK を触らずクリップボードへ degrade。
      const liff = isLiffConfigured() ? await getLiff() : null
      if (liff && liff.isApiAvailable("shareTargetPicker")) {
        await liff.shareTargetPicker([{ type: "text", text: shareText }])
      } else {
        await navigator.clipboard.writeText(shareText)
        showToast(t("toastLineShareFallback"))
      }
    } catch {
      showToast(t("toastShareFailed"))
    }
  }, [info?.referral_code, showToast, t])

  const handleMailShare = useCallback(async () => {
    const code = info?.referral_code
    if (!code) return
    const subject = encodeURIComponent(t("mailSubject"))
    const body = encodeURIComponent(buildShareText(code, t("shareTextBody")))
    const mailtoUrl = `mailto:?subject=${subject}&body=${body}`
    try {
      const { getLiff, isLiffConfigured } = await import("@/lib/liff/init")
      const liff = isLiffConfigured() ? await getLiff() : null
      if (liff) {
        // LIFF webview では openWindow(external=true) でOS のメールアプリを起動する。
        // window.location.href = 'mailto:' は LINE 内ブラウザが外部ブラウザを開くだけで
        // メールアプリが起動しないため使用しない。
        liff.openWindow({ url: mailtoUrl, external: true })
      } else {
        window.open(mailtoUrl, "_blank")
      }
    } catch {
      window.open(mailtoUrl, "_blank")
    }
  }, [info?.referral_code, t])

  const displayInfo = info ?? EMPTY_INFO

  const totalReward = Number(displayInfo.total_payout_jpy).toLocaleString("ja-JP")
  const monthlyReward = Number(displayInfo.current_month_reward_jpy).toLocaleString("ja-JP")

  const operatingCount = displayInfo.referred_users.filter(
    (u) => u.status === "active"
  ).length

  return (
    <div className="space-y-4 pb-4">
      {/* トースト */}
      {toast && (
        <div className="fixed top-16 left-1/2 -translate-x-1/2 z-[60]
                        flex items-center gap-2 bg-zinc-800 border border-zinc-700
                        text-zinc-100 text-sm px-4 py-2 rounded-xl shadow-lg
                        animate-in fade-in duration-200">
          <CheckCircle className="w-4 h-4 text-[#4ade9a]" />
          {toast}
        </div>
      )}

      {/* エラーバナー */}
      {error && (
        <div className="text-xs text-amber-400 bg-amber-400/10 border border-amber-400/30
                        rounded-xl px-3 py-2">
          {error}{t("offlineLabel")}
        </div>
      )}

      {/* 報酬サマリーカード */}
      <div className="bg-[#1a3d2e] rounded-2xl p-5">
        {loading ? (
          <div className="h-20 flex items-center justify-center">
            <div className="w-6 h-6 border-2 border-[#4ade9a] border-t-transparent rounded-full animate-spin" />
          </div>
        ) : (
          <>
            <p className="text-zinc-400 text-xs mb-1">{t("totalRewardLabel")}</p>
            <p className="text-[#4ade9a] text-3xl font-bold mb-1">
              ¥{totalReward}
            </p>
            <p className="text-zinc-400 text-xs mb-5">
              {displayInfo.referral_count}{t("referralCountLabel")}
            </p>

            {/* 統計 3つ */}
            <div className="grid grid-cols-3 gap-2 pt-4 border-t border-white/10">
              <StatCard
                icon={<Users className="w-4 h-4" />}
                label={t("statsReferralCount")}
                value={`${displayInfo.referral_count}`}
              />
              <StatCard
                icon={<TrendingUp className="w-4 h-4" />}
                label={t("statsOperating")}
                value={`${operatingCount}`}
              />
              <StatCard
                icon={<Gift className="w-4 h-4" />}
                label={t("statsMonthlyReward")}
                value={`¥${monthlyReward}`}
              />
            </div>
          </>
        )}
      </div>

      {/* 紹介コード */}
      <div className="space-y-2">
        <p className="text-zinc-400 text-xs font-medium px-1">{t("referralCodeLabel")}</p>
        {displayInfo.referral_code ? (
          <div className="flex items-center gap-2">
            <div className="flex-1 bg-zinc-800 rounded-xl px-4 py-3 flex items-center">
              <span className="text-white font-mono text-2xl tracking-widest">
                {displayInfo.referral_code}
              </span>
            </div>
            <button
              onClick={handleCopyCode}
              className="flex items-center gap-1.5 bg-[#1D9E75] hover:bg-[#17855f]
                         text-white text-sm font-semibold px-4 py-3 rounded-xl
                         transition-colors whitespace-nowrap"
            >
              <Copy className="w-4 h-4" />
              {t("copyCodeBtn")}
            </button>
          </div>
        ) : (
          <button
            onClick={handleCreateCode}
            disabled={creatingCode || loading}
            className="w-full bg-[#1D9E75] hover:bg-[#17855f] disabled:opacity-50
                       text-white text-sm font-semibold py-3 rounded-xl
                       transition-colors"
          >
            {creatingCode ? t("creatingCodeBtn") : t("createCodeBtn")}
          </button>
        )}
      </div>

      {/* シェアボタン */}
      {displayInfo.referral_code && (
        <div className="space-y-2">
          <p className="text-zinc-400 text-xs font-medium px-1">{t("shareSectionLabel")}</p>
          <div className="space-y-2">
            <button
              onClick={handleLineShare}
              className="w-full flex items-center gap-3 bg-[#06C755] hover:bg-[#05a848]
                         text-white font-semibold py-3 px-4 rounded-xl
                         transition-colors"
            >
              <Share2 className="w-5 h-5" />
              <span className="flex-1 text-left">{t("lineShareBtn")}</span>
              <ChevronRight className="w-4 h-4 opacity-60" />
            </button>

            <button
              onClick={handleMailShare}
              className="w-full flex items-center gap-3 bg-blue-600 hover:bg-blue-500
                         text-white font-semibold py-3 px-4 rounded-xl
                         transition-colors"
            >
              <Mail className="w-5 h-5" />
              <span className="flex-1 text-left">{t("mailShareBtn")}</span>
              <ChevronRight className="w-4 h-4 opacity-60" />
            </button>

            <button
              onClick={handleCopyLink}
              className="w-full flex items-center gap-3 bg-zinc-700 hover:bg-zinc-600
                         text-white font-semibold py-3 px-4 rounded-xl
                         transition-colors"
            >
              <Copy className="w-5 h-5" />
              <span className="flex-1 text-left">{t("copyLinkBtn")}</span>
              <ChevronRight className="w-4 h-4 opacity-60" />
            </button>
          </div>
        </div>
      )}

      {/* 報酬の仕組み */}
      <div className="space-y-2">
        <p className="text-zinc-400 text-xs font-medium px-1">{t("howItWorksLabel")}</p>
        <div className="bg-zinc-900 border border-zinc-800 rounded-2xl p-4 space-y-4">
          <HowItWorksStep
            step={1}
            text={t("howItWorksStep1")}
          />
          <HowItWorksStep
            step={2}
            text={t("howItWorksStep2")}
          />
          <HowItWorksStep
            step={3}
            text={t("howItWorksStep3")}
            reward={t("howItWorksReward")}
          />
        </div>
      </div>

      {/* 紹介した友達リスト */}
      {displayInfo.referred_users.length > 0 && (
        <div className="space-y-2">
          <p className="text-zinc-400 text-xs font-medium px-1">{t("referredUsersLabel")}</p>
          <div className="space-y-2">
            {displayInfo.referred_users.map((user, i) => (
              <ReferredUserRow key={i} user={user} tPanel={t} />
            ))}
          </div>
        </div>
      )}

      {!loading && displayInfo.referred_users.length === 0 && displayInfo.referral_code && (
        <div className="text-center py-8 text-zinc-600 text-sm">
          {t("noReferredUsers")}
        </div>
      )}
    </div>
  )
}

function StatCard({
  icon,
  label,
  value,
}: {
  icon: React.ReactNode
  label: string
  value: string
}) {
  return (
    <div className="flex flex-col items-center gap-1">
      <div className="text-[#4ade9a]">{icon}</div>
      <p className="text-white font-semibold text-sm">{value}</p>
      <p className="text-zinc-500 text-[10px]">{label}</p>
    </div>
  )
}

function HowItWorksStep({
  step,
  text,
  reward,
}: {
  step: number
  text: string
  reward?: string
}) {
  return (
    <div className="flex items-start gap-3">
      <div className="w-6 h-6 rounded-full bg-[#1a3d2e] border border-[#1D9E75]
                      flex items-center justify-center flex-shrink-0 mt-0.5">
        <span className="text-[#4ade9a] text-xs font-bold">{step}</span>
      </div>
      <div className="flex-1">
        <p className="text-white text-sm">{text}</p>
        {reward && (
          <p className="text-[#4ade9a] text-xs font-semibold mt-0.5">
            → {reward}
          </p>
        )}
      </div>
    </div>
  )
}

function ReferredUserRow({
  user,
  tPanel,
}: {
  user: { name: string; joined_at: string; status: string; reward_jpy: string }
  tPanel: TFn
}) {
  const isActive = user.status === "active"
  const initial = user.name ? user.name.charAt(0).toUpperCase() : "?"
  const joinedDate = user.joined_at ? user.joined_at.slice(0, 10) : ""
  const rewardJpy = Number(user.reward_jpy).toLocaleString("ja-JP")

  return (
    <div className="flex items-center gap-3 bg-zinc-900 border border-zinc-800 rounded-xl px-4 py-3">
      {/* アバター */}
      <div className="w-9 h-9 rounded-full bg-[#1a3d2e] border border-[#1D9E75]
                      flex items-center justify-center flex-shrink-0">
        <span className="text-[#4ade9a] text-sm font-bold">{initial}</span>
      </div>

      {/* 名前・日付 */}
      <div className="flex-1 min-w-0">
        <p className="text-white text-sm font-medium truncate">{user.name}</p>
        <p className="text-zinc-500 text-xs mt-0.5">{tPanel("joinedDateLabel")} {joinedDate}</p>
      </div>

      {/* ステータス・報酬 */}
      <div className="flex flex-col items-end gap-1">
        <span
          className={`text-xs border rounded-full px-2 py-0.5 ${
            isActive
              ? "text-[#4ade9a] border-[#1D9E75]"
              : "text-zinc-400 border-zinc-700"
          }`}
        >
          {user.status === "active"
            ? tPanel("statusActive")
            : tPanel("statusRegistered")}
        </span>
        <span className="text-zinc-300 text-xs">¥{rewardJpy}</span>
      </div>
    </div>
  )
}
