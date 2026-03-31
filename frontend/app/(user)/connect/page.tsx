// Copyright (c) Ultra AutoTrade. All rights reserved.
'use client'

import { useState, useEffect } from 'react'
import { useRouter } from 'next/navigation'
import { Wallet, CheckCircle, AlertTriangle, ArrowRight } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { useWallet } from '@/hooks/useWallet'
import { useAuth } from '@/lib/auth'
import { useMinimumBalance } from '@/hooks/useMinimumBalance'
import { ARBITRUM_CHAIN_IDS } from '@/lib/web3/config'

const STEP_LABELS = [
  'ウォレット接続',
  'ネットワーク確認',
  '規約同意',
]

function StepIndicator({ currentStep }: { currentStep: number }) {
  return (
    <div className="flex items-center justify-center gap-0 mb-8">
      {STEP_LABELS.map((label, index) => {
        const stepNum = index + 1
        const isDone = currentStep > stepNum
        const isActive = currentStep === stepNum
        return (
          <div key={stepNum} className="flex items-center">
            <div className="flex flex-col items-center">
              <div
                className={`w-8 h-8 rounded-full flex items-center justify-center text-sm font-bold transition-all ${
                  isDone
                    ? 'bg-emerald-500 text-white'
                    : isActive
                    ? 'bg-blue-600 text-white'
                    : 'bg-zinc-800 text-zinc-500'
                }`}
              >
                {isDone ? <CheckCircle className="w-4 h-4" /> : stepNum}
              </div>
              <span
                className={`mt-1 text-xs whitespace-nowrap ${
                  isActive ? 'text-blue-400 font-medium' : isDone ? 'text-emerald-400' : 'text-zinc-600'
                }`}
              >
                {label}
              </span>
            </div>
            {index < STEP_LABELS.length - 1 && (
              <div
                className={`w-12 h-0.5 mx-1 mb-5 transition-all ${
                  currentStep > stepNum ? 'bg-emerald-500' : 'bg-zinc-700'
                }`}
              />
            )}
          </div>
        )
      })}
    </div>
  )
}

