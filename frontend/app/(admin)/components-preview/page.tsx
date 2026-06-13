'use client'
// Copyright (c) 2026 Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.

import { useTranslations } from 'next-intl'
import { DollarSign } from 'lucide-react'
import AuthGuard from '@/components/AuthGuard'
import {
  HealthFactorGauge,
  StatusBadge,
  TradeActionBadge,
  ConfidenceBar,
  EmergencyStopButton,
  TxHashLink,
  AssetIcon,
  KPICard,
  WalletAddressMask,
  DateRangeFilter,
} from '@/components/shared'

export default function ComponentsPreviewPage() {
  const t = useTranslations('AdminComponentsPreview')
  return (
    <AuthGuard adminOnly>
    <div className="container mx-auto p-8 space-y-10">
      <h1 className="text-3xl font-bold">{t('title')}</h1>

      {/* HealthFactorGauge */}
      <section className="space-y-4">
        <h2 className="text-xl font-semibold border-b pb-2">HealthFactorGauge</h2>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-6">
          <div className="p-4 border rounded-lg space-y-2">
            <p className="text-xs text-muted-foreground">{t('hfSm')}</p>
            <HealthFactorGauge value={2.5} size="sm" />
          </div>
          <div className="p-4 border rounded-lg space-y-2">
            <p className="text-xs text-muted-foreground">{t('hfMd')}</p>
            <HealthFactorGauge value={1.8} size="md" />
          </div>
          <div className="p-4 border rounded-lg space-y-2">
            <p className="text-xs text-muted-foreground">{t('hfLg')}</p>
            <HealthFactorGauge value={1.3} size="lg" />
          </div>
          <div className="p-4 border rounded-lg space-y-2">
            <p className="text-xs text-muted-foreground">{t('hfNull')}</p>
            <HealthFactorGauge value={null} />
          </div>
        </div>
      </section>

      {/* StatusBadge */}
      <section className="space-y-4">
        <h2 className="text-xl font-semibold border-b pb-2">StatusBadge</h2>
        <div className="flex flex-wrap gap-4">
          <StatusBadge status="NORMAL" />
          <StatusBadge status="SAFE_MODE" />
          <StatusBadge status="HARD_STOP" />
          <StatusBadge status="PAUSED" />
        </div>
      </section>

      {/* TradeActionBadge */}
      <section className="space-y-4">
        <h2 className="text-xl font-semibold border-b pb-2">TradeActionBadge</h2>
        <div className="flex flex-wrap gap-4">
          <TradeActionBadge action="BUY" />
          <TradeActionBadge action="SELL" />
          <TradeActionBadge action="HOLD" />
        </div>
      </section>

      {/* ConfidenceBar */}
      <section className="space-y-4">
        <h2 className="text-xl font-semibold border-b pb-2">ConfidenceBar</h2>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-6">
          <div className="p-4 border rounded-lg space-y-2">
            <p className="text-xs text-muted-foreground">{t('cbHigh')}</p>
            <ConfidenceBar value={85} />
          </div>
          <div className="p-4 border rounded-lg space-y-2">
            <p className="text-xs text-muted-foreground">{t('cbLow')}</p>
            <ConfidenceBar value={45} />
          </div>
          <div className="p-4 border rounded-lg space-y-2">
            <p className="text-xs text-muted-foreground">{t('cbNoLabel')}</p>
            <ConfidenceBar value={60} showLabel={false} />
          </div>
          <div className="p-4 border rounded-lg space-y-2">
            <p className="text-xs text-muted-foreground">{t('cbThreshold')}</p>
            <ConfidenceBar value={55} threshold={50} />
          </div>
        </div>
      </section>

      {/* EmergencyStopButton */}
      <section className="space-y-4">
        <h2 className="text-xl font-semibold border-b pb-2">EmergencyStopButton</h2>
        <div className="flex flex-wrap gap-4 items-center">
          <div className="space-y-1">
            <p className="text-xs text-muted-foreground">inline variant</p>
            <EmergencyStopButton
              variant="inline"
              onStop={async () => {
                await new Promise((r) => setTimeout(r, 1000))
              }}
            />
          </div>
          <p className="text-xs text-muted-foreground italic">
            {t('floatingNote')}
          </p>
        </div>
      </section>

      {/* TxHashLink */}
      <section className="space-y-4">
        <h2 className="text-xl font-semibold border-b pb-2">TxHashLink</h2>
        <div className="flex flex-wrap gap-6">
          <div className="space-y-1">
            <p className="text-xs text-muted-foreground">Arbitrum (truncate=true)</p>
            <TxHashLink hash="0x1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef" chain="arbitrum" />
          </div>
          <div className="space-y-1">
            <p className="text-xs text-muted-foreground">Base (truncate=false)</p>
            <TxHashLink hash="0xabcd1234efgh5678" chain="base" truncate={false} />
          </div>
          <div className="space-y-1">
            <p className="text-xs text-muted-foreground">Ethereum</p>
            <TxHashLink hash="0xdeadbeefdeadbeefdeadbeefdeadbeef" chain="ethereum" />
          </div>
        </div>
      </section>

      {/* AssetIcon */}
      <section className="space-y-4">
        <h2 className="text-xl font-semibold border-b pb-2">AssetIcon</h2>
        <div className="flex flex-wrap gap-6 items-end">
          {(['USDC', 'USDT', 'ETH', 'WETH', 'WBTC', 'DAI', 'AAVE'] as const).map((symbol) => (
            <div key={symbol} className="flex flex-col items-center gap-1">
              <AssetIcon symbol={symbol} size="lg" />
              <AssetIcon symbol={symbol} size="md" />
              <AssetIcon symbol={symbol} size="sm" />
              <span className="text-xs text-muted-foreground">{symbol}</span>
            </div>
          ))}
        </div>
      </section>

      {/* KPICard */}
      <section className="space-y-4">
        <h2 className="text-xl font-semibold border-b pb-2">KPICard</h2>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          <KPICard
            label={t('kpiTotalAsset')}
            value="12,345"
            prefix="$"
            trend="up"
            trendValue="+5.2%"
            icon={DollarSign}
          />
          <KPICard
            label={t('kpiDailyPnl')}
            value="-234"
            prefix="$"
            trend="down"
            trendValue="-1.8%"
          />
          <KPICard
            label={t('kpiWinRate')}
            value="68.4"
            suffix="%"
            trend="flat"
            trendValue="±0%"
          />
          <KPICard
            label={t('kpiTradeCount')}
            value={42}
            suffix={t('kpiTradeCountSuffix')}
          />
        </div>
      </section>

      {/* WalletAddressMask */}
      <section className="space-y-4">
        <h2 className="text-xl font-semibold border-b pb-2">WalletAddressMask</h2>
        <div className="flex flex-wrap gap-6">
          <div className="space-y-1">
            <p className="text-xs text-muted-foreground">{t('walletDefaultChars')}</p>
            <WalletAddressMask address="0x742d35Cc6634C0532925a3b844Bc454e4438f44e" />
          </div>
          <div className="space-y-1">
            <p className="text-xs text-muted-foreground">{t('walletChars10')}</p>
            <WalletAddressMask address="0x742d35Cc6634C0532925a3b844Bc454e4438f44e" chars={10} />
          </div>
        </div>
      </section>

      {/* DateRangeFilter */}
      <section className="space-y-4">
        <h2 className="text-xl font-semibold border-b pb-2">DateRangeFilter</h2>
        <div className="space-y-4">
          <div className="space-y-2">
            <p className="text-xs text-muted-foreground">{t('datePresetsOn')}</p>
            <DateRangeFilter onChange={(range) => console.log('range:', range)} />
          </div>
          <div className="space-y-2">
            <p className="text-xs text-muted-foreground">{t('datePresetsOff')}</p>
            <DateRangeFilter onChange={(range) => console.log('range:', range)} presets={false} />
          </div>
        </div>
      </section>

      {/* floating EmergencyStopButton demo */}
      <EmergencyStopButton
        variant="floating"
        onStop={async () => {
          await new Promise((r) => setTimeout(r, 1500))
        }}
      />
    </div>
    </AuthGuard>
  )
}
