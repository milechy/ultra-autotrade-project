'use client'
// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.
// frontend/components/user/StripePaymentMethodCard.tsx
//
// F-7: 月額サブスク課金のクレジットカード登録 UX。
// SetupIntent (usage=off_session) で保存したカードに、毎月バックエンドが
// off-session PaymentIntent で自動課金する (StripeBillingAdapter)。
//
// 使用先:
//   - app/(user)/fee-approve/page.tsx  (PWA)
//   - app/(liff)/liff-fee-approve/page.tsx (LIFF)

import { useEffect, useState, type FormEvent } from 'react'
import { useTranslations } from 'next-intl'
import { loadStripe, type Stripe } from '@stripe/stripe-js'
import { Elements, PaymentElement, useStripe, useElements } from '@stripe/react-stripe-js'
import { CheckCircle2, AlertTriangle, Loader2, CreditCard } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { apiFetch, apiPost } from '@/lib/api/client'

const STRIPE_PUBLISHABLE_KEY = process.env.NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY ?? ''

// loadStripe は呼び出しごとに新規スクリプトタグを作らないよう module scope で 1 回だけ実行。
let stripePromise: Promise<Stripe | null> | null = null
function getStripePromise(): Promise<Stripe | null> | null {
  if (!STRIPE_PUBLISHABLE_KEY) return null
  if (!stripePromise) stripePromise = loadStripe(STRIPE_PUBLISHABLE_KEY)
  return stripePromise
}

interface PaymentMethodInfo {
  registered: boolean
  brand: string | null
  last4: string | null
}

function CardSetupForm({
  onSuccess,
  onCancel,
}: {
  onSuccess: () => void
  onCancel: () => void
}) {
  const t = useTranslations('UserStripePaymentMethodCard')
  const stripe = useStripe()
  const elements = useElements()
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    if (!stripe || !elements) return
    setSubmitting(true)
    setError(null)

    const { error: confirmError, setupIntent } = await stripe.confirmSetup({
      elements,
      redirect: 'if_required',
    })

    if (confirmError) {
      setError(confirmError.message ?? t('errorGeneric'))
      setSubmitting(false)
      return
    }

    if (setupIntent?.status === 'succeeded') {
      try {
        await apiPost('/api/user/billing/payment-method/confirm', {
          setup_intent_id: setupIntent.id,
        })
        onSuccess()
        return
      } catch {
        setError(t('errorConfirm'))
      }
    } else {
      setError(t('errorGeneric'))
    }
    setSubmitting(false)
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <PaymentElement />
      {error && (
        <div className="flex items-start gap-2">
          <AlertTriangle className="h-4 w-4 text-red-400 shrink-0 mt-0.5" />
          <p className="text-xs text-red-300">{error}</p>
        </div>
      )}
      <div className="flex gap-2">
        <Button type="button" variant="outline" className="flex-1" onClick={onCancel}>
          {t('cancelButton')}
        </Button>
        <Button type="submit" className="flex-1" disabled={!stripe || submitting}>
          {submitting ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            t('submitButton')
          )}
        </Button>
      </div>
    </form>
  )
}

export function StripePaymentMethodCard() {
  const t = useTranslations('UserStripePaymentMethodCard')
  const [info, setInfo] = useState<PaymentMethodInfo | null>(null)
  const [infoLoading, setInfoLoading] = useState(true)
  const [errorMsg, setErrorMsg] = useState<string | null>(null)
  const [clientSecret, setClientSecret] = useState<string | null>(null)
  const [starting, setStarting] = useState(false)

  function fetchStatus() {
    setInfoLoading(true)
    apiFetch<PaymentMethodInfo>('/api/user/billing/payment-method')
      .then((data) => setInfo(data))
      .catch((err: unknown) => {
        setErrorMsg(err instanceof Error ? err.message : t('errorBackend'))
      })
      .finally(() => setInfoLoading(false))
  }

  useEffect(fetchStatus, [])

  async function handleStartRegister() {
    setStarting(true)
    setErrorMsg(null)
    try {
      const res = await apiPost<{ client_secret: string }>('/api/user/billing/setup-intent', {})
      setClientSecret(res.client_secret)
    } catch (err: unknown) {
      setErrorMsg(err instanceof Error ? err.message : t('errorSetupIntent'))
    } finally {
      setStarting(false)
    }
  }

  const stripePromise = getStripePromise()

  if (!stripePromise) {
    return (
      <Card className="border-zinc-800 bg-zinc-900/60">
        <CardContent className="pt-4 pb-4">
          <p className="text-sm text-zinc-400">{t('notConfigured')}</p>
        </CardContent>
      </Card>
    )
  }

  if (infoLoading) {
    return (
      <Card className="border-zinc-800 bg-zinc-900/60">
        <CardContent className="pt-6 pb-6 flex items-center justify-center gap-2">
          <Loader2 className="h-4 w-4 animate-spin text-zinc-400" />
          <span className="text-sm text-zinc-400">{t('loadingInfo')}</span>
        </CardContent>
      </Card>
    )
  }

  if (clientSecret) {
    return (
      <Card className="border-zinc-800 bg-zinc-900/60">
        <CardHeader className="pb-2">
          <CardTitle className="text-base">{t('cardTitle')}</CardTitle>
        </CardHeader>
        <CardContent>
          <Elements stripe={stripePromise} options={{ clientSecret }}>
            <CardSetupForm
              onSuccess={() => {
                setClientSecret(null)
                fetchStatus()
              }}
              onCancel={() => setClientSecret(null)}
            />
          </Elements>
        </CardContent>
      </Card>
    )
  }

  return (
    <Card className="border-zinc-800 bg-zinc-900/60">
      <CardHeader className="pb-2">
        <CardTitle className="text-base">{t('cardTitle')}</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        {info?.registered ? (
          <div className="flex items-center gap-2">
            <CheckCircle2 className="h-5 w-5 text-emerald-400 shrink-0" />
            <span className="text-sm text-emerald-400 font-medium">
              {t('registeredLabel', { brand: info.brand ?? '', last4: info.last4 ?? '' })}
            </span>
          </div>
        ) : (
          <div className="flex items-center gap-2">
            <CreditCard className="h-5 w-5 text-zinc-400 shrink-0" />
            <span className="text-sm text-zinc-400">{t('notRegistered')}</span>
          </div>
        )}

        <Button
          className="w-full bg-blue-600 hover:bg-blue-500 text-white"
          onClick={handleStartRegister}
          disabled={starting}
        >
          {starting ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : info?.registered ? (
            t('changeButton')
          ) : (
            t('registerButton')
          )}
        </Button>

        {errorMsg && (
          <div className="flex items-start gap-2">
            <AlertTriangle className="h-4 w-4 text-red-400 shrink-0 mt-0.5" />
            <p className="text-xs text-red-300">{errorMsg}</p>
          </div>
        )}
      </CardContent>
    </Card>
  )
}
