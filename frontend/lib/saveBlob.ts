// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.
/**
 * Blob を端末にファイル保存する共通ユーティリティ（モバイル / アプリ内ブラウザ / iOS PWA 堅牢版）。
 *
 * 背景（2026-07-09）:
 *   各画面（TaxPanel / performance / history / trades）にコピーされていた
 *   「anchor.download + createObjectURL」方式は、端末依存で無言失敗していた:
 *     1. URL.revokeObjectURL を link.click() 直後に同期実行 → モバイルでは DL 処理が
 *        非同期のため revoke が先行し、DL がキャンセルされる。
 *     2. anchor を DOM に append せず click → 一部エンジン（iOS Safari / WebView）で発火しない。
 *     3. LINE アプリ内ブラウザ / iOS PWA(standalone) は blob + download 属性の DL を丸ごと拒否。
 *   → 「通常ブラウザ = 成功 / アプリ内・PWA = 失敗」という報告に一致。
 *
 * 対策:
 *   (a) モバイル / standalone(PWA) では Web Share API(files) を優先し、ネイティブの
 *       共有・保存シート経由で保存させる（アプリ内ブラウザ / iOS PWA でも動く）。
 *   (b) それ以外（デスクトップ等）は DOM に append した anchor で download し、
 *       revoke は十分に遅延させて click の非同期 DL 処理との race を避ける。
 *   デスクトップの挙動は従来どおり（Web Share は使わない）に保つ。
 */
export async function saveBlob(blob: Blob, filename: string): Promise<void> {
  const nav = navigator as Navigator & {
    canShare?: (data?: { files?: File[] }) => boolean
    share?: (data?: { files?: File[]; title?: string }) => Promise<void>
  }

  // standalone(PWA) or モバイル UA のときのみ Web Share を優先する（デスクトップ挙動は不変）。
  const preferShare =
    (typeof window !== 'undefined' &&
      window.matchMedia?.('(display-mode: standalone)')?.matches === true) ||
    /iphone|ipad|ipod|android/i.test(navigator.userAgent || '')

  if (preferShare && typeof nav.canShare === 'function' && typeof nav.share === 'function') {
    try {
      const file = new File([blob], filename, { type: blob.type || 'text/csv' })
      if (nav.canShare({ files: [file] })) {
        await nav.share({ files: [file], title: filename })
        return
      }
    } catch {
      // 共有非対応 / ユーザーキャンセル / user-gesture 失効 → 下の anchor 方式へフォールバック。
    }
  }

  // デスクトップ / 対応ブラウザ: DOM に append した anchor で download。
  const objectUrl = URL.createObjectURL(blob)
  try {
    const link = document.createElement('a')
    link.href = objectUrl
    link.download = filename
    link.rel = 'noopener'
    link.style.display = 'none'
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
  } finally {
    // click 後の DL 処理は非同期で走るため、revoke は十分に遅延させる（race による DL 中断を回避）。
    setTimeout(() => URL.revokeObjectURL(objectUrl), 10_000)
  }
}
