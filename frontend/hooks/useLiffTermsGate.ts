// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.
// frontend/hooks/useLiffTermsGate.ts
//
// LIFF (BtoC 消費者) の重要事項同意 (terms_version="liff-v3") を入口非依存で
// 強制するためのゲート判定フック。
//
// 背景 (Asana 1215360586206558):
//   同意の強制は従来 /liff-login → /liff-confirm の 1 経路にしか無く、
//   リッチメニュー / ブックマーク等で /liff-chat に直接アクセスすると
//   重要事項確認を一度も通らずホームが描画されていた。非カストディアル・
//   元本喪失・鍵喪失の法的同意としては入口非依存で強制する必要がある。
//   本フックを (liff)/layout.tsx から呼び、未同意なら /liff-confirm へ誘導する。
//
// fail-closed: settings 取得失敗時は "not-accepted" を返し同意画面へ送る。
//   /liff-confirm 側が再度 settings を確認し、同意済みなら /liff-chat へ戻すため
//   already-agreed ユーザーがロックされることはない (再同意は冪等)。

"use client"

import { useEffect, useState } from "react"

import { getAuthToken } from "@/lib/auth/token-key"

/** liff-confirm / settings_router (LIFF_TERMS_VERSION) と一致させること。 */
const LIFF_TERMS_VERSION = "liff-v3"

/** ブラウザ wallet 経路の同意バージョン (POST /auth/terms/accept で記録)。 */
const BROWSER_TERMS_VERSION = "2.0"

/** デフォルト accepted バージョン一覧 (LIFF 経路向け後方互換)。 */
const DEFAULT_ACCEPTED_VERSIONS: readonly string[] = [LIFF_TERMS_VERSION]

export type LiffTermsGateState = "loading" | "accepted" | "not-accepted"

/**
 * 重要事項同意の状態を返す。LIFF / ブラウザ両経路に対応。
 *
 * @param enabled          false の間はゲートを無効化し常に "accepted" を返す
 *                         (除外ページ / 未認証時に呼び出し側が無効化する)。
 * @param acceptedVersions 「同意済み」とみなすバージョン一覧。
 *                         デフォルト ['liff-v3'] — 既存 LIFF 呼び出しは引数省略で後方互換。
 *                         ブラウザ経路では ['liff-v3', '2.0'] を渡す。
 */
export function useLiffTermsGate(
  enabled: boolean,
  acceptedVersions: readonly string[] = DEFAULT_ACCEPTED_VERSIONS
): LiffTermsGateState {
  const [state, setState] = useState<LiffTermsGateState>("loading")

  useEffect(() => {
    if (!enabled) {
      setState("accepted")
      return
    }

    const token = getAuthToken()
    if (!token) {
      // 認証は別ガード (auth guard) が担保。token 無しでは同意判定不能のため
      // ここでは pass-through し、auth guard 側に委ねる。
      setState("accepted")
      return
    }

    const apiBase = process.env.NEXT_PUBLIC_API_URL ?? ""
    let cancelled = false
    setState("loading")

    fetch(`${apiBase}/api/user/settings`, {
      headers: { Authorization: `Bearer ${token}` },
    })
      .then((r) => (r.ok ? r.json() : null))
      .then((data: { terms_version?: string | null } | null) => {
        if (cancelled) return
        setState(
          data?.terms_version != null && acceptedVersions.includes(data.terms_version)
            ? "accepted"
            : "not-accepted"
        )
      })
      .catch(() => {
        if (cancelled) return
        // 法的同意ガード: 不確定時は同意画面へ誘導 (fail-closed)。
        setState("not-accepted")
      })

    return () => {
      cancelled = true
    }
  }, [enabled, acceptedVersions])

  return state
}

export { LIFF_TERMS_VERSION, BROWSER_TERMS_VERSION }
