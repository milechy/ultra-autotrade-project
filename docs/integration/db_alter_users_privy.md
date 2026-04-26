# DB ALTER設計書: privy_did追加 + hashed_password nullable化

**Asana GID:** 1214162094702307  
**関連タスク:** 1214176336328111 (CHECK制約追加 + 実行、2026-05-03予定)  
**ステータス:** 設計書完成（実DB ALTERは別タスクで実施）  
**作成日:** 2026-04-26

---

## 1. AS-IS スキーマ（users テーブル現状）

```sql
CREATE TABLE users (
    id                    INTEGER       PRIMARY KEY AUTOINCREMENT,
    email                 VARCHAR(255)  NOT NULL UNIQUE,
    username              VARCHAR(100)  NOT NULL UNIQUE,
    hashed_password       VARCHAR(255)  NOT NULL,          -- ← 変更対象
    role                  VARCHAR(20)   NOT NULL DEFAULT 'viewer',
    is_active             BOOLEAN       NOT NULL DEFAULT TRUE,
    created_at            TIMESTAMPTZ   NOT NULL,
    updated_at            TIMESTAMPTZ   NOT NULL,
    terms_accepted_at     TIMESTAMPTZ   NULL,
    terms_version         VARCHAR(20)   NULL,
    risk_mode             VARCHAR(20)   NULL DEFAULT 'conservative',
    notification_email    VARCHAR(255)  NULL,
    notification_frequency VARCHAR(20)  NOT NULL DEFAULT 'important',
    max_single_trade_usd  NUMERIC(20,2) NULL,
    max_daily_trade_usd   NUMERIC(20,2) NULL,
    user_mode             VARCHAR(20)   NOT NULL DEFAULT 'managed',
    execution_policy      VARCHAR(20)   NOT NULL DEFAULT 'auto_execute',
    wallet_address        VARCHAR(42)   NULL UNIQUE,
    invited_by            INTEGER       NULL REFERENCES users(id),
    tier                  VARCHAR(20)   NOT NULL DEFAULT 'LOWER',
    last_judgment_at      TIMESTAMPTZ   NULL
);

CREATE UNIQUE INDEX ix_users_email    ON users(email);
CREATE UNIQUE INDEX ix_users_username ON users(username);
CREATE UNIQUE INDEX ix_users_wallet_address ON users(wallet_address) WHERE wallet_address IS NOT NULL;
```

**認証経路（AS-IS）:**
- `POST /auth/register` → email/password → bcrypt hash → `hashed_password` に保存
- `POST /auth/login` → bcrypt 検証 (`hashed_password` 参照)
- `POST /auth/wallet/connect` → ランダムパスワードを生成して `hashed_password` に保存
- `POST /auth/line` → ランダムパスワード (`secrets.token_hex(32)`) を `hashed_password` に保存

---

## 2. TO-BE スキーマ（Privy対応後）

```sql
-- 変更点:
-- (A) hashed_password: NOT NULL → NULL
-- (B) privy_did: 新規追加 VARCHAR(255) UNIQUE NULL
-- (C) CHECK制約: hashed_password と privy_did の排他必須

ALTER TABLE users ALTER COLUMN hashed_password DROP NOT NULL;

ALTER TABLE users ADD COLUMN privy_did VARCHAR(255) NULL;
CREATE UNIQUE INDEX ix_users_privy_did ON users(privy_did) WHERE privy_did IS NOT NULL;

ALTER TABLE users ADD CONSTRAINT chk_users_auth_method
    CHECK (hashed_password IS NOT NULL OR privy_did IS NOT NULL);
```

**TO-BE スキーマ差分:**

| カラム          | AS-IS              | TO-BE                        |
|-----------------|--------------------|------------------------------|
| hashed_password | VARCHAR(255) NOT NULL | VARCHAR(255) NULL          |
| privy_did       | (存在しない)       | VARCHAR(255) NULL UNIQUE     |
| CHECK制約       | (存在しない)       | `chk_users_auth_method` 追加 |

**認証経路（TO-BE）:**
- email/password ユーザー: `hashed_password` あり / `privy_did` NULL
- Privy ユーザー:           `hashed_password` NULL / `privy_did` あり
- wallet/LINE ユーザー:     `hashed_password` あり (ランダム) / `privy_did` NULL
- 両方認証ユーザー（将来）: `hashed_password` あり / `privy_did` あり

---

## 3. Alembic Migration スクリプト（案）

> **注意:** このスクリプトは実装案です。実行は行いません。
> `backend/alembic/versions/` にはコミットしないこと。

