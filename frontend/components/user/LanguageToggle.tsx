'use client'

import { useLocale } from 'next-intl'
import { useRouter } from 'next/navigation'
import { useTransition } from 'react'

export function LanguageToggle() {
  const locale = useLocale()
  const router = useRouter()
  const [isPending, startTransition] = useTransition()

  const toggleLocale = () => {
    const next = locale === 'ja' ? 'en' : 'ja'
    document.cookie = `NEXT_LOCALE=${next}; path=/; max-age=31536000; Secure; SameSite=Strict`
    startTransition(() => {
      router.refresh()
    })
  }

  return (
    <button
      onClick={toggleLocale}
      disabled={isPending}
      className="flex items-center gap-1.5 rounded-full border border-border px-3 py-1 text-sm font-medium transition-colors hover:bg-muted disabled:opacity-50"
      aria-label="Toggle language"
    >
      <span className={locale === 'ja' ? 'font-bold text-foreground' : 'text-muted-foreground'}>
        JA
      </span>
      <span className="text-muted-foreground">/</span>
      <span className={locale === 'en' ? 'font-bold text-foreground' : 'text-muted-foreground'}>
        EN
      </span>
    </button>
  )
}
