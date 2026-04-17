# 40_multi_wallet_design.md
# マルチユーザーウォレット対応設計書

作成日: 2026-04-14
Asana: 1213878769221132
ブランチ: feature/multi-wallet-design

---

## 1. 概要

### 1.1 現在のアーキテクチャ（Phase 1: シングルウォレット）

パートナー（山本さん）名義の **1 ウォレット** で全 Aave 操作を行う中央集権型。

```
環境変数
  AAVE_WALLET_PRIVATE_KEY  ← Web3AaveClient が Account.from_key() で使用
  AAVE_WALLET_ADDRESS      ← rebalance_service._get_wallet_address() がフォールバック

Web3AaveClient.__init__()  (backend/app/aave/client.py:L326-L379)
  └─ self.account = Account.from_key(settings.wallet_private_key)

deposit() / withdraw()  (client.py:L156-L192)
  引数: wallet_address: str, private_key: str
  → バックエンドが秘密鍵を直接保持して署名・送信

テスターの資金
  fund_allocations.allocated_amount_usd  ← 会計上の按分スライスのみ
  オンチェーン残高は1ウォレットに集約（物理分離なし）
```

**問題点:**
1. バックエンドが秘密鍵（`AAVE_WALLET_PRIVATE_KEY`）を保持 → セキュリティリスク
2. `fund_allocations.tester_name` が `users.username` への文字列マッチ → FK なし、整合性リスク
3. テスターごとの独立した Aave ポジションを持てない
4. Health Factor が1ウォレットの集約値のみ → ユーザーごとのリスク管理不可

### 1.2 目標アーキテクチャ（Phase 2+: マルチウォレット）

各ユーザーが **Privy Embedded Wallet**（MPC）を保有し、自分の署名で Aave を操作する。

```
ユーザーごとの Privy Embedded Wallet
  users.wallet_address  ← Privy 接続時に記録済み
  users.privy_user_id   ← Privy DID（追加予定）

フロントエンド署名フロー:
  Privy useWallets() → wallet.getEthereumProvider()
  → ethers.BrowserProvider → getSigner()
  → ユーザー自身が署名

バックエンド:
  秘密鍵を保持しない
  unsigned tx を構築して返す → フロントが署名 → 署名済み tx を受け取って送信
```

### 1.3 移行戦略

```
Phase 1（現在）: 1ウォレット集約、tester_name文字列マッチ
    ↓ 後方互換を維持したまま段階移行
Phase 1.5（即時実施可能）: fund_allocations FK化、データ整合性修正
    ↓
Phase 2（BVI法人設立 + 森先生Privy MPC確認後）: 個人ウォレット、非カストディアル
    ↓
Phase 3（マルチチェーン対応後）: クロスチェーン残高集約
```

---

## 2. データモデル変更

### 2.1 Phase 1.5: fund_allocations FK 化（即時実施可能）

#### 現状の問題

`backend/app/partner/allocation_models.py:L46`:
```python
tester_name: Mapped[str] = mapped_column(String(100), nullable=False)
```

`backend/app/partner/allocation_service.py:L214` のマッチングロジック:
```python
query = db.query(FundAllocation).filter(
    FundAllocation.tester_name == current_user.username,  # ← 文字列マッチ
)
```

**リスク:** `users.username` を変更すると `fund_allocations.tester_name` と不一致になり割り振りが消える。FK 制約なし。

#### DB 変更

```sql
-- Phase 1.5: tester_user_id カラム追加（tester_nameは後方互換のため残す）
ALTER TABLE fund_allocations
  ADD COLUMN tester_user_id INTEGER REFERENCES users(id) ON DELETE SET NULL;

-- 既存データのバックフィル（username でマッチング）
UPDATE fund_allocations fa
  SET tester_user_id = (
    SELECT u.id FROM users u WHERE u.username = fa.tester_name LIMIT 1
  )
WHERE tester_user_id IS NULL;

-- バックフィル確認
SELECT COUNT(*) FROM fund_allocations WHERE tester_user_id IS NULL;
-- → 0 であればバックフィル完了
```

#### コード変更（`allocation_models.py`）

```python
# 追加: tester_user_id カラム
tester_user_id: Mapped[Optional[int]] = mapped_column(
    Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, default=None, index=True
)
```

#### コード変更（`allocation_service.py:get_my_allocation()`、L213〜L215）

