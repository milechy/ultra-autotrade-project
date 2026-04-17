# eKYC/本人確認 設計ドキュメント

> 作成日: 2026-04-12
> ステータス: Draft（弁護士レビュー・TrustDock見積もり待ち）
> Asana: 1213978581275568（期限: 2026-04-23）

---

## 1. 目的

| 目的 | 根拠 |
|------|------|
| LINEミニアプリ金融サービス審査の通過要件を満たす | LINEミニアプリ審査通過要件書（2026/4/11版）にeKYC必須の明記あり |
| 犯罪収益移転防止法（犯収法）への対応準備 | 暗号資産交換業登録の要否にかかわらず、金融サービスとして整備が望ましい |
| 18歳未満の利用排除 | 年齢制限は利用規約に追加予定。技術的なゲートも必要 |
| KYCなし取引を禁止する技術的担保 | 現状は認証のみでKYC未完了ユーザーも取引可能（ギャップ） |

---

## 2. 現状の認証アーキテクチャ（調査結果）

### 2-1. バックエンド認証構成

**実装済みファイル:**

| ファイル | 役割 |
|---------|------|
| `backend/app/auth/models.py` | Userモデル（KYCフィールドなし） |
| `backend/app/auth/router.py` | `/auth/register`, `/auth/login`, `/auth/me` 等 |
| `backend/app/auth/service.py` | AuthService（JWT発行・検証・ユーザーCRUD） |
| `backend/app/auth/dependencies.py` | `get_current_user`, `require_admin` 等のガード |
| `backend/app/auth/line.py` | LINEログイン（IDトークン検証・ユーザー自動生成） |

**Userモデルの現状フィールド（KYC関連フィールドは存在しない）:**

```python
class User(Base):
    __tablename__ = "users"
    id, email, username, hashed_password
    role: str  # admin / partner / editor / viewer
    is_active: bool
    created_at, updated_at
    terms_accepted_at, terms_version
    risk_mode, notification_email, notification_frequency
    max_single_trade_usd, max_daily_trade_usd
    user_mode, execution_policy
    wallet_address
    invited_by  # ForeignKey users.id
    tier: str  # GENERAL / UPPER
    last_judgment_at
    # ← KYCフィールドは完全に存在しない
```

**現状のガード構造（dependencies.py）:**

```
get_current_user → require_active_user → require_viewer
                                       → require_editor
                                       → require_partner
                                       → require_admin
```

KYCチェックはどのレイヤーにも存在しない。

### 2-2. LINEログインの実装状態

`backend/app/auth/line.py` にて以下が実装済み:
- `verify_line_id_token()`: LINE IDトークンをLINE APIで検証
- `get_or_create_line_user()`: LINEユーザーID → `line_<userId>@line.local` の疑似メールで自動登録

LINEユーザーは `role=UserRole.VIEWER`, `is_active=True` で自動作成される。
現在はeKYCのステータス管理なし。

### 2-3. フロントエンド認証構成

| 経路 | 実装 |
|------|------|
| LIFFアクセス | `frontend/app/(liff)/liff-login/page.tsx` → LINEログイン |
| 通常ブラウザ | `frontend/app/(user)/connect/page.tsx` → Privy（email/wallet）|
| オンボーディング | `frontend/app/(user)/onboarding/page.tsx` |

---

## 3. eKYCフロー設計

### 3-1. 全体フロー図

