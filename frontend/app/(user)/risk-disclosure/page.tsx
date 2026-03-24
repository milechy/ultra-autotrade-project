// Copyright (c) Ultra AutoTrade. All rights reserved.
'use client'

import { useRouter } from 'next/navigation'
import { ArrowLeft, AlertTriangle } from 'lucide-react'
import { Button } from '@/components/ui/button'

export default function RiskDisclosurePage() {
  const router = useRouter()

  return (
    <div className="min-h-screen bg-zinc-950 text-zinc-100">
      <div className="max-w-2xl mx-auto px-4 py-8">
        <Button
          variant="ghost"
          size="sm"
          className="mb-6 text-zinc-400 hover:text-zinc-100"
          onClick={() => router.push('/connect')}
        >
          <ArrowLeft className="mr-2 h-4 w-4" />
          戻る
        </Button>

        <div className="flex items-center gap-3 mb-2">
          <AlertTriangle className="h-6 w-6 text-yellow-400" />
          <h1 className="text-2xl font-bold">Ultra AutoTrade リスク開示文書</h1>
        </div>
        <p className="text-sm text-zinc-500 mb-8">最終更新日：2026年3月24日</p>

        <div className="rounded-lg border border-yellow-800 bg-yellow-950/30 p-4 mb-8">
          <p className="text-sm text-yellow-300">
            本サービスの利用には様々なリスクが伴います。以下のリスクを十分にご理解のうえ、ご利用ください。
          </p>
        </div>

        <div className="space-y-8 text-sm text-zinc-300 leading-relaxed">
          <section>
            <h2 className="text-base font-semibold text-zinc-100 mb-2">暗号資産のリスク</h2>
            <p>暗号資産は価格変動が非常に大きく、短期間で大幅に価値が変動する場合があります。投資した元本を下回る可能性があり、場合によっては全額を失う可能性があります。</p>
          </section>

          <section>
            <h2 className="text-base font-semibold text-zinc-100 mb-2">DeFiのリスク</h2>
            <p>分散型金融（DeFi）プロトコルはスマートコントラクトの脆弱性を含む可能性があります。また、ネットワーク混雑時には取引が遅延または失敗する場合があります。これらの要因により資産が失われる可能性があります。</p>
          </section>

          <section>
            <h2 className="text-base font-semibold text-zinc-100 mb-2">AI判定のリスク</h2>
            <p>本サービスのAIは完璧ではなく、誤った判断を行う可能性があります。特に市場が急変する状況では、AIの対応能力に限界があります。AI判定を盲目的に信頼することは避けてください。</p>
          </section>

          <section>
            <h2 className="text-base font-semibold text-zinc-100 mb-2">運用上のリスク</h2>
            <p>AaveなどのDeFiプロトコルでは、担保比率（Health Factor）が一定水準を下回ると清算が発生し、資産の一部が失われる可能性があります。また、ガス代の変動により予期しないコストが発生することがあります。</p>
          </section>

          <section>
            <h2 className="text-base font-semibold text-zinc-100 mb-2">テスト期間の特記事項</h2>
            <p>現在の運用はテストネット環境です。テストネットのトークンは実際の経済的価値を持ちません。テスト結果は実際の市場環境を完全には反映しない場合があります。</p>
          </section>

          <section>
            <h2 className="text-base font-semibold text-zinc-100 mb-2">ご理解いただきたいこと</h2>
            <ul className="list-disc list-inside space-y-1 mt-2">
              <li>本サービスは投資助言サービスではありません</li>
              <li>運用結果はすべてお客様の自己責任となります</li>
              <li>過去の運用実績は将来の結果を保証するものではありません</li>
              <li>余裕資金の範囲内でご利用ください</li>
            </ul>
          </section>
        </div>
      </div>
    </div>
  )
}
