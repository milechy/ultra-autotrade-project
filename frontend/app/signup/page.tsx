'use client'
// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.

// frontend/app/signup/page.tsx
// 一般公開ユーザー登録ページ（partner 招待・紹介コード不要）。
// backend POST /auth/register-open に対応。
// 公開は NEXT_PUBLIC_PUBLIC_REGISTRATION_ENABLED フラグで gate（既定 false）。
import { useRouter } from 'next/navigation'
import { useState, FormEvent } from 'react'
import { useTranslations } from 'next-intl'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { AlertCircle } from 'lucide-react'
import { registerOpen } from '@/lib/api/auth'
import { isPublicRegistrationEnabled } from '@/lib/flags'
import { setAuthToken } from "@/lib/auth/token-key"

function SignupForm() {
  const router = useRouter()
  const t = useTranslations('Signup')

  const [email, setEmail] = useState('')
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [consent, setConsent] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    if (!consent) {
      setError(t('consentRequired'))
      return
    }
    setError(null)
    setSubmitting(true)
    try {
      const result = await registerOpen({
        email,
        username,
        password,
        terms_consent: true,
      })
      setAuthToken(result.access_token)
      localStorage.setItem('ultra_auth_expires', String(Date.now() + result.expires_in * 1000))
      router.replace('/user/dashboard')
    } catch (err: unknown) {
      const message =
        err && typeof err === 'object' && 'message' in err
          ? String((err as { message: string }).message)
          : t('registrationFailed')
      setError(message)
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <main className="flex min-h-screen items-center justify-center bg-muted/40 p-4">
      <Card className="w-full max-w-sm">
        <CardHeader className="text-center">
          <CardTitle className="text-2xl">Ultra AutoTrade</CardTitle>
          <CardDescription>{t('cardDescription')}</CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={(e) => { void handleSubmit(e) }} className="space-y-4">
            {error && (
              <Alert variant="destructive">
                <AlertCircle className="h-4 w-4" />
                <AlertDescription>{error}</AlertDescription>
              </Alert>
            )}

            <div className="space-y-1.5">
              <Label htmlFor="email">{t('emailLabel')}</Label>
              <Input
                id="email"
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
                autoComplete="email"
                disabled={submitting}
                placeholder="you@example.com"
              />
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="username">{t('usernameLabel')}</Label>
              <Input
                id="username"
                type="text"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                required
                autoComplete="username"
                disabled={submitting}
                placeholder="山田太郎"
              />
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="password">{t('passwordLabel')}</Label>
              <Input
                id="password"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                minLength={8}
                autoComplete="new-password"
                disabled={submitting}
              />
              <p className="text-xs text-muted-foreground">{t('passwordHint')}</p>
            </div>

            {/* 利用規約・プライバシーポリシー同意 */}
            <div className="flex items-start gap-2 rounded-lg border border-blue-200 bg-blue-50 p-3 dark:border-blue-800 dark:bg-blue-950/20">
              <input
                id="consent"
                type="checkbox"
                checked={consent}
                onChange={(e) => setConsent(e.target.checked)}
                required
                disabled={submitting}
                className="mt-0.5 h-4 w-4 shrink-0 accent-blue-600"
              />
              <Label htmlFor="consent" className="text-xs leading-relaxed cursor-pointer">
                {t('consentPrefix')}
                <a href="/terms" target="_blank" rel="noopener noreferrer" className="underline underline-offset-4 hover:text-primary">
                  {t('termsLink')}
                </a>
                {t('consentAnd')}
                <a href="/privacy-policy" target="_blank" rel="noopener noreferrer" className="underline underline-offset-4 hover:text-primary">
                  {t('privacyLink')}
                </a>
                {t('consentSuffix')}
              </Label>
            </div>

            <Button type="submit" className="w-full" disabled={submitting || !consent}>
              {submitting ? t('submittingButton') : t('submitButton')}
            </Button>
          </form>

          <p className="mt-6 text-center text-xs text-muted-foreground">
            {t('hasAccountText')}
            <a href="/login" className="underline underline-offset-4 hover:text-primary ml-1">
              {t('loginLink')}
            </a>
          </p>
        </CardContent>
      </Card>
    </main>
  )
}

function ComingSoon() {
  const t = useTranslations('Signup')
  return (
    <main className="flex min-h-screen items-center justify-center bg-muted/40 p-4">
      <Card className="w-full max-w-sm">
        <CardHeader className="text-center">
          <CardTitle className="text-2xl">Ultra AutoTrade</CardTitle>
          <CardDescription>{t('comingSoonDescription')}</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <Alert>
            <AlertCircle className="h-4 w-4" />
            <AlertDescription>
              {t('comingSoonMessage')}
            </AlertDescription>
          </Alert>
          <Button variant="outline" className="w-full" onClick={() => { window.location.href = '/login' }}>
            {t('comingSoonLoginButton')}
          </Button>
        </CardContent>
      </Card>
    </main>
  )
}

export default function SignupPage() {
  const t = useTranslations('Signup')
  const enabled = isPublicRegistrationEnabled()
  return (
    <>
      <title>{t('title')}</title>
      {enabled ? <SignupForm /> : <ComingSoon />}
    </>
  )
}