```
[LINEミニアプリ起動]
  ↓
[LINEログイン（OAuth 2.0）]  ← 既存実装（backend/app/auth/line.py）
  ↓
[JWT発行 → アプリセッション確立]
  ↓
[KYCステータス確認: GET /api/user/kyc/status]
  │
  ├─ kyc_status = "approved"
  │    └→ [ダッシュボード（全機能利用可能）]
  │
  ├─ kyc_status = "pending"
  │    └→ [審査中画面]（「審査中です。しばらくお待ちください」）
  │         ↓ Webhook受信（TrustDock → バックエンド）
  │         ↓ LINE通知（審査完了/却下）
  │
  ├─ kyc_status = "rejected"
  │    └→ [却下・再申請画面]（却下理由表示 + 再申請ボタン）
  │
  └─ kyc_status = null（未申請）
       ↓
  [eKYC開始画面（/user/kyc）]
       ↓
  [利用規約・プライバシーポリシー同意チェックボックス]
       ↓
  [年齢確認（生年月日入力）]
       ├─ 18歳未満 → [利用不可画面（「18歳未満の方はご利用いただけません」）]
       └─ 18歳以上 → 続行
       ↓
  [eKYCプロバイダーSDK起動（TrustDock または SumSub）]
       ↓
  [身分証撮影（運転免許証 / マイナンバーカード / 在留カード）]
       ↓
  [顔認証（ライブネス検知）]
       ↓
  [申請完了 → kyc_status = "pending" に更新]
       ↓
  [審査中画面（/user/kyc/pending）]
       ↓
  [Webhook受信: POST /api/webhooks/trustdock]
       ├─ 審査OK  → kyc_status = "approved"
       └─ 審査NG  → kyc_status = "rejected" + 却下理由保存
       ↓
  [LINE通知（審査結果をLINE Messaging APIでプッシュ）]
       ↓
  [ウォレット接続・取引機能解放]
```

### 3-2. KYCステータス定義

| ステータス | 説明 | 許可される操作 |
|----------|------|--------------|
| `null` | 未申請 | アプリ閲覧のみ。eKYC開始画面へリダイレクト |
| `"pending"` | 審査中 | アプリ閲覧のみ。取引・Aave操作不可 |
| `"approved"` | 承認済み | 全機能利用可能 |
| `"rejected"` | 却下 | 再申請可能。取引・Aave操作不可 |
| `"expired"` | 有効期限切れ | 再申請必要（将来対応。犯収法では5年更新が必要な場合あり）|

---

## 4. DBスキーマ変更案

### 4-1. usersテーブルへのカラム追加

```sql
-- KYCステータス・プロバイダー情報
ALTER TABLE users ADD COLUMN IF NOT EXISTS kyc_status VARCHAR(20) DEFAULT NULL;
  -- null / 'pending' / 'approved' / 'rejected' / 'expired'

ALTER TABLE users ADD COLUMN IF NOT EXISTS kyc_provider VARCHAR(50) DEFAULT NULL;
  -- 'trustdock' / 'sumsub'

ALTER TABLE users ADD COLUMN IF NOT EXISTS kyc_reference_id VARCHAR(100) DEFAULT NULL;
  -- プロバイダー発行の申請ID（Webhook照合に使用）

ALTER TABLE users ADD COLUMN IF NOT EXISTS kyc_submitted_at TIMESTAMP WITH TIME ZONE DEFAULT NULL;
ALTER TABLE users ADD COLUMN IF NOT EXISTS kyc_approved_at TIMESTAMP WITH TIME ZONE DEFAULT NULL;
ALTER TABLE users ADD COLUMN IF NOT EXISTS kyc_rejected_reason TEXT DEFAULT NULL;

-- 年齢確認
ALTER TABLE users ADD COLUMN IF NOT EXISTS birth_date DATE DEFAULT NULL;
ALTER TABLE users ADD COLUMN IF NOT EXISTS is_age_verified BOOLEAN DEFAULT FALSE;
```

**注意:** 氏名・住所・身分証画像等の個人情報はeKYCプロバイダー側で管理し、
当社DBには審査ステータスと参照IDのみを保存する（最小限の個人情報保持原則）。

### 4-2. KYC審査ログテーブル（監査用・7年間保存）

```sql
CREATE TABLE IF NOT EXISTS kyc_audit_logs (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    action VARCHAR(50) NOT NULL,
      -- 'submitted' / 'approved' / 'rejected' / 'expired' / 'admin_override'
    provider VARCHAR(50),
    reference_id VARCHAR(100),
    details JSONB,  -- Webhookペイロードの安全な部分（個人情報除く）
    performed_by INTEGER REFERENCES users(id),  -- 管理者操作の場合は管理者ID
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_kyc_audit_user_id ON kyc_audit_logs(user_id);
CREATE INDEX idx_kyc_audit_created_at ON kyc_audit_logs(created_at);
```

