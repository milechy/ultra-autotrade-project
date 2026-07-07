# 13_security_design.md
Ultra AutoTrade – セキュリティ設計書（完全版）

本ドキュメントは、AI 判定 → Bybit 取引 / Aave 自動運用システムにおいて
「資金を失わない」「外部鍵・ウォレットへの不正アクセスを防ぐ」ことを目的に作成する。

関連ドキュメント:
- `docs/07_aave_operation_logic.md` — Aave 運用ロジック・リスク制限値
- `docs/17_staging_environment_config.md` — Staging 環境設定
- `docs/21_production_environment_config.md` — Production 環境設定
- `docs/22_production_release_checklist.md` — リリース前チェックリスト
- `docs/33_emergency_stop_governance.md` — 緊急停止ガバナンス

---

# 1. APIキー・秘密情報管理

## 1.1 APIキーの保存場所

- すべて **環境変数** で管理する
- `.env.*` ファイルを使用する場合は必ず `.gitignore` に追加
- GitHub に push される形で保存してはならない
- ログ・APM ツールへの API キー出力は禁止（マスキング必須）

## 1.2 本番／開発キーの分離

```
AAVE_PRIVATE_KEY_PROD   ← .env.production にのみ定義
AAVE_PRIVATE_KEY_DEV    ← .env.staging または .env.local
```

- 本番用キー・秘密情報は `.env.production` にのみ定義する
- `.env.staging` と `.env.production` の中身を `sed` で一括コピーしない
  （2026-04-18 インシデント: 一括書き換えで両ファイルが同一内容になった）
- 特に API キー・ウォレット秘密鍵は環境ごとに **物理的に異なるもの** を用意する
- 各環境の設定詳細は `docs/17_staging_environment_config.md` / `docs/21_production_environment_config.md` を参照

### BVI 法人設立・HSM 移行（将来対応）

現状は `chmod 600` + Hetzner VPS 上の `.env.production` による管理。
将来は BVI 法人設立後に HashiCorp Vault または AWS KMS への移行を検討する。
詳細: `docs/41_kms_vault_design.md`

## 1.3 Aave 関連環境変数

| 変数名 | 説明 | デフォルト値 |
|-------|------|------------|
| `AAVE_NETWORK` | 接続ネットワーク | `base_sepolia` (Phase 1) |
| `AAVE_RPC_URL` | メイン RPC エンドポイント | (必須) |
| `AAVE_DEFAULT_ASSET_SYMBOL` | デフォルト運用資産 | `USDC` |
| `AAVE_MAX_SINGLE_TRADE_USD` | 1回の最大取引上限(USD) | `100.0` |
| `AAVE_MIN_HEALTH_FACTOR` | HF 下限（HARD_STOP 閾値） | `1.6` |
| `AAVE_TRADE_COOLDOWN_SECONDS` | 操作間最小クールダウン | `600`（10分） |

- 未設定時は `backend/app/aave/config.py` の安全なデフォルト値が適用される
- カスタムリミッター（F-17a）が有効な場合、`AAVE_MIN_HEALTH_FACTOR` より低い値が
  適用されることがある（ただし絶対ハードリミット 1.2 が下限）。詳細は 3.2 節を参照

## 1.4 Phase 1 期間中の意図的な .env 乖離（2026-09-30 まで）

本番コンテナは現在以下の値で稼働中:

```
APP_ENV=staging
BYBIT_SANDBOX=true
AAVE_NETWORK=base_sepolia
```

これは **意図的な設定** である。山本さんパートナーテスト（$4,600 相当）が
Base Sepolia + Bybit Sandbox で行われており、実資金リスクなしに本番フローを
検証するための Phase 1 運用方針。

- Phase 2（メインネット本格移行）移行後に `AAVE_NETWORK=base` および
  `BYBIT_SANDBOX=false` へ切り替える
- 切り替え時には `scripts/check_env_separation.sh` で検証後デプロイすること
- CI の `.github/workflows/env-separation-check.yml` が `.env.staging` と
  `.env.production` の意味的差分を自動検証する

---

# 2. 秘密鍵・ウォレット保護

## 2.1 Aave 運用ウォレット原則

