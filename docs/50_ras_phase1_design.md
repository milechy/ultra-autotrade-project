# RAS Phase 1: Referral Attribution System Design

## 概要

Referral Attribution System (RAS) は Ultra AutoTrade の紹介報酬機能 (Phase 1) です。
ユーザーが友人を紹介し、その友人が投資を開始したとき、紹介元ユーザーが報酬を得る仕組みです。

**タイムライン:**
- 本番デプロイ予定: 2026-05-15 (F-17 + RAS Phase 1 一括)
- 現在フェーズ: Phase 1 設計・実装（Lane 5: docs & parallel tasks）

**関連 Asana タスク:**
- Lane 5 本体: GID 1214630216568311 (docs + scripts)
- F-17/9 Toaster: GID 1214630020324132 (レイアウト修正)

---

## DB スキーマ

### 新規テーブル: referrals

```sql
CREATE TABLE IF NOT EXISTS referrals (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    referrer_user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    referred_email VARCHAR(255) NOT NULL UNIQUE,
    referred_user_id UUID REFERENCES users(id) ON DELETE SET NULL,
    referred_consent_text VARCHAR(500),
    referred_consent_accepted_at TIMESTAMP,
    status VARCHAR(50) DEFAULT 'pending',  -- pending | active | claimed | expired
    claim_status VARCHAR(50) DEFAULT 'unclaimed',  -- unclaimed | claimed
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

**フィールド説明:**
- `referrer_user_id`: 紹介元ユーザー ID
- `referred_email`: 紹介対象者のメールアドレス
- `referred_user_id`: 紹介対象者のユーザー ID (投資開始後に populate)
- `referred_consent_text`: 紹介対象者が同意した文言 (署名用)
- `referred_consent_accepted_at`: 同意タイムスタンプ
- `status`: ライフサイクル状態
  - `pending`: 紹介メール未開
  - `active`: メール開封・同意画面表示
  - `claimed`: 初回投資完了 → 報酬確定
  - `expired`: 180日未アクティベーション
- `claim_status`: 報酬請求状態

### users テーブル追加カラム

```sql
ALTER TABLE users ADD COLUMN IF NOT EXISTS referral_code VARCHAR(16) UNIQUE DEFAULT NULL;
ALTER TABLE users ADD COLUMN IF NOT EXISTS referrer_user_id UUID DEFAULT NULL REFERENCES users(id) ON DELETE SET NULL;
```

**フィールド説明:**
- `referral_code`: ユーザーの紹介コード (e.g., `ref_abc123xyz`)
- `referrer_user_id`: 自分を紹介してくれたユーザー ID

---

## API エンドポイント

### 1. 紹介リンク生成

**`POST /referral/generate`**
- リクエスト: `{ "referral_code": "ref_abc123xyz" }`
- レスポンス: `{ "referral_url": "https://app.ultra-auto-trade.com/auth/register?ref=ref_abc123xyz" }`
- 説明: マイページから紹介リンクを取得

### 2. 紹介対象者招待

**`POST /referral/invite`**
- 認証: ✅ 必須 (referrer user)
- リクエスト:
  ```json
  {
    "referred_email": "friend@example.com",
    "message": "Ultra AutoTrade で自動取引を始めませんか？"
  }
  ```
- レスポンス: `{ "referral_id": "uuid", "status": "pending" }`
- 説明: 友人にメール招待を送信

### 3. 紹介登録ページ表示

**`GET /auth/register?ref=ref_abc123xyz`**
- 認証: ❌ 不要 (public)
- レスポンス: フロントエンド登録フォーム + 紹介元情報表示
- 説明: 紹介コード付きで登録ページを表示

### 4. 紹介対象者ユーザー作成（登録完了）

**`POST /auth/register`** (既存、拡張)
- リクエスト:
  ```json
  {
    "email": "friend@example.com",
    "password": "...",
    "referral_code": "ref_abc123xyz",
    "agreed_to_referral_terms": true
  }
  ```
- 説明: 紹介コード付きで登録し、`referrals.referred_user_id` を populate

### 5. 紹介状態確認

**`GET /referral/status/{referral_id}`**
- 認証: ✅ 必須 (referrer user)
- レスポンス:
  ```json
  {
    "referral_id": "uuid",
    "referred_email": "friend@example.com",
    "status": "active",
    "claim_status": "unclaimed",
    "referred_deposit_jpy": 1000000,
    "reward_eligible": true,
    "created_at": "2026-05-08T10:00:00Z"
  }
  ```

### 6. 報酬一覧

**`GET /referral/rewards`**
- 認証: ✅ 必須
- レスポンス:
  ```json
  {
    "total_rewards_jpy": "150000",
    "pending_count": 2,
    "claimed_count": 3,
    "rewards": [
      {
        "referral_id": "uuid",
        "referred_email": "friend@example.com",
        "reward_jpy": "50000",
        "claim_status": "claimed",
        "claimed_at": "2026-05-01T15:30:00Z"
      }
    ]
  }
  ```

---

## 画面設計

### ユーザー側

#### 1. マイページ → 「紹介で稼ぐ」タブ
- 紹介コード表示 (`ref_abc123xyz`)
- コピーボタン
- 紹介URL生成・コピーボタン
- 招待メール送信フォーム (email入力 + メッセージ)
- 現在の紹介状態 (pending/active/claimed カウント)
- 報酬一覧表

#### 2. 登録ページ (紹介コード付き)
- `GET /auth/register?ref=ref_abc123xyz` でアクセス
- 紹介元ユーザー名表示 (「XXXさんからの紹介」)
- 紹介同意チェックボックス + 法務文言
- 通常の登録フォーム
- 確認ボタンで `/auth/register` に POST

#### 3. マイページ → 「紹介履歴」タブ (admin/partner ロール)
- 全紹介一覧表
- フィルター: status (pending/active/claimed), claim_status (unclaimed/claimed)

### Admin側

#### 管理画面 → 「紹介管理」
- 全紹介一覧 (フィルター + ページング)
- 手動報酬調整ボタン
- CSVエクスポート

---

## fund_allocations との共存ルール

RAS Phase 1 では、紹介報酬は `fund_allocations` テーブルに含めない。

**理由:**
- `fund_allocations` = ユーザー資産配分 (Aave / Protocol 単位)
- `referrals` = 紹介報酬トラッキング (独立したビジネスロジック)
- Phase 2 で report_allocations に統合する予定

**設計:**
- `referrals.claim_status = 'claimed'` → 対応する報酬額を別途ウォレットに振込 or deposit
- 現在: Phase 1 では報酬はシステムに蓄積（振込機能は Phase 2）

---

## 同意フロー

### 法務未クリア事項 ⚠️

**TBD — 森先生レビュー待ち (claude.ai C1 確認待ち)**

以下の項目は法務部の最終確認が必要です:

1. **紹介同意文言** (`referred_consent_text`)
   - テンプレート案は `backend/app/referral/consent_templates.py` に記載予定
   - 実運用では森先生の法務レビュー版を使用すること
   - 日本語・英語両対応（翻訳は ja.json）

2. **紹介元ユーザーの責務**
   - 紹介した友人が金銭損失を出した場合の法的責任
   - 紹介報酬の税務処理（所得税分類）

3. **報酬の振込タイミング**
   - 翌月振込か月内か → 法務 & 経理の判断待ち
   - 振込手数料はユーザー負担か、システム負担か

4. **キャンセルポリシー**
   - 紹介後30日以内のキャンセルは報酬対象外か
   - ユーザーが紹介を取り消せるか

### 実装時の注意

**現在のコード実装:**
- `backend/app/referral/` に法務フローの仮実装あり
- `referred_consent_text` には仮テンプレートを埋め込み
- 本番運用時は森先生の承認版テキストに置き換え（`REFERRAL_CONSENT_TEMPLATE` env var）

---

## Phase 2 引き継ぎ項目

RAS Phase 1 は以下をスコープ外とします。Phase 2 で実装予定:

### P2-1: 報酬振込機能
- 紹介報酬のウォレット振込
- 月次バッチ処理 (`scheduled_tasks.py`)

### P2-2: 報酬の fund_allocations 統合
- `fund_allocations` に `type='referral_reward'` を追加
- Tier / RiskMode ごとの報酬額計算ロジック

### P2-3: 紹介コード有効期限
- 180日未使用の紹介 → `status='expired'` 自動遷移
- Cron job 実装

### P2-4: 多言語対応 (英語)
- `referred_consent_text` の英語版
- 紹介UI テキスト全翻訳

### P2-5: アナリティクス
- 紹介成功率レポート
- 報酬額トレンド

---

## 開発チェックリスト (Lane 5)

### S1: ドキュメント (✅ 本ファイル)
- [x] docs/50_ras_phase1_design.md 作成

### S2: docs/15 凍結期間追記
- [ ] docs/15_rollback_procedures.md に凍結期間ノート追記
- [ ] 他の docs/15_*.md ファイルの追記

### S4: Toaster レイアウト監査 (M2)
- [ ] 全レイアウト × Toaster マトリクス作成
- [ ] 欠損があれば feature/ras-l5-toaster-fix PR 分離

### S5: 山本さん staging UPDATE (M3、claude.ai C2 待ち)
- [ ] Phase 1: 現在の risk_mode 値確認 (@phase1-investigator)
- [ ] Phase 2: UPDATE 文 + pg_dump 手順作成 (@phase2-implementer)
- [ ] Phase 3: UPDATE 実行 + Slack 通知 (@phase3-deployer)

---

## Toaster レイアウト監査 (M2 - 2026-05-08)

### 監査結果マトリクス

| ファイル | Toaster 状態 | 対応 |
|---------|-----------|------|
| `frontend/components/providers/AdminProviders.tsx` | ❌ **欠損** | ✅ Fix PR 必要 (feature/ras-l5-toaster-fix) |
| `frontend/components/providers/PartnerProviders.tsx` | ✅ あり | OK |
| `frontend/components/user/UserProviders.tsx` | ✅ あり | OK |
| `frontend/app/(admin)/layout.tsx` | 依存: AdminProviders (❌ 欠損継承) | ✅ Fix で解決 |
| `frontend/app/(partner)/layout.tsx` | 依存: PartnerProviders (✅) | OK |
| `frontend/app/(user)/layout.tsx` | 依存: UserProviders (✅) | OK |
| `frontend/app/user/layout.tsx` | 依存: UserProviders (✅) | OK |
| `frontend/app/(liff)/layout.tsx` | 独立 (LINE LIFF context) | OK（toast 不要） |

### 修正内容 (feature/ras-l5-toaster-fix PR)

**AdminProviders.tsx に Toaster 追加:**

```tsx
import { Toaster } from 'sonner'

export function AdminProviders({ children }: { children: React.ReactNode }) {
  return (
    <AuthProvider>
      <AdminGuard>
        <AppShell>
          {children}
          <Toaster position="top-center" richColors />
        </AppShell>
      </AdminGuard>
    </AuthProvider>
  )
}
```

### 参考: F-17 時の追加 (PR #193)

PartnerProviders.tsx に Toaster 追加済 (commit abaecdc)。
AdminProviders.tsx も同パターンで追加。

---

## 参考リンク

- **Asana Lane 5 本体**: GID 1214630216568311
- **Asana F-17/9 Toaster**: GID 1214630020324132 (M2 完了)
- **本番デプロイ予定**: 2026-05-15