---

## 5. バックエンドAPI設計

### 5-1. 新規エンドポイント一覧

| Method | Path | 説明 | 認証 |
|--------|------|------|------|
| GET | `/api/user/kyc/status` | 自分のKYCステータス取得 | Bearer（本人） |
| POST | `/api/user/kyc/start` | eKYC開始（プロバイダーSDKセッショントークン取得） | Bearer（本人） |
| POST | `/api/user/kyc/age-verify` | 年齢確認（生年月日送信） | Bearer（本人） |
| POST | `/api/webhooks/trustdock` | TrustDock審査結果Webhook受信 | Webhook署名検証（HMAC） |
| POST | `/api/webhooks/sumsub` | SumSub審査結果Webhook受信（代替） | Webhook署名検証 |
| GET | `/api/admin/kyc/users` | KYC管理一覧（管理者用） | Bearer（admin） |
| PUT | `/api/admin/kyc/users/{id}/override` | KYCステータス手動変更（管理者用） | Bearer（admin） |

### 5-2. レスポンス定義

**GET /api/user/kyc/status:**
```json
{
  "kyc_status": "approved",
  "kyc_provider": "trustdock",
  "kyc_submitted_at": "2026-04-12T10:00:00Z",
  "kyc_approved_at": "2026-04-12T15:00:00Z",
  "is_age_verified": true
}
```

**POST /api/user/kyc/start (200 OK):**
```json
{
  "session_token": "eyJ...",   // TrustDock SDK起動に使用
  "provider": "trustdock",
  "expires_in": 3600
}
```

**POST /api/user/kyc/age-verify (200 OK):**
```json
{
  "is_eligible": true,         // 18歳以上なら true
  "is_age_verified": true
}
```

**エラーケース（KYC未完了で取引系APIを呼んだ場合）:**
```json
{
  "detail": "KYC verification required",
  "kyc_status": null,
  "kyc_url": "/user/kyc"
}
```
→ HTTP 403 Forbidden

### 5-3. KYCガード（middleware / Depends）

```python
# backend/app/auth/dependencies.py に追加予定

async def require_kyc_approved(
    user: User = Depends(require_active_user),
) -> User:
    """
    KYC承認済みユーザーを要求する。

    Aave操作・取引系エンドポイントに適用。
    KYCが未完了の場合は 403 を返す。
    """
    if user.kyc_status != "approved":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="KYC verification required",
            headers={"X-KYC-Required": "true"},
        )
    return user
```

**適用対象エンドポイント（実装時に追加）:**
- `POST /aave/rebalance`
- `POST /aave/deposit`
- `POST /aave/withdraw`
- `POST /exchange/order`
- `POST /proposals/{id}/approve`

---

## 6. フロントエンド設計

### 6-1. 新規ページ構成

```
frontend/app/(user)/
  kyc/
    page.tsx           # eKYC開始・ステータス振り分け（ハブページ）
    verify/
      page.tsx         # eKYCプロバイダーSDK表示（iframe or redirect）
    pending/
      page.tsx         # 審査中画面
    rejected/
      page.tsx         # 却下・再申請画面
```

### 6-2. KYCガードコンポーネント

取引機能を持つページをラップし、KYC未完了ユーザーをブロックする:

```tsx
// frontend/components/kyc/KYCGuard.tsx
// KYCガード: 取引系ページをラップして、KYC未完了ユーザーを /user/kyc にリダイレクト

<KYCGuard>
  <DashboardContent />   // Approve, Trade, Grid, History等の取引系ページ
</KYCGuard>
```

**KYCGuardの動作:**
- `kyc_status === "approved"` → 子コンポーネントをそのまま表示
- `kyc_status === "pending"` → 「審査中バナー」を表示（機能はロック）
- `kyc_status === null / "rejected"` → `/user/kyc` にリダイレクト

### 6-3. LIFFページへの適用