- Aave 運用に使用する秘密鍵は **最低限の金額のみ保持した専用ウォレット** に限定する
- 運用額に応じてウォレットを分割（資産集中を避ける）
- 秘密鍵は UAT 運営側がコード・ログに書かない設計原則を維持する

## 2.2 ハードウェアウォレット

本番環境では可能であれば Ledger などの HW Wallet を使用する。

## 2.3 マルチシグ設定（将来対応）

Gnosis Safe を利用し、大きなアクションは multi-sig 承認を要件とする（Phase 3 以降）。

## 2.4 Privy / MetaMask ウォレット方式

UAT ユーザー向けのウォレット接続は以下の2方式を採用する:

### Privy (MPC ウォレット)

- `@privy-io/react-auth` による非カストディアル型 MPC ウォレット
- ユーザーが秘密鍵を直接管理しない。UAT 運営も秘密鍵を保持しない設計
- フロントエンド: `frontend/lib/wallet/PrivyRootProvider.tsx` → SSR 無効で読み込み
- ウォレット接続後、`wallet_address` を users テーブルに保存
  （形式: `wallet_{address_slug}@wallet.local`）
- デフォルトチェーン: `NEXT_PUBLIC_DEFAULT_CHAIN_ID`（staging: Base Sepolia = 84532）
- 法的分類は森先生レビュー中（非カストディアル扱いの前提で設計）

### MetaMask / EOA ウォレット

- `useWallets()` フックで外部ウォレット署名を取得
- `POST /api/auth/wallet` でサーバーサイド署名検証（ECDSA recover）
- `backend/app/auth/service.py:verify_wallet_signature()` で実装
- 本番 Base Mainnet 接続時は Cloudflare Tunnel 経由のみ許可

## 2.5 operator fee wallet の Privy Server Wallet 化（2026-07-07）

手数料徴収用 operator wallet の署名方式を、**生の秘密鍵を env に置く旧式**から
**Privy Server Wallet（TEE 内署名）** に置換可能にした（`FEE_SIGNING_MODE` で切替）。

| モード | 秘密鍵の所在 | 署名 | env に残る秘密 |
|---|---|---|---|
| `raw_key`（既定・後方互換） | `.env` の `OPERATOR_FEE_WALLET_KEY`（生鍵） | `w3.eth.account.sign_transaction`（ローカル） | ブロックチェーン秘密鍵そのもの |
| `privy` | Privy TEE（2-of-2 分割・署名時のみ再構成・即破棄） | `PrivyRestClient.send_transaction`（`eth_sendTransaction`） | P-256 authorization 鍵のみ（=ブロックチェーン鍵ではない） |

- **設計原則（2.1 節）との整合**: `privy` モードでは「秘密鍵をコード・env・ログに書かない」を
  完全に満たす。env に残る P-256 authorization 鍵は「Privy に対してこの操作を承認する」鍵であり、
  Privy policy（`build_operator_fee_policy`: aToken 宛の `eth_sendTransaction` のみ ALLOW）の
  外は動かせない。漏洩しても生鍵のように全資産を持ち出せない。
- **二重ガード**: Privy policy（TEE・宛先 allowlist）+ backend（`_execute_transfer` の allowance
  チェック + transferFrom 宛先を operator address に固定）。calldata 動的参照は Privy 未サポートの
  ため、transferFrom の引数制約は backend 側で enforce する。
- **実装**: `backend/app/fees/fee_transfer_service.py`（`FEE_SIGNING_MODE` / `_submit_transferfrom_privy`）、
  `backend/app/privy/rest_client.py`（`send_transaction` / `create_wallet`）、
  `backend/app/privy/policy_mapper.py`（`build_operator_fee_policy`）。
- **セットアップ**: `backend/scripts/setup_operator_fee_privy_wallet.py`（policy + server wallet 作成、
  既定 dry-run）。key quorum(L0) は委譲経路と共用（`privy_register_key_quorum.py`）。
- **移行手順**: ①L0 登録 → ②setup スクリプトで policy+wallet 作成 → ③新 operator address へ
  ユーザー allowance 再承認 → ④`FEE_SIGNING_MODE=privy` + `OPERATOR_FEE_PRIVY_WALLET_ID` 設定 →
  ⑤staging-v4 で小額 transferFrom 検証 → ⑥検証後に旧 `OPERATOR_FEE_WALLET_KEY`（生鍵）を env から削除。
