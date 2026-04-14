# 41_kms_vault_design.md
# KMS/Vault 移行 + 秘密鍵ローテーション設計書

作成日: 2026-04-14
Asana: 1213880674055757 (KMS/Vault移行) / 1213877084585962 (ローテーション)
ブランチ: feature/kms-vault-design

---

## 1. 概要

### 1.1 現状の課題

Ultra AutoTrade の秘密情報管理は、現時点で以下の問題を抱えている。

| 課題 | 詳細 | リスク |
|------|------|--------|
| プレーンテキスト保存 | 全秘密情報が `.env.production` / `.env.staging` にプレーンテキストで保存 | ファイル漏洩 = 全秘密漏洩 |
| 暗号化なし | `encrypt` / `decrypt` / `Fernet` / `KMS` / `Vault` の参照がアプリコード内にゼロ | 保存時・転送時の暗号化保護なし |
| ローテーション機構なし | 鍵の更新は手動変更以外の方法がない | インシデント発生時の即時無効化不可 |
| 監査ログなし | 誰がいつ秘密にアクセスしたかの記録がない | 不正アクセスの検知・事後調査不可 |
| 最小権限の欠如 | 全コンテナが `.env.production` 経由で全環境変数を参照可能 | backend の脆弱性 = 全秘密の漏洩 |
| プライベートキーのメモリ展開 | `Account.from_key(settings.wallet_private_key)` (client.py:L379) で秘密鍵が Python オブジェクトとしてメモリ上に永続 | メモリダンプ攻撃・GC タイミングまで秘密鍵が残存 |

### 1.2 目標

1. **秘密情報の一元管理**: 全秘密情報を KMS/Vault で一元管理し、プレーンテキストの `.env` ファイルへの依存を解消
2. **自動ローテーション対応**: JWT シークレット・API キーの自動/半自動ローテーション
3. **監査ログ**: アクセス記録（誰が・いつ・どの秘密に・何の操作をしたか）
4. **最小権限**: サービスごとに必要な秘密のみアクセス可能なスコープ制限
5. **Aave 秘密鍵のメモリ非展開**: KMS 内でトランザクション署名を完結させ、秘密鍵を一切メモリに出さない

### 1.3 制約

- **インフラ**: Hetzner VPS（AWS/GCP マネージド KMS は API 経由での利用は可能だが、VPC Private Link 等の閉域接続は不可）
- **フェーズ**: BVI 法人設立前は商用 Vault ライセンス不要（OSS で対応可）
- **Phase 2 との整合性**: `docs/40_multi_wallet_design.md` の Phase 2 で `AAVE_WALLET_PRIVATE_KEY` 自体が廃止予定。KMS 移行は Phase C として Phase 2 と同期させる
- **コスト**: スタートアップフェーズのため最小コストを優先。Phase A はゼロコストで実現する

---

## 2. 秘密情報の分類と優先度

### Tier 1: 資金リスク（最優先・P0）

| 変数名 | 用途 | 漏洩時の影響 | 主な使用箇所 |
|--------|------|-------------|-------------|
| `AAVE_WALLET_PRIVATE_KEY` | Aave 操作 EOA 秘密鍵 | **全資金喪失** | `aave/config.py:L140`, `aave/client.py:L379` |
| `AAVE_PRIVATE_KEY_STAGING` | staging 用 EOA 秘密鍵 | テスト資金喪失 | `aave/config.py:L121`, `aave/config.py:L202` |

**重大リスク**: `Web3AaveClient.__init__()` (client.py:L379) で `Account.from_key(settings.wallet_private_key)` を呼び出し、秘密鍵が Python `LocalAccount` オブジェクトとして JVM heap に展開される。GC まで秘密鍵がメモリ上に残存する。

### Tier 2: 認証・アクセス制御（P1）

| 変数名 | 用途 | 漏洩時の影響 | 主な使用箇所 |
|--------|------|-------------|-------------|
| `JWT_SECRET_KEY` | JWT 署名鍵 | セッションハイジャック・全ユーザーの認証バイパス | `auth/service.py:L35` (`AuthService.SECRET_KEY`) |
| `INTERNAL_API_TOKEN` | スケジューラー内部 API 認証トークン | 不正 API 呼び出し・AI 判定の改ざん | `core/config.py` (Settings クラス) |
| `DATABASE_URL` | PostgreSQL 接続文字列（パスワード含む） | 全 DB データ漏洩 | `core/config.py`, `docker-compose.production.yml:L104` |
| `POSTGRES_PASSWORD` | DB 直接アクセスパスワード | DB データ漏洩 | `docker-compose.production.yml:L66` |

**現状の脆弱性**: `auth/service.py:L35` で `os.getenv("JWT_SECRET_KEY", "development-secret-key-change-in-production")` としており、フォールバック値が弱いデフォルトキー。`validate_secret_key()` (L55) で staging/production 環境での弱いキー使用を起動時に検証しているが、技術的な暗号化保護はない。

