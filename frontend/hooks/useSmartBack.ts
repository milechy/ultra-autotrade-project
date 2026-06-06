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
 * - ブラウザ履歴がある場合（同一タブ遷移）は `router.back()` で「来訪元」に戻す。
 *   これにより /signup から開いて戻ると /signup に、/connect から開いて戻ると
 *   /connect に戻る（従来は遷移先が /connect 固定で、/signup 等から開くと
 *   無関係なウォレット接続画面に飛ばされていた）。
 * - 履歴が無い場合（`target="_blank"` で別タブが開かれた、ブックマーク等で直接
 *   URL を開いた）は戻り先が存在しないため、安全な `fallback`（既定はトップ `/`）へ。
 *
 * @param fallback 履歴が無いときの遷移先（既定 `/`）
 */
export function useSmartBack(fallback = '/') {
  const router = useRouter()
  return useCallback(() => {
    if (typeof window !== 'undefined' && window.history.length > 1) {
      router.back()
    } else {
      router.push(fallback)
    }
  }, [router, fallback])
}