```python
# backend/migrations_draft/f0a1b2c3d4e5_add_privy_did_nullable_hashed_password.py
"""Add privy_did to users and make hashed_password nullable

Revision ID: f0a1b2c3d4e5
Revises: e5f6a7b8c9d0
Create Date: 2026-05-03 00:00:00.000000

実行前提条件:
  - 全既存ユーザーが hashed_password IS NOT NULL であること (AS-IS 満たしている)
  - CHECK制約追加後、全行が通ること (既存行は hashed_password あり → 常に満たす)

実行タイミング:
  - Asana GID 1214176336328111 (2026-05-03予定)
  - バックエンドデプロイ前に手動 ALTER TABLE で先行適用も可
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "f0a1b2c3d4e5"
down_revision: Union[str, Sequence[str], None] = "e5f6a7b8c9d0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # (A) hashed_password を nullable に変更
    op.alter_column(
        "users",
        "hashed_password",
        existing_type=sa.String(length=255),
        nullable=True,
    )

    # (B) privy_did カラム追加
    op.add_column(
        "users",
        sa.Column("privy_did", sa.String(length=255), nullable=True),
    )

    # (B) privy_did にパーシャルユニークインデックス
    op.create_index(
        "ix_users_privy_did",
        "users",
        ["privy_did"],
        unique=True,
        postgresql_where=sa.text("privy_did IS NOT NULL"),
    )

    # (C) CHECK制約: どちらか一方は必須
    op.create_check_constraint(
        "chk_users_auth_method",
        "users",
        "hashed_password IS NOT NULL OR privy_did IS NOT NULL",
    )


def downgrade() -> None:
    # (C) CHECK制約削除
    op.drop_constraint("chk_users_auth_method", "users", type_="check")

    # (B) インデックス + カラム削除
    op.drop_index("ix_users_privy_did", table_name="users")
    op.drop_column("users", "privy_did")

    # (A) hashed_password を NOT NULL に戻す
    # 注意: privy_did のみのユーザーが存在する場合はロールバック不可
    op.alter_column(
        "users",
        "hashed_password",
        existing_type=sa.String(length=255),
        nullable=False,
    )
```

---

## 4. ロールバック手順

### 4a. Alembic ロールバック（privy_did ユーザーが存在しない場合のみ可能）

```bash
# Hetzner VPS 上で実行
docker exec ultra-autotrade-backend-production \
    alembic -c alembic.ini downgrade e5f6a7b8c9d0
```

**制約:** `hashed_password IS NULL` の行（privy_did のみユーザー）が存在する場合、
`hashed_password` を NOT NULL に戻す手順が失敗する。
その場合は以下の手動手順が必要:

```sql
-- privy_did ユーザーを削除またはランダムパスワードで埋める
UPDATE users
SET hashed_password = '<bcrypt_random_hash>'
WHERE hashed_password IS NULL;

-- その後 ALTER TABLE
ALTER TABLE users ALTER COLUMN hashed_password SET NOT NULL;
```

### 4b. 手動 SQL ロールバック

```sql
-- Step 1: CHECK制約削除
ALTER TABLE users DROP CONSTRAINT IF EXISTS chk_users_auth_method;

-- Step 2: インデックス削除
DROP INDEX IF EXISTS ix_users_privy_did;

-- Step 3: カラム削除
ALTER TABLE users DROP COLUMN IF EXISTS privy_did;

-- Step 4: NOT NULL 復元（privy_did のみユーザーがいない前提）
ALTER TABLE users ALTER COLUMN hashed_password SET NOT NULL;
```

---

## 5. ダウンタイム見積もり

### PostgreSQL の動作特性

| 操作                                  | ロック              | 予想時間（6ユーザー） |
|---------------------------------------|---------------------|----------------------|
| `ALTER COLUMN ... DROP NOT NULL`      | ACCESS EXCLUSIVE    | < 10ms（メタデータ変更のみ） |
| `ADD COLUMN ... NULL`                 | ACCESS EXCLUSIVE    | < 10ms（メタデータ変更のみ） |
| `CREATE UNIQUE INDEX ... WHERE NULL`  | SHARE UPDATE EXCLUSIVE | < 10ms（6行） |
| `ADD CONSTRAINT CHECK ...`            | ACCESS EXCLUSIVE    | < 50ms（全行スキャン、6行のみ） |

**合計予想ダウンタイム:** < 100ms（実質ゼロダウンタイム）

### 本番環境での注意

- PostgreSQL 16 の `ALTER COLUMN DROP NOT NULL` はテーブル書き換え不要（メタデータ変更）
- `ADD COLUMN NULL` もテーブル書き換え不要
- CHECK制約は全行スキャンが必要だが、6ユーザーは無視できる
- 操作はトランザクション内で実行するため、失敗時は自動ロールバック