### Tier 3: 外部 API キー（P1）

| 変数名 | 用途 | 漏洩時の影響 | 主な使用箇所 |
|--------|------|-------------|-------------|
| `ANTHROPIC_API_KEY` | Claude API（AI 判定主力） | 課金被害・無制限 API 利用 | `ai/service.py` |
| `OPENAI_API_KEY` | GPT-4o（BUY/SELL クロス検証） | 課金被害 | `ai/service.py` |
| `PERPLEXITY_API_KEY` | マクロ経済データフィード | 課金被害 | `data_feeds/finance_feed.py:L81` (`os.getenv("PERPLEXITY_API_KEY")`) |
| `MMT_API_KEY` | mmt.gg マーケットデータ | 課金被害・データ停止 | `data_feeds/mmt_feed.py` (`os.getenv("MMT_API_KEY")`) |
| `BYBIT_API_KEY` / `BYBIT_API_SECRET` | Bybit 取引所認証 | 不正取引リスク | `exchange/client.py` |
| `OKX_API_KEY` / `OKX_API_SECRET` / `OKX_PASSPHRASE` | OKX バックアップ取引所 | 不正取引リスク | `exchange/client.py` |

### Tier 4: 通知・Webhook（P2）

| 変数名 | 用途 |
|--------|------|
| `SLACK_WEBHOOK_URL` | Slack 通知 Webhook |
| `LINE_CHANNEL_ACCESS_TOKEN` | LINE Messaging API トークン |
| `LINE_CHANNEL_SECRET` | LINE チャネルシークレット |
| `VAPID_PRIVATE_KEY` | Web Push 通知暗号化キー |

### Tier 5: フロントエンドビルド時（P2）

| 変数名 | 用途 |
|--------|------|
| `NEXT_PUBLIC_PRIVY_APP_ID` | Privy アプリ ID（公開値だが管理対象） |
| `NEXT_PUBLIC_WALLETCONNECT_PROJECT_ID` | WalletConnect プロジェクト ID |

> **注意**: `NEXT_PUBLIC_*` はビルド時 JS に埋め込まれるため、厳密には秘密ではない。ただし `docker-compose.production.yml:L146-L160` の `build.args` で管理されており、設定ミスがインシデントにつながるため一元管理対象に含める。

---

## 3. 推奨アーキテクチャ

### 3.1 KMS/Vault 候補の比較

| ソリューション | コスト (月) | Hetzner 対応 | 自動ローテーション | KMS 署名 | 複雑度 | 推奨フェーズ |
|---|---|---|---|---|---|---|
| **SOPS + age** (暗号化ファイル) | ¥0 | ✅ ネイティブ | ❌ 手動のみ | ❌ | 低 | Phase A |
| **Docker Secrets + tmpfs** | ¥0 | ✅ | ❌ | ❌ | 低 | Phase A |
| **HashiCorp Vault OSS** (self-hosted) | ¥0 (Hetzner サーバコストのみ) | ✅ | ✅ (Transit Secrets Engine) | △ (Transit で HMAC 署名可) | 高 | Phase B |
| **AWS Secrets Manager + KMS** | $0.40/secret/月 + KMS $1/key/月 | API 経由 | ✅ | ✅ (`sign_raw_hash()`) | 中 | Phase B/C |
| **Google Cloud Secret Manager + Cloud KMS** | 同等 | API 経由 | ✅ | ✅ | 中 | Phase B/C |
| **Infisical** (OSS/SaaS) | OSS: ¥0, SaaS: $18/月 | ✅ | ✅ | ❌ | 中 | Phase B 代替 |

**推奨**: 段階的移行（Phase A → B → C）。Hetzner VPS 単体でゼロコスト開始し、BVI 法人設立・資産規模拡大に応じて商用ソリューションへ移行。

### 3.2 推奨: 段階的移行戦略

```
Phase A（即時・コストゼロ）
  ├─ SOPS + age: .env.production を暗号化、復号キーは Hetzner 上のみ
  ├─ Docker Secrets + tmpfs: コンテナへの秘密情報注入をファイルベースに変更
  ├─ SecretProvider 抽象レイヤー導入 (secrets.py)
  └─ ログマスクの技術的強制実装（docs/13 ルール 5 の実装化）

Phase B（BVI 法人設立後 / 資産規模 $50K 超）
  ├─ HashiCorp Vault OSS を Hetzner に self-hosted
  ├─ Vault Agent Sidecar でコンテナへの秘密情報注入
  ├─ 自動ローテーション（JWT 90日、DB パスワード 180日）
  └─ Vault Audit Log による全アクセス記録

Phase C（Phase 2 マルチウォレット移行時: docs/40 参照）
  ├─ AWS KMS または Vault Transit Engine で Aave トランザクション署名
  ├─ AAVE_WALLET_PRIVATE_KEY 完全廃止（Privy MPC と同期）
  └─ KMSSigner 実装（秘密鍵がメモリに展開されない設計）
```