`frontend/app/(liff)/liff-approve/page.tsx` などLIFF内の取引系ページにも
同様のKYCガードを適用する。

---

## 7. eKYCプロバイダー統合設計

### 7-1. プロバイダー比較

| 項目 | TrustDock | SumSub |
|------|-----------|--------|
| LINE推奨 | ✅ 公式推奨 | △ |
| 日本語UI | ✅ ネイティブ | △（設定可） |
| 日本の身分証対応 | ✅ 運転免許証・マイナンバー・在留カード等 | ✅ |
| SDK形式 | Web SDK（JS）+ iOS/Android | Web SDK + iOS/Android |
| LIFF内動作 | 要検証 | 要検証 |
| 審査時間 | 即日〜翌営業日 | 数分〜数時間（AI審査） |
| 費用 | **要見積もり（問合せ済み）** | $199〜/月 + 従量 |
| 契約 | 法人名義が必要か要確認 | 法人なしで契約可の場合あり |

### 7-2. TrustDock統合フロー

```
フロントエンド                    バックエンド              TrustDock
    |                               |                        |
    | POST /api/user/kyc/start      |                        |
    |-----------------------------→|                        |
    |                               | TrustDock API呼び出し   |
    |                               |----------------------→|
    |                               |← セッショントークン      |
    | ← session_token               |                        |
    |                               |                        |
    | TrustDock Web SDK起動          |                        |
    | (session_token渡す)            |                        |
    |-----------------------------------------------→ |     |
    |          身分証撮影・顔認証                        |     |
    |←----------------------------------------------- |     |
    |                               |                        |
    | kyc_status = "pending"表示     |                        |
    |                               |                        |
    |                  (審査完了後)   |                        |
    |                               |← POST /webhooks/trustdock
    |                               |   {result: "approved", |
    |                               |    reference_id: "..."}|
    |                               |                        |
    |                               | kyc_statusをapprovedに更新
    |                               | KYC audit log記録       |
    |                               | LINE通知送信             |
    |                               |                        |
    | (LINEプッシュ通知受信)           |                        |
    | → アプリ再起動 → ダッシュボード   |                        |
```

### 7-3. プロバイダー抽象化設計（将来の切り替えに備える）

```python
# backend/app/kyc/provider.py（新規モジュール）

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum


class KYCResultStatus(str, Enum):
    APPROVED = "approved"
    REJECTED = "rejected"
    PENDING = "pending"


@dataclass
class KYCResult:
    status: KYCResultStatus
    reference_id: str
    rejected_reason: str | None = None


class BaseKYCProvider(ABC):
    """eKYCプロバイダーの抽象基底クラス。"""

    @abstractmethod
    async def create_verification_session(self, user_id: int) -> dict:
        """eKYCセッション開始。フロントエンドSDK用トークンを返す。"""

    @abstractmethod
    async def verify_webhook(self, payload: bytes, signature: str) -> bool:
        """Webhook署名検証。HMAC-SHA256等で検証。"""

    @abstractmethod
    async def parse_result(self, payload: dict) -> KYCResult:
        """Webhookペイロードから審査結果をパース。"""
```

---

## 8. セキュリティ考慮事項

| 考慮事項 | 対応方針 |
|---------|---------|
| 身分証画像の管理 | Ultra AutoTradeサーバーには保存しない。eKYCプロバイダー側で管理（参照IDのみ保持） |
| 個人情報の最小化 | DBに保存するのは: kyc_status, kyc_provider, kyc_reference_id, kyc_*_at, birth_date のみ |
| Webhook改ざん防止 | 受信時にHMAC-SHA256署名検証を必須とする。署名不一致は即座に400エラー |
| KYC審査ログの保存期間 | 7年間（金融規制・犯収法の記録保存要件に対応） |
| 管理者によるKYC手動変更 | 全操作を`kyc_audit_logs`テーブルに記録（`performed_by`フィールドで誰が変更したか追跡） |
| 年齢確認の迂回防止 | 生年月日のバリデーションはバックエンドで行う（フロントエンドのみでは迂回可能） |
| KYC未完了ユーザーの取引防止 | バックエンドの`require_kyc_approved`デコレータで全取引系APIをガード（フロントエンドのみのガードでは不十分） |

