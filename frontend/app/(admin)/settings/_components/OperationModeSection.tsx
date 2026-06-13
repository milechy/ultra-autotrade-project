'use client'
// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.

import React, { useState } from 'react'
import { useTranslations } from 'next-intl'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from '@/components/ui/dialog'
import { StatusBadge } from '@/components/shared/StatusBadge'

type OperationMode = 'NORMAL' | 'SAFE_MODE' | 'HARD_STOP'

interface OperationModeSectionProps {
  mode: OperationMode
  onModeChange: (mode: OperationMode) => void
}

export function OperationModeSection({
  mode,
  onModeChange,
}: OperationModeSectionProps) {
  const t = useTranslations('AdminOperationMode')
  const [pendingMode, setPendingMode] = useState<OperationMode | null>(null)

  const MODE_CONFIG: Record<
    OperationMode,
    { label: string; description: string; buttonClass: string }
  > = {
    NORMAL: {
      label: t('modeNormalLabel'),
      description: t('modeNormalDescription'),
      buttonClass:
        'border-green-600 text-green-400 bg-green-900/20 hover:bg-green-900/40',
    },
    SAFE_MODE: {
      label: t('modeSafeModeLabel'),
      description: t('modeSafeModeDescription'),
      buttonClass:
        'border-yellow-600 text-yellow-400 bg-yellow-900/20 hover:bg-yellow-900/40',
    },
    HARD_STOP: {
      label: t('modeHardStopLabel'),
      description: t('modeHardStopDescription'),
      buttonClass:
        'border-red-600 text-red-400 bg-red-900/20 hover:bg-red-900/40',
    },
  }

  const handleModeClick = (target: OperationMode) => {
    if (target === mode) return
    setPendingMode(target)
  }

  const handleConfirm = () => {
    if (pendingMode) {
      onModeChange(pendingMode)
    }
    setPendingMode(null)
  }

  const handleCancel = () => {
    setPendingMode(null)
  }

  return (
    <>
      <Card className="bg-gray-900 border-gray-800">
        <CardHeader className="pb-3">
          <div className="flex items-center justify-between">
            <CardTitle className="text-gray-100 text-base font-semibold">
              {t('title')}
            </CardTitle>
            <StatusBadge status={mode} />
          </div>
        </CardHeader>
        <CardContent>
          <div className="flex flex-wrap gap-3">
            {(Object.keys(MODE_CONFIG) as OperationMode[]).map((m) => {
              const cfg = MODE_CONFIG[m]
              const isActive = m === mode
              return (
                <button
                  key={m}
                  onClick={() => handleModeClick(m)}
                  disabled={isActive}
                  className={`px-5 py-2 rounded-lg border font-medium text-sm transition-colors disabled:opacity-60 disabled:cursor-default ${
                    isActive
                      ? 'opacity-60 cursor-default ' + cfg.buttonClass
                      : cfg.buttonClass + ' cursor-pointer'
                  }`}
                >
                  {cfg.label}
                </button>
              )
            })}
          </div>
          <p className="mt-3 text-xs text-gray-500">
            {/* TODO: PUT /api/automation/mode */}
            {t('currentMode')}: <span className="text-gray-300 font-medium">{MODE_CONFIG[mode].label}</span>
            {' — '}{MODE_CONFIG[mode].description}
          </p>
        </CardContent>
      </Card>

      <Dialog open={pendingMode !== null} onOpenChange={(open) => { if (!open) handleCancel() }}>
        <DialogContent className="bg-gray-900 border-gray-700 text-gray-100 max-w-md">
          <DialogHeader>
            <DialogTitle className="text-gray-100">{t('dialogTitle')}</DialogTitle>
            <DialogDescription className="text-gray-400">
              {t('dialogDescription')}{' '}
              <span className="font-semibold text-gray-200">
                {pendingMode ? MODE_CONFIG[pendingMode].label : ''}
              </span>{' '}
              {t('dialogDescriptionSuffix')}
              {pendingMode === 'HARD_STOP' && (
                <span className="block mt-2 text-red-400 font-medium">
                  {t('hardStopWarning')}
                </span>
              )}
            </DialogDescription>
          </DialogHeader>
          <DialogFooter className="gap-2 mt-2">
            <Button
              variant="outline"
              onClick={handleCancel}
              className="border-gray-700 text-gray-300 hover:bg-gray-800"
            >
              {t('cancelBtn')}
            </Button>
            <Button
              onClick={handleConfirm}
              className={
                pendingMode === 'HARD_STOP'
                  ? 'bg-red-700 hover:bg-red-600 text-white'
                  : pendingMode === 'SAFE_MODE'
                  ? 'bg-yellow-700 hover:bg-yellow-600 text-white'
                  : 'bg-green-700 hover:bg-green-600 text-white'
              }
            >
              {t('confirmBtn')}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  )
}
