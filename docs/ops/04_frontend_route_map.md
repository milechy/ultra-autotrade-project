# Ultra AutoTrade — フロントエンドルートマップ

> 生成: 2026-04-24 / `find frontend/app -name "page.tsx"` + コード実抽出
> Next.js App Router 構成。`(group)` はルートに影響しない。

---

## 1. layout.tsx 一覧

| ファイル | 対象グループ | ガード | 主な提供コンポーネント |
|----------|-------------|--------|----------------------|
| `app/layout.tsx` | ルート (全ページ) | なし | フォント・テーマ・globals |
| `app/(admin)/layout.tsx` | `/dashboard`, `/users` 等 admin ページ | `AdminGuard` (AdminProviders内) | `AdminProviders`, `TermsGuard` |
| `app/(partner)/layout.tsx` | `/partner/*` | `PartnerGuard` (PartnerProviders内) | `PartnerProviders` |
| `app/(user)/layout.tsx` | `/(user)/*` グループ | なし (ページ内 AuthGuard) | `UserHeader`, `BottomNav`, `EmergencyStopFloat`, `PrivyRootProvider` |
| `app/user/layout.tsx` | `/user/*` | なし (ページ内 AuthGuard) | `UserHeader`, `BottomNav`, `EmergencyStopFloat`, `WagmiRootProvider` |
| `app/(liff)/layout.tsx` | `/liff-*` | なし | LINE LIFF 専用ラッパー |
| `app/(user)/copy-trading/layout.tsx` | `/(user)/copy-trading` | — | コピートレード専用レイアウト |
| `app/user/copy-trading/layout.tsx` | `/user/copy-trading` | — | コピートレード専用レイアウト |

---

## 2. ガード一覧

### AdminGuard
`frontend/components/providers/AdminProviders.tsx` に定義。
- `!isAuthenticated` → `/login` にリダイレクト
- `!isAdmin` → `isPartner` なら `/partner/dashboard`、それ以外は `/user/dashboard`

**適用画面 (layout 経由):** `(admin)` グループ配下の全ページ

**個別に `AuthGuard adminOnly` を追加している画面:**
- `(admin)/rate-limits`
- `(admin)/settings/config`
- `(admin)/settings/system`
- `(admin)/settings/users`

### PartnerGuard
`frontend/components/providers/PartnerProviders.tsx` に定義。
- `!isAuthenticated` → `/login`
- `!isPartner` → `/user/dashboard`

**適用画面 (layout 経由):** `(partner)` グループ配下の全ページ

### AuthGuard (コンポーネント)
`frontend/components/AuthGuard.tsx`。ページ内で個別に使用。`adminOnly` prop あり。

**AuthGuard のみ使用 (admin ページ):**
- `(admin)/exchange`, `(admin)/trades`, `(admin)/rebalance`
- `(admin)/knowledge`, `(admin)/knowledge/rag-test`, `(admin)/knowledge/search`
- `(admin)/settings/account`

**AuthGuard のみ使用 (user ページ):**
- `user/settings`, `user/copy-trading`, `user/trade`, `user/history`, `user/grid`
- `(user)/copy-trading`, `(user)/trade`, `(user)/ai-feed`, `(user)/grid`

### 認証不要画面
- `/` (ランディング)
- `/login`
- `/register`
- `/(user)/privacy-policy`, `/(user)/terms`, `/(user)/risk-disclosure`
- `/liff-login`, `/liff-approve`, `/liff-history`

---

## 3. 全 page.tsx 一覧

### admin グループ `(admin)/` → URL は `/(admin)` なし