### 将来スケール時の考慮（参考）

| ユーザー数 | ALTER COLUMN DROP NOT NULL | ADD CONSTRAINT CHECK |
|-----------|---------------------------|----------------------|
| 100       | < 10ms                    | < 100ms              |
| 10,000    | < 10ms                    | < 500ms              |
| 1,000,000 | < 10ms                    | 1-5秒                |

1,000,000ユーザーでも `ALTER COLUMN` 自体は瞬時。CHECK制約のみ時間がかかる。
現状6ユーザーでは問題なし。

---

## 6. 関連コードの修正影響範囲

### 6a. 必須修正（privy_did 新規エンドポイント実装時に同時修正が必要）

#### `backend/app/auth/models.py`（Userモデル）

```python
# 変更前 (L195)
hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)

# 変更後
hashed_password: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
privy_did: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, unique=True)
```

Docstringも更新:
- `hashed_password`: "bcrypt ハッシュ化されたパスワード（Privy認証ユーザーの場合は NULL）"
- `privy_did`: "Privy DID（email/passwordユーザーの場合は NULL）"

モデルファイル冒頭のALTER TABLE コメントも追加（Alembic未使用プロジェクト規則に従い）:
```python
# ALTER TABLE users ALTER COLUMN hashed_password DROP NOT NULL;
# ALTER TABLE users ADD COLUMN privy_did VARCHAR(255) NULL;
# CREATE UNIQUE INDEX ix_users_privy_did ON users(privy_did) WHERE privy_did IS NOT NULL;
# ALTER TABLE users ADD CONSTRAINT chk_users_auth_method
#     CHECK (hashed_password IS NOT NULL OR privy_did IS NOT NULL);
```

#### `backend/app/auth/service.py`

| メソッド          | 行   | 修正内容 |
|-------------------|------|----------|
| `authenticate_user` | L211 | `user.hashed_password` が None の場合の早期リターン追加 |
| `verify_password`   | L95  | 引数型を `str` → `Optional[str]` に変更し、None 時は False を返す |
| `create_user`       | L246-249 | Privy ユーザー用パスを追加（`privy_did` 指定時は `hashed_password` 不要） |
| `update_user`       | L300 | `hashed_password` がある場合のみ更新（現状は問題なし） |
| `create_wallet_user` | L394 | 変更不要（ランダムパスワードを引き続き使用） |

新規メソッドが必要:
```python
@classmethod
def get_user_by_privy_did(cls, db: Session, privy_did: str) -> Optional[User]:
    """Privy DID でユーザーを取得する。"""
    return db.query(User).filter(User.privy_did == privy_did).first()

@classmethod
def create_privy_user(cls, db: Session, privy_did: str, email: str, username: str) -> User:
    """Privy認証ユーザーを作成する（hashed_password なし）。"""
    ...

@classmethod
def link_privy_did(cls, db: Session, user: User, privy_did: str) -> User:
    """既存ユーザーに Privy DID を紐付ける。"""
    ...
```

#### `backend/app/auth/router.py`

| エンドポイント        | 行   | 修正内容 |
|-----------------------|------|----------|
| `POST /auth/change-password` | L229 | `user.hashed_password` が None の場合は 400 エラー（Privy ユーザーはパスワード変更不可） |

新規エンドポイントが必要（Asana GID 1214176336328111 の実装スコープ）:
- `POST /auth/privy-login` — Privy IDトークン検証 → JWTを返す
- `POST /auth/privy-link` — 既存ユーザーに Privy DID を紐付ける

#### `backend/app/auth/schemas.py`

- `UserResponse`: `privy_did: Optional[str]` フィールド追加（フロント表示不要なら除外も可）

### 6b. テスト影響範囲

#### `backend/tests/conftest.py`

```python
# 現状 (推定): User fixture が hashed_password に直接文字列を渡している場合は問題なし
# SQLAlchemy モデルの nullable=True 変更後も既存 fixture は動作する

# 影響箇所の確認コマンド:
# grep -n "hashed_password\|User(" backend/tests/conftest.py
```

実際の `conftest.py` に `hashed_password` の直接設定が存在しない（`AuthService.create_user()` 経由）ため、
モデル変更後も fixture は影響を受けない可能性が高い。要確認。

#### 認証系テスト

```
backend/tests/test_auth*.py  # ログイン・パスワード変更テスト
```

Privy 新規エンドポイントのテストを追加する必要がある:
- `test_privy_login_success`
- `test_privy_login_invalid_token`
- `test_privy_link_existing_user`
- `test_privy_user_cannot_change_password` (`hashed_password IS NULL` の場合)

