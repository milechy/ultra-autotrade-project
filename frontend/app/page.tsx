// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.

import Link from 'next/link'
import { Brain, Shield, Eye, AlertTriangle, Wallet, CheckCircle } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from '@/components/ui/accordion'

const features = [
  {
    icon: Brain,
    title: 'AI戦略判断',
    description: 'Claude Opus + GPT-4oのクロス検証で精度の高い判断',
  },
  {
    icon: Shield,
    title: '安全第一設計',
    description: 'Health Factor監視・緊急停止・取引制限で資産を保護',
  },
  {
    icon: Eye,
    title: '透明な運用',
    description: 'AI判定の理由を全て公開。ブラックボックスなし',
  },
]

const steps = [
  { number: 1, icon: Wallet, title: 'ウォレット接続', description: 'MetaMask等のウォレットを接続して開始' },
  { number: 2, icon: Brain, title: 'AIが市場を分析', description: '最新の市場データをAIがリアルタイム解析' },
  { number: 3, icon: Eye, title: '提案を確認・承認', description: 'AIの判断根拠を確認してから承認' },
  { number: 4, icon: CheckCircle, title: '安全に自動執行', description: '複数の安全チェックを経て自動実行' },
]

const faqItems = [
  {
    question: 'Ultra AutoTradeとは？',
    answer:
      'Ultra AutoTradeは、AaveV3とAIを組み合わせたDeFi資産運用プラットフォームです。Claude OpusとGPT-4oのクロス検証により、高精度な取引判断を実現します。',
  },
  {
    question: '資金は安全ですか？',
    answer:
      'Health Factor監視、緊急停止機能、1回あたり最大10%の取引制限など、多層的な安全機能を備えています。ただし、暗号資産取引にはリスクが伴います。',
  },
  {
    question: '最低運用額はいくらですか？',
    answer:
      '現在のPoC段階では最低運用額の制限はありませんが、ガス代等のコストを考慮すると一定額以上の運用を推奨しています。詳細はドキュメントをご確認ください。',
  },
  {
    question: '手数料はかかりますか？',
    answer:
      'プラットフォーム手数料については現在策定中です。ブロックチェーン上のガス代（ネットワーク手数料）は別途発生します。',
  },
  {
    question: '対応ウォレットは何ですか？',
    answer:
      'MetaMask、WalletConnect対応ウォレットに対応予定です。Arbitrum Oneネットワークへの接続が必要です。',
  },
  {
    question: 'どのチェーン・プロトコルに対応していますか？',
    answer:
      'Arbitrum One上のAave V3に対応しています。今後、他のチェーンやプロトコルへの対応も検討しています。',
  },
]

