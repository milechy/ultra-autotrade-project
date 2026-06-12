// Copyright (c) Ultra AutoTrade. All rights reserved.
'use client'

import { ArrowLeft } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { useSmartBack } from '@/hooks/useSmartBack'

export default function TermsPage() {
  const goBack = useSmartBack()

  return (
    <div className="min-h-screen bg-zinc-950 text-zinc-100">
      <div className="max-w-2xl mx-auto px-4 py-8">
        <Button
          variant="ghost"
          size="sm"
          className="mb-6 text-zinc-400 hover:text-zinc-100"
          onClick={goBack}
        >
          <ArrowLeft className="mr-2 h-4 w-4" />
          戻る
        </Button>

        <h1 className="text-2xl font-bold mb-2">Ultra AutoTrade 利用規約</h1>
        <p className="text-sm text-zinc-500 mb-8">最終更新日：2026年6月8日</p>

        <div className="space-y-8 text-sm text-zinc-300 leading-relaxed">
          <section>
            <h2 className="text-base font-semibold text-zinc-100 mb-2">1. サービスの概要</h2>
            <p>Ultra AutoTrade（以下「本サービス」）は、AI技術を活用した暗号資産自動運用支援サービスです。本サービスはAaveなどのDeFiプロトコルを通じた資産運用の補助を行います。</p>
          </section>

          <section>
            <h2 className="text-base font-semibold text-zinc-100 mb-2">2. テスト期間について</h2>
            <p>現在、本サービスはテストネット環境での試験運用中です。テスト期間中はテストネット上のトークンのみを使用し、実際の資産は使用しません。テスト結果はサービス改善に活用されます。</p>
          </section>

          <section>
            <h2 className="text-base font-semibold text-zinc-100 mb-2">3. ウォレット接続</h2>
            <p>本サービスへのアクセスにはウォレット接続が必要です。お客様の秘密鍵は当社サーバーに送信・保存されることはありません。ウォレットの管理責任はお客様自身にあります。</p>
          </section>

          <section>
            <h2 className="text-base font-semibold text-zinc-100 mb-2">4. AI判定について</h2>
            <p>本サービスのAIによる取引判定は参考情報の提供を目的としており、投資助言には該当しません。AI判定に基づく運用により損失が発生する可能性があります。</p>
          </section>

          <section>
            <h2 className="text-base font-semibold text-zinc-100 mb-2">5. 運用モードについて</h2>
            <p>本サービスでは、以下の2つの運用モードをご利用いただけます。</p>
            <ul className="mt-2 space-y-2 list-disc list-inside">
              <li>
                <span className="font-medium text-zinc-200">お任せモード（デフォルト）</span>：AIの判定に基づき、取引を自動的に執行します。お客様が個別の取引を承認する必要はありませんが、いつでもモードを変更または緊急停止することができます。
              </li>
              <li>
                <span className="font-medium text-zinc-200">手動モード</span>：AIが提案した取引について、お客様の明示的な承認が必要です。承認なしに取引が執行されることはありません。
              </li>
            </ul>
            <p className="mt-2">モードの切替は設定画面からいつでも変更可能です。また、緊急停止機能により即座に運用を停止することができます。</p>
          </section>

          <section>
            <h2 className="text-base font-semibold text-zinc-100 mb-2">6. 取引の執行</h2>
            <p>取引の執行方法は、選択された運用モードによって異なります。お任せモードでは、AIの判定に基づき自動的に取引が執行されます。手動モードでは、すべての取引においてお客様の明示的な承認が必要です。いずれのモードにおいても、当社のリスク管理基準を超える取引は執行されません。</p>
          </section>

          <section>
            <h2 className="text-base font-semibold text-zinc-100 mb-2">7. 手数料</h2>
            <p>テスト期間中、本サービスの利用料は無料です。ただし、ブロックチェーンのガス代はお客様負担となります（テストネットのガス代は無料です）。</p>
          </section>

          <section>
            <h2 className="text-base font-semibold text-zinc-100 mb-2">8. 免責事項</h2>
            <p>本サービスは資産の値上がりを保証するものではありません。システム障害、ネットワーク障害、その他の要因によりサービスが中断する可能性があります。当社はこれらにより生じた損害について責任を負いません。</p>
          </section>

          <section>
            <h2 className="text-base font-semibold text-zinc-100 mb-2">9. プライバシー</h2>
            <p>本サービスが収集する情報はウォレットアドレスおよび取引履歴のみです。個人を特定できる情報は収集しません。</p>
          </section>

          <section>
            <h2 className="text-base font-semibold text-zinc-100 mb-2">10. 禁止事項</h2>
            <p>本サービスのリバースエンジニアリング、不正アクセス、システムへの攻撃、または他のユーザーへの妨害行為を禁止します。</p>
          </section>

          <section>
            <h2 className="text-base font-semibold text-zinc-100 mb-2">11. 規約の変更</h2>
            <p>本規約は事前通知のうえ変更されることがあります。変更後も本サービスを継続して利用された場合、変更後の規約に同意したものとみなします。</p>
          </section>
        </div>
      </div>
    </div>
  )
}