---

## 4. 抽象化レイヤー設計

### 4.1 `backend/app/utils/secrets.py`（新規ファイル）

```python
# backend/app/utils/secrets.py
"""
秘密情報取得の抽象インターフェース。

Phase A: EnvSecretProvider（既存の os.getenv() ラッパー）
Phase B: VaultSecretProvider（HashiCorp Vault API）
Phase B代替: AWSSecretProvider（AWS Secrets Manager）
"""
from abc import ABC, abstractmethod


class SecretProvider(ABC):
    """秘密情報取得の抽象インターフェース。"""

    @abstractmethod
    def get_secret(self, key: str) -> str:
        """
        指定されたキーの秘密情報を返す。
        秘密の値はログに出力しないこと。

        Raises:
            SecretNotFoundError: キーが存在しない場合
            SecretProviderError: プロバイダーの接続エラー
        """
        ...

    @abstractmethod
    def rotate_secret(self, key: str) -> str:
        """
        指定されたキーの秘密情報をローテーションし、新しい値を返す。

        Returns:
            新しい秘密情報の値
        """
        ...


class SecretNotFoundError(Exception):
    """秘密情報が見つからない場合の例外。"""


class SecretProviderError(Exception):
    """秘密情報プロバイダーのエラー。"""


class EnvSecretProvider(SecretProvider):
    """
    Phase A: 既存の環境変数ベース（フォールバック実装）。

    os.getenv() を SecretProvider インターフェース経由で呼び出す薄いラッパー。
    Phase B 移行時は VaultSecretProvider に差し替えるだけで既存コードは無変更。
    """

    def get_secret(self, key: str) -> str:
        import os
        value = os.getenv(key)
        if value is None:
            raise SecretNotFoundError(f"Secret not found: {key}")
        return value

    def rotate_secret(self, key: str) -> str:
        raise NotImplementedError(
            "EnvSecretProvider does not support rotation. "
            "Upgrade to VaultSecretProvider for Phase B."
        )


class VaultSecretProvider(SecretProvider):
    """
    Phase B: HashiCorp Vault KV Secrets Engine v2。

    Vault Agent Sidecar が /run/secrets/ に書き込んだトークンを使用。
    または VAULT_TOKEN 環境変数 + Vault API 直接呼び出し。
    """

    def __init__(self, vault_addr: str, token: str, mount_path: str = "secret") -> None:
        self._vault_addr = vault_addr
        self._token = token
        self._mount_path = mount_path

    def get_secret(self, key: str) -> str:
        # hvac ライブラリ経由で Vault API を呼び出す
        # import hvac
        # client = hvac.Client(url=self._vault_addr, token=self._token)
        # response = client.secrets.kv.v2.read_secret_version(path=key, mount_point=self._mount_path)
        # return response["data"]["data"]["value"]
        raise NotImplementedError("Implement in Phase B")

    def rotate_secret(self, key: str) -> str:
        # Vault Dynamic Secrets または手動ローテーション API を呼び出す
        raise NotImplementedError("Implement in Phase B")


class AWSSecretProvider(SecretProvider):
    """
    Phase B 代替: AWS Secrets Manager + KMS。

    boto3 ライブラリ経由で AWS API を呼び出す。
    Hetzner から AWS API エンドポイントへの HTTPS 通信が必要。
    """

    def __init__(self, region: str = "ap-northeast-1") -> None:
        self._region = region

    def get_secret(self, key: str) -> str:
        # import boto3
        # client = boto3.client("secretsmanager", region_name=self._region)
        # response = client.get_secret_value(SecretId=key)
        # return response["SecretString"]
        raise NotImplementedError("Implement in Phase B")

    def rotate_secret(self, key: str) -> str:
        # import boto3
        # client = boto3.client("secretsmanager", region_name=self._region)
        # client.rotate_secret(SecretId=key)
        raise NotImplementedError("Implement in Phase B")


def get_secret_provider() -> SecretProvider:
    """
    環境変数 SECRET_PROVIDER に基づいてプロバイダーを返す。

    SECRET_PROVIDER=env (default) → EnvSecretProvider
    SECRET_PROVIDER=vault         → VaultSecretProvider
    SECRET_PROVIDER=aws           → AWSSecretProvider
    """
    import os
    provider = os.getenv("SECRET_PROVIDER", "env").lower()
    if provider == "vault":
        return VaultSecretProvider(
            vault_addr=os.environ["VAULT_ADDR"],
            token=os.environ["VAULT_TOKEN"],
        )
    if provider == "aws":
        return AWSSecretProvider(region=os.getenv("AWS_REGION", "ap-northeast-1"))
    return EnvSecretProvider()
```

### 4.2 `backend/app/aave/signer.py`（新規ファイル）

