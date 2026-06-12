// Copyright (c) Ultra AutoTrade. All rights reserved.
'use client'

import { ArrowLeft } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { useSmartBack } from '@/hooks/useSmartBack'

export default function PrivacyPolicyPage() {
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

        <h1 className="text-2xl font-bold mb-2">Ultra AutoTrade プライバシーポリシー</h1>
        <p className="text-sm text-zinc-500 mb-8">最終更新日：2026年3月24日</p>

        <div className="space-y-8 text-sm text-zinc-300 leading-relaxed">
          <section>
            <h2 className="text-base font-semibold text-zinc-100 mb-2">1. 収集する情報・利用目的</h2>
            <p>Ultra AutoTrade（以下「本サービス」）は、以下の情報を収集します。</p>
            <ul className="list-disc list-inside mt-2 space-y-1">
              <li>ウォレットアドレス（DeFiプロトコルとの接続に利用）</li>
              <li>取引履歴・操作ログ（サービス品質向上・不正検知に利用）</li>
              <li>ブラウザの種類・IPアドレス（セキュリティ監視に利用）</li>
            </ul>
            <p className="mt-2">収集した情報は、本サービスの運営・改善・セキュリティ確保の目的にのみ使用します。個人を特定できる情報（氏名・メールアドレス等）は収集しません。</p>
          </section>

          <section>
            <h2 className="text-base font-semibold text-zinc-100 mb-2">2. ウォレットアドレスの扱い</h2>
            <p>ウォレットアドレスはパブリックなブロックチェーン識別子であり、本サービスへの接続・取引履歴の記録に使用します。お客様の秘密鍵（プライベートキー）は当社サーバーに送信・保存されることは一切ありません。ウォレットの管理責任はお客様自身にあります。</p>
          </section>

          <section>
            <h2 className="text-base font-semibold text-zinc-100 mb-2">3. Cookie・ローカルストレージ</h2>
            <p>本サービスは、以下の目的でCookieおよびブラウザのローカルストレージを使用します。</p>
            <ul className="list-disc list-inside mt-2 space-y-1">
              <li>セッション管理（ログイン状態の維持）</li>
              <li>ウォレット接続状態の保持</li>
              <li>利用規約・設定の同意記録</li>
            </ul>
            <p className="mt-2">ブラウザの設定でCookieを無効にした場合、一部機能が正常に動作しない場合があります。</p>
          </section>

          <section>
            <h2 className="text-base font-semibold text-zinc-100 mb-2">4. 第三者への提供（Aave・WalletConnect）</h2>
            <p>本サービスは以下の第三者サービスと連携しており、利用に際してそれぞれのプライバシーポリシーが適用されます。</p>
            <ul className="list-disc list-inside mt-2 space-y-1">
              <li><strong className="text-zinc-100">Aave Protocol</strong>: DeFi資産運用のためにブロックチェーン上でスマートコントラクトを呼び出します。取引はパブリックなブロックチェーン上に記録されます。</li>
              <li><strong className="text-zinc-100">WalletConnect</strong>: ウォレット接続の仲介サービスです。接続情報はWalletConnectのサーバーを経由します。詳細はWalletConnectのプライバシーポリシーをご確認ください。</li>
            </ul>
            <p className="mt-2">これらの第三者サービスへの情報提供は、本サービスの機能提供に必要な範囲に限定されます。</p>
          </section>

          <section>
            <h2 className="text-base font-semibold text-zinc-100 mb-2">5. データ保持期間</h2>
            <p>収集した情報は以下の期間保持します。</p>
            <ul className="list-disc list-inside mt-2 space-y-1">
              <li>取引履歴・操作ログ：最終アクセスから1年間</li>
              <li>セッション情報：セッション終了後30日間</li>
              <li>ローカルストレージのデータ：お客様がブラウザのデータを削除するまで</li>
            </ul>
            <p className="mt-2">保持期間終了後は、安全な方法でデータを削除します。</p>
          </section>

          <section>
            <h2 className="text-base font-semibold text-zinc-100 mb-2">6. ユーザーの権利</h2>
            <p>お客様は以下の権利を有します。</p>
            <ul className="list-disc list-inside mt-2 space-y-1">
              <li>収集した情報の開示請求</li>
              <li>不正確な情報の訂正請求</li>
              <li>情報の削除請求</li>
              <li>データ処理への異議申し立て</li>
            </ul>
            <p className="mt-2">これらの権利を行使する場合は、下記の問い合わせ先までご連絡ください。</p>
          </section>

          <section>
            <h2 className="text-base font-semibold text-zinc-100 mb-2">7. セキュリティ</h2>
            <p>本サービスは、収集した情報を不正アクセス・漏洩・改ざんから保護するために、業界標準のセキュリティ対策を実施しています。ただし、インターネット上での完全なセキュリティを保証することはできません。</p>
          </section>

          <section>
            <h2 className="text-base font-semibold text-zinc-100 mb-2">8. プライバシーポリシーの変更</h2>
            <p>本ポリシーは事前通知のうえ変更されることがあります。重要な変更がある場合は、本サービス上でお知らせします。変更後も本サービスを継続して利用された場合、変更後のポリシーに同意したものとみなします。</p>
          </section>

          <section>
            <h2 className="text-base font-semibold text-zinc-100 mb-2">9. 問い合わせ先</h2>
            <p>本ポリシーに関するご質問・ご要望は、本サービスのサポートチームまでお問い合わせください。お問い合わせの際は、ウォレットアドレスおよびご要望の内容をお伝えください。</p>
          </section>
        </div>
      </div>
    </div>
  )
}
