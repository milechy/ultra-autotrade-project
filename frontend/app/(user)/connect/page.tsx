// Copyright (c) Ultra AutoTrade. All rights reserved.
'use client'

import { useState, useEffect } from 'react'
import { useRouter } from 'next/navigation'
import { usePrivy, useWallets } from '@privy-io/react-auth'
import { ethers } from 'ethers'
import { Wallet, CheckCircle, AlertTriangle, ArrowRight } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { useAuth } from '@/lib/auth'
import { useMinimumBalance } from '@/hooks/useMinimumBalance'
import { apiPut } from '@/lib/api/client'
import { OperationModeSelector } from '@/components/OperationModeSelector'

type UserMode = 'managed' | 'active' | 'pro'

const USER_MODE_STORAGE_KEY = 'ultra_user_mode'

// Base Sepolia (testnet only)
const SUPPORTED_CHAIN_IDS = [84532]

const CHAIN_DISPLAY_NAMES: Record<number, string> = {
  84532: 'Base Sepolia',
}

function getNetworkDisplayName(chainId: number | null): string {
  if (chainId == null) return '不明なネットワーク'
  return CHAIN_DISPLAY_NAMES[chainId] ?? `Chain ${chainId}`
}

// Privy returns chainId as "eip155:84532" or just "84532"
function parsePrivyChainId(chainIdStr: string | undefined): number | null {
  if (!chainIdStr) return null
  const str = chainIdStr.includes(':') ? chainIdStr.split(':')[1] : chainIdStr
  const num = parseInt(str, 10)
  return isNaN(num) ? null : num
}

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
  const { login, authenticated } = usePrivy()
  const { wallets } = useWallets()
  const { checkMinimum, minimumUSD } = useMinimumBalance()

  const [termsAccepted, setTermsAccepted] = useState(false)
  const [riskAccepted, setRiskAccepted] = useState(false)
  const [authError, setAuthError] = useState<string | null>(null)
  const [isAuthenticating, setIsAuthenticating] = useState(false)
  const [userMode, setUserMode] = useState<UserMode>('managed')

  // Load saved mode from localStorage on mount
  useEffect(() => {
    const saved = localStorage.getItem(USER_MODE_STORAGE_KEY)
    if (saved === 'managed' || saved === 'active' || saved === 'pro') {
      setUserMode(saved)
    }
  }, [])

  const handleModeSelect = (mode: UserMode) => {
    setUserMode(mode)
    localStorage.setItem(USER_MODE_STORAGE_KEY, mode)
  }

  const wallet = wallets[0] ?? null
  const address = wallet?.address ?? null
  const chainId = parsePrivyChainId(wallet?.chainId)
  const isConnected = authenticated && wallet != null

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

  const isCorrectNetwork = chainId != null && SUPPORTED_CHAIN_IDS.includes(chainId)
  // Balance check is informational only — do not block onboarding (testnet has no minimum)
  const allChecksPass = isConnected && isCorrectNetwork

  // Calculate current step for indicator
  const currentStep = !isConnected ? 1 : !isCorrectNetwork ? 2 : 3

  const handleStart = async () => {
    if (!address || !wallet) return
    setAuthError(null)
    setIsAuthenticating(true)
    try {
      const eip1193 = await wallet.getEthereumProvider()
      const ethProvider = new ethers.BrowserProvider(eip1193 as unknown as ethers.Eip1193Provider)
      const signer = await ethProvider.getSigner()
      await loginWithWallet(address, signer)
      // Sync user mode to backend (fire-and-forget; auth continues on failure)
      try {
        await apiPut('/api/user/settings', { user_mode: userMode })
      } catch (modeErr) {
        console.error('Failed to sync user mode:', modeErr)
      }
      router.push('/user/dashboard')
    } catch {
      setAuthError('認証に失敗しました。もう一度お試しください。')
    } finally {
      setIsAuthenticating(false)
    }
  }

  return (
    <div className="min-h-screen bg-zinc-950 text-zinc-100">
      <div className="max-w-2xl mx-auto px-4 py-8">

        {/* Step Indicator */}
        <StepIndicator currentStep={currentStep} />

        {/* Header */}
        <div className="text-center mb-8">
          <h1 className="text-2xl font-bold text-zinc-100 mb-2">ウォレットを接続</h1>
          <p className="text-sm text-zinc-400">
            ウォレットまたはメールアドレスで接続してください
          </p>
        </div>

        <div className="space-y-4">

          {/* Connect Button — hidden once connected */}
          {!isConnected && (
            <Button
              size="lg"
              className="w-full bg-blue-600 hover:bg-blue-500 text-white font-semibold py-6 text-base"
              onClick={login}
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
                      {getNetworkDisplayName(chainId)} に接続済み
                    </span>
                  </div>
                ) : (
                  <div className="space-y-3">
                    <div className="flex items-start gap-2">
                      <AlertTriangle className="h-5 w-5 text-yellow-400 shrink-0 mt-0.5" />
                      <p className="text-sm text-yellow-300">
                        Base Sepoliaに切り替えてください
                      </p>
                    </div>
                    <Button
                      variant="outline"
                      size="sm"
                      className="w-full border-blue-600 text-blue-400 hover:bg-blue-950/40"
                      onClick={() => wallet?.switchChain(84532)}
                    >
                      Base Sepolia (テスト用) に切り替える
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

          {/* Operation Mode Selector — shown after all checks pass */}
          {allChecksPass && (
            <Card className="border-zinc-800 bg-zinc-900/60">
              <CardContent className="pt-4 pb-4">
                <p className="text-xs font-semibold text-zinc-500 uppercase tracking-wide mb-3">
                  運用モード選択
                </p>
                <OperationModeSelector
                  currentMode={userMode}
                  onModeChange={(mode) => handleModeSelect(mode as UserMode)}
                />
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
              className="w-full bg-emerald-600 hover:bg-emerald-500 text-white font-semibold py-6 text-base disabled:opacity-50 disabled:cursor-not-allowed"
              disabled={!termsAccepted || !riskAccepted || isAuthenticating || !wallet}
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