- **安全弁**: `FEE_TRANSFER_ENABLED=false` の間はモードに関わらず一切送金しない（DB 記録のみ）。
  本番の有効化は別途人間判断（実資金移動）。

---

# 3. 操作額制限（スマートコントラクト保護）

## 3.1 標準リミッター（default / strict モード）

```
・1回の最大投資額: 総資産の 10% 以内
・1日の最大投資額: 総資産の 30% 以内
・Aave 操作クールダウン: 10 分（600秒）
・HF 下限: 1.6（HARD_STOP）/ 1.8（SAFE_MODE 遷移）
```

実装:
- 単回 10% チェック: `backend/app/aave/rebalance_service.py:447`
- HF チェック: `backend/app/aave/config.py:107`, `rebalance_service.py:620`
- クールダウン: `backend/app/aave/service.py:88`, `rebalance_config.py:151`

## 3.2 カスタムリミッター（F-17a / CUSTOM_LIMITER）

山本さんパートナーテスト（最大 $4,600）対応として、環境変数ベースで
標準リミッターを緩和する仕組みを実装している。

```
CUSTOM_LIMITER_ENABLED=true           # 有効化フラグ
CUSTOM_LIMITER_EXPIRES_ON=2026-05-15  # 自動失効日（YYYY-MM-DD）
CUSTOM_HF_MIN=1.3                     # カスタム HF 下限
CUSTOM_SINGLE_TRADE_PCT=20            # 単回上限 (% of total assets)
CUSTOM_DAILY_TRADE_PCT=60             # 日次上限 (% of total assets)
CUSTOM_COOLDOWN_SECONDS=120           # クールダウン秒数
```

### ハードリミット（絶対値 — コード側で強制、env で上書き不可）

| 項目 | ハードリミット |
|------|-------------|
| HF 最小値 | **1.2** 以上 |
| 単回最大 | **40%** 以下 |
| 日次最大 | **90%** 以下 |
| クールダウン最小 | **60 秒** 以上 |

実装: `backend/app/aave/risk_limiter.py`（`get_effective_limits()` 関数）

### 動作フロー

1. `CUSTOM_LIMITER_ENABLED` が `true/1/yes` でない → strict デフォルトを使用
2. `CUSTOM_LIMITER_EXPIRES_ON` が過去の日付 → strict デフォルトに自動復帰（ログ警告）
3. 有効な場合 → カスタム値をハードリミットでクランプして適用
4. 起動時に Slack へ `:warning:` 通知（`notify_slack_if_custom()`）

### 現在の状態（2026-04-19 時点）

- F-17a は `.env.production` に未設定（無効）
- 山本さんテスト用の有効化は Phase 1 テスト計画に従って判断
- 後継: F-17b で管理画面 UI + 監査ログを実装予定

---

# 4. 通信暗号化ポリシー

- すべて HTTPS / TLS（Cloudflare Tunnel 経由）
- API 通信ログには資格情報を含めない
- Hetzner VPS への接続は SSH 公開鍵認証 + Cloudflare Tunnel 経由のみ許可
  - パスワードログインは禁止
  - 不要なポートは開放しない（8000/3000 はローカルバインドまたは Tunnel 経由）
- フロントエンド → バックエンド通信は同じ Cloudflare Tunnel ドメイン内で完結
  （Mixed Content を避けるため HTTP 直 IP アクセスは禁止）

---

# 5. ログのサニタイズ（匿名化）

ログに以下を出力してはならない:

- APIキー・シークレット
- 秘密鍵（private key）
- JWT トークン全体（先頭12文字 + "..." でよい）
- Privy 認証トークン（同上）
- 生のウォレットアドレス → 先頭6文字 + 末尾4文字（例: `0x5a39...eb20`）

実装例（`backend/app/auth/service.py:404`）:

```python
logger.info("Created wallet user: %s (wallet=%s...)", user.email, wallet_address[:10])
```

---

# 6. セキュリティ自動化

- エラー多発時に自動停止（circuit_closed フラグ）
- AI 判定が異常値連続（例: BUY/SELL が 5 回連続） → SAFE_MODE 遷移
- Aave HF < `AAVE_MIN_HEALTH_FACTOR`（デフォルト 1.6、カスタムリミッター有効時は最低 1.2） → HARD_STOP 自動発動

