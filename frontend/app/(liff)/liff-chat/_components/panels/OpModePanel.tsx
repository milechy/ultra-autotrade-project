// Copyright (c) Ultra AutoTrade. All rights reserved.
"use client"

import { useEffect, useState } from "react"
import { Bot, MousePointer2 } from "lucide-react"
import { useTranslations } from "next-intl"
import { useSigners, useUser, useWallets } from "@privy-io/react-auth"
import { getAuthToken } from "@/lib/auth/token-key"
import { isAggressiveTierEnabled, isAutoModeEnabled } from "@/lib/flags"
import { DEPOSIT_GATE_USD } from "@/lib/web3/config"
import { liffFetch } from "@/lib/liff/liff-fetch"
import { track, EV } from "@/lib/posthog"
import AggressiveRiskDisclosureModal from "@/components/settings/AggressiveRiskDisclosureModal"
import {
  delegationParamsForScope,
  DelegationNotReadyError,
  effectiveScope,
  getDelegation,
  grantAllowsPendle,
  grantDelegation,
  type ManagedScope,
  needsReconsentForYield,
  prepareDelegation,
  revokeDelegation,
  RiskModeNotAvailableError,
  SCOPE_TO_RISK_MODE,
  updateRiskMode,
} from "@/lib/api/delegation"
import { ManagedScopeSheet } from "./ManagedScopeSheet"

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
  // 運用方針（安全重視 / 利回り重視）。実効値は risk_mode と委譲枠の**両方**が
  // Pendle を許して初めて "yield"（effectiveScope 参照）。
  const [scope, setScope] = useState<ManagedScope>("safety")
  const [aggressiveAcked, setAggressiveAcked] = useState(false)
  const [needsResign, setNeedsResign] = useState(false)
  const [sheetOpen, setSheetOpen] = useState(false)
  const [disclosureOpen, setDisclosureOpen] = useState(false)
  // 開示同意の完了を待って consent 本体を再開するための保留 scope。
  const [pendingScope, setPendingScope] = useState<ManagedScope | null>(null)
  const { addSigners, removeSigners } = useSigners()
  const { wallets } = useWallets()
  const { refreshUser } = useUser()

  const SCOPE_SELECTABLE = CONSENT_ENABLED && isAggressiveTierEnabled()

  function showToast(msg: string) {
    setToast(msg)
    setTimeout(() => setToast(null), 2500)
  }

  function embeddedEoaAddress(): string | null {
    // Privy embedded wallet (TEE) を委譲対象 EOA とする。外部 wallet は除外。
    return wallets.find((w) => w.walletClientType === "privy")?.address ?? null
  }

  // Privy 内部 wallet ID を解決する。Wallet.id はログイン時点(未委譲)では常に null
  // （Privy SDK 仕様: "Null if the wallet is not delegated"）で、addSigners 成功直後に
  // refreshUser() で最新の linkedAccounts を取得して初めて埋まる。委譲(SCW)執行の
  // wallet_sendCalls が要求する識別子（2026-07-16、per-user 解決の唯一の確実な経路）。
  async function resolvePrivyWalletId(eoa: string): Promise<string | undefined> {
    try {
      const refreshed = await refreshUser()
      const account = refreshed.linkedAccounts.find(
        (a) => a.type === "wallet" && a.address === eoa
      )
      return account && account.type === "wallet" && account.id ? account.id : undefined
    } catch {
      // 解決できなくても致命的ではない（_resolve_privy_wallet_id が env フォールバックに頼る）
      console.warn("[opMode] privy_wallet_id resolution failed after addSigners")
      return undefined
    }
  }

  // managed への切替時: 委譲枠を作成（prepare）→ Privy で session signer を consent
  // （addSigners）→ backend に grant 確定。失敗時は signer をロールバックする。
  // 戻り値: consent + grant が成功したか。
  async function runDelegationConsent(targetScope: ManagedScope): Promise<boolean> {
    const params = delegationParamsForScope(targetScope)

    // 既に有効な委譲grant(signer/policy付き)があれば再consent不要。addSigners()を
    // 同じPrivy signerに対して再度呼ぶと「Duplicate signer(s) provided when updating
    // wallet」400で必ず失敗する(2026-07-17 本番実機で確認: 一度成功した後、モードを
    // 切り替えて再度「おまかせ」を選ぶと再現)。既存の有効grantを検出したら
    // addSigners自体をスキップし、そのまま利用する。
    //
    // ただし**方針が変わる場合は再consentが必須**。Privy policy の宛先 allowlist は
    // prepare 時の allowed_protocols から作られ TEE が enforce するため、枠を作り直さずに
    // 表示だけ変えると「利回り重視と表示されるが Pendle は TEE に拒否される」嘘になる。
    // その場合は removeSigners → 新 policy で addSigners し直す（Duplicate signer 回避）。
    let reusableGrant = false
    try {
      const existing = await getDelegation()
      if (existing && existing.privy_signer_id && existing.privy_policy_id) {
        const scopeMatches = grantAllowsPendle(existing) === (targetScope === "yield")
        if (scopeMatches) return true
        // 方針が変わる → 既存 signer を外してから作り直す
        reusableGrant = true
      }
    } catch {
      // 既存grant確認に失敗しても、通常のconsentフローにフォールバックする(非致命的)。
    }

    const eoa = embeddedEoaAddress()
    if (!eoa) {
      showToast(t("consentNoWallet"))
      return false
    }

    if (reusableGrant) {
      try {
        await removeSigners({ address: eoa })
      } catch {
        // 既存 signer を外せないと addSigners が Duplicate signer 400 で必ず失敗する。
        console.warn("[opMode] removeSigners failed before scope change")
        showToast(t("consentFailed"))
        return false
      }
    }

    let prep
    try {
      prep = await prepareDelegation(params)
    } catch (e) {
      if (e instanceof DelegationNotReadyError) {
        showToast(t("consentNotReady"))
        return false
      }
      showToast(t("consentFailed"))
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

    const privyWalletId = await resolvePrivyWalletId(eoa)

    try {
      await grantDelegation({
        ...params,
        privy_policy_id: prep.privy_policy_id,
        privy_signer_id: prep.privy_signer_id,
        ...(privyWalletId ? { privy_wallet_id: privyWalletId } : {}),
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

  /**
   * 委譲枠が確定した**後**に risk_mode を倒す。
   *
   * 順序が逆だと「risk_mode=aggressive なのに委譲枠に pendle が無い」状態になり、Pendle 提案は
   * 生成されるのに broadcast されず approved のまま滞留する。grant が先行する分には
   * （権限が未使用なだけで）無害なので、必ず grant → risk_mode の順にする。
   */
  async function applyRiskMode(targetScope: ManagedScope): Promise<void> {
    try {
      await updateRiskMode(SCOPE_TO_RISK_MODE[targetScope])
      setScope(targetScope)
      setNeedsResign(false)
    } catch (e) {
      // backend 未解禁(403) / 開示未同意(412) → 委譲枠は yield でも risk_mode は
      // conservative のまま = Pendle 提案は生成されない（無害な側に倒れる）。
      if (e instanceof RiskModeNotAvailableError) {
        setScope("safety")
        showToast(t("scopeYieldUnavailable"))
        return
      }
      showToast(t("consentFailed"))
    }
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
    // おまかせ（managed）= 一任運用。投資運用業の登録/法務クリアまでフラグで非表示。
    // 詳細は isAutoModeEnabled の JSDoc 参照。
    {
      id: "managed" as UserMode,
      label: t("managedLabel"),
      // CONSENT_ENABLED=false のときは「準備中」文言、true(委譲consentフローが実際に
      // 動く環境)では実際の上限内自動実行の説明に切り替える(2026-07-17、実装完了に
      // 追随して固定「準備中」文言のまま出し続けないようにする)。
      desc: CONSENT_ENABLED ? t("managedDescLive") : t("managedDesc"),
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
  ].filter((m) => isAutoModeEnabled() || m.id !== "managed")

  const MODE_LABEL: Record<UserMode, string> = {
    managed: t("managedLabel"),
    active: t("activeLabel"),
  }

  // 初回ロード: GET /api/user/settings（risk_mode / aggressive_ack_at も含む）
  useEffect(() => {
    liffFetch("/api/user/settings")
      .then((res) => (res.ok ? res.json() : Promise.reject(res.status)))
      .then(
        (data: {
          user_mode: UserMode
          risk_mode?: string | null
          aggressive_ack_at?: string | null
        }) => {
          setCurrentMode(data.user_mode)
          setAggressiveAcked(Boolean(data.aggressive_ack_at))
          return data.risk_mode ?? null
        }
      )
      .then(async (mode) => {
        // 実効方針は risk_mode と委譲枠の論理積。フラグ off のときは委譲枠を見に行かない
        // （従来どおり方針の概念自体を出さない）。
        if (!SCOPE_SELECTABLE) return
        const grant = await getDelegation().catch(() => null)
        setScope(effectiveScope(grant, mode))
        setNeedsResign(needsReconsentForYield(grant, mode))
      })
      .catch(() => {
        // 取得失敗時はデフォルト表示なし
      })
      .finally(() => setLoading(false))
    // SCOPE_SELECTABLE は build-time 定数なので依存に入れない（再実行させない）。
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // モード切替の実処理。targetScope は managed のときだけ意味を持つ。
  // CONSENT_ENABLED off（本番既定）のときは従来どおり即切替（PUT のみ）。
  async function applyMode(newMode: UserMode, targetScope: ManagedScope) {
    const token = getAuthToken()
    if (!token) {
      showToast(t("toastAuthExpired"))
      return
    }
    const prev = currentMode
    const modeChanged = newMode !== prev

    // 委譲 consent（managed への切替 / 方針変更・フラグ on のときのみ）
    if (CONSENT_ENABLED && newMode === "managed") {
      setBusy(true)
      try {
        const ok = await runDelegationConsent(targetScope)
        if (!ok) return // consent 未完了 → モード変更しない（toast は内部で表示済み）
      } finally {
        setBusy(false)
      }
    }

    // 既に managed で方針だけ変えた場合は user_mode の PUT（入金ゲート含む）は不要。
    if (!modeChanged) {
      if (SCOPE_SELECTABLE && newMode === "managed") await applyRiskMode(targetScope)
      return
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
      if (!res.ok) {
        // 入金ゲート: managed(完全おまかせ)切替に最低入金額 $200 が必要（A-2 で 422）。
        if (res.status === 422) {
          const body = await res.json().catch(() => null)
          if (body?.detail?.code === "DEPOSIT_BELOW_MINIMUM") {
            setCurrentMode(prev)
            showToast(t("toastDepositRequired", { gate: String(DEPOSIT_GATE_USD) }))
            return
          }
        }
        throw new Error(`HTTP ${res.status}`)
      }
      track(EV.OPMODE_CHANGE, { mode: newMode })
      // managed から離脱したら委譲を取消す（フラグ on のみ）
      if (CONSENT_ENABLED && prev === "managed" && newMode !== "managed") {
        await revokeDelegationConsent()
      }
      // risk_mode は委譲枠が確定してから最後に倒す（applyRiskMode の docstring 参照）。
      if (SCOPE_SELECTABLE && newMode === "managed") await applyRiskMode(targetScope)
      showToast(t("toastSwitched", { mode: MODE_LABEL[newMode] }))
    } catch {
      // ロールバック
      setCurrentMode(prev)
      showToast(t("toastSwitchFailed"))
    }
  }

  // おまかせは運用方針シートを挟む（既に managed でも方針変更のため開く）。
  // CONSENT_ENABLED off のときは「完全おまかせ」を選択不可にする（2026-08-04 PR2）。
  // 過去は同意フローをスキップして状態表示だけ変更していたため、委譲grantが
  // 一度も作られないまま「おまかせ」表示になる乖離が発生していた。正しい縮退は
  // 「そのモードを選べない」こと（docs/internal/2026-08-04_claude_md_addition_draft.md §3）。
  function handleSelect(newMode: UserMode) {
    if (busy) return
    if (newMode === "managed" && !CONSENT_ENABLED) {
      showToast(t("consentNotReady"))
      return
    }
    if (SCOPE_SELECTABLE && newMode === "managed") {
      setSheetOpen(true)
      return
    }
    if (newMode === currentMode) return
    void applyMode(newMode, "safety")
  }

  // 利回り重視はリスク開示への同意が前提（backend も 412 で二重にガードする）。
  async function handleScopeConfirm(targetScope: ManagedScope) {
    if (targetScope === "yield" && !aggressiveAcked) {
      setPendingScope(targetScope)
      setDisclosureOpen(true)
      return
    }
    setSheetOpen(false)
    await applyMode("managed", targetScope)
  }

  async function handleDisclosureConsented() {
    setDisclosureOpen(false)
    setAggressiveAcked(true)
    const target = pendingScope ?? "yield"
    setPendingScope(null)
    setSheetOpen(false)
    await applyMode("managed", target)
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
          // CONSENT_ENABLED off のとき「完全おまかせ」は選択不可（準備中）。
          const isConsentNotReady = mode.id === "managed" && !CONSENT_ENABLED
          const isDisabled = busy || isConsentNotReady
          return (
            <button
              key={mode.id}
              type="button"
              data-testid={`opmode-option-${mode.id}`}
              aria-pressed={isSelected}
              disabled={isDisabled}
              onClick={() => handleSelect(mode.id)}
              className={[
                "w-full text-left rounded-2xl border-2 p-4 transition-all",
                mode.bg,
                mode.border,
                isSelected ? "opacity-100" : "opacity-60",
                isDisabled ? "cursor-not-allowed" : "",
              ].join(" ")}
            >
              <div className="flex items-center gap-3">
                <Icon className={`w-6 h-6 shrink-0 ${mode.color}`} />
                <div>
                  <p className="text-[#1c1a27] font-bold text-base">{mode.label}</p>
                  <p className="text-[#736f7e] text-sm mt-0.5">{mode.desc}</p>
                  {/* 現在の運用方針。おまかせ選択中のみ表示する。 */}
                  {SCOPE_SELECTABLE && mode.id === "managed" && isSelected && (
                    <p
                      className="mt-1.5 text-xs font-medium text-[#1D9E75]"
                      data-testid="opmode-current-scope"
                    >
                      {scope === "yield" ? t("scopeYieldLabel") : t("scopeSafetyLabel")}
                    </p>
                  )}
                </div>
              </div>
            </button>
          )
        })}
      </div>

      {/* risk_mode が委譲枠より先行している = Pendle 提案は生成されるが broadcast されず
          approved のまま滞留する状態。黙って放置せず再署名を促す。 */}
      {SCOPE_SELECTABLE && needsResign && (
        <button
          type="button"
          data-testid="opmode-reconsent-cta"
          disabled={busy}
          onClick={() => setSheetOpen(true)}
          className="w-full rounded-xl border border-amber-500 bg-amber-500/10 p-3 text-left text-xs text-[#1c1a27] disabled:opacity-60"
        >
          {t("scopeReconsentRequired")}
        </button>
      )}

      {/* 開示モーダル表示中はシートを畳む。モーダル(z-50)はシート(z-70)より下に敷かれるため、
          両方出すとモーダルがシートの裏に隠れて操作不能になる。モーダルを閉じるとシートに戻る。 */}
      {sheetOpen && !disclosureOpen && (
        <ManagedScopeSheet
          currentScope={scope}
          requiresResignature={currentMode === "managed"}
          busy={busy}
          onConfirm={handleScopeConfirm}
          onCancel={() => setSheetOpen(false)}
        />
      )}

      {disclosureOpen && (
        <AggressiveRiskDisclosureModal
          onConsented={handleDisclosureConsented}
          onCancel={() => {
            setDisclosureOpen(false)
            setPendingScope(null)
          }}
        />
      )}
    </div>
  )
}