```python
# 変更前（文字列マッチ）:
query = db.query(FundAllocation).filter(
    FundAllocation.tester_name == current_user.username,
)

# 変更後（FK + フォールバック）:
query = db.query(FundAllocation).filter(
    db.query(FundAllocation).filter(
        (FundAllocation.tester_user_id == current_user.id)
        | (
            (FundAllocation.tester_user_id == None)  # noqa: E711
            & (FundAllocation.tester_name == current_user.username)
        )
    )
)
```

#### コード変更（`allocation_service.py:create_allocation()`、L53〜L62）

```python
allocation = FundAllocation(
    partner_id=partner_id,
    tester_name=request.tester_name,
    tester_user_id=request.tester_user_id,  # ← 追加（Optional）
    ...
)
```

### 2.2 Phase 2: users テーブル拡張

```sql
-- Privy ユーザー識別子（did:privy:xxxx 形式）
ALTER TABLE users ADD COLUMN privy_user_id VARCHAR(255) UNIQUE;
ALTER TABLE users ADD COLUMN privy_did VARCHAR(255);

-- ウォレット種別
--   'none'           : ウォレット未接続（デフォルト）
--   'privy_embedded' : Privy MPC Embedded Wallet（メール/SNSログイン後に自動生成）
--   'external'       : MetaMask等の外部ウォレット（SIWE認証済み）
--   'partner_shared' : パートナーのウォレットを共有（仮想按分モード継続）
ALTER TABLE users ADD COLUMN wallet_type VARCHAR(20) NOT NULL DEFAULT 'none';

-- wallet_type に合わせて既存データをバックフィル
UPDATE users SET wallet_type = 'external'
  WHERE wallet_address IS NOT NULL AND privy_user_id IS NULL;
```

現状の `users.wallet_address`（`auth/models.py:L95`、`String(42), unique=True`）は
Privy 接続フロー（`/user/connect/page.tsx:L149` — `loginWithWallet(address, signer)`）
で書き込み済みのため、カラム自体は変更不要。

### 2.3 Phase 2: wallet_positions テーブル（新規）

ユーザーごとの Aave ポジションをリアルタイム追跡する。

```sql
CREATE TABLE wallet_positions (
  id                 SERIAL PRIMARY KEY,
  user_id            INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  wallet_address     VARCHAR(42) NOT NULL,
  protocol           VARCHAR(20) NOT NULL DEFAULT 'aave_v3',
  chain_id           INTEGER NOT NULL DEFAULT 8453,  -- Base Mainnet
  -- Aave AccountData フィールド
  deposited_usd      NUMERIC(20, 6) NOT NULL DEFAULT 0,
  current_value_usd  NUMERIC(20, 6) NOT NULL DEFAULT 0,
  health_factor      NUMERIC(10, 4),
  -- 同期メタデータ
  last_synced_at     TIMESTAMP WITH TIME ZONE,
  created_at         TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
  updated_at         TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
  -- 複合ユニーク: 1ユーザー×1プロトコル×1チェーン
  UNIQUE (user_id, protocol, chain_id)
);

CREATE INDEX wallet_positions_wallet_address_idx ON wallet_positions(wallet_address);
CREATE INDEX wallet_positions_user_id_idx ON wallet_positions(user_id);
```

---

## 3. Aave 操作のウォレット解決フロー

### 3.1 Phase 1（現在）

```
rebalance_service._get_wallet_address()  (rebalance_service.py:L211-L217)
  └─ os.environ.get("AAVE_WALLET_ADDRESS", "")
  └─ フォールバック: getattr(self._aave_settings, "wallet_address", "")

→ 全ユーザーが同一ウォレットにフォールバック。
  deposit()/withdraw() は引数 private_key: str に AAVE_WALLET_PRIVATE_KEY を渡す。
```

`allocation_service._get_wallet_address(partner: User)` (L165-L174):
```python
if partner.wallet_address:
    return partner.wallet_address          # ← users.wallet_address 優先
return os.getenv("AAVE_WALLET_ADDRESS", "")  # ← 環境変数フォールバック
```
この実装はすでにマルチウォレット化の伏線が張られている。

### 3.2 Phase 2（マルチウォレット）

```python
def _resolve_wallet(user: User) -> tuple[str, WalletMode]:
    """
    ユーザーのウォレット種別に応じてアドレスと操作モードを解決する。
    """
    match user.wallet_type:
        case "privy_embedded" | "external":
            # ユーザー個人のウォレット — フロント署名が必須
            return user.wallet_address, WalletMode.FRONTEND_SIGN
        case "partner_shared":
            # パートナーのウォレット — 仮想按分モード継続
            partner = db.query(User).filter(User.id == user.invited_by).first()
            return partner.wallet_address, WalletMode.PARTNER_SHARED
        case _:
            raise WalletNotConfiguredError(user.id)
```

