# Base Mainnet 切替手順書

> 最終更新: 2026-04-25
> Base Sepolia (現状) → Base Mainnet (切替後) の本番デプロイ手順
> 想定読み手: 小林 (実行者)、山本さん (確認者)
> 関連: docs/22_production_release_checklist.md, docs/30_rpc_plan_requirements.md, docs/15_rollback_procedures.md

---

## 0. 前提条件

以下がすべて満たされた状態で本手順書を実行すること。未完了の項目があれば切替を延期する。

- [ ] 法人設立完了 (BVI)
- [ ] 森先生レビュー完了 (Privy MPC 非カストディアル分類)
- [ ] Phase 1 例外期限 (2026-09-30) 到来前 or 法的承認取得後
- [ ] Alchemy Base Mainnet API キー取得済み
- [ ] Infura Base Mainnet API キー取得済み (フェイルオーバー用)
- [ ] 本番ウォレット (Base Mainnet 用) 作成済み — Sepolia 用と物理的に別アドレス・別秘密鍵
- [ ] 本番ウォレットへの初期 USDC 入金完了 (山本さん 10 万円相当)

---

## 1. 切替前チェックリスト

```
[ ] Phase 1 例外解除タスク (Asana GID 1214121075911255) 完了
[ ] AI 判定が直近 24h で BUY/SELL を出している (proposals 起票実績あり)
[ ] 山本さんへの事前周知完了 (24h 前 — §6 テンプレ参照)
[ ] .env.production バックアップ取得
[ ] 本番 DB バックアップ取得 (docs/31_backup_restore_procedures.md §2 参照)
[ ] ロールバック手順書 (docs/15) 最新化済み
[ ] 本番ウォレット残高確認: USDC > 初期投入額の 90%
```

---

## 2. 切替対象一覧

### 2.1 環境変数 (.env.production)

| 変数 | 切替前 (Sepolia) | 切替後 (Mainnet) | 備考 |
|---|---|---|---|
| `APP_ENV` | `staging` (Phase 1 例外) | `production` | 例外解除と同時 |
| `AAVE_NETWORK` | `base_sepolia` | `base` | config.py legacy フィールド |
| `AAVE_ACTIVE_CHAINS` | `base_sepolia` | `base` | chains.py 経由でチェーン設定解決 |
| `ALCHEMY_RPC_URL_BASE_SEPOLIA` | `https://base-sepolia.g.alchemy.com/v2/...` | (削除 or コメントアウト) | Sepolia 専用、Mainnet では不使用 |
| `AAVE_RPC_URL_BASE` | (未設定) | `https://base-mainnet.g.alchemy.com/v2/{KEY}` | chains.py `"base"` エントリが読む変数 |
| `AAVE_RPC_URL` | Sepolia URL | Base Mainnet URL (Alchemy) | legacy 単チェーンモード用フォールバック |
| `AAVE_RPC_URL_SECONDARY` | (なし) | Base Mainnet URL (Infura) | `RPCProvider` のセカンダリ |
| `AAVE_POOL_ADDRESS` | `0x8bAB6d1b75f19e9eD9fCe8b9BD338844fF79aE27` | `0xA238Dd80C259a72e81d7e4664a9801593F98d1c5` | chains.py `base` 定義と一致 |
| `AAVE_WALLET_PRIVATE_KEY` | Sepolia ウォレット秘密鍵 | Mainnet ウォレット秘密鍵 (新規) | 物理的に別鍵 — 絶対に使い回さない |
| `AAVE_WALLET_ADDRESS` | Sepolia アドレス | Mainnet アドレス (新規) | |
| `BYBIT_SANDBOX` | `true` | `false` | 実資金取引に切替 |
| `AI_SHADOW_MODE` | `false` | `false` | 変更なし |
| `REBALANCE_SHADOW_MODE` | `false` | `false` | 変更なし |

> **補足 — チェーンレジストリとの対応:**
> `AAVE_ACTIVE_CHAINS=base` に設定すると、`chains.py` の `"base"` エントリを読み込む。
> - chain_id: `8453`
> - pool_address: `0xA238Dd80C259a72e81d7e4664a9801593F98d1c5`
> - RPC 環境変数: `AAVE_RPC_URL_BASE`
> - USDC アドレス: `0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913`
>
> 上記は `backend/app/aave/chains.py` の `CHAIN_REGISTRY["base"]` に定義済み。コード変更不要。

### 2.2 フロントエンド (docker-compose.production.yml build.args)

| 変数 | 切替前 (Sepolia) | 切替後 (Mainnet) |
|---|---|---|
| `NEXT_PUBLIC_DEFAULT_CHAIN_ID` | `84532` | `8453` |
| `NEXT_PUBLIC_DEFAULT_CHAIN` | `base-sepolia` | `base-mainnet` |
| `NEXT_PUBLIC_RPC_URL` | Base Sepolia RPC URL | Base Mainnet RPC URL (Alchemy) |