```python
# backend/app/aave/signer.py
"""
トランザクション署名の抽象インターフェース。

Phase 1（現在）: LocalSigner — Account.from_key() を使う既存方式のラッパー
Phase C:         KMSSigner  — AWS KMS リモート署名（秘密鍵がメモリに出ない）
Phase 2:         PrivyRelaySigner — フロントエンド Privy 署名のリレー（docs/40 参照）
"""
from abc import ABC, abstractmethod
from typing import Any


class TransactionSigner(ABC):
    """トランザクション署名の抽象インターフェース。"""

    @property
    @abstractmethod
    def address(self) -> str:
        """署名に使用するウォレットアドレス（0x...）。"""
        ...

    @abstractmethod
    def sign_transaction(self, tx: dict[str, Any]) -> Any:
        """
        トランザクションに署名して署名済み tx を返す。

        Args:
            tx: web3.py 形式のトランザクション dict
                {"to": "0x...", "value": 0, "gas": 21000, ...}

        Returns:
            SignedTransaction オブジェクト（.rawTransaction が使用可能）
        """
        ...


class LocalSigner(TransactionSigner):
    """
    Phase 1: ローカル秘密鍵署名（現状方式のラッパー）。

    Web3AaveClient.__init__() (client.py:L379) で Account.from_key() した
    LocalAccount オブジェクトをラップして TransactionSigner インターフェースに適合させる。

    制約: 秘密鍵がメモリに展開されるため、Phase C で KMSSigner に置き換える。
    """

    def __init__(self, private_key: str) -> None:
        from eth_account import Account
        self._account = Account.from_key(private_key)

    @property
    def address(self) -> str:
        return self._account.address

    def sign_transaction(self, tx: dict[str, Any]) -> Any:
        return self._account.sign_transaction(tx)


class KMSSigner(TransactionSigner):
    """
    Phase C: AWS KMS リモート署名（秘密鍵がメモリに出ない設計）。

    AWS KMS の非対称キー（ECC_SECG_P256K1 = secp256k1）を使用し、
    sign_raw_hash() でトランザクションハッシュに署名する。

    秘密鍵は KMS の HSM 内に閉じ込められ、アプリコードからは一切参照不可。

    実装要件:
    - KMS キーは ECC_SECG_P256K1 アルゴリズムで作成
    - 公開鍵から Ethereum アドレスを導出
    - v, r, s の回復識別子 (recovery_id) を手動計算
    """

    def __init__(self, key_id: str, region: str = "ap-northeast-1") -> None:
        self._key_id = key_id
        self._region = region
        # 公開鍵から Ethereum アドレスを導出（起動時に1回だけ実行）
        self._address = self._derive_address()

    def _derive_address(self) -> str:
        # import boto3, eth_keys
        # kms = boto3.client("kms", region_name=self._region)
        # pub_key_der = kms.get_public_key(KeyId=self._key_id)["PublicKey"]
        # pub_key = eth_keys.keys.PublicKey.from_compressed_bytes(pub_key_der[-64:])
        # return pub_key.to_checksum_address()
        raise NotImplementedError("Implement in Phase C")

    @property
    def address(self) -> str:
        return self._address

    def sign_transaction(self, tx: dict[str, Any]) -> Any:
        # import boto3
        # kms = boto3.client("kms", region_name=self._region)
        # tx_hash = Web3.solidity_keccak(...)  # RLP エンコード + keccak256
        # resp = kms.sign(
        #     KeyId=self._key_id,
        #     Message=tx_hash,
        #     MessageType="DIGEST",
        #     SigningAlgorithm="ECDSA_SHA_256",
        # )
        # # DER → r, s の解析 + recovery_id の計算
        raise NotImplementedError("Implement in Phase C")


class PrivyRelaySigner(TransactionSigner):
    """
    Phase 2: フロントエンド Privy 署名のリレー（docs/40_multi_wallet_design.md）。

    バックエンドは unsigned tx を構築して返し、
    フロントエンドが Privy useWallets() で署名した結果を受け取って submit する。
    バックエンドは秘密鍵を一切保持しない。

    フロー:
      1. バックエンド: unsigned_tx = build_unsigned_tx(params)  → フロントへ返却
      2. フロントエンド: signed_tx = await wallet.signTransaction(unsigned_tx)
      3. フロントエンド: POST /api/aave/submit-tx  { signed_tx }
      4. バックエンド: w3.eth.send_raw_transaction(signed_tx)
    """

    @property
    def address(self) -> str:
        # フロントエンドから渡された wallet_address を使用
        raise NotImplementedError("Implement in Phase 2")

    def sign_transaction(self, tx: dict[str, Any]) -> Any:
        # PrivyRelaySigner はバックエンドでは署名しない
        # 署名はフロントエンド側で行われる
        raise NotImplementedError(
            "PrivyRelaySigner does not sign on the backend. "
            "Use build_unsigned_tx() and return to frontend."
        )
```

### 4.3 `aave/config.py` の移行計画