### 6c. 変更不要（影響なし）

- `backend/app/automation/` — users テーブルを直接参照しない
- `backend/app/aave/` — 同上
- `backend/app/exchange/` — 同上
- `frontend/` — `privy_did` はフロントに返却しない（セキュリティ上）
- `backend/app/auth/line.py` — LINE 認証はランダムパスワード方式を継続使用

---

## 7. リスク評価

### 7a. 既存ユーザー（hashed_password あり）への影響

| リスク | 評価 | 対策 |
|--------|------|------|
| hashed_password NOT NULL → NULL で既存ログインが壊れる | **低**（NULL許容はデータ削除しない） | ALTER COLUMN DROP NOT NULL はメタデータ変更のみ |
| CHECK制約追加で既存行が失敗する | **なし**（全既存行が hashed_password IS NOT NULL） | 事前確認SQL実行 |
| wallet/LINE ユーザーへの影響 | **なし**（ランダムパスワードが設定済み） | 変更不要 |

**事前確認SQL（ALTER前に必ず実行）:**
```sql
-- hashed_password が NULL の既存ユーザーがいないことを確認
SELECT COUNT(*) FROM users WHERE hashed_password IS NULL;
-- → 0 であること

-- 全ユーザー数確認（本番6ユーザー想定）
SELECT COUNT(*) FROM users;
```

### 7b. Privy新規ユーザー（privy_did のみ）のCRUD整合性

| 操作 | 考慮事項 |
|------|----------|
| CREATE | `hashed_password=NULL, privy_did=<did>` → CHECK制約 OK |
| READ   | 変更なし |
| UPDATE（パスワード変更） | `hashed_password IS NULL` の場合は 400 を返す（変更不可） |
| DELETE | 変更なし |
| ログイン（email/password） | `authenticate_user` が `hashed_password IS NULL` を早期検出して None を返す |

### 7c. 移行完了後のロールバックリスク

privy_did のみユーザーが1人でも作成された後は、`hashed_password NOT NULL` へのロールバックは
データを削除しないと不可能。移行後は「前進のみ」と考える。

### 7d. インデックス効率

`privy_did` はパーシャルユニークインデックス (`WHERE privy_did IS NOT NULL`) を使用するため、
NULL 行（既存全ユーザー）はインデックスに含まれず、インデックスサイズが最小化される。

---

## 8. 実行チェックリスト（実施時の参照用）

```
□ (事前) docker ps | grep postgres でコンテナ名を確認
□ (事前) SELECT COUNT(*) FROM users WHERE hashed_password IS NULL; → 0 であること
□ (事前) SELECT COUNT(*) FROM users; → 現在の全ユーザー数を記録
□ (実施) ALTER TABLE users ALTER COLUMN hashed_password DROP NOT NULL;
□ (実施) ALTER TABLE users ADD COLUMN privy_did VARCHAR(255) NULL;
□ (実施) CREATE UNIQUE INDEX ... WHERE privy_did IS NOT NULL;
□ (実施) ALTER TABLE users ADD CONSTRAINT chk_users_auth_method ...;
□ (確認) \d users でスキーマ確認
□ (確認) SELECT COUNT(*) FROM users; → 同じ件数であること
□ (確認) 既存ユーザーでログイン動作確認
□ (完了) Asana GID 1214162094702307 を完了にマーク
```

---

## 9. 申し送り事項（Asana GID 1214176336328111 へ）

GID 1214176336328111「CHECK制約追加と実際のDB ALTER実施（2026-05-03）」担当者への申し送り:

1. **実行するSQL:** 本書の §3「Alembic Migration スクリプト（案）」の `upgrade()` 相当の4ステップ
2. **事前確認必須:** §8「実行チェックリスト」の事前チェック2項目を必ず実行すること
3. **コード修正は別スコープ:** DB ALTER 実施前に `backend/app/auth/models.py` の `hashed_password` の型を `Optional[str]` に変更してデプロイする必要がある（DB が nullable になる前にコード変更するとエラーにはならないが、逆順は問題）
4. **Privy エンドポイント実装との順序:**
   - DB ALTER → `models.py` 修正 → `service.py` に `get_user_by_privy_did` 等追加 → `POST /auth/privy-login` 実装
   - DB ALTER なしで Privy エンドポイントを実装しても INSERT 時に CHECK 制約違反でエラーになる
5. **ロールバック窓口:** Privy ユーザーが1人も作成されていない間のみロールバック可能

---

*本書は設計書のみ。実DB ALTER は Asana GID 1214176336328111 で実施。*
