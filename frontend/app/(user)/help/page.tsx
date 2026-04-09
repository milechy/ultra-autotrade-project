'use client'
// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.

import { HelpCircle } from 'lucide-react'
import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from '@/components/ui/accordion'

const faqs = [
  {
    id: 'item-1',
    question: 'Health Factor（HF）とは何ですか？',
    answer:
      'Aaveにおける担保の安全度指標です。1.0を下回ると清算リスクが発生します。当システムでは1.6以上を維持するよう自動管理しています。',
  },
  {
    id: 'item-2',
    question: 'HFが1.6を下回るとどうなりますか？',
    answer:
      'SAFE_MODEに移行し、新規供給を停止します。必要に応じて自動でポジション縮小を行います。HF < 1.3の場合はHARD_STOP（全引き出し）が発動します。',
  },
  {
    id: 'item-3',
    question: '緊急停止が発動したらどうすればいいですか？',
    answer:
      'すべての自動取引が停止します。資金はAave上に安全に保管されたままです。管理者が状況を確認後、手動で再開します。特にユーザー側の操作は不要です。',
  },
  {
    id: 'item-4',
    question: '利回りが下がったのはなぜですか？',
    answer:
      'AaveのUSDC供給利率は市場の需給で変動します。借入需要が減ると利率が低下します。AIが市場状況を判断し、最適なタイミングでの運用を目指しています。',
  },
  {
    id: 'item-5',
    question: '運用をやめたい場合はどうすればいいですか？',
    answer:
      '管理者にご連絡ください。Aaveからの引き出し手続きを行います。資金はお使いのウォレットに返却されます。',
  },
  {
    id: 'item-6',
    question: 'AIの判定はどのくらいの頻度で行われますか？',
    answer:
      '4時間ごとに自動で市場分析と判定を実施します。判定結果はダッシュボードで確認できます。',
  },
  {
    id: 'item-7',
    question: '取引の承認期限はありますか？',
    answer:
      'アクティブモードの場合、AI提案から1時間以内に承認/否認してください。タイムアウトで自動キャンセルされます。',
  },
  {
    id: 'item-8',
    question: '最低運用金額はいくらですか？',
    answer:
      'テスト期間中は特に制限はありません。本番環境での最低金額は別途ご案内します。',
  },
  {
    id: 'item-9',
    question: 'テストネットと本番の違いは何ですか？',
    answer:
      'テストネットは仮想資金で動作確認を行う環境です。本番は実際のUSDCを使用します。操作方法は同じですが、テストネットでの損益は実際の資産に影響しません。',
  },
  {
    id: 'item-10',
    question: '問題が発生した場合の連絡先は？',
    answer:
      'Slack #ultra-auto-project チャンネル、またはプロジェクト担当者に直接ご連絡ください。エラーのスクリーンショットと再現手順を添えていただけると迅速に対応できます。',
  },
]

export default function HelpPage() {
  return (
    <div className="min-h-screen bg-zinc-950 text-zinc-100">
      <div className="max-w-2xl mx-auto px-4 py-8">
        <div className="flex items-center gap-3 mb-2">
          <HelpCircle className="h-6 w-6 text-blue-400" />
          <h1 className="text-2xl font-bold">よくある質問</h1>
        </div>
        <p className="text-sm text-zinc-500 mb-8">Ultra AutoTradeの利用に関するFAQです</p>

        <Accordion type="single" collapsible className="space-y-0">
          {faqs.map((faq) => (
            <AccordionItem
              key={faq.id}
              value={faq.id}
              className="border-zinc-800"
            >
              <AccordionTrigger className="text-zinc-100 hover:text-zinc-100 hover:no-underline text-sm font-medium">
                {faq.question}
              </AccordionTrigger>
              <AccordionContent className="text-zinc-400 text-sm leading-relaxed">
                {faq.answer}
              </AccordionContent>
            </AccordionItem>
          ))}
        </Accordion>
      </div>
    </div>
  )
}