現状（`aave/config.py:L140-L141`）:
```python
wallet_private_key = get_env("AAVE_WALLET_PRIVATE_KEY", required=False)
```

Phase A（SecretProvider 経由に変更）:
```python
# backend/app/aave/config.py の get_aave_settings() 内
from app.utils.secrets import get_secret_provider, SecretNotFoundError

provider = get_secret_provider()
try:
    wallet_private_key = provider.get_secret("AAVE_WALLET_PRIVATE_KEY")
except SecretNotFoundError:
    wallet_private_key = None
```

Phase C（KMSSigner 導入後は wallet_private_key フィールド自体を削除）:
```python
# AaveSettings から wallet_private_key フィールドを削除
# Web3AaveClient.__init__() を KMSSigner を受け取る形に変更
# docs/40 Phase 2 の AAVE_WALLET_PRIVATE_KEY 廃止と同期
```

---

## 5. ローテーション設計

### 5.1 ローテーション対象と頻度

| 秘密情報 | ローテーション頻度 | 方式 | ダウンタイム | 備考 |
|---------|------------------|------|-------------|------|
| `JWT_SECRET_KEY` | 90 日 | 新旧並行検証（grace period 24h） | なし | セクション 5.2 参照 |
| `INTERNAL_API_TOKEN` | 90 日 | 即時切替 | スケジューラー再起動のみ | 影響範囲: `scheduled_tasks.py` |
| `ANTHROPIC_API_KEY` | プロバイダー推奨 | プロバイダーダッシュボードで再発行 → Vault 更新 | なし | 手動トリガー |
| `OPENAI_API_KEY` | 同上 | 同上 | なし | 手動トリガー |
| `BYBIT_API_KEY/SECRET` | 180 日 または 漏洩疑い時 | 手動（Bybit ダッシュボード） | なし | withdraw 権限は付与しないこと |
| `DATABASE_URL` (`POSTGRES_PASSWORD`) | 180 日 | psql でパスワード変更 → 全サービス再起動 | 数秒 (rolling restart) | セクション 5.3 参照 |
| `AAVE_WALLET_PRIVATE_KEY` | **ローテーション不可** | Phase 2 で Privy MPC に移行（docs/40）して廃止 | N/A | EOA 変更 = Aave ポジションの移行が必要 |
| `LINE_CHANNEL_ACCESS_TOKEN` | 30 日（LINE 仕様） | LINE Developers Console で再発行 | なし | 手動トリガー |

### 5.2 `JWT_SECRET_KEY` ローテーション（ゼロダウンタイム）

JWT のローテーションは「新旧キー並行検証」パターンで実装する。

**Phase A: 手動ローテーション手順**

```
1. 新しい JWT_SECRET_KEY を生成
   python -c "import secrets; print(secrets.token_urlsafe(64))"

2. .env.production に JWT_SECRET_KEY_OLD = <旧キー> を追加
   JWT_SECRET_KEY = <新キー> に更新

3. auth/service.py の verify_token() を以下のように変更:
   a. まず JWT_SECRET_KEY（新）で検証
   b. InvalidTokenError なら JWT_SECRET_KEY_OLD（旧）で検証
   c. create_access_token() では JWT_SECRET_KEY（新）のみ使用

4. バックエンドを rolling restart（ダウンタイムなし）

5. 24 時間の grace period 後に JWT_SECRET_KEY_OLD を削除
   → アクセストークンの有効期限は 24 時間（ACCESS_TOKEN_EXPIRE_MINUTES=1440）
     なので 24h 後には全既存トークンが新キーで発行済み

6. バックエンドを再度 rolling restart
```

**Phase B: Vault Dynamic Secrets によるゼロタッチローテーション**

```
1. Vault の Transit Secrets Engine でローテーション設定
2. vault.policy で ultra-backend に JWT_SECRET_KEY の read/rotate を許可
3. Vault Agent が .env に JWT_SECRET_KEY を定期書き込み
4. アプリ側: 環境変数変更を HUP シグナルで動的リロード（FastAPI lifespan イベント活用）
```

### 5.3 DB パスワードローテーション

```bash
# Step 1: PostgreSQL でパスワード変更
docker exec ultra-autotrade-postgres-production \
  psql -U ultra -c "ALTER USER ultra PASSWORD '<new_password>';"

# Step 2: .env.production の DATABASE_URL と POSTGRES_PASSWORD を更新
# （Vault を使用している場合は vault kv put で更新）

# Step 3: バックエンドを rolling restart（接続プールが新パスワードで再接続）
docker compose -f docker-compose.production.yml up -d --no-deps backend

# Step 4: ヘルスチェックで接続確認
curl -s https://api.ultra-auto-trade.com/health | jq '.database'
```

### 5.4 `rotate_secrets.py`（新規ファイル）

