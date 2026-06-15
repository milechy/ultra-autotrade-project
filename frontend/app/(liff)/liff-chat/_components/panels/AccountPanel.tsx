// Copyright (c) Ultra AutoTrade. All rights reserved.
"use client"

import { useState, useEffect, useRef } from "react"
import { useRouter } from "next/navigation"
import { usePrivy } from "@privy-io/react-auth"
import {
  Copy,
  LogOut,
  Trash2,
  Building2,
  ChevronDown,
  Check,
  Pencil,
  Camera,
  X,
} from "lucide-react"
import { useTranslations } from "next-intl"
import { useLanguage } from "@/lib/useLanguage"
import { getAuthToken, clearAuthToken } from "@/lib/auth/token-key"
import { useWallet } from "@/hooks/useWallet"
import { liffFetch } from "@/lib/liff/liff-fetch"

interface UserData {
  id?: number
  email?: string
  username?: string
  user_mode?: "managed" | "active" | "pro"
  created_at?: string
  wallet_address?: string
  avatar_url?: string
  // 法人決算月 (1-12)。backend /api/user/settings で永続化される。
  corporate_fiscal_month?: number | null
}

// アバター画像のローカル保持キー（backend に avatar upload エンドポイントが
// 無いため、選択画像は localStorage に dataURL で退避しフロント内で表示する。
// 将来 POST /api/user/avatar 等が実装されたら差し替える。下記 TODO 参照）
const AVATAR_LS_KEY = "liff_avatar_data"

interface CorpForm {
  name: string
  number: string
  rep: string
  month: number
}

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? ""

