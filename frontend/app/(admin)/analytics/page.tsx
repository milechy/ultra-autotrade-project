'use client'

import AuthGuard from '@/components/AuthGuard'
import { POSTHOG_KEY, POSTHOG_HOST, EV } from '@/lib/posthog'

const EVENT_DESCRIPTIONS: Record<string, string> = {
  [EV.MENU_OPEN]:           'ハンバーガーメニューを開いた',
  [EV.PANEL_OPEN]:          'スライドパネルを開いた（パネル種別付き）',
  [EV.ASSET_GRAPH_OPEN]:    '資産グラフパネルを開いた',
  [EV.GRAPH_PERIOD_CHANGE]: 'グラフ期間を切り替えた（1M/3M/6M/1Y）',
  [EV.REASON_TOGGLE]:       'AI判定の理由トグルをクリックした',
  [EV.JUDGMENT_APPROVE]:    'AI判定を承認した（BUY/SELL）',
  [EV.JUDGMENT_REJECT]:     'AI判定を却下した',
  [EV.EMERGENCY_STOP]:      '緊急停止を実行した',
  [EV.CHAT_OPEN]:           'チャットFABをタップした',
  [EV.LANGUAGE_TOGGLE]:     '言語を切り替えた（JP/EN）',
  [EV.ACCOUNT_OPEN]:        'アカウントパネルを開いた',
}

export default function AnalyticsPage() {
  const configured = !!POSTHOG_KEY

  return (
    <AuthGuard adminOnly>
      <div style={{ maxWidth: 900 }}>
        <h1 style={{ fontSize: 20, fontWeight: 700, marginBottom: 8 }}>行動分析（PostHog）</h1>
        <p style={{ color: '#666', fontSize: 14, marginBottom: 24 }}>
          LIFF チャット画面でのユーザー行動トラッキング一覧。
        </p>

        {!configured && (
          <div style={{ background: '#fff3cd', border: '1px solid #ffc107', borderRadius: 8, padding: 16, marginBottom: 24 }}>
            <strong>⚠️ POSTHOG_KEY 未設定</strong>
            <p style={{ margin: '8px 0 0', fontSize: 13, color: '#856404' }}>
              環境変数 <code>NEXT_PUBLIC_POSTHOG_KEY</code> を設定してフロントエンドをリビルドしてください。
            </p>
          </div>
        )}

        {configured && (
          <div style={{ background: '#d1fae5', border: '1px solid #10b981', borderRadius: 8, padding: 16, marginBottom: 24 }}>
            <strong>✅ PostHog 設定済み</strong>
            <p style={{ margin: '8px 0 0', fontSize: 13, color: '#065f46' }}>
              ホスト: <code>{POSTHOG_HOST}</code>
              <br />
              <a href="https://us.posthog.com" target="_blank" rel="noreferrer" style={{ color: '#065f46' }}>
                PostHog ダッシュボードを開く →
              </a>
            </p>
          </div>
        )}

        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
          <thead>
            <tr style={{ background: '#f5f5f5' }}>
              <th style={{ textAlign: 'left', padding: '8px 12px', borderBottom: '2px solid #ddd' }}>イベント名</th>
              <th style={{ textAlign: 'left', padding: '8px 12px', borderBottom: '2px solid #ddd' }}>発生条件</th>
            </tr>
          </thead>
          <tbody>
            {Object.entries(EVENT_DESCRIPTIONS).map(([event, desc], i) => (
              <tr key={event} style={{ background: i % 2 === 0 ? '#fff' : '#fafafa' }}>
                <td style={{ padding: '8px 12px', borderBottom: '1px solid #eee', fontFamily: 'monospace', color: '#0284c7' }}>
                  {event}
                </td>
                <td style={{ padding: '8px 12px', borderBottom: '1px solid #eee', color: '#444' }}>
                  {desc}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </AuthGuard>
  )
}
