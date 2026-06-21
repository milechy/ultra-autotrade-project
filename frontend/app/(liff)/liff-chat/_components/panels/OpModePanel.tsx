// Copyright (c) Ultra AutoTrade. All rights reserved.
"use client"

import { useEffect, useState } from "react"
import { Bot, MousePointer2 } from "lucide-react"
import { useTranslations } from "next-intl"
import { useSigners, useWallets } from "@privy-io/react-auth"
import { getAuthToken } from "@/lib/auth/token-key"
import { liffFetch } from "@/lib/liff/liff-fetch"
import { track, EV } from "@/lib/posthog"
import {
  DEFAULT_DELEGATION_PARAMS,
  DelegationNotReadyError,
  grantDelegation,
  prepareDelegation,
  revokeDelegation,
} from "@/lib/api/delegation"

type UserMode = "managed" | "active"

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? ""

// dormant フラグ: off（本番既定）のとき従来どおり user_mode の設定更新のみ（on-chain 委譲なし）。
// on かつ backend L0 登録済みのときのみ、managed 選択で session signer の consent フローを走らせる。
const CONSENT_ENABLED = process.env.NEXT_PUBLIC_DELEGATION_CONSENT_ENABLED === "true"

export function OpModePanel() {
  const t = useTranslations("Liff.panels.opMode")
  const [currentMode, setCurrentMode] = useState<UserMode | null>(null)
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [toast, setToast] = useState<string | null>(null)
  const { addSigners, removeSigners } = useSigners()
  const { wallets } = useWallets()

  function showToast(msg: string) {
    setToast(msg)
    setTimeout(() => setToast(null), 2500)
  }

  function embeddedEoaAddress(): string | null {
    // Privy embedded wallet (TEE) を委譲対象 EOA とする。外部 wallet は除外。
    return wallets.find((w) => w.walletClientType === "privy")?.address ?? null
  }

  // managed への切替時: 委譲枠を作成（prepare）→ Privy で session signer を consent
  // （addSigners）→ backend に grant 確定。失敗時は signer をロールバックする。
  // 戻り値: consent + grant が成功したか。
  async function runDelegationConsent(): Promise<boolean> {
    let prep
    try {
      prep = await prepareDelegation(DEFAULT_DELEGATION_PARAMS)
    } catch (e) {
      if (e instanceof DelegationNotReadyError) {
        showToast(t("consentNotReady"))
        return false
      }
      showToast(t("consentFailed"))
      return false
    }

    const eoa = embeddedEoaAddress()
    if (!eoa) {
      showToast(t("consentNoWallet"))
      return false
    }

    try {
      await addSigners({
        address: eoa,
        signers: [{ signerId: prep.privy_signer_id, policyIds: [prep.privy_policy_id] }],
      })
    } catch {
      // ユーザーが consent をキャンセル / 失敗 → 何も確定しない
      showToast(t("consentCancelled"))
      return false
    }

    try {
      await grantDelegation({
        ...DEFAULT_DELEGATION_PARAMS,
        privy_policy_id: prep.privy_policy_id,
        privy_signer_id: prep.privy_signer_id,
      })
    } catch {
      // grant 保存失敗 → 付与済み signer をロールバック（非カストディアル維持）
      try {
        await removeSigners({ address: eoa })
      } catch {
        // ロールバック失敗はログのみ（致命的でない）
        console.warn("[opMode] signer rollback failed after grant error")
      }
      showToast(t("consentFailed"))
      return false
    }
    return true
  }

  // managed から離脱時: session signer と grant を取消す（best-effort）。
  async function revokeDelegationConsent(): Promise<void> {
    const eoa = embeddedEoaAddress()
    try {
      if (eoa) await removeSigners({ address: eoa })
    } catch {
      console.warn("[opMode] removeSigners failed on revoke")
    }
    try {
      await revokeDelegation()
    } catch {
      console.warn("[opMode] revokeDelegation failed")
    }
  }

  const MODES = [
    {
      id: "managed" as UserMode,
      label: t("managedLabel"),
      desc: t("managedDesc"),
      icon: Bot,
      color: "text-[#1D9E75]",
      bg: "bg-[#1D9E75]/10",
      border: "border-[#1D9E75]",
    },
    {
      id: "active" as UserMode,
      label: t("activeLabel"),
      desc: t("activeDesc"),
      icon: MousePointer2,
      color: "text-blue-600",
      bg: "bg-blue-500/10",
      border: "border-blue-500",
    },
  ]

  const MODE_LABEL: Record<UserMode, string> = {
    managed: t("managedLabel"),
    active: t("activeLabel"),
  }

  // 初回ロード: GET /api/user/settings
  useEffect(() => {
    liffFetch("/api/user/settings")
      .then((res) => (res.ok ? res.json() : Promise.reject(res.status)))
      .then((data: { user_mode: UserMode }) => {
        setCurrentMode(data.user_mode)
      })
      .catch(() => {
        // 取得失敗時はデフォルト表示なし
      })
      .finally(() => setLoading(false))
  }, [])

  // モード切替。CONSENT_ENABLED off（本番既定）のときは従来どおり即切替（PUT のみ）。
  // on のときは managed 選択で委譲 consent フロー、managed 離脱で revoke を挟む。
  async function handleSelect(newMode: UserMode) {
    if (newMode === currentMode || busy) return
    const token = getAuthToken()
    if (!token) {
      showToast(t("toastAuthExpired"))
      return
    }
    const prev = currentMode

    // 委譲 consent（managed への切替・フラグ on のときのみ）
    if (CONSENT_ENABLED && newMode === "managed") {
      setBusy(true)
      try {
        const ok = await runDelegationConsent()
        if (!ok) return // consent 未完了 → モード変更しない（toast は内部で表示済み）
      } finally {
        setBusy(false)
      }
    }

    // 楽観的更新
    setCurrentMode(newMode)
    try {
      const res = await fetch(`${API_BASE}/api/user/settings`, {
        method: "PUT",
        headers: {
          Authorization: `Bearer ${token}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ user_mode: newMode }),
      })
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      track(EV.OPMODE_CHANGE, { mode: newMode })
      // managed から離脱したら委譲を取消す（フラグ on のみ）
      if (CONSENT_ENABLED && prev === "managed" && newMode !== "managed") {
        await revokeDelegationConsent()
      }
      showToast(t("toastSwitched", { mode: MODE_LABEL[newMode] }))
    } catch {
      // ロールバック
      setCurrentMode(prev)
      showToast(t("toastSwitchFailed"))
    }
  }

  return (
    <div className="space-y-4 relative" data-testid="opmode-panel">
      {/* トースト */}
      {toast && (
        <div
          role="status"
          data-testid="opmode-toast"
          className="fixed top-4 left-1/2 -translate-x-1/2 z-[60] px-4 py-2 rounded-xl bg-[#1b1a23] border border-[#1c1a27]/15 text-[#fbf7f0] text-sm shadow-lg whitespace-nowrap"
        >
          {toast}
        </div>
      )}

      {/* 現在のモード表示カード */}
      <div className="bg-gradient-to-br from-[#b9a4f2] via-[#ecaccd] to-[#fbd9a0] rounded-2xl px-4 py-4 flex items-center justify-between">
        <div>
          <p className="text-xl font-bold text-[#1c1a27]" data-testid="opmode-current">
            {loading
              ? t("loadingMode")
              : currentMode
              ? MODE_LABEL[currentMode]
              : t("modeUnset")}
          </p>
          <p className="text-[#736f7e] text-sm mt-0.5">{t("currentModeLabel")}</p>
        </div>
        <span className="text-xs text-[#1D9E75] border border-[#1D9E75] rounded-full px-2 py-1">
          {t("activeBadge")}
        </span>
      </div>

      {/* モード選択カード */}
      <div className="space-y-3">
        {MODES.map((mode) => {
          const Icon = mode.icon
          const isSelected = currentMode === mode.id
          return (
            <button
              key={mode.id}
              type="button"
              data-testid={`opmode-option-${mode.id}`}
              aria-pressed={isSelected}
              disabled={busy}
              onClick={() => handleSelect(mode.id)}
              className={[
                "w-full text-left rounded-2xl border-2 p-4 transition-all",
                mode.bg,
                mode.border,
                isSelected ? "opacity-100" : "opacity-60",
                busy ? "cursor-not-allowed" : "",
              ].join(" ")}
            >
              <div className="flex items-center gap-3">
                <Icon className={`w-6 h-6 shrink-0 ${mode.color}`} />
                <div>
                  <p className="text-[#1c1a27] font-bold text-base">{mode.label}</p>
                  <p className="text-[#736f7e] text-sm mt-0.5">{mode.desc}</p>
                </div>
              </div>
            </button>
          )
        })}
      </div>
    </div>
  )
}
