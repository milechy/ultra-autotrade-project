// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.
"use client"

import * as React from "react"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Button } from "@/components/ui/button"
import { Checkbox } from "@/components/ui/checkbox"
import { Label } from "@/components/ui/label"

export interface GasFeeApprovalDialogProps {
  /** ダイアログを開くかどうか */
  open: boolean
  /** USDC 建てのガス額 (例: 0.12 → "$0.12 USDC") */
  gasEstimateUsdc: number
  /**
   * USD 換算額。省略時は USDC 額と同値表示 (USDC ≈ $1 前提)。
   * 実値は呼出側でオラクル経由で渡す想定。
   */
  gasEstimateUsd?: number
  /** ユーザが「承認」を押したときに呼ばれる。auto = 次回以降自動承認チェックの状態 */
  onApprove: (opts: { rememberApproval: boolean }) => void
  /** ユーザが「キャンセル」を押したとき・閉じたときに呼ばれる */
  onCancel: () => void
  /** approve 押下後の処理中フラグ。true の間ボタンを無効化しスピナ表示 */
  loading?: boolean
}

/**
 * 初回 tx の前に、ガス代として消費する USDC 額を提示し、承認を取る Dialog。
 *
 * 仕様原文では Paymaster は将来扱いだったが、Q3 reframe で MVP 格上げ。
 * 初回 tx 前にこのダイアログでユーザに承認を取り、以降は自動送信させる前提。
 *
 * - USD 換算を併記 (オラクル経由の値を呼出側で渡す)
 * - 「次回以降は自動で承認します」チェックボックス (localStorage は呼出側の hook で保存)
 * - キャンセル時は tx を発火しない
 * - a11y: aria-label / keyboard escape (Radix Dialog 経由)
 * - loading 状態
 */
export function GasFeeApprovalDialog({
  open,
  gasEstimateUsdc,
  gasEstimateUsd,
  onApprove,
  onCancel,
  loading = false,
}: GasFeeApprovalDialogProps): React.ReactElement {
  const [rememberApproval, setRememberApproval] = React.useState<boolean>(true)

  const formattedUsdc = gasEstimateUsdc.toLocaleString("en-US", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 4,
  })
  const usdValue = gasEstimateUsd ?? gasEstimateUsdc
  const formattedUsd = usdValue.toLocaleString("en-US", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })

  const handleApprove = React.useCallback(() => {
    if (loading) return
    onApprove({ rememberApproval })
  }, [loading, onApprove, rememberApproval])

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        if (loading) return // 処理中の close は無視
        if (!next) onCancel()
      }}
    >
      <DialogContent
        className="sm:max-w-md"
        aria-label="初回ガス代の承認ダイアログ"
      >
        <DialogHeader>
          <DialogTitle>初回ガス代の承認</DialogTitle>
          <DialogDescription>
            初回のガス代として ~${formattedUsdc} USDC (約 ${formattedUsd}) を消費します。
            次回以降は自動で承認することもできます。
          </DialogDescription>
        </DialogHeader>

        <div
          className="rounded-md border p-3 text-sm"
          role="group"
          aria-label="ガス代見積もり"
        >
          <div className="flex items-center justify-between">
            <span className="text-muted-foreground">推定ガス代</span>
            <span className="font-medium">
              ~${formattedUsdc} USDC
              <span className="ml-2 text-xs text-muted-foreground">
                (≈ ${formattedUsd})
              </span>
            </span>
          </div>
          <p className="mt-2 text-xs text-muted-foreground">
            Base 上の ERC-20 Paymaster を使い、ETH を持っていなくても
            USDC でガス代を支払える仕組みです。
          </p>
        </div>

        <div className="flex items-center gap-2 pt-1">
          <Checkbox
            id="remember-approval"
            checked={rememberApproval}
            onCheckedChange={(v) => setRememberApproval(v === true)}
            disabled={loading}
            aria-label="次回以降は自動で承認します"
          />
          <Label
            htmlFor="remember-approval"
            className="cursor-pointer text-sm font-normal"
          >
            次回以降は自動で承認します
          </Label>
        </div>

        <DialogFooter className="gap-2 sm:gap-2">
          <Button
            variant="outline"
            onClick={onCancel}
            disabled={loading}
            aria-label="キャンセル"
          >
            キャンセル
          </Button>
          <Button
            onClick={handleApprove}
            disabled={loading}
            aria-label="承認"
            aria-busy={loading}
          >
            {loading ? (
              <span className="inline-flex items-center gap-2">
                <span
                  className="inline-block h-3 w-3 animate-spin rounded-full border-2 border-current border-t-transparent"
                  aria-hidden="true"
                />
                送信中...
              </span>
            ) : (
              "承認"
            )}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

export default GasFeeApprovalDialog