export function AccountPanel() {
  const t = useTranslations("Liff.panels.account")
  const { language } = useLanguage()
  const router = useRouter()
  const { logout: privyLogout, authenticated } = usePrivy()
  // ウォレット表示の単一情報源化: backend の wallet_address が未記録でも、
  // Privy embedded（または injected）ウォレットのアドレスを useWallet から拾って
  // 「未連携」誤表示を防ぐ（Asana 1215576087505209）。
  const { address: liveWalletAddress } = useWallet()
  // 認証状態。未ログイン時に「ログアウト」/「アカウント削除」等の操作系を出さないためのガード。
  // backend JWT (getAuthToken) か Privy authenticated のどちらかがあれば「ログイン済み」とみなす
  // (UserHeader.tsx の {(user||token)&&…} ガード = commit 5c42868 を LIFF v3 にポート)。
  // token は localStorage 依存で SSR 不可のため、hydration mismatch を避けて useEffect で取得する。
  const [hasToken, setHasToken] = useState(false)
  const isAuthed = authenticated || hasToken
  const [userData, setUserData] = useState<UserData | null>(null)
  const [corpExpanded, setCorpExpanded] = useState(false)
  const [corpForm, setCorpForm] = useState<CorpForm>({ name: "", number: "", rep: "", month: 0 })
  const [corpSaved, setCorpSaved] = useState(false)
  const [deleteSheet, setDeleteSheet] = useState(false)
  const [deleteSubmitting, setDeleteSubmitting] = useState(false)
  const [toastMsg, setToastMsg] = useState("")
  const [copied, setCopied] = useState(false)

  // ユーザー名インライン編集
  const [editingName, setEditingName] = useState(false)
  const [nameDraft, setNameDraft] = useState("")
  const [nameSaving, setNameSaving] = useState(false)

  // アバター画像（localStorage 退避の dataURL。null = イニシャルアバター表示）
  const [avatarData, setAvatarData] = useState<string | null>(null)
  const fileInputRef = useRef<HTMLInputElement | null>(null)

  const showToast = (msg: string) => {
    setToastMsg(msg)
    setTimeout(() => setToastMsg(""), 2000)
  }

  // backend JWT の有無を client 側で確定（SSR では localStorage 不可）
  useEffect(() => {
    setHasToken(!!getAuthToken())
  }, [])

  // ユーザー設定を取得（/api/user/settings + /auth/me を併用）
  useEffect(() => {
    // settings エンドポイント（user_mode 等）
    liffFetch("/api/user/settings")
      .then((r) => (r.ok ? r.json() : null))
      .then((data: UserData | null) => {
        if (data) {
          setUserData((prev) => ({ ...prev, ...data }))
          // 決算月は backend を正本とする（localStorage の同期復元より後に解決するため勝つ）。
          if (typeof data.corporate_fiscal_month === "number") {
            setCorpForm((p) => ({ ...p, month: data.corporate_fiscal_month as number }))
          }
        }
      })
      .catch(() => {})

    // auth/me エンドポイント（created_at, wallet_address）
    liffFetch("/auth/me")
      .then((r) => (r.ok ? r.json() : null))
      .then(
        (
          data: {
            email?: string
            created_at?: string
            wallet_address?: string
          } | null,
        ) => {
          if (data) {
            setUserData((prev) => ({
              ...prev,
              ...(data.email && { email: data.email }),
              ...(data.created_at && { created_at: data.created_at }),
              ...(data.wallet_address && { wallet_address: data.wallet_address }),
            }))
          }
        },
      )
      .catch(() => {})
  }, [])

  // 法人情報を localStorage から復元
  useEffect(() => {
    try {
      const saved = localStorage.getItem("liff_corp_info")
      if (saved) {
        const parsed = JSON.parse(saved) as CorpForm
        setCorpForm(parsed)
      }
    } catch {
      // ignore
    }
  }, [])

  // アバター画像を localStorage から復元
  useEffect(() => {
    try {
      const saved = localStorage.getItem(AVATAR_LS_KEY)
      if (saved) setAvatarData(saved)
    } catch {
      // ignore
    }
  }, [])

  // イニシャル生成
  const getInitial = () => {
    if (userData?.username) return userData.username.charAt(0).toUpperCase()
    if (userData?.email) return userData.email.charAt(0).toUpperCase()
    return "U"
  }

  // 表示名（username か email の @ 前）
  const getDisplayName = () => {
    if (userData?.username) return userData.username
    if (userData?.email) return userData.email.split("@")[0]
    return t("defaultUser")
  }

  // ウォレットアドレス短縮表示。backend の wallet_address を優先し、
  // 未記録時は Privy/injected の実ウォレット（liveWalletAddress）にフォールバック。
  const getShortAddress = () => {
    const addr = userData?.wallet_address ?? liveWalletAddress
    if (!addr) return null
    return `${addr.slice(0, 6)}…${addr.slice(-4)}`
  }

  // 運用開始日フォーマット（locale に応じて EN/JA 日付形式を切り替え）
  const getStartedAt = () => {
    if (!userData?.created_at) return "—"
    const d = new Date(userData.created_at)
    return new Intl.DateTimeFormat(language === "en" ? "en-US" : "ja-JP", {
      year: "numeric",
      month: "long",
      day: "numeric",
    }).format(d)
  }

  // 運用モード表示
  const getModeLabel = () => {
    if (userData?.user_mode === "managed") return t("modeManagedLabel")
    if (userData?.user_mode === "active") return t("modeActiveLabel")
    return t("modeUnknown")
  }

  // ウォレットアドレスコピー（表示と同じ単一情報源を使う）
  const handleCopyWallet = async () => {
    const addr = userData?.wallet_address ?? liveWalletAddress
    if (!addr) return
    try {
      await navigator.clipboard.writeText(addr)
      setCopied(true)
      showToast(t("toastCopied"))
      setTimeout(() => setCopied(false), 2000)
    } catch {
      showToast(t("toastCopyFailed"))
    }
  }

  // 法人情報保存。決算月 (month) は backend に永続化し（TAX & REPORTS 法人モードの
  // アンロック条件）、name/number/rep は backend に対応カラムが無いため localStorage 保持。
  const handleCorpSave = async () => {
    // name/number/rep は引き続きローカル保持
    try {
      localStorage.setItem("liff_corp_info", JSON.stringify(corpForm))
    } catch {
      // ignore
    }

    // 決算月を backend に PUT（corporate_fiscal_month）。既存 settings の partial PUT を踏襲。
    const token = getAuthToken() ?? ""
    if (token && corpForm.month >= 1 && corpForm.month <= 12) {
      try {
        const res = await fetch(`${API_BASE}/api/user/settings`, {
          method: "PUT",
          headers: {
            Authorization: `Bearer ${token}`,
            "Content-Type": "application/json",
          },
          body: JSON.stringify({ corporate_fiscal_month: corpForm.month }),
        })
        if (res.ok) {
          const updated = (await res.json().catch(() => null)) as {
            corporate_fiscal_month?: number | null
          } | null
          setUserData((prev) => ({
            ...prev,
            corporate_fiscal_month: updated?.corporate_fiscal_month ?? corpForm.month,
          }))
        } else if (res.status === 401) {
          showToast(t("toastAuthExpired"))
          return
        } else {
          showToast(t("toastCorpFiscalFailed"))
          return
        }
      } catch {
        showToast(t("toastNetworkError"))
        return
      }
    }

    setCorpSaved(true)
    showToast(t("toastCorpSaved"))
    setTimeout(() => setCorpSaved(false), 2000)
  }

  // ユーザー名編集を開始（現在の表示名を draft に展開）
  const handleStartEditName = () => {
    setNameDraft(userData?.username ?? getDisplayName())
    setEditingName(true)
  }

  // ユーザー名を保存（PUT /api/user/settings — 既存 settings エンドポイントに
  // 部分更新で username を送る。既存コードベースで user_mode 等の partial PUT が
  // 確認済みのため同パターンを踏襲する）
  const handleSaveName = async () => {
    const next = nameDraft.trim()
    if (!next) {
      showToast(t("toastNameEmpty"))
      return
    }
    if (next === (userData?.username ?? "")) {
      setEditingName(false)
      return
    }
    const token = getAuthToken() ?? ""
    if (!token) {
      showToast(t("toastAuthExpired"))
      return
    }
    setNameSaving(true)
    try {
      const res = await fetch(`${API_BASE}/api/user/settings`, {
        method: "PUT",
        headers: {
          Authorization: `Bearer ${token}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ username: next }),
      })
      if (res.ok) {
        // backend が永続化した実値を反映（validator で小文字化される場合がある）
        const updated = (await res.json().catch(() => null)) as {
          username?: string
        } | null
        setUserData((prev) => ({ ...prev, username: updated?.username ?? next }))
        setEditingName(false)
        showToast(t("toastNameChanged"))
      } else if (res.status === 409) {
        showToast(t("toastNameDuplicate"))
      } else if (res.status === 422) {
        showToast(t("toastNameFormatError"))
      } else if (res.status === 401) {
        showToast(t("toastAuthExpired"))
      } else {
        // 偽装成功はしない（非永続をマスクしていた旧 fallback を撤廃）
        showToast(t("toastNameSaveFailed"))
      }
    } catch {
      showToast(t("toastNetworkError"))
    } finally {
      setNameSaving(false)
    }
  }

  // アバター画像を選択（ファイル選択ダイアログを開く）
  const handlePickAvatar = () => {
    fileInputRef.current?.click()
  }

  // アバター画像ファイルを読み込み（dataURL 化して表示 + localStorage 退避）
  // TODO: backend に画像アップロードエンドポイント（例 POST /api/user/avatar、
  //       multipart/form-data）が無いため、現状は localStorage に dataURL 退避のみ。
  //       実装後は FormData で POST し、返却された avatar_url を userData に反映する。
  const handleAvatarChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    e.target.value = "" // 同じファイルを再選択できるようにリセット
    if (!file) return
    if (!file.type.startsWith("image/")) {
      showToast(t("toastIconNotImage"))
      return
    }
    // 2MB 超は localStorage quota を圧迫するため拒否
    if (file.size > 2 * 1024 * 1024) {
      showToast(t("toastIconTooLarge"))
      return
    }
    const reader = new FileReader()
    reader.onload = () => {
      const dataUrl = typeof reader.result === "string" ? reader.result : null
      if (!dataUrl) return
      setAvatarData(dataUrl)
      try {
        localStorage.setItem(AVATAR_LS_KEY, dataUrl)
      } catch {
        // quota 超過などは握り潰す（表示は維持）
      }
      showToast(t("toastIconChanged"))
    }
    reader.onerror = () => showToast(t("toastIconLoadFailed"))
    reader.readAsDataURL(file)
  }

  // アバター画像をクリア（イニシャルアバターへ戻す）
  const handleClearAvatar = () => {
    setAvatarData(null)
    try {
      localStorage.removeItem(AVATAR_LS_KEY)
    } catch {
      // ignore
    }
    showToast(t("toastIconReset"))
  }

  // ログアウト
  const handleLogout = async () => {
    const { getLiff, isLiffConfigured } = await import("@/lib/liff/init")
    const liffMode = isLiffConfigured()

    // 1. Privy ログアウト
    try {
      await privyLogout()
    } catch {
      // ignore
    }

    // 2. LINE LIFF ログアウト（LIFF モードのみ。ブラウザ PWA モードでは skip）
    if (liffMode) {
      try {
        const liff = await getLiff()
        if (liff.isLoggedIn()) liff.logout()
      } catch {
        // ignore
      }
    }

    // 3. トークンクリア（正準キー + 旧キーの両方を消す）
    clearAuthToken()

    // 4. リダイレクト（LIFF モードは /liff-login、ブラウザは /login）
    router.replace(liffMode ? "/liff-login" : "/login")
  }

  // アカウント削除申請
  // backend: POST /api/user/delete-request（require_active_user / 冪等）。
  // 申請は account_deletion_requests に記録される。成功時のみ受付完了を表示し、
  // 失敗（404 含む）は誤魔化さず実エラーを表示する（押せるのに黙って失敗を防ぐ）。
  const handleDeleteRequest = async () => {
    const token = getAuthToken() ?? ""
    setDeleteSubmitting(true)
    try {
      const res = await fetch(`${API_BASE}/api/user/delete-request`, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${token}`,
          "Content-Type": "application/json",
        },
      })
      if (res.ok) {
        // 新規申請・既存 pending（already_requested）いずれも受付済みとして扱う
        showToast(t("toastDeleteRequested"))
        setDeleteSheet(false)
      } else if (res.status === 409) {
        // 残高ありなどサーバ側拒否（将来仕様）— シートは開いたまま理由を見せる
        showToast(t("toastDeleteBalanceError"))
      } else {
        // 404/5xx 等は実エラーとして扱う（成功偽装で dismiss しない）
        showToast(t("toastDeleteError"))
      }
    } catch {
      // ネットワークエラー — 実エラー表示
      showToast(t("toastDeleteError"))
    } finally {
      setDeleteSubmitting(false)
    }
  }

  const shortAddress = getShortAddress()

  return (
    <div className="space-y-4">
      {/* プロフィールカード */}
      <div className="bg-gradient-to-br from-[#b9a4f2] via-[#ecaccd] to-[#fbd9a0] rounded-2xl p-4">
        <div className="flex items-center gap-3">
          {/* アバター（画像 or イニシャル）＋ 変更ボタン */}
          <div className="relative flex-shrink-0">
            <button
              type="button"
              onClick={handlePickAvatar}
              aria-label={t("changeIconAriaLabel")}
              className="w-14 h-14 rounded-full overflow-hidden bg-[#1D9E75]/20 border border-[#1D9E75] flex items-center justify-center text-[#1D9E75] text-xl font-bold"
            >
              {avatarData ? (
                // eslint-disable-next-line @next/next/no-img-element
                <img
                  src={avatarData}
                  alt={t("avatarAlt")}
                  className="w-full h-full object-cover"
                />
              ) : (
                getInitial()
              )}
            </button>
            <span className="absolute -bottom-0.5 -right-0.5 w-5 h-5 rounded-full bg-[#1D9E75] flex items-center justify-center pointer-events-none">
              <Camera className="w-3 h-3 text-white" />
            </span>
            {/* 隠し file input（画像アップロード/選択） */}
            <input
              ref={fileInputRef}
              type="file"
              accept="image/*"
              onChange={handleAvatarChange}
              className="hidden"
              data-testid="avatar-file-input"
            />
          </div>
          <div className="flex-1 min-w-0">
            {editingName ? (
              <div className="flex items-center gap-2">
                <input
                  value={nameDraft}
                  onChange={(e) => setNameDraft(e.target.value)}
                  autoFocus
                  maxLength={40}
                  placeholder={t("editNamePlaceholder")}
                  aria-label={t("editNameAriaLabel")}
                  className="flex-1 min-w-0 ax-card-warm text-[#1c1a27] px-2.5 py-1.5 rounded-lg text-sm outline-none focus:ring-1 focus:ring-[#1D9E75]"
                />
                <button
                  type="button"
                  onClick={handleSaveName}
                  disabled={nameSaving}
                  aria-label={t("saveNameAriaLabel")}
                  className="w-7 h-7 rounded-lg bg-[#1D9E75] flex items-center justify-center disabled:opacity-40"
                >
                  <Check className="w-4 h-4 text-white" />
                </button>
                <button
                  type="button"
                  onClick={() => setEditingName(false)}
                  disabled={nameSaving}
                  aria-label={t("cancelEditAriaLabel")}
                  className="w-7 h-7 rounded-lg ax-card-warm flex items-center justify-center disabled:opacity-40"
                >
                  <X className="w-4 h-4 text-[#736f7e]" />
                </button>
              </div>
            ) : (
              <div className="flex items-center gap-1.5">
                <p className="text-[#1c1a27] font-semibold truncate">{getDisplayName()}</p>
                <button
                  type="button"
                  onClick={handleStartEditName}
                  aria-label={t("editNameEditAriaLabel")}
                  className="flex-shrink-0 text-[#736f7e] hover:text-[#1D9E75] transition-colors"
                >
                  <Pencil className="w-3.5 h-3.5" />
                </button>
              </div>
            )}
            {userData?.email && (
              <p className="text-[#736f7e] text-sm truncate">{userData.email}</p>
            )}
            {avatarData && !editingName && (
              <button
                type="button"
                onClick={handleClearAvatar}
                className="text-[#736f7e] hover:text-[#1c1a27] text-xs mt-1 transition-colors"
              >
                {t("resetIcon")}
              </button>
            )}
            {/* ログイン方法バッジ（LIFF = LINE ログイン） */}
            <div className="flex flex-wrap gap-1 mt-1">
              <span className="ax-card-warm text-[#1c1a27] text-xs px-2 py-0.5 rounded-full">
                {t("lineLoginBadge")}
              </span>
            </div>
          </div>
        </div>
      </div>

      {/* 運用情報セクション */}
      <div className="ax-card-warm rounded-xl overflow-hidden">
        {/* 運用開始日 */}
        <div className="flex items-center justify-between px-4 py-3 border-b border-[#1c1a27]/15">
          <span className="text-[#736f7e] text-sm">{t("startedAt")}</span>
          <span className="text-[#1c1a27] text-sm">{getStartedAt()}</span>
        </div>

        {/* 運用モード */}
        <div className="flex items-center justify-between px-4 py-3 border-b border-[#1c1a27]/15">
          <span className="text-[#736f7e] text-sm">{t("opMode")}</span>
          <span className="text-[#1c1a27] text-sm">{getModeLabel()}</span>
        </div>

        {/* ウォレットアドレス */}
        <div className="flex items-center justify-between px-4 py-3">
          <span className="text-[#736f7e] text-sm">{t("wallet")}</span>
          {shortAddress ? (
            <button
              onClick={handleCopyWallet}
              className="flex items-center gap-1.5 text-[#1c1a27] text-sm"
            >
              <span className="font-mono text-xs">{shortAddress}</span>
              {copied ? (
                <Check className="w-3.5 h-3.5 text-[#1D9E75]" />
              ) : (
                <Copy className="w-3.5 h-3.5 text-[#736f7e]" />
              )}
            </button>
          ) : (
            <span className="text-[#736f7e] text-sm">{t("walletNotLinked")}</span>
          )}
        </div>
      </div>

      {/* 法人情報セクション（アコーディオン） */}
      <div className="ax-card-warm rounded-xl overflow-hidden">
        <button
          onClick={() => setCorpExpanded((v) => !v)}
          className="flex items-center justify-between w-full px-4 py-3.5"
        >
          <div className="flex items-center gap-2">
            <Building2 className="w-4 h-4 text-[#736f7e]" />
            <span className="text-[#1c1a27] text-sm font-medium">{t("corpSectionTitle")}</span>
          </div>
          <ChevronDown
            className={`w-4 h-4 text-[#736f7e] transition-transform duration-200 ${
              corpExpanded ? "rotate-180" : ""
            }`}
          />
        </button>

        {corpExpanded && (
          <div className="px-4 pb-4 space-y-3 border-t border-[#1c1a27]/15 pt-3">
            <input
              placeholder={t("corpNamePlaceholder")}
              value={corpForm.name}
              onChange={(e) => setCorpForm((p) => ({ ...p, name: e.target.value }))}
              className="w-full ax-card-warm-soft text-[#1c1a27] px-3 py-2.5 rounded-lg text-sm placeholder-[#736f7e] border border-[#1c1a27]/15 outline-none focus:ring-1 focus:ring-[#1D9E75]"
            />
            <input
              placeholder={t("corpNumberPlaceholder")}
              value={corpForm.number}
              onChange={(e) => setCorpForm((p) => ({ ...p, number: e.target.value }))}
              maxLength={13}
              inputMode="numeric"
              className="w-full ax-card-warm-soft text-[#1c1a27] px-3 py-2.5 rounded-lg text-sm placeholder-[#736f7e] border border-[#1c1a27]/15 outline-none focus:ring-1 focus:ring-[#1D9E75]"
            />
            <input
              placeholder={t("corpRepPlaceholder")}
              value={corpForm.rep}
              onChange={(e) => setCorpForm((p) => ({ ...p, rep: e.target.value }))}
              className="w-full ax-card-warm-soft text-[#1c1a27] px-3 py-2.5 rounded-lg text-sm placeholder-[#736f7e] border border-[#1c1a27]/15 outline-none focus:ring-1 focus:ring-[#1D9E75]"
            />

            {/* 決算月グリッド */}
            <div>
              <p className="text-[#736f7e] text-xs mb-2">{t("corpFiscalMonthLabel")}</p>
              <div className="grid grid-cols-6 gap-1.5">
                {Array.from({ length: 12 }, (_, i) => i + 1).map((m) => (
                  <button
                    key={m}
                    onClick={() => setCorpForm((p) => ({ ...p, month: m }))}
                    className={`py-2 rounded-lg text-sm font-medium transition-colors ${
                      corpForm.month === m
                        ? "bg-[#1D9E75] text-white"
                        : "ax-card-warm-soft text-[#736f7e] border border-[#1c1a27]/15 hover:bg-black/5"
                    }`}
                  >
                    {t("corpFiscalMonthUnit", { m })}
                  </button>
                ))}
              </div>
            </div>

            <button
              onClick={handleCorpSave}
              disabled={!corpForm.name || !corpForm.number || !corpForm.rep || !corpForm.month}
              className="w-full py-3 bg-[#1D9E75] text-white rounded-xl text-sm font-semibold disabled:opacity-40 disabled:cursor-not-allowed transition-opacity"
            >
              {corpSaved ? t("corpSavedBtn") : t("corpSaveBtn")}
            </button>
          </div>
        )}
      </div>

      {/* ログアウト / 削除は認証済みのみ表示（未ログイン時の誤表示を防ぐ） */}
      {isAuthed && (
        <>
          {/* ログアウトボタン */}
          <button
            onClick={handleLogout}
            className="flex items-center gap-3 w-full px-4 py-4 ax-card-warm rounded-xl hover:bg-black/5 transition-colors"
          >
            <LogOut className="w-5 h-5 text-red-600" />
            <span className="text-red-600 font-medium">{t("logoutBtn")}</span>
          </button>

          {/* アカウント削除ボタン */}
          <div className="flex justify-center pb-2">
            <button
              onClick={() => setDeleteSheet(true)}
              className="flex items-center gap-2 px-4 py-2 text-[#736f7e] hover:text-[#1c1a27] transition-colors"
            >
              <Trash2 className="w-4 h-4" />
              <span className="text-xs">{t("deleteAccountBtn")}</span>
            </button>
          </div>
        </>
      )}

      {/* 削除確認ボトムシート */}
      {deleteSheet && (
        <>
          <div
            className="fixed inset-0 z-[60] bg-black/60"
            onClick={() => setDeleteSheet(false)}
          />
          <div
            className="fixed bottom-0 left-0 right-0 z-[70] ax-card-warm rounded-t-2xl px-4 pb-8 pt-4
                        animate-in slide-in-from-bottom duration-300"
          >
            <div className="mx-auto mb-4 h-1 w-8 rounded-full bg-[#1c1a27]/10" />
            <h3 className="text-[#1c1a27] font-semibold mb-2">{t("deleteSheetTitle")}</h3>
            <p className="text-[#736f7e] text-sm mb-6">
              {t("deleteSheetDesc")}
            </p>
            <button
              onClick={handleDeleteRequest}
              disabled={deleteSubmitting}
              className="w-full py-3.5 bg-red-600/20 border border-red-600 text-red-600 rounded-xl font-medium mb-3 disabled:opacity-50"
            >
              {deleteSubmitting ? t("deleteSubmittingBtn") : t("deleteSubmitBtn")}
            </button>
            <button
              onClick={() => setDeleteSheet(false)}
              disabled={deleteSubmitting}
              className="w-full py-3.5 border border-[#1c1a27]/15 text-[#736f7e] rounded-xl font-medium disabled:opacity-50"
            >
              {t("deleteCancelBtn")}
            </button>
          </div>
        </>
      )}

      {/* トースト */}
      {toastMsg && (
        <div className="fixed bottom-24 left-1/2 -translate-x-1/2 z-[80] bg-[#1b1a23] text-[#fbf7f0] px-4 py-2 rounded-full text-sm whitespace-nowrap">
          {toastMsg}
        </div>
      )}
    </div>
  )
}
