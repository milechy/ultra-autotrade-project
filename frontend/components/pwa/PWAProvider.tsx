'use client'
// Copyright (c) Ultra AutoTrade. All rights reserved.

import { useEffect } from 'react'
import { registerSW } from '@/lib/pwa/register'

export function PWAProvider({ children }: { children: React.ReactNode }) {
  useEffect(() => {
    registerSW()
  }, [])

  return <>{children}</>
}
