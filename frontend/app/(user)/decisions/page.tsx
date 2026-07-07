'use client'
// Copyright (c) Ultra AutoTrade. All rights reserved.

// This route is a duplicate of /user/decisions (see frontend/app/user/decisions/page.tsx),
// which is the live, nav-linked page (frontend/app/user/dashboard/_components/LatestDecision.tsx
// links here via href="/user/decisions"). No in-app link points at /decisions, so this page
// only exists as a redirect target for anyone with a stale bookmark/link to /decisions.
// Kept (not deleted) per URL-cleanup policy; the original implementation lives on unused in
// ./_components for history.
import { useEffect } from 'react'
import { useRouter } from 'next/navigation'
import { LoadingPage } from '@/components/shared/LoadingSpinner'

export default function DecisionsRedirectPage() {
  const router = useRouter()

  useEffect(() => {
    router.replace('/user/decisions')
  }, [router])

  return <LoadingPage />
}