| URL パス | ファイル | ガード | 備考 |
|----------|----------|--------|------|
| `/dashboard` | `(admin)/dashboard/page.tsx` | AdminGuard | admin メインダッシュボード |
| `/dashboard/automation` | `(admin)/dashboard/automation/page.tsx` | AdminGuard | 自動化ステータス |
| `/dashboard/reports` | `(admin)/dashboard/reports/page.tsx` | AdminGuard | レポート |
| `/ai-decisions` | `(admin)/ai-decisions/page.tsx` | AdminGuard | AI判定履歴 |
| `/ai-learning` | `(admin)/ai-learning/page.tsx` | AdminGuard | AI学習管理 |
| `/ai-monitor` | `(admin)/ai-monitor/page.tsx` | AdminGuard | AIモニター |
| `/components-preview` | `(admin)/components-preview/page.tsx` | AdminGuard | UIプレビュー (開発用) |
| `/data-feeds` | `(admin)/data-feeds/page.tsx` | AdminGuard | 外部データフィード |
| `/events` | `(admin)/events/page.tsx` | AdminGuard | イベント一覧 |
| `/exchange` | `(admin)/exchange/page.tsx` | AdminGuard + AuthGuard | 取引所管理 |
| `/knowledge` | `(admin)/knowledge/page.tsx` | AdminGuard + AuthGuard | ナレッジHub |
| `/knowledge/rag-test` | `(admin)/knowledge/rag-test/page.tsx` | AdminGuard + AuthGuard | RAGテスト |
| `/knowledge/search` | `(admin)/knowledge/search/page.tsx` | AdminGuard + AuthGuard | ナレッジ検索 |
| `/proposals` | `(admin)/proposals/page.tsx` | AdminGuard | 提案管理 (admin) |
| `/protocols` | `(admin)/protocols/page.tsx` | AdminGuard | プロトコルヘルス |
| `/rate-limits` | `(admin)/rate-limits/page.tsx` | AdminGuard + AuthGuard(adminOnly) | レート制限 |
| `/rebalance` | `(admin)/rebalance/page.tsx` | AdminGuard + AuthGuard | Aave リバランス |
| `/reports` | `(admin)/reports/page.tsx` | AdminGuard | 月次レポート |
| `/sentiment` | `(admin)/sentiment/page.tsx` | AdminGuard | センチメント分析 |
| `/settings/account` | `(admin)/settings/account/page.tsx` | AdminGuard + AuthGuard | アカウント設定 |
| `/settings/config` | `(admin)/settings/config/page.tsx` | AdminGuard + AuthGuard(adminOnly) | システム設定 |
| `/settings/system` | `(admin)/settings/system/page.tsx` | AdminGuard + AuthGuard(adminOnly) | システム管理 |
| `/settings/users` | `(admin)/settings/users/page.tsx` | AdminGuard + AuthGuard(adminOnly) | ユーザー管理 (admin) |
| `/trades` | `(admin)/trades/page.tsx` | AdminGuard + AuthGuard | 取引一覧 |
| `/users` | `(admin)/users/page.tsx` | AdminGuard | ユーザー一覧 |

### partner グループ `(partner)/`

| URL パス | ファイル | ガード | 備考 |
|----------|----------|--------|------|
| `/partner/dashboard` | `(partner)/partner/dashboard/page.tsx` | PartnerGuard | パートナーダッシュボード |
| `/partner/notifications` | `(partner)/partner/notifications/page.tsx` | PartnerGuard | 通知ログ |
| `/partner/proposals` | `(partner)/partner/proposals/page.tsx` | PartnerGuard | AI提案管理 |
| `/partner/settings` | `(partner)/partner/settings/page.tsx` | PartnerGuard | パートナー設定 |
| `/partner/users` | `(partner)/partner/users/page.tsx` | PartnerGuard | テスター管理 |

### user グループ `(user)/` (BottomNav + EmergencyStopFloat 付き / PrivyRootProvider)

| URL パス | ファイル | ガード | 備考 |
|----------|----------|--------|------|
| `/ai-feed` | `(user)/ai-feed/page.tsx` | AuthGuard | AIフィード |
| `/approve` | `(user)/approve/page.tsx` | なし | 取引承認 |
| `/connect` | `(user)/connect/page.tsx` | なし | ウォレット接続 |
| `/copy-trading` | `(user)/copy-trading/page.tsx` | AuthGuard | コピートレード |
| `/decisions` | `(user)/decisions/page.tsx` | なし | AI判定一覧 |
| `/grid` | `(user)/grid/page.tsx` | AuthGuard | Grid Bot |
| `/history` | `(user)/history/page.tsx` | なし | 取引履歴 |
| `/onboarding` | `(user)/onboarding/page.tsx` | なし | オンボーディング |
| `/privacy-policy` | `(user)/privacy-policy/page.tsx` | なし | プライバシーポリシー |
| `/risk-disclosure` | `(user)/risk-disclosure/page.tsx` | なし | リスク開示 |
| `/settings` | `(user)/settings/page.tsx` | なし | ユーザー設定 |
| `/strategies` | `(user)/strategies/page.tsx` | なし | 戦略選択 |
| `/terms` | `(user)/terms/page.tsx` | なし | 利用規約 |
| `/trade` | `(user)/trade/page.tsx` | AuthGuard | トレード実行 |

