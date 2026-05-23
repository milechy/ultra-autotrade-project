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

export interface GasFeeApprovalDialogProps {
  /** ダイアログを開くかどうか */
  open: boolean
  /** USDC 建てのガス額 (例: 0.12 → "$0.12 USDC") */
  gasEstimateUsdc: number
  /** ユーザが「承認」を押したときに呼ばれる */
  onApprove: () => void
  /** ユーザが「キャンセル」を押したとき・閉じたときに呼ばれる */
  onCancel: () => void
}

/**
 * 初回 tx の前に、ガス代として消費する USDC 額を提示し、承認を取る Dialog。
 *
 * 仕様原文では Paymaster は将来扱いだったが、Q3 reframe で MVP 格上げ。
 * 初回 tx 前にこのダイアログでユーザに承認を取り、以降は自動送信させる前提。
 */
export function GasFeeApprovalDialog({
  open,
  gasEstimateUsdc,
  onApprove,
  onCancel,
}: GasFeeApprovalDialogProps): React.ReactElement {
  const formatted = gasEstimateUsdc.toLocaleString("en-US", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 4,
  })

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        if (!next) onCancel()
      }}
    >
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>初回ガス代の承認</DialogTitle>
          <DialogDescription>
            初回のガス代として ~${formatted} USDC を消費します。
            次回以降は自動です。
          </DialogDescription>
        </DialogHeader>

        <div className="rounded-md border p-3 text-sm">
          <div className="flex items-center justify-between">
            <span className="text-muted-foreground">推定ガス代</span>
            <span className="font-medium">~${formatted} USDC</span>
          </div>
          <p className="mt-2 text-xs text-muted-foreground">
            Base 上の ERC-20 Paymaster を使い、ETH を持っていなくても
            USDC でガス代を支払える仕組みです。
          </p>
        </div>

        <DialogFooter className="gap-2 sm:gap-2">
          <Button variant="outline" onClick={onCancel}>
            キャンセル
          </Button>
          <Button onClick={onApprove}>承認</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

export default GasFeeApprovalDialog