```python
# backend/scripts/rotate_secrets.py
"""
秘密情報ローテーション補助スクリプト。

Usage:
    # JWT_SECRET_KEY 新旧並行設定を dry-run 確認
    python -m scripts.rotate_secrets --target jwt --dry-run

    # 実行（新キーの生成と .env への書き込み）
    python -m scripts.rotate_secrets --target jwt --execute

    # DB パスワードローテーション
    python -m scripts.rotate_secrets --target db_password --dry-run
    python -m scripts.rotate_secrets --target db_password --execute

対応ターゲット:
    jwt         : JWT_SECRET_KEY の grace period 付きローテーション
    internal_api: INTERNAL_API_TOKEN の即時切替
    db_password : POSTGRES_PASSWORD の変更
"""
```

---

## 6. 監査ログ設計

### 6.1 ログポリシー

秘密情報アクセスイベントは以下の形式で記録する:

```json
{
  "timestamp": "2026-04-14T00:00:00Z",
  "event": "secret_access",
  "service": "ultra-backend",
  "secret_key_name": "JWT_SECRET_KEY",
  "action": "read",
  "caller": "auth.service.AuthService.create_access_token",
  "result": "success"
}
```

**禁止事項**（docs/13 ルール 5 に準拠）:
- ログに秘密の**値**を含めない（変数名のみ）
- ウォレットアドレスは先頭 6 文字 + 末尾 4 文字のみ（`0x1234...5678`）

### 6.2 Phase A の実装

`secrets.py` の `SecretProvider.get_secret()` を呼び出した際に、以下のログを出力する:

```python
logger.info(
    "Secret accessed: key=%s, caller=%s",
    key,  # 変数名のみ。値は絶対に記録しない
    caller_info,
)
```

### 6.3 Phase B: Vault 監査ログ

HashiCorp Vault の Audit Devices を有効化:

```bash
vault audit enable file file_path=/var/log/vault/audit.log
```

Vault 監査ログは全リクエスト（read/write/rotate）を HMAC 化して記録する。
秘密の値は HMAC で難読化されるため、ログから平文値は復元不可。

---

## 7. `docs/13_security_design.md` との整合性

| docs/13 ルール | 現状 | 本設計での対応 |
|---------------|------|--------------|
| 1.1 環境変数で管理 | ✅ 準拠（.env 経由） | Phase A: `SecretProvider` 経由に統一し、Docker Secrets / tmpfs に移行 |
| 1.2 本番/開発キーの分離 | ✅ ルールは存在（技術的強制なし） | Phase A: SOPS + age でファイル単位の暗号化、復号キーを環境分離 |
| 1.3 本番 .env は .gitignore | ✅ 準拠 | 変更なし |
| 2.2 HW Wallet 推奨 | ❌ 未実装 | Phase C: AWS KMS (HSM) = 物理 HW Wallet と同等のセキュリティ |
| 2.3 マルチシグ（任意） | ❌ 未実装 | Phase 2+: Gnosis Safe 検討（docs/40 と同期） |
| 3. 操作額制限 | ✅ 準拠（`AAVE_MAX_SINGLE_TRADE_USD` 等） | 変更なし |
| 5. ログサニタイズ | ⚠️ ルールのみ（技術的強制なし） | Phase A: `SecretProvider.get_secret()` でアクセスログを統一。値をログに出力しない実装を強制 |
| 9.2 Docker: env_file | ✅ 準拠（docker-compose.production.yml:L103） | Phase A: Docker Secrets + tmpfs に段階移行 |
| 9.2 Dockerfile に秘密を書かない | ✅ 準拠 | 変更なし |
| 10.3 インシデント時のローテーション | ⚠️ 手順はあるが手動 | Phase B: Vault でワンコマンドローテーション |

**docs/13 が未カバーの領域（本設計で新規追加）**:
- 秘密鍵のメモリ非展開（KMS リモート署名）
- 監査ログ（アクセス記録の技術的実装）
- 自動ローテーション（grace period 付き JWT ローテーション）
- 最小権限原則の技術的実装（サービスごとのスコープ制限）

---

## 8. 影響範囲マップ

### P0: プライベートキー直接使用（最優先）

| ファイル | 行番号 | 変更内容 |
|---------|-------|---------|
| `backend/app/aave/config.py` | L121, L140, L202 | `get_env("AAVE_WALLET_PRIVATE_KEY")` → `get_secret_provider().get_secret("AAVE_WALLET_PRIVATE_KEY")` |
| `backend/app/aave/client.py` | L326-L327 | `if not settings.wallet_private_key: raise` の条件を `TransactionSigner` の有無チェックに変更 |
| `backend/app/aave/client.py` | L379 | `Account.from_key(settings.wallet_private_key)` → `LocalSigner(settings.wallet_private_key)` でラップ（Phase A）、`KMSSigner(key_id)` に置き換え（Phase C） |
| `backend/app/aave/client.py` | L156, L184 | `deposit()` / `withdraw()` の `private_key: str` 引数を `signer: TransactionSigner` に変更（Phase C） |
| `backend/app/partner/allocation_service.py` | L175 | `os.getenv("AAVE_WALLET_ADDRESS", "")` → `get_secret_provider().get_secret("AAVE_WALLET_ADDRESS")` |

