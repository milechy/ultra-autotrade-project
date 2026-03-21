'use client'
// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.

import React, { useState } from 'react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from '@/components/ui/dialog'

export interface APIKey {
  name: string
  createdAt: string
  maskedKey: string
  status: 'active' | 'inactive'
}

interface APIKeySectionProps {
  apiKeys: APIKey[]
  onRotate: (keyName: string) => void
}

export function APIKeySection({ apiKeys, onRotate }: APIKeySectionProps) {
  const [rotateTarget, setRotateTarget] = useState<string | null>(null)
  const [rotating, setRotating] = useState(false)

  const handleRotateClick = (name: string) => {
    setRotateTarget(name)
  }

  const handleConfirmRotate = async () => {
    if (!rotateTarget) return
    setRotating(true)
    try {
      // TODO: POST /api/settings/api-keys/rotate
      await new Promise<void>((resolve) => setTimeout(resolve, 800))
      onRotate(rotateTarget)
    } finally {
      setRotating(false)
      setRotateTarget(null)
    }
  }

  return (
    <>
      <Card className="bg-gray-900 border-gray-800">
        <CardHeader className="pb-3">
          <CardTitle className="text-gray-100 text-base font-semibold">
            APIキー管理
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow className="border-gray-800 hover:bg-transparent">
                  <TableHead className="text-gray-500 text-xs">キー名</TableHead>
                  <TableHead className="text-gray-500 text-xs">作成日</TableHead>
                  <TableHead className="text-gray-500 text-xs">マスクキー</TableHead>
                  <TableHead className="text-gray-500 text-xs">ステータス</TableHead>
                  <TableHead className="text-gray-500 text-xs text-right">操作</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {apiKeys.map((key) => (
                  <TableRow
                    key={key.name}
                    className="border-gray-800 hover:bg-gray-800/30"
                  >
                    <TableCell className="text-gray-200 text-sm font-medium">
                      {key.name}
                    </TableCell>
                    <TableCell className="text-gray-400 text-sm">
                      {key.createdAt}
                    </TableCell>
                    <TableCell className="text-gray-400 text-sm font-mono">
                      {key.maskedKey}
                    </TableCell>
                    <TableCell>
                      <span
                        className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${
                          key.status === 'active'
                            ? 'bg-green-900/40 text-green-400 border border-green-800'
                            : 'bg-gray-800 text-gray-500 border border-gray-700'
                        }`}
                      >
                        {key.status === 'active' ? '有効' : '無効'}
                      </span>
                    </TableCell>
                    <TableCell className="text-right">
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => handleRotateClick(key.name)}
                        className="border-gray-700 text-gray-300 hover:bg-gray-800 text-xs"
                      >
                        ローテーション
                      </Button>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
          <p className="mt-3 text-xs text-gray-600">
            Phase 1はモック表示のみ。APIキーのフルテキストは表示されません。
          </p>
        </CardContent>
      </Card>

      <Dialog
        open={rotateTarget !== null}
        onOpenChange={(open) => {
          if (!open) setRotateTarget(null)
        }}
      >
        <DialogContent className="bg-gray-900 border-gray-700 text-gray-100 max-w-md">
          <DialogHeader>
            <DialogTitle className="text-gray-100">APIキーのローテーション確認</DialogTitle>
            <DialogDescription className="text-gray-400">
              <span className="font-semibold text-gray-200">{rotateTarget}</span>{' '}
              をローテーションしますか？現在のキーは無効化されます。
            </DialogDescription>
          </DialogHeader>
          <DialogFooter className="gap-2 mt-2">
            <Button
              variant="outline"
              onClick={() => setRotateTarget(null)}
              disabled={rotating}
              className="border-gray-700 text-gray-300 hover:bg-gray-800"
            >
              キャンセル
            </Button>
            <Button
              onClick={handleConfirmRotate}
              disabled={rotating}
              className="bg-blue-700 hover:bg-blue-600 text-white"
            >
              {rotating ? 'ローテーション中...' : 'ローテーションする'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  )
}