> フロントエンド変数は `build.args` に指定し、`docker compose build --no-cache frontend` が必須。
> `env_file` だけでは JS バンドルに焼き込まれない (docs/CLAUDE.md §2026-04-03 追加)。

### 2.3 コード (確認のみ、変更不要)

| ファイル | 確認内容 |
|---|---|
| `backend/app/aave/chains.py` | `CHAIN_REGISTRY["base"]` に chain_id=8453, pool_address 定義済み ✅ |
| `backend/app/aave/rpc_provider.py` | primary/secondary フェイルオーバー実装済み ✅ |
| `backend/app/aave/client.py` | `AAVE_ACTIVE_CHAINS` 経由で chain_id 8453 動作確認 (Base Sepolia テストで実証) ✅ |

---

## 3. 切替実行手順 (本番作業、claude.ai の 3 段プロンプト準拠)

> **⚠️ 実行者: 小林。各フェーズで claude.ai のレビューを取得してから次フェーズへ進む。**

### Phase A: 事前確認 (read-only、所要 5 分)

```bash
# 1. 本番コンテナとネットワーク確認
docker ps | grep ultra-autotrade-production
docker inspect ultra-autotrade-backend-production --format "{{index .Config.Labels \"com.docker.compose.project\"}}"

# 2. ヘルスチェック
curl -sf https://api.ultra-auto-trade.com/health | python3 -m json.tool
# → {"status": "ok", "scheduler_healthy": true, ...}

# 3. 現在の .env.production の AAVE 変数確認 (値は出力しない)
grep -E "^AAVE_ACTIVE_CHAINS|^AAVE_NETWORK|^APP_ENV|^BYBIT_SANDBOX" .env.production

# 4. AI 判定直近 48h 確認
docker exec ultra-autotrade-postgres-production psql -U ultra -d ultra_autotrade \
  -c "SELECT action, created_at FROM ai_decisions ORDER BY created_at DESC LIMIT 10;"
```

### Phase B: プラン提示 → claude.ai 承認取得

以下を claude.ai に貼り付け、「このプランで実行してよいか」の承認を取得する:

```
## 本番切替プラン (Base Sepolia → Base Mainnet)

### 変更対象ファイル
- .env.production (§2.1 の変数群)

### バックアップ計画
- .env.production: cp .env.production .env.production.bak_$(date +%Y%m%d_%H%M%S)
- DB: docs/31_backup_restore_procedures.md §2 実行

### ロールバックトリガー
- /aave/status で chain_id が 8453 以外を返す
- deposit E2E テスト失敗
- HF < 1.6
- Slack アラート (任意のERROR)

### 推定所要時間: 20-25 分
```

### Phase C: 実行 (所要 20-25 分)

```bash
# --- Step 1: バックアップ ---
BACKUP_FILE=".env.production.bak_$(date +%Y%m%d_%H%M%S)"
cp .env.production "$BACKUP_FILE"
md5sum "$BACKUP_FILE"  # ハッシュ記録
echo "バックアップ: $BACKUP_FILE"

# --- Step 2: Mainnet ウォレットへ動作確認用少額送金 ---
# 新規 Mainnet ウォレットに $10 USDC を送金 (手動、Rabby/MetaMask から)
# 送金完了を TX ハッシュで確認してから次へ

# --- Step 3: .env.production 変数を一括書換 ---
# ⚠️ 以下は awk で明示行指定。sed による一括置換は禁止 (2026-04-18 インシデント防止)
# 各変数を1つずつ確認しながら更新すること。

# APP_ENV
printf '\nAPP_ENV=production\n' >> .env.production  # 既存行は先にコメントアウト

# AAVE_NETWORK / AAVE_ACTIVE_CHAINS
# AAVE_POOL_ADDRESS
# AAVE_RPC_URL_BASE (新規追加)
# AAVE_RPC_URL, AAVE_RPC_URL_SECONDARY
# AAVE_WALLET_PRIVATE_KEY, AAVE_WALLET_ADDRESS
# BYBIT_SANDBOX=false
# → 各行を個別に更新。値はコンテナ外で確認後にセット。

# 差分確認 (パスワードマスク)
diff <(sed -E 's|(KEY|SECRET|PRIVATE_KEY|RPC_URL)=(.{6})[^[:space:]]+|\1=\2***|g' "$BACKUP_FILE") \
     <(sed -E 's|(KEY|SECRET|PRIVATE_KEY|RPC_URL)=(.{6})[^[:space:]]+|\1=\2***|g' .env.production)

# --- Step 4: バックエンド再起動 (フロントエンドは別途) ---
docker compose -f docker-compose.production.yml --env-file .env.production \
  up -d --no-deps ultra-autotrade-backend-production

# --- Step 5: ヘルスチェック ---
sleep 10
curl -sf https://api.ultra-auto-trade.com/health | python3 -m json.tool
# → {"status": "ok", ...}

# --- Step 6: Aave チェーン確認 ---
curl -sf https://api.ultra-auto-trade.com/aave/status | python3 -m json.tool
# → chain_id=8453, health_factor > 1.6

# --- Step 7: 少額 deposit E2E テスト ---
# $10 USDC deposit → 5 分待機 → withdraw $10
# 実行コマンドは docs/22_production_release_checklist.md §9 参照

# --- Step 8: 本番ウォレットへ残額入金 ---
# 動作確認完了後、山本さんの 10 万円相当 USDC を本番ウォレットへ入金

# --- Step 9: フロントエンド再ビルド (NEXT_PUBLIC_* 変数変更がある場合) ---
docker compose -f docker-compose.production.yml --env-file .env.production \
  build --no-cache ultra-autotrade-frontend-production
docker compose -f docker-compose.production.yml --env-file .env.production \
  up -d --no-deps ultra-autotrade-frontend-production

# --- Step 10: Slack 切替完了報告 ---
WEBHOOK=$(grep SLACK_WEBHOOK_URL .env.production | cut -d= -f2-)
curl -s -X POST "$WEBHOOK" \
  -H "Content-Type: application/json" \
  -d '{"text": "✅ Base Mainnet 切替完了 (Base Sepolia → Base Mainnet)\n- chain_id: 8453\n- HF: >1.6\n- deposit E2E: 通過\n- BYBIT_SANDBOX: false"}'
```