**新規作成ファイル**:
- `backend/app/utils/secrets.py` — `SecretProvider` 抽象レイヤー
- `backend/app/aave/signer.py` — `TransactionSigner` 抽象レイヤー
- `backend/scripts/rotate_secrets.py` — ローテーションスクリプト

### P1: 認証・API キー管理

| ファイル | 行番号 | 変更内容 |
|---------|-------|---------|
| `backend/app/auth/service.py` | L35-L38 | `SECRET_KEY = os.getenv("JWT_SECRET_KEY", ...)` → `SecretProvider.get_secret("JWT_SECRET_KEY")` に変更。クラス変数から `lifespan` イベントでの初期化に移行 |
| `backend/app/auth/service.py` | L55-L78 | `validate_secret_key()` は維持しつつ、ローテーション用に `SECRET_KEY_OLD` のフォールバック検証を追加 |
| `backend/app/data_feeds/finance_feed.py` | L81 | `os.getenv("PERPLEXITY_API_KEY")` → `get_secret_provider().get_secret("PERPLEXITY_API_KEY")` |
| `backend/app/data_feeds/mmt_feed.py` | (起動時 os.getenv 箇所) | 同上、`MMT_API_KEY` |

### P2: インフラ設定

| ファイル | 変更内容 |
|---------|---------|
| `docker-compose.production.yml` | `env_file: .env.production` を Docker Secrets + tmpfs 方式に段階移行（Phase B）。Phase A は `chmod 600 .env.production` と SOPS 暗号化のみ |
| `backend/.env.staging.example` | `SECRET_PROVIDER=env` を追加、SOPS 対応後の利用方法をコメントで記載 |

### P3: テスト基盤

| ファイル | 変更内容 |
|---------|---------|
| `backend/tests/` 全体 | `os.environ.setdefault("JWT_SECRET_KEY", "test-...")` パターンを `pytest.fixture` + `monkeypatch` で統一 |
| `backend/scripts/backfill_tester_user_id.py` | L21: `os.environ.setdefault("JWT_SECRET_KEY", "backfill-script-key")` → スクリプト専用の `EnvSecretProvider` 設定に変更 |

---

## 9. 移行手順（本番適用）

### Phase A: 即時対応（コストゼロ）

**SOPS + age セットアップ**

```bash
# 1. age キー生成（Hetzner サーバ上で実行）
age-keygen -o /etc/ultra-autotrade/age-key.txt
chmod 600 /etc/ultra-autotrade/age-key.txt

# 2. .env.production を SOPS で暗号化（ローカル Mac で実行）
sops --encrypt \
  --age <hetzner-public-key> \
  --encrypted-regex "^(AAVE_WALLET_PRIVATE_KEY|JWT_SECRET_KEY|INTERNAL_API_TOKEN|DATABASE_URL|.*PASSWORD|.*SECRET|.*KEY)$" \
  .env.production > .env.production.enc

# 3. Hetzner に .env.production.enc のみ配置（復号は Hetzner 上でのみ可能）
scp .env.production.enc ubuntu@hetzner:/opt/ultra-autotrade/
# ※ .env.production.enc は Git 管理可（暗号化済みのため）

# 4. デプロイ時に復号
ssh ubuntu@hetzner
cd /opt/ultra-autotrade
SOPS_AGE_KEY_FILE=/etc/ultra-autotrade/age-key.txt \
  sops --decrypt .env.production.enc > .env.production
```

**ファイル権限の強制**

```bash
chmod 600 /opt/ultra-autotrade/.env.production
chown ultra:ultra /opt/ultra-autotrade/.env.production
```

**テスト手順**

```bash
# 復号後の .env.production が正しく読み込まれることを確認
docker compose -f docker-compose.production.yml config | grep -v "KEY\|SECRET\|PASSWORD"
curl https://api.ultra-auto-trade.com/health | jq '.status'
```

**切替手順（ダウンタイムなし）**

```bash
# 既存の .env.production をバックアップ
cp .env.production .env.production.bak.$(date +%Y%m%d)

# SOPS 復号済みの .env.production をサービスに反映
docker compose -f docker-compose.production.yml up -d --no-deps backend
```

---

### Phase B: HashiCorp Vault 構築（BVI 法人設立後）

**Vault サーバ起動（Hetzner 上の Docker Compose に追加）**

```yaml
# docker-compose.production.yml への追加
vault:
  image: hashicorp/vault:1.16
  container_name: ultra-autotrade-vault-production
  environment:
    VAULT_DEV_ROOT_TOKEN_ID: ${VAULT_ROOT_TOKEN}  # 本番では Dev モードを使わない
  ports:
    - "127.0.0.1:8200:8200"
  volumes:
    - ./docker/vault/config.hcl:/vault/config/config.hcl:ro
    - vault-data-production:/vault/data
  command: vault server -config=/vault/config/config.hcl
  cap_add:
    - IPC_LOCK
  restart: always
```

