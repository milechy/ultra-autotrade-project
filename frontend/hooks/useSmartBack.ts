// Copyright (c) Ultra AutoTrade. All rights reserved.
'use client'

import { useCallback } from 'react'
import { useRouter } from 'next/navigation'

/**
 * 「戻る」ボタン共通フック。
 *
 * 規約 / プライバシーポリシー / リスク開示など、複数の入口（/connect・/signup・
 * 設定画面・LIFF webview 等）からリンクされる法的文書ページで使う。
 *
 * 挙動:
 * 挙動（優先順）:
 * 1. URL に `?return=<path>` がある場合はそこへ `router.push`（最優先）。
 *    liff-chat 等から新規タブ／新規履歴で開かれると router.back() が来訪元に戻れず
 *    （history.length=1 → fallback `/` → 未認証だと /connect に飛ぶ）問題になるため、
 *    呼び出し側が戻り先を明示できるようにする。open-redirect 防止のため同一オリジンの
 *    相対パス（`/` 始まり・`//` 除外）のみ許可する。
 * 2. ブラウザ履歴がある場合（同一タブ遷移）は `router.back()` で「来訪元」に戻す。
 *    これにより /signup から開いて戻ると /signup に、/connect から開いて戻ると /connect に戻る。
 * 3. 履歴が無い場合（別タブ・ブックマーク直開き等）は安全な `fallback`（既定はトップ `/`）へ。
 *
 * @param fallback 履歴も `?return` も無いときの遷移先（既定 `/`）
 */
export function useSmartBack(fallback = '/') {
  const router = useRouter()
  return useCallback(() => {
    if (typeof window !== 'undefined') {
      const ret = new URLSearchParams(window.location.search).get('return')
      if (ret && ret.startsWith('/') && !ret.startsWith('//')) {
        router.push(ret)
        return
      }
      if (window.history.length > 1) {
        router.back()
        return
      }
    }
    router.push(fallback)
  }, [router, fallback])
}