---

## 9. LINEミニアプリ審査との整合性

| 審査要件 | 対応内容 |
|---------|---------|
| eKYC必須 | TrustDock（またはSumSub）で対応 |
| 18歳未満排除 | ①生年月日入力によるフロントエンドチェック、②身分証のeKYCによる年齢照合（二重確認） |
| 日本語UI | 全eKYCフローを日本語で提供（TrustDock: 日本語ネイティブ対応） |
| KYCなし取引禁止 | バックエンドの`require_kyc_approved`ガードで技術的に強制 |
| 本人確認書類の対応 | 運転免許証・マイナンバーカード・在留カード・パスポート |

---

## 10. 実装フェーズ分割

| フェーズ | 内容 | 前提条件 | 工数目安 |
|---------|------|---------|---------|
| **Phase A** | DBスキーマ追加（ALTER TABLE）+ KYCステータスAPI（GET/POST）+ `require_kyc_approved`ガード実装 | なし（即時着手可） | 2〜3日 |
| **Phase B** | 年齢確認UI + KYCステータス表示UI（/user/kyc ハブ・pending・rejected ページ） | Phase A完了 | 2〜3日 |
| **Phase C** | TrustDock SDK統合（フロントエンドSDK起動 + バックエンドセッション生成API） | TrustDock契約完了 | 3〜5日 |
| **Phase D** | Webhook受信エンドポイント + LINE通知連携（審査完了を通知） | Phase C完了 | 2〜3日 |
| **Phase E** | 管理者KYC管理画面（一覧・手動ステータス変更・審査ログ表示） | Phase A完了 | 2〜3日 |

**合計見込み工数:** 11〜17日（Phase A〜E全実装）

**最小MVP（LINE審査に必要な最低限）:** Phase A + B + C + D = 9〜14日

---

## 11. 未決事項（弁護士・パートナー確認待ち）

| # | 項目 | 確認先 | 優先度 | 影響 |
|---|------|-------|-------|------|
| 1 | 暗号資産交換業登録の要否 | 森先生 | P0 | eKYCの法的根拠の強度に影響 |
| 2 | Privy MPC方式の非カストディアル適格性 | 森先生 | P0 | 非カストディアル主張の根拠 |
| 3 | eKYCベンダー最終選定（TrustDock vs SumSub） | 山本さん（予算承認） | P0 | Phase C以降の実装に直結 |
| 4 | 法人設立前のeKYCベンダー契約可否 | 森先生 + TrustDock営業 | P1 | 実装スケジュールに影響 |
| 5 | eKYCで取得した個人情報の自社での保存可否 | 森先生 | P1 | DBスキーマの範囲（Section 4）に影響 |
| 6 | 審査ログの保存期間（犯収法上の要件） | 森先生 | P1 | 7年を前提に設計中だが確認が必要 |
| 7 | `"expired"`ステータスの更新頻度（再KYCの要否） | 森先生 | P2 | 将来の保守コストに影響 |

---

## 付録: 現状のユーザー登録フローとeKYC挿入箇所

```
現在のフロー（LINEミニアプリ経由）:

[LINE起動] → [LINEログイン] → [JWT取得] → [ダッシュボード（全機能）]
                                               ↑
                                       ←← ここでKYCチェックなし（問題）

eKYC追加後のフロー:

[LINE起動] → [LINEログイン] → [JWT取得] → [KYCステータス確認]
                                               ↓
                                    approved? → [ダッシュボード（全機能）]
                                    null?    → [eKYC開始画面]
                                    pending? → [審査中画面]
                                    rejected?→ [再申請画面]
```

**フロントエンドでの実装箇所:**
- `frontend/app/(liff)/layout.tsx` — LIFFレイアウトでKYCガード追加
- `frontend/app/(user)/onboarding/page.tsx` — オンボーディング後にeKYC誘導
- 取引系ページ全般 — `<KYCGuard>` コンポーネントでラップ