## 6.1 ヘルスファクター監視

`MonitoringService.record_health_factor()` が定期的に HF を取得し:

```
HF >= 1.8          → NORMAL（通常運用）
1.6 <= HF < 1.8    → SAFE_MODE（取引量抑制）
HF < 1.6           → HARD_STOP（全操作停止 + Slack 通知）
```

実装: `backend/app/automation/monitoring_service.py:193`

## 6.2 OR ロジック緊急停止（docs/33 と整合）

`emergency_stop` フラグは **OR 条件** で管理される:

- 一度 `True` になったら、明示的な `clear_emergency_stop()` 呼び出しまで `False` に戻らない
- HF 回復のみでは自動解除されない（オペレーターの意図的な操作が必要）
- 再起動時も `state.json` から `emergency_stop=True` を復元する（意図的な停止を引き継ぐ）

実装: `backend/app/automation/monitoring_service.py:239-244`

詳細ガバナンス: `docs/33_emergency_stop_governance.md`

---

# 7. 緊急停止トリガー条件

以下のいずれかで HARD_STOP が発動する:

```
・Aave HF < 1.6（または CUSTOM_HF_MIN を下回った場合）
・AI API エラー率 > 20%
・Aave RPC 応答なし 3回連続
・Aave Gas エラー 2回連続
・価格変動 > 20% / 1日（StressController）
```

発動後:
- 全 Aave 操作を停止
- LINE / Slack へ通知
- `state.json` に `emergency_stop=True` を記録（再起動後も維持）

手動解除: `POST /api/automation/emergency-stop` (ADMIN ロールのみ resume 可能)

---

# 8. バージョン管理のセキュリティ

- GitHub Personal Access Token は Fine-Grained トークン推奨（classic 禁止）
- SSH 認証必須
- `main` ブランチへの直接 push は禁止（PR + レビュー必須）
- `.env.*` ファイルはすべて `.gitignore` に含める
- PR #90 以降: CI の `env-separation-check.yml` が `.env.staging` vs `.env.production` の
  意図的乖離を自動検証する（`scripts/check_env_separation.sh`）

---

# 9. インフラデプロイ時の秘密情報管理

## 9.1 環境ごとの .env 方針

| ファイル | 使用環境 | 配置場所 |
|---------|---------|---------|
| `.env.production` | 本番（port 3000/8000） | Hetzner VPS `/opt/ultra-autotrade/` |
| `.env.staging` | 公開 staging（旧 production） | 同上 |
| `.env.staging-new` | True Staging / Shadow Mode | 同上 |
| `.env.local` | ローカル開発 | 開発マシンのみ |

- ファイル権限: `chmod 600`、所有ユーザー: `ultra`
- **`sed -i` による両ファイル一括更新は禁止**（2026-04-18 インシデント教訓）
- 正しい更新手順:
  1. `.env.staging` を先に編集
  2. `.env.production` を別コマンドで編集（値が本番固有なら差別化）
  3. `bash scripts/check_env_separation.sh` で検証
  4. コミット

## 9.2 Docker 運用時の秘密情報

- `docker-compose.production.yml` から `env_file: .env.production` として読み込む
- Dockerfile に API キー・秘密情報を**絶対に書かない**（`env_file` / `environment` 経由のみ）
- コンテナログに API キー・トークンを出さない（マスキング徹底）
- `NEXT_PUBLIC_*` 変数はビルド時に JS バンドルへ焼き込まれるため、変更時はフロントエンド再ビルドが必須

## 9.3 デプロイ実行環境

- **Hetzner VPS 上でのみ** `scripts/deploy_production.sh` を実行する
- ローカル Mac からの直接デプロイ禁止
- Hetzner 上で直接 `git commit` / `git merge` / `nano` 編集は禁止
  （正規フロー: ローカル Mac → GitHub push → Hetzner `git pull origin main`）

## 9.4 デプロイユーザと権限管理

- アプリケーション専用ユーザー `ultra` のみプロジェクトディレクトリに書き込み可能
- SSH ログインは公開鍵認証のみ、パスワードログイン禁止
- `sudo` 権限は最小限

## 9.5 ログと秘密情報の取り扱い