**秘密情報の移行**

```bash
# 1. Vault 初期化
vault operator init
vault operator unseal  # 3 回（Shamir's Secret Sharing）

# 2. KV Secrets Engine v2 を有効化
vault secrets enable -path=ultra kv-v2

# 3. 秘密情報を Vault に書き込み
vault kv put ultra/production \
  JWT_SECRET_KEY=<value> \
  INTERNAL_API_TOKEN=<value>
  # ※ 値は標準入力から渡す（シェル履歴に残さない）

# 4. バックエンド用ポリシー
vault policy write ultra-backend - <<EOF
path "ultra/data/production" {
  capabilities = ["read"]
}
path "ultra/data/production/jwt" {
  capabilities = ["read", "update"]  # JWT ローテーション用
}
EOF

# 5. AppRole 認証（Docker コンテナ用）
vault auth enable approle
vault write auth/approle/role/ultra-backend \
  secret_id_ttl=24h \
  token_policies=ultra-backend
```

**Vault Agent Sidecar 設定**

```bash
# docker-compose.production.yml の backend サービスに Vault Agent を追加
# Agent が .env.production を /run/secrets/ 配下に動的に書き込む
```

**テスト・切替手順**

```bash
# 1. SECRET_PROVIDER=vault を .env.production に追加
# 2. VAULT_ADDR=http://vault:8200 を追加
# 3. バックエンド rolling restart
# 4. /health でシークレット取得が成功しているか確認
# 5. 旧 .env.production の秘密情報エントリを削除（SOPS で更新）
```

---

### Phase C: KMS リモート署名（Phase 2 と同期）

**前提条件**

- `docs/40_multi_wallet_design.md` の Phase 2 実装完了
- BVI 法人の AWS アカウント取得
- Aave ポジションが新ウォレット（Privy MPC）に移行完了

**AWS KMS キー作成**

```bash
# ECC_SECG_P256K1 (secp256k1) キーを作成
aws kms create-key \
  --key-usage SIGN_VERIFY \
  --key-spec ECC_SECG_P256K1 \
  --description "ultra-autotrade-aave-signer"

# 公開鍵から Ethereum アドレスを導出
aws kms get-public-key --key-id <key-id> --output text --query PublicKey | \
  python -c "..."  # DER → 非圧縮公開鍵 → keccak256 → Ethereum アドレス
```

**実装手順**

```
1. KMSSigner を backend/app/aave/signer.py に実装
2. AaveSettings から wallet_private_key フィールドを削除
3. Web3AaveClient.__init__() を KMSSigner / LocalSigner を受け取る形に変更
4. deposit() / withdraw() の private_key: str 引数を TransactionSigner に変更
5. テスト: Sepolia testnet で KMS 署名トランザクションの動作確認
6. 本番: Aave ポジションを新ウォレットに移行後、AAVE_WALLET_PRIVATE_KEY を Vault から削除
```

---

## 10. 付録: 実装チェックリスト

### Phase A チェックリスト（コード変更前に確認）

- [ ] `backend/app/utils/secrets.py` に `SecretProvider` / `EnvSecretProvider` を実装
- [ ] `backend/app/aave/signer.py` に `TransactionSigner` / `LocalSigner` を実装
- [ ] `backend/app/aave/config.py:L140` を `SecretProvider.get_secret()` に変更
- [ ] `backend/app/auth/service.py:L35` を `SecretProvider.get_secret()` に変更
- [ ] Hetzner 上で `chmod 600 .env.production` を確認
- [ ] SOPS + age の暗号化・復号フローをテスト環境で動作確認
- [ ] `scripts/rotate_secrets.py --target jwt --dry-run` の動作確認
- [ ] `ruff check . && mypy app/ && pytest --cov-fail-under=80` 全通過

### Phase B チェックリスト

- [ ] HashiCorp Vault OSS が Hetzner 上で起動・初期化済み
- [ ] 全 Tier 1-3 の秘密情報が Vault に移行済み
- [ ] Vault Audit Log が有効化済み
- [ ] `SECRET_PROVIDER=vault` でバックエンドが正常起動することを確認
- [ ] JWT ローテーション（grace period 24h）のエンドツーエンド動作確認

### Phase C チェックリスト

- [ ] `docs/40_multi_wallet_design.md` Phase 2 実装完了
- [ ] AWS KMS ECC_SECG_P256K1 キー作成済み
- [ ] `KMSSigner.sign_transaction()` の Sepolia テストネット動作確認
- [ ] `AAVE_WALLET_PRIVATE_KEY` を Vault から削除
- [ ] `AaveSettings.wallet_private_key` フィールド削除
- [ ] `client.py:L379` の `Account.from_key()` 呼び出し削除