### 3.3 署名フロー（Phase 2: 非カストディアル）

バックエンドは秘密鍵を保持しない。全トランザクションはユーザーがフロントで署名する。

```
フロントエンド                               バックエンド
    │                                           │
    │  1. AI判定結果 → 提案通知                 │
    │  ← ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─│
    │                                           │
    │  2. ユーザーが提案を承認（proposals画面）  │
    │  ──────────────────────────────────────→  │
    │                                           │
    │  3. POST /api/wallet/build-tx             │
    │  ──────────────────────────────────────→  │
    │     { proposal_id, action, amount_usd }   │
    │                                           │
    │  4. unsigned tx data を返却               │
    │  ← ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─│
    │     { to, data, value, gas, chainId }     │
    │                                           │
    │  5. Privy getSigner().sendTransaction()   │
    │     ユーザーが明示的に署名                │
    │                                           │
    │  6. POST /api/wallet/submit-tx            │
    │  ──────────────────────────────────────→  │
    │     { signed_tx_hex, proposal_id }        │
    │                                           │
    │  7. eth_sendRawTransaction → オンチェーン │
    │                                           │
    │  8. tx 結果通知（Slack / LINE）            │
    │  ← ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─│
```

**セキュリティ上の注意:**
- バックエンドは `build-tx` でトランザクション内容（to アドレス、amount）を検証してから構築
- フロントで金額を改ざんしても、`submit-tx` 受け取り時に `proposal_id` と署名 tx の内容を照合
- Health Factor チェック（< 1.6 なら HARD_STOP）は `build-tx` 内でも実施

---

## 4. Privy バックエンド統合

### 4.1 Privy JWT 検証

フロントの `PrivyRootClient.tsx`（`frontend/lib/wallet/PrivyRootClient.tsx:L5`）は
`@privy-io/react-auth` の `PrivyProvider` を使用。
バックエンドでは **Privy Server SDK（`@privy-io/server-auth`）** で JWT を検証する。

```python
# backend/app/auth/privy_service.py（新規）
from privy import PrivyClient  # @privy-io/server-auth の Python 版

class PrivyAuthService:
    def verify_token(self, privy_token: str) -> PrivyClaims:
        """
        Privy JWT を検証し、privy_user_id と wallet_address を返す。
        検証失敗時は AuthenticationError を raise。
        """
        ...
```

移行期間中は既存の SIWE + バックエンド JWT 方式と **共存**。
`POST /api/auth/wallet` エンドポイント（`backend/app/auth/router.py:L356`）は変更なし。

### 4.2 新規エンドポイント

```
POST /api/auth/privy/verify
  リクエスト: { privy_token: str }
  処理: Privy JWT 検証 → users.privy_user_id 更新 → バックエンド JWT 発行
  レスポンス: { access_token: str, token_type: "bearer" }

GET /api/wallet/position
  認証: Bearer token
  処理: wallet_positions テーブル or Aave RPC からユーザーのポジション取得
  レスポンス: WalletPositionResponse

POST /api/wallet/build-tx
  認証: Bearer token
  リクエスト: { proposal_id: int, action: "deposit"|"withdraw", amount_usd: Decimal }
  処理: HF チェック → unsigned tx 構築（to/data/value/gas/chainId）
  レスポンス: { tx_data: UnsignedTxResponse }

POST /api/wallet/submit-tx
  認証: Bearer token
  リクエスト: { signed_tx_hex: str, proposal_id: int }
  処理: proposal との照合 → eth_sendRawTransaction → wallet_positions 更新
  レスポンス: { tx_hash: str, status: "submitted" }
```

---

## 5. モニタリング変更

### 5.1 monitoring_service.py

`check_health_factors_concurrent()` のシグネチャ（`monitoring_service.py:L901-L908`）:
```python
async def check_health_factors_concurrent(
    self,
    wallets: List[str],             # ← すでにリスト型対応済み
    get_health_factor_func: Callable[[str], Optional[Decimal]],
    *,
    max_concurrent: int = 10,
    timeout_seconds: float = 30.0,
) -> List[Optional[Decimal]]:
```