- API レスポンス・リクエストをログに記録する場合、アクセストークン・ウォレットアドレスをマスクまたは削除
- ログは Loki（`ultra-autotrade-loki-staging`）に集約
- ログローテーション設定済み（長期間の生ログ保持を防止）

## 9.6 環境ごとの接続先分離

| 変数 | Staging (port 8001) | 本番相当 (port 8000) |
|-----|---------------------|---------------------|
| `AAVE_NETWORK` | `base-sepolia` | `base_sepolia`（Phase 1 期間中） |
| `BYBIT_SANDBOX` | `true` | `true`（Phase 1 期間中） |
| `APP_ENV` | `staging` | `staging`（Phase 1 期間中） |
| `AI_SHADOW_MODE` | `true` | `false` |
| `REBALANCE_SHADOW_MODE` | `true` | `false` |

Phase 2 以降: `AAVE_NETWORK=base`, `BYBIT_SANDBOX=false`, `APP_ENV=production` に切り替え

---

# 10. バックアップ・リストア時のセキュリティ方針

## 10.1 バックアップの方針

- `.env.production` を含む設定ファイルは以下の条件を満たす場合にのみバックアップする:
  - 暗号化されたストレージに保存
  - バックアップファイル自体も Git / 共有ストレージに無防備に置かない
  - アクセス権を最小限の運用メンバーに限定
- バックアップ対象: `.env.production`、デプロイスクリプト、docker-compose ファイル、運用ランブック
- バックアップ作成時は作成日時・作成者・対象環境を記録する
- Hetzner 上の `.env.production.bak.*` ファイルは5世代まで自動保存（`deploy_production.sh` が管理）

## 10.2 リストア時のチェック

- バックアップから `.env.production` を復元する際は以下を確認:
  - 復元対象が正しい環境（production）向けのファイルであること
  - staging 用のキー・ウォレット情報が混入していないこと
  - 期限切れのキーが含まれていないこと
- 復元後に必ず実施:
  - `docs/21_production_environment_config.md` 記載の必須項目が埋まっている
  - `docs/22_production_release_checklist.md` の「前提条件チェック」を満たす

## 10.3 インシデント時のキー・秘密情報の扱い

- `.env.production` の内容が漏えいした疑いがある場合:
  - 直ちに該当する API キー・秘密鍵をローテーションする
  - Aave / Bybit / Privy 側で古いキーの無効化を行う
  - ログ・監査情報を確認し、不正アクセスや不正トレードがないかを調査する
  - 詳細手順: `docs/19_operations_runbook.md` のインシデント対応セクション

---

# 11. パートナー管理画面の権限分離（方式 B）

## 11.1 ロール設計

| ロール | 権限 | 代表ユーザー |
|-------|------|------------|
| `admin` | 全操作（緊急停止解除含む） | 運営チーム |
| `partner` | 資金配分操作、緊急停止発動、proposal 承認 | 山本さん (id=11) |
| `editor` | 管理画面編集（テスト用途） | partner@ultra-autotrade.com |
| `viewer` | 閲覧のみ（Privy ウォレット自動登録） | テスターユーザー |

## 11.2 パートナーテスト運用（方式 B）

- 山本さん1アカウント (`partner` ロール) が配下テスターの資金を一元管理
- `fund_allocations` テーブルで `partner_id` と `tester_user_id` / `tester_name` を紐付け
- テスターは `viewer` ロールで閲覧のみ（資金操作不可）
- 招待コードベース登録フロー（`invitations` テーブル）

## 11.3 緊急停止権限の非対称性

- `partner` ロール: 緊急停止の**発動のみ**可能
- 緊急停止の**解除（resume）は `admin` ロールのみ**
- 詳細: `docs/33_emergency_stop_governance.md:2`

---

最終更新: 2026-04-19
主要変更:
- OctoBot 依存の全記述を削除（アーキテクチャは Knowledge Hub → AI → Bybit/Aave に）
- Privy / MetaMask ウォレット方式（2.4 節）を追加
- F-17a カスタムリミッター（3.2 節）を追加（ハードリミット明記）
- OR ロジック緊急停止（6.2 節）を追加（docs/33 整合）
- Phase 1 期間中の意図的 .env 乖離（1.4 節）を追加
- パートナー管理画面の権限分離 方式 B（11 節）を追加