### user グループ `/user/` (BottomNav + EmergencyStopFloat 付き / WagmiRootProvider)

| URL パス | ファイル | ガード | 備考 |
|----------|----------|--------|------|
| `/user` | `user/page.tsx` | なし | /user ルート (リダイレクト) |
| `/user/ai-feed` | `user/ai-feed/page.tsx` | なし | AIフィード |
| `/user/approve` | `user/approve/page.tsx` | なし | 取引承認 |
| `/user/copy-trading` | `user/copy-trading/page.tsx` | AuthGuard | コピートレード |
| `/user/dashboard` | `user/dashboard/page.tsx` | なし | ユーザーダッシュボード |
| `/user/decisions` | `user/decisions/page.tsx` | なし | AI判定 |
| `/user/grid` | `user/grid/page.tsx` | AuthGuard | Grid Bot |
| `/user/help` | `user/help/page.tsx` | なし | ヘルプ |
| `/user/history` | `user/history/page.tsx` | AuthGuard | 取引履歴 |
| `/user/onboarding` | `user/onboarding/page.tsx` | なし | オンボーディング |
| `/user/performance` | `user/performance/page.tsx` | なし | パフォーマンス |
| `/user/settings` | `user/settings/page.tsx` | AuthGuard | 設定 |
| `/user/simulation` | `user/simulation/page.tsx` | なし | シミュレーション |
| `/user/trade` | `user/trade/page.tsx` | AuthGuard | トレード |
| `/user/wallet` | `user/wallet/page.tsx` | なし | ウォレット |

### LIFF グループ `(liff)/`

| URL パス | ファイル | ガード |
|----------|----------|--------|
| `/liff-approve` | `(liff)/liff-approve/page.tsx` | なし |
| `/liff-history` | `(liff)/liff-history/page.tsx` | なし |
| `/liff-login` | `(liff)/liff-login/page.tsx` | なし |

### その他 (認証不要)

| URL パス | ファイル |
|----------|----------|
| `/` | `app/page.tsx` (ランディング) |
| `/login` | `app/login/page.tsx` |
| `/register` | `app/register/page.tsx` |

---

## 4. ナビゲーション構造

### admin ナビ (`UserHeader` — isAdmin 時)
管理者は `(admin)` グループ配下のサイドナビ / ヘッダーナビを使用。UserHeader 内の admin 専用リンクは別途 AdminSidebar/AppShell で管理。

### partner ナビ (`UserHeader` — isPartner 時)
```
ダッシュボード → /partner/dashboard
取引承認      → /user/approve          ← ⚠️ user レイアウト (P2 既知問題)
テスター管理  → /partner/users
AI提案        → /partner/proposals
設定          → /partner/settings
```

### user ナビ (`UserHeader` — isAuthenticated かつ非 admin/partner 時)
```
ダッシュボード → /user/dashboard
AI判定         → /user/ai-feed
取引承認       → /user/approve
取引履歴       → /user/history
設定           → /user/settings
Grid Bot       → /user/grid
Copy Trading   → /user/copy-trading
ウォレット     → /user/wallet
```

### BottomNav (モバイル、`md:hidden`)
`(user)` / `user/` レイアウト共通。partner レイアウトには**含まれない**。
```
ホーム         → /dashboard
AI判定         → /decisions
戦略           → /strategies
承認           → /approve  (バッジ付き)
履歴           → /history
設定           → /settings
```

---

## 5. ロール別アクセスマトリクス

| 画面カテゴリ | admin | partner | viewer (tester) | 未認証 |
|-------------|-------|---------|-----------------|--------|
| `/dashboard` (admin) | ✅ | ❌→/partner/dashboard | ❌→/user/dashboard | ❌→/login |
| `/partner/dashboard` | ❌→/user/dashboard | ✅ | ❌→/user/dashboard | ❌→/login |
| `/user/dashboard` | ✅ (リダイレクトで到達) | ✅ (誤誘導で到達) | ✅ | ❌→/login |
| `/user/approve` | ✅ | ✅ (userレイアウト表示) | ✅ | 表示はされるが API 401 |
| `/login` | ✅ (認証後リダイレクト) | ✅ | ✅ | ✅ |
| `/register` | ✅ | ✅ | ✅ | ✅ |
| `/(user)/*` 全般 | ✅ | ✅ | ✅ | 画面による |
| `/liff-*` | ✅ | ✅ | ✅ | ✅ |