export default function ConnectPage() {
  const router = useRouter()
  const { loginWithWallet } = useAuth()
  const { address, isConnected, chainId, connect, switchToArbitrum, switchToArbitrumSepolia, switchToBaseSepolia, switchToBase, switchToOptimism, switchToMainnet, signer } = useWallet()
  const { checkMinimum, minimumUSD } = useMinimumBalance()

  const [termsAccepted, setTermsAccepted] = useState(false)
  const [riskAccepted, setRiskAccepted] = useState(false)
  const [authError, setAuthError] = useState<string | null>(null)
  const [isAuthenticating, setIsAuthenticating] = useState(false)

  // Simulate minimum balance check with a mock value when connected
  // In production this would come from Aave account data
  const mockAccountData = {
    totalCollateralBase: BigInt(0),
    totalDebtBase: BigInt(0),
    availableBorrowsBase: BigInt(0),
    currentLiquidationThreshold: BigInt(0),
    ltv: BigInt(0),
    healthFactor: BigInt(0),
  }
  const balanceCheck = checkMinimum(mockAccountData)

  const isCorrectNetwork = chainId != null && ARBITRUM_CHAIN_IDS.includes(chainId)
  // Balance check is informational only — do not block onboarding (testnet has no minimum)
  const allChecksPass = isConnected && isCorrectNetwork

  // Calculate current step for indicator
  const currentStep = !isConnected ? 1 : !isCorrectNetwork ? 2 : 3

  // If already connected with correct network and terms accepted → redirect
  useEffect(() => {
    if (isConnected && termsAccepted && riskAccepted) {
      // handled by button click
    }
  }, [isConnected, termsAccepted, riskAccepted])

  // If already fully connected on load, skip to dashboard
  useEffect(() => {
    // Only redirect if wallet was already connected before this page loaded
    // We don't auto-redirect here — user must click "運用を開始する"
  }, [])

  const handleStart = async () => {
    if (!address || !signer) return
    setAuthError(null)
    setIsAuthenticating(true)
    try {
      await loginWithWallet(address, signer)
      router.push('/user/dashboard')
    } catch (err) {
      setAuthError('認証に失敗しました。もう一度お試しください。')
    } finally {
      setIsAuthenticating(false)
    }
  }

  return (
    <div className="min-h-screen bg-zinc-950 text-zinc-100">
      <div className="max-w-md mx-auto px-4 py-8">

        {/* Step Indicator */}
        <StepIndicator currentStep={currentStep} />

        {/* Header */}
        <div className="text-center mb-8">
          <h1 className="text-2xl font-bold text-zinc-100 mb-2">ウォレットを接続</h1>
          <p className="text-sm text-zinc-400">
            MetaMaskまたはWalletConnect対応ウォレットで接続してください
          </p>
        </div>

        <div className="space-y-4">

          {/* Connect Button — hidden once connected */}
          {!isConnected && (
            <Button
              size="lg"
              className="w-full bg-blue-600 hover:bg-blue-500 text-white font-semibold py-6 text-base"
              onClick={connect}
            >
              <Wallet className="mr-2 h-5 w-5" />
              ウォレットを接続する
            </Button>
          )}

          {/* Connected address badge */}
          {isConnected && address && (
            <div className="flex items-center justify-center gap-2 py-2 px-4 rounded-lg bg-zinc-900 border border-zinc-800">
              <CheckCircle className="h-4 w-4 text-emerald-400" />
              <span className="text-sm text-zinc-400">接続済み:</span>
              <span className="text-sm font-mono text-zinc-200">
                {address.slice(0, 6)}…{address.slice(-4)}
              </span>
            </div>
          )}

          {/* Network Check Card — shown after connected */}
          {isConnected && (
            <Card className="border-zinc-800 bg-zinc-900/60">
              <CardContent className="pt-4 pb-4">
                <p className="text-xs font-semibold text-zinc-500 uppercase tracking-wide mb-3">
                  ネットワーク確認
                </p>
                {isCorrectNetwork ? (
                  <div className="flex items-center gap-2">
                    <CheckCircle className="h-5 w-5 text-emerald-400 shrink-0" />
                    <span className="text-sm text-emerald-400 font-medium">
                      対応ネットワークに接続済み
                    </span>
                  </div>
                ) : (
                  <div className="space-y-3">
                    <div className="flex items-start gap-2">
                      <AlertTriangle className="h-5 w-5 text-yellow-400 shrink-0 mt-0.5" />
                      <p className="text-sm text-yellow-300">
                        対応ネットワークに切り替えてください
                      </p>
                    </div>
                    <p className="text-xs text-zinc-500 font-semibold uppercase tracking-wide">テストネット</p>
                    <Button
                      variant="outline"
                      size="sm"
                      className="w-full border-blue-600 text-blue-400 hover:bg-blue-950/40"
                      onClick={switchToBaseSepolia}
                    >
                      Base Sepolia (テスト用) に切り替える
                    </Button>
                    <Button
                      variant="outline"
                      size="sm"
                      className="w-full border-yellow-600 text-yellow-400 hover:bg-yellow-950/40"
                      onClick={switchToArbitrumSepolia}
                    >
                      Arbitrum Sepolia (テスト用) に切り替える
                    </Button>
                    <p className="text-xs text-zinc-500 font-semibold uppercase tracking-wide pt-1">メインネット</p>
                    <Button
                      variant="outline"
                      size="sm"
                      className="w-full border-zinc-600 text-zinc-400 hover:bg-zinc-800/40"
                      onClick={switchToBase}
                    >
                      Base に切り替える
                    </Button>
                    <Button
                      variant="outline"
                      size="sm"
                      className="w-full border-zinc-600 text-zinc-400 hover:bg-zinc-800/40"
                      onClick={switchToArbitrum}
                    >
                      Arbitrum One に切り替える
                    </Button>
                    <Button
                      variant="outline"
                      size="sm"
                      className="w-full border-zinc-600 text-zinc-400 hover:bg-zinc-800/40"
                      onClick={switchToOptimism}
                    >
                      Optimism に切り替える
                    </Button>
                    <Button
                      variant="outline"
                      size="sm"
                      className="w-full border-zinc-600 text-zinc-400 hover:bg-zinc-800/40"
                      onClick={switchToMainnet}
                    >
                      Ethereum に切り替える
                    </Button>
                  </div>
                )}
              </CardContent>
            </Card>
          )}

          {/* Min Balance Card — shown after connected + correct network */}
          {isConnected && isCorrectNetwork && (
            <Card className="border-zinc-800 bg-zinc-900/60">
              <CardContent className="pt-4 pb-4">
                <p className="text-xs font-semibold text-zinc-500 uppercase tracking-wide mb-3">
                  最低残高確認
                </p>
                {balanceCheck.isBelowMinimum ? (
                  <div className="flex items-start gap-2">
                    <AlertTriangle className="h-5 w-5 text-yellow-400 shrink-0 mt-0.5" />
                    <div>
                      <p className="text-sm text-yellow-300">{balanceCheck.message}</p>
                      <p className="text-xs text-zinc-500 mt-1">
                        最低運用額: ${minimumUSD.toLocaleString()} USD
                      </p>
                    </div>
                  </div>
                ) : (
                  <div className="flex items-center gap-2">
                    <CheckCircle className="h-5 w-5 text-emerald-400 shrink-0" />
                    <span className="text-sm text-emerald-400 font-medium">
                      残高確認 OK
                    </span>
                  </div>
                )}
              </CardContent>
            </Card>
          )}

          {/* Terms Checkboxes — shown after all checks pass */}
          {allChecksPass && (
            <Card className="border-zinc-800 bg-zinc-900/60">
              <CardContent className="pt-4 pb-4">
                <p className="text-xs font-semibold text-zinc-500 uppercase tracking-wide mb-4">
                  規約同意
                </p>
                <div className="space-y-4">
                  <label className="flex items-start gap-3 cursor-pointer group">
                    <input
                      type="checkbox"
                      checked={termsAccepted}
                      onChange={e => setTermsAccepted(e.target.checked)}
                      className="mt-0.5 h-4 w-4 rounded border-zinc-600 bg-zinc-800 accent-blue-600 cursor-pointer"
                    />
                    <span className="text-sm text-zinc-300 group-hover:text-zinc-100 transition-colors">
                      <a
                        href="/terms"
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-blue-400 hover:underline"
                        onClick={e => e.stopPropagation()}
                      >
                        利用規約
                      </a>
                      に同意します
                    </span>
                  </label>

                  <label className="flex items-start gap-3 cursor-pointer group">
                    <input
                      type="checkbox"
                      checked={riskAccepted}
                      onChange={e => setRiskAccepted(e.target.checked)}
                      className="mt-0.5 h-4 w-4 rounded border-zinc-600 bg-zinc-800 accent-blue-600 cursor-pointer"
                    />
                    <span className="text-sm text-zinc-300 group-hover:text-zinc-100 transition-colors">
                      <a
                        href="/risk-disclosure"
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-blue-400 hover:underline"
                        onClick={e => e.stopPropagation()}
                      >
                        リスク開示文書
                      </a>
                      を確認しました
                    </span>
                  </label>
                </div>
              </CardContent>
            </Card>
          )}

          {/* Start Button */}
          {allChecksPass && authError && (
            <div className="flex items-center gap-2 py-2 px-4 rounded-lg bg-red-950/40 border border-red-800">
              <AlertTriangle className="h-4 w-4 text-red-400 shrink-0" />
              <span className="text-sm text-red-300">{authError}</span>
            </div>
          )}

          {allChecksPass && (
            <Button
              size="lg"
              className="w-full bg-emerald-600 hover:bg-emerald-500 text-white font-semibold py-6 text-base disabled:opacity-40 disabled:cursor-not-allowed"
              disabled={!termsAccepted || !riskAccepted || isAuthenticating || !signer}
              onClick={handleStart}
            >
              {isAuthenticating ? '認証中...' : '運用を開始する'}
              {!isAuthenticating && <ArrowRight className="ml-2 h-5 w-5" />}
            </Button>
          )}

        </div>
      </div>
    </div>
  )
}
