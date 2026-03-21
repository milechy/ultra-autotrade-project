// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.
'use client'

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Label } from '@/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'

type Language = 'ja' | 'en'

interface LanguageCardProps {
  language: Language
  onLanguageChange: (value: Language) => void
}

export function LanguageCard({ language, onLanguageChange }: LanguageCardProps) {
  return (
    <Card className="bg-zinc-900 border-zinc-800">
      <CardHeader className="pb-3">
        <CardTitle className="text-base text-zinc-100">言語</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="space-y-1.5">
          <Label className="text-zinc-300 text-sm">表示言語</Label>
          <Select
            value={language}
            onValueChange={(v) => onLanguageChange(v as Language)}
          >
            <SelectTrigger className="bg-zinc-800 border-zinc-700 text-zinc-100">
              <SelectValue />
            </SelectTrigger>
            <SelectContent className="bg-zinc-800 border-zinc-700">
              <SelectItem value="ja" className="text-zinc-100 focus:bg-zinc-700 focus:text-zinc-100">
                日本語
              </SelectItem>
              <SelectItem value="en" className="text-zinc-100 focus:bg-zinc-700 focus:text-zinc-100">
                English
              </SelectItem>
            </SelectContent>
          </Select>
        </div>
        <p className="text-xs text-zinc-500">
          * 言語切替は次回リリースで対応予定です
        </p>
      </CardContent>
    </Card>
  )
}