> Step 10 の後、§6 の山本さん宛 DM を送信する。

---

## 4. ロールバック手順

詳細は `docs/15_rollback_procedures.md` に従う。

要旨:

```bash
# 1. .env.production をバックアップから復元
cp "$BACKUP_FILE" .env.production

# 2. バックエンド再起動
docker compose -f docker-compose.production.yml --env-file .env.production \
  up -d --no-deps ultra-autotrade-backend-production

# 3. 確認
curl -sf https://api.ultra-auto-trade.com/health | python3 -m json.tool
curl -sf https://api.ultra-auto-trade.com/aave/status | python3 -m json.tool
# → chain_id=84532 (Base Sepolia に戻っていること)

# 4. Mainnet ウォレットの残資金を保管用ウォレットへ移動 (手動)
```

---

## 5. 切替後監視 (24h)

| 確認項目 | 方法 | 頻度 |
|---|---|---|
| Health Factor | Slack `#ultra-auto-project` HF アラート | 自動 (60 秒間隔) |
| AI 判定 BUY/SELL 出現 | `/proposals` ページ or DB直参照 | 4 時間ごと |
| RPC フェイルオーバー | `docker logs ultra-autotrade-backend-production \| grep "RPC:"` | 異常時 |
| Bybit 本番 API 疎通 | `/exchange/status` エンドポイント | 切替直後・24h 後 |
| 山本さん異常報告 | Slack DM + `#ultra-auto-project` | 随時 |

切替後 24h 異常なければ本番稼働を正式確認とする。

---

## 6. 補足: 山本さんへの事前周知テンプレ

切替 24h 前に Slack DM で送信する。

```
山本さん

お疲れ様です。小林です。

明日 [日付・時刻] に、テスト環境 (Base Sepolia) から
本番ネットワーク (Base Mainnet) への切替を実施します。

■ 作業時間: [XX:XX 〜 XX:XX 頃、約 30 分]
■ 影響: 切替作業中 (約 10 分) はシステムが一時停止します
■ 切替後: USDC の入金が完了し、実際の Aave 運用が開始されます

作業中に問題が発生した場合は即座にロールバックします。
ご不明な点があればお知らせください。

よろしくお願いいたします。
小林
```

切替完了後の DM:

```
山本さん

Base Mainnet への切替が完了しました。
- chain_id: 8453 (Base Mainnet)
- Health Factor: 正常範囲
- テスト deposit/withdraw: 通過

引き続き本番テストをよろしくお願いいたします。
何か異常があれば Slack でご連絡ください。

小林
```

---

## 関連ドキュメント

| ドキュメント | 参照タイミング |
|---|---|
| `docs/15_rollback_procedures.md` | ロールバック実行時 |
| `docs/22_production_release_checklist.md` | デプロイ前後の全体チェック |
| `docs/30_rpc_plan_requirements.md` | RPC プロバイダー選定・費用見積もり |
| `docs/31_backup_restore_procedures.md` | DB バックアップ手順 |
| `docs/ops/03_deploy_procedures.md` | Docker コンテナ名・ネットワーク確認 |
| `backend/app/aave/chains.py` | Base Mainnet コントラクトアドレス確認 |