**Phase 1（現在）:** `wallets` に `[env.AAVE_WALLET_ADDRESS]` の1要素を渡す。
**Phase 2:** `wallet_positions` テーブルからアクティブなウォレットアドレスを取得して渡す。

```python
# Phase 2 での呼び出し例
active_wallets = (
    db.query(WalletPosition.wallet_address)
    .filter(WalletPosition.last_synced_at >= threshold)
    .distinct()
    .all()
)
wallets = [row.wallet_address for row in active_wallets]
hf_list = await monitoring.check_health_factors_concurrent(wallets, get_hf)
```

HF が 1.6 未満のウォレットが検出された場合は **ユーザーごとに個別通知**（既存のグローバル緊急停止とは分離）。

### 5.2 通知フロー変更

`notifications/service.py:L174` の `send(payload, user_wallet: str)` は
現状ウォレットアドレスベース。Phase 2 では `user_id` ベースに変更し、
各ユーザーの通知設定（LINE / Slack / Push）に従って個別送信する。

```python
# 変更前
await notification_service.send(payload, user_wallet=wallet_address)

# 変更後
await notification_service.send_to_user(payload, user_id=user.id)
```

---

## 6. 移行計画

### Phase 1.5（即時実施可能、テスター影響なし）

実施条件: アーキテクチャ変更なし、既存テスターへの影響なし。
推定作業: 1日（DB変更 + コード変更 + テスト）

- [ ] `ALTER TABLE fund_allocations ADD COLUMN tester_user_id INTEGER REFERENCES users(id)`
- [ ] 既存データのバックフィル SQL 実行
- [ ] `backend/app/partner/allocation_models.py`: `tester_user_id` カラム追加
- [ ] `backend/app/partner/allocation_service.py:get_my_allocation()` マッチングロジック修正（L214）
- [ ] `backend/app/partner/allocation_service.py:create_allocation()` に `tester_user_id` 対応
- [ ] pytest 新規テスト追加（tester_user_id でのマッチング確認）
- [ ] DoD 全通過

### Phase 2（BVI法人設立 + 森先生Privy MPC確認後）

実施条件:
- BVI 法人設立完了（資産保有主体の確定）
- 森先生による Privy MPC セミカストディアルリスクの法的確認
- テスターへの移行案内（既存の仮想按分から個人ウォレットへ）

推定作業: 2〜3週間

- [ ] `ALTER TABLE users ADD COLUMN privy_user_id VARCHAR(255) UNIQUE`
- [ ] `ALTER TABLE users ADD COLUMN privy_did VARCHAR(255)`
- [ ] `ALTER TABLE users ADD COLUMN wallet_type VARCHAR(20) DEFAULT 'none'`
- [ ] `CREATE TABLE wallet_positions` （上記 DDL 参照）
- [ ] `backend/app/auth/privy_service.py` 新規作成（Privy Server SDK）
- [ ] `POST /api/auth/privy/verify` エンドポイント追加
- [ ] `POST /api/wallet/build-tx` エンドポイント追加
- [ ] `POST /api/wallet/submit-tx` エンドポイント追加
- [ ] `backend/app/aave/rebalance_service.py:_get_wallet_address()` をユーザーIDベースに変更
- [ ] `backend/app/aave/client.py`: `deposit()/withdraw()` の `private_key` 引数を段階的廃止
- [ ] `backend/app/aave/config.py`: `AAVE_WALLET_PRIVATE_KEY` を deprecated として残しつつ警告
- [ ] `frontend/app/(user)/connect/page.tsx`: `build-tx` → Privy 署名 → `submit-tx` フロー追加
- [ ] `backend/app/automation/monitoring_service.py`: `wallet_positions` からウォレットリスト取得
- [ ] E2E テスト（Playwright）

### Phase 3（マルチチェーン対応後）

- [ ] `wallet_positions.chain_id` を活用したチェーン別残高集約
- [ ] Ethereum / Arbitrum / Base / Optimism のクロスチェーンリバランス
- [ ] チェーンごとの Health Factor 個別監視

---

## 7. セキュリティ考慮事項

| Phase | リスク | 対策 |
|-------|--------|------|
| 1.5 | なし（DB FK 追加のみ） | — |
| 2 | unsigned tx 構築後のフロント改ざん | `submit-tx` で proposal_id と tx 内容を照合 |
| 2 | Privy MPC セミカストディアルリスク | 森先生の法的確認を待って実施 |
| 2 | `AAVE_WALLET_PRIVATE_KEY` 残存リスク | Phase 2 完了後に環境変数から削除 |
| 2 | HF チェック bypass | `build-tx` 内でも HF < 1.6 を HARD_STOP |
| 3 | クロスチェーンブリッジリスク | ブリッジは使わない（各チェーン独立） |