export default function LandingPage() {
  return (
    <div className="min-h-screen bg-gray-950 text-gray-100">
      {/* Hero Section */}
      <section
        className="relative flex min-h-screen flex-col items-center justify-center px-4 py-24 text-center"
        style={{
          backgroundImage:
            'linear-gradient(rgba(255,255,255,0.03) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,0.03) 1px, transparent 1px)',
          backgroundSize: '40px 40px',
        }}
      >
        <div className="absolute inset-0 bg-gradient-to-b from-blue-950/30 via-gray-950/80 to-gray-950 pointer-events-none" />
        <div className="relative z-10 max-w-3xl mx-auto">
          <h1 className="text-4xl font-bold tracking-tight text-white sm:text-5xl md:text-6xl">
            AIが導く、次世代DeFi運用
          </h1>
          <p className="mt-6 text-lg text-gray-400 sm:text-xl">
            Aave V3 × AI戦略判断で、あなたの資産を安全に最適化
          </p>
          <div className="mt-10">
            <Button
              asChild
              size="lg"
              className="bg-blue-500 hover:bg-blue-600 text-white text-base px-8 py-6 h-auto"
            >
              <Link href="/connect">ウォレットを接続する</Link>
            </Button>
          </div>
        </div>
      </section>

      {/* Features Section */}
      <section className="px-4 py-20 bg-gray-900">
        <div className="max-w-5xl mx-auto">
          <h2 className="text-2xl font-bold text-center text-white mb-12">
            なぜUltra AutoTradeなのか
          </h2>
          <div className="grid grid-cols-1 gap-6 md:grid-cols-3">
            {features.map(({ icon: Icon, title, description }) => (
              <Card key={title} className="bg-gray-800 border-gray-700">
                <CardHeader className="pb-3">
                  <div className="mb-3 flex h-10 w-10 items-center justify-center rounded-lg bg-blue-500/20">
                    <Icon className="h-5 w-5 text-blue-400" />
                  </div>
                  <CardTitle className="text-white text-lg">{title}</CardTitle>
                </CardHeader>
                <CardContent>
                  <p className="text-gray-400 text-sm">{description}</p>
                </CardContent>
              </Card>
            ))}
          </div>
        </div>
      </section>

      {/* Supported Protocols Section */}
      <section className="px-4 py-16 bg-gray-950">
        <div className="max-w-3xl mx-auto text-center">
          <h2 className="text-xl font-semibold text-gray-400 mb-8 uppercase tracking-widest text-sm">
            対応プロトコル・チェーン
          </h2>
          <div className="flex flex-wrap justify-center gap-4">
            {['Aave V3', 'Arbitrum One'].map((label) => (
              <span
                key={label}
                className="inline-flex items-center rounded-full border border-blue-500/40 bg-blue-500/10 px-5 py-2 text-sm font-medium text-blue-300"
              >
                {label}
              </span>
            ))}
          </div>
        </div>
      </section>

      {/* How It Works Section */}
      <section className="px-4 py-20 bg-gray-900">
        <div className="max-w-3xl mx-auto">
          <h2 className="text-2xl font-bold text-center text-white mb-12">
            ご利用の流れ
          </h2>
          <div className="flex flex-col gap-4">
            {steps.map(({ number, icon: Icon, title, description }) => (
              <Card key={number} className="bg-gray-800 border-gray-700">
                <CardContent className="flex items-start gap-4 py-5">
                  <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-blue-500 text-white font-bold text-sm">
                    {number}
                  </div>
                  <div className="flex-1">
                    <div className="flex items-center gap-2 mb-1">
                      <Icon className="h-4 w-4 text-blue-400" />
                      <span className="font-semibold text-white">{title}</span>
                    </div>
                    <p className="text-sm text-gray-400">{description}</p>
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
        </div>
      </section>

      {/* Risk Disclaimer Section */}
      <section className="px-4 py-16 bg-gray-950">
        <div className="max-w-3xl mx-auto">
          <Card className="border-yellow-600/40 bg-yellow-900/10">
            <CardContent className="py-6">
              <div className="flex items-start gap-3">
                <AlertTriangle className="h-5 w-5 text-yellow-500 shrink-0 mt-0.5" />
                <div className="space-y-2">
                  <p className="text-sm font-semibold text-yellow-400">リスク免責事項</p>
                  <p className="text-sm text-gray-400">
                    暗号資産の運用にはリスクが伴います。元本保証はありません。
                  </p>
                  <p className="text-sm text-gray-400">
                    過去の実績は将来の利回りを保証するものではありません。
                  </p>
                  <p className="text-sm text-gray-400">
                    投資は自己責任でお願いいたします。
                  </p>
                </div>
              </div>
            </CardContent>
          </Card>
        </div>
      </section>

      {/* FAQ Section */}
      <section className="px-4 py-20 bg-gray-900">
        <div className="max-w-3xl mx-auto">
          <h2 className="text-2xl font-bold text-center text-white mb-12">
            よくある質問
          </h2>
          <Accordion type="single" collapsible className="w-full">
            {faqItems.map((item, index) => (
              <AccordionItem
                key={index}
                value={`item-${index}`}
                className="border-gray-700"
              >
                <AccordionTrigger className="text-gray-200 hover:text-white hover:no-underline text-left">
                  {item.question}
                </AccordionTrigger>
                <AccordionContent className="text-gray-400">
                  {item.answer}
                </AccordionContent>
              </AccordionItem>
            ))}
          </Accordion>
        </div>
      </section>

      {/* Footer CTA Section */}
      <section className="px-4 py-24 bg-gray-950 text-center">
        <div className="max-w-xl mx-auto">
          <h2 className="text-3xl font-bold text-white mb-4">さあ、始めましょう</h2>
          <p className="text-gray-400 mb-10">
            AIと一緒に、次世代のDeFi運用を体験してください。
          </p>
          <Button
            asChild
            size="lg"
            className="bg-blue-500 hover:bg-blue-600 text-white text-base px-8 py-6 h-auto"
          >
            <Link href="/connect">ウォレットを接続する</Link>
          </Button>
        </div>
      </section>

      {/* Footer */}
      <footer className="border-t border-gray-800 bg-gray-950 px-4 py-8 text-center">
        <p className="text-xs text-gray-600">
          © 2026 Ultra AutoTrade. All rights reserved.
        </p>
      </footer>
    </div>
  )
}
