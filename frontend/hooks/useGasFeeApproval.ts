// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.
"use client"

import * as React from "react"

/**
 * localStorage key for "user has approved gas fee deduction in USDC at least once"
 *
 * 仕様原文では Paymaster は将来扱いだったが、Q3 reframe で MVP 格上げ。
 * 初回 tx 前に GasFeeApprovalDialog で承認を取り、ユーザが「次回以降自動」を
 * チェックしていればこのフラグを localStorage に保存する。
 */
export const PAYMASTER_APPROVED_KEY = "uata.paymaster.approved"

export interface UseGasFeeApprovalResult {
  /** true なら GasFeeApprovalDialog を表示する必要がある */
  needsApproval: boolean
  /** 「承認 + 次回以降も自動」を選んだときに呼ぶ */
  markApproved: () => void
  /** 設定を消し、次回 tx で再度ダイアログを出す */
  reset: () => void
}

function readApproved(): boolean {
  if (typeof window === "undefined") return false
  try {
    return window.localStorage.getItem(PAYMASTER_APPROVED_KEY) === "1"
  } catch {
    // localStorage アクセス不可 (Private mode / SSR 等) は未承認扱い
    return false
  }
}

/**
 * 「初回承認済みフラグ」を localStorage で管理する hook。
 *
 * - SSR/CSR の hydration 差分を避けるため、初期値は false で mount 後に同期する。
 * - storage event を購読し、別タブでの変更にも追従する。
 */
export function useGasFeeApproval(): UseGasFeeApprovalResult {
  const [approved, setApproved] = React.useState<boolean>(false)

  React.useEffect(() => {
    setApproved(readApproved())

    const handler = (e: StorageEvent) => {
      if (e.key === PAYMASTER_APPROVED_KEY) {
        setApproved(readApproved())
      }
    }
    if (typeof window !== "undefined") {
      window.addEventListener("storage", handler)
      return () => window.removeEventListener("storage", handler)
    }
    return undefined
  }, [])

  const markApproved = React.useCallback(() => {
    if (typeof window === "undefined") return
    try {
      window.localStorage.setItem(PAYMASTER_APPROVED_KEY, "1")
    } catch {
      // 無視 (Private mode 等)
    }
    setApproved(true)
  }, [])

  const reset = React.useCallback(() => {
    if (typeof window === "undefined") return
    try {
      window.localStorage.removeItem(PAYMASTER_APPROVED_KEY)
    } catch {
      // 無視
    }
    setApproved(false)
  }, [])

  return {
    needsApproval: !approved,
    markApproved,
    reset,
  }
}

export default useGasFeeApproval