**Phase 2 の最大のセキュリティ改善:** `AAVE_WALLET_PRIVATE_KEY` をバックエンドから完全廃止。
秘密鍵がサーバーサイドに存在しなくなるため、サーバー侵害時の資産リスクが劇的に低減する。

---

## 8. 既存コード影響マップ

### Phase 1.5 の変更対象

| ファイル | 対象箇所 | 変更内容 |
|---------|---------|---------|
| `backend/app/partner/allocation_models.py` | `FundAllocation` クラス（L20〜）| `tester_user_id: Mapped[Optional[int]]` カラム追加 |
| `backend/app/partner/allocation_service.py` | `get_my_allocation()` L213-L215 | `tester_name` 文字列マッチ → `tester_user_id` FK マッチ（フォールバック付き） |
| `backend/app/partner/allocation_service.py` | `create_allocation()` L46-L67 | `tester_user_id` フィールドを `AllocationCreateRequest` から受け取り保存 |
| `backend/app/partner/allocation_schemas.py` | `AllocationCreateRequest` | `tester_user_id: Optional[int] = None` フィールド追加 |

### Phase 2 の変更対象

| ファイル | 対象箇所 | 変更内容 |
|---------|---------|---------|
| `backend/app/auth/models.py` | `User` クラス（L40〜） | `privy_user_id`, `privy_did`, `wallet_type` カラム追加 |
| `backend/app/aave/rebalance_service.py` | `_get_wallet_address()` L211-L217 | `AAVE_WALLET_ADDRESS` 環境変数依存を廃止、`user.wallet_address` 直接参照 |
| `backend/app/aave/client.py` | `deposit()` L152-L177, `withdraw()` L179-L192 | `private_key: str` 引数を `Optional` → 将来廃止 |
| `backend/app/aave/config.py` | `get_aave_settings()` L121, L140 | `AAVE_WALLET_PRIVATE_KEY` / `AAVE_PRIVATE_KEY_STAGING` を deprecated 警告付きで残存 |
| `backend/app/automation/monitoring_service.py` | `check_health_factors_concurrent()` L901 の呼び出し元 | `wallet_positions` テーブルからウォレットリストを取得して渡す |
| `backend/app/notifications/service.py` | `send()` L174 | `user_wallet: str` → `user_id: int` ベースに変更 |
| `frontend/app/(user)/connect/page.tsx` | `handleStart()` L141-L162 | `build-tx` → Privy 署名 → `submit-tx` フロー追加 |
| `frontend/lib/wallet/PrivyRootClient.tsx` | `PrivyProvider.config.supportedChains` L17-L33 | Base Mainnet / Arbitrum One を追加（Phase 3 で拡張） |

### 新規作成ファイル

| ファイル | 内容 |
|---------|------|
| `backend/app/auth/privy_service.py` | Privy Server SDK JWT 検証 |
| `backend/app/wallet/` | ウォレット操作モジュール（build-tx / submit-tx / position） |
| `backend/app/wallet/models.py` | `WalletPosition` SQLAlchemy モデル |
| `backend/app/wallet/router.py` | `/api/wallet/*` エンドポイント |
| `backend/tests/test_wallet_service.py` | ウォレット操作テスト |

---

## 9. 参考

- `backend/app/auth/models.py` — `User` クラス、`wallet_address` カラム（L95）
- `backend/app/partner/allocation_models.py` — `FundAllocation`、`tester_name`（L46）
- `backend/app/partner/allocation_service.py` — `_get_wallet_address()`（L165）、マッチング（L214）
- `backend/app/aave/rebalance_service.py` — `_get_wallet_address()`（L211）
- `backend/app/aave/client.py` — `BaseAaveClient.deposit()`（L152）、`Web3AaveClient.__init__()`（L311）
- `backend/app/aave/config.py` — `AaveSettings.wallet_private_key`（L47）
- `backend/app/automation/monitoring_service.py` — `check_health_factors_concurrent()`（L901）
- `frontend/lib/wallet/PrivyRootClient.tsx` — `PrivyProvider` 設定
- `frontend/app/(user)/connect/page.tsx` — `loginWithWallet()`（L149）
- `docs/13_security_design.md` — セキュリティルール（HF < 1.6 HARD_STOP 等）
