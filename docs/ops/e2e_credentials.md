# E2E credentials 運用手順 (yamamoto-partner-flow.spec.ts)

最終更新: 2026-05-27

## 1. 概要

Playwright `frontend/e2e/yamamoto-partner-flow.spec.ts` (TC1-TC7) を staging で
完走させるための credentials と DB seed の運用手順。

設計の基本原則:

- **山本さん本人 (user_id=11) の credentials は絶対に使わない。**
- e2e 専用 user (id=999998) を staging DB に常駐させて使う。
  山本さん user_id=11 と固定値で絶対衝突しない。
- testnet 専用 wallet。mainnet 鍵は不使用。
- credentials なしで Playwright を回しても **緑にならない**
  (launch_gate L3 が "NO TESTS RAN" を FAIL として扱う)。
- §7 verify.sh 罠防止: skip だらけで緑にする経路は閉じる。
- §13/§15 整合: env 分離・本番 DB 不可侵を維持。

## 2. env name 一覧

`/opt/ultra-autotrade/.env.e2e` に下記を配置 (staging VPS 上、gitignored)。
テンプレートは `frontend/.env.e2e.example`。

| 名前 | 用途 | 例 |
|------|------|----|
| `E2E_PARTNER_EMAIL` | Playwright login + seed の email | `e2e-partner@ultra-autotrade.local` |
| `E2E_PARTNER_PASSWORD` | 平文 (Playwright login 用) | (任意) |
| `E2E_PARTNER_PASSWORD_HASH` | bcrypt ハッシュ (seed_e2e_user.sh が DB に書く) | `$2b$12$...` |
| `E2E_PARTNER_WALLET_ADDRESS` | testnet wallet address | `0x...` |
| `E2E_APPROVE_MUTATE` | 既定 0。1 でのみ approve クリック実行 | `0` |
| `E2E_INTERNAL_BACKEND_URL` | Lane G CF Access relay 先 | `http://localhost:8082` |
| `STAGING_URL` | Playwright baseURL | `https://app-staging.ultra-auto-trade.com` |

## 3. `/opt/ultra-autotrade/.env.e2e` への配置手順 (staging VPS)

staging は本番 Hetzner VPS (77.42.46.155) 上に同居 ([[staging-lives-on-prod-vps]])。
dev VPS 上には .env.e2e は無い。dev からは触らない ([[no-prod-vps-commands-from-dev]])。

```bash
# 1) staging VPS 上で example をコピー
cp /opt/ultra-autotrade/frontend/.env.e2e.example /opt/ultra-autotrade/.env.e2e
chmod 600 /opt/ultra-autotrade/.env.e2e

# 2) エディタで実値に置換
#    E2E_PARTNER_PASSWORD       平文 (Playwright 用)
#    E2E_PARTNER_PASSWORD_HASH  上の bcrypt (htpasswd -bnBC 12 "" "<password>" | tr -d ':\n' で生成)
#    E2E_PARTNER_WALLET_ADDRESS testnet wallet (Base Sepolia / Mumbai 等)

# 3) パーミッション再確認
ls -l /opt/ultra-autotrade/.env.e2e   # -rw------- であること
```

## 4. seed script の流し方

```bash
# staging VPS 上で
cd /opt/ultra-autotrade
source /opt/ultra-autotrade/.env.e2e
# DATABASE_URL は .env.staging-new から自動取得されるが、明示も可
export DATABASE_URL=postgresql://...staging-new...
bash scripts/seed_e2e_user.sh --env=staging
```

期待出力:

```
[INFO] DB 名再確認 OK: current_database()=...staging...
=== seed_e2e_user.sh: target ===
  ...
[OK] E2E user seed 完了 (id=999998 on ...staging...)
```

二重ガード:

1. `--env=production` は exit 2 で拒否される。
2. `current_database()` の戻り値が "staging" を含まなければ exit 2 で拒否される。

冪等性: 何度実行しても id=999998 の row が `ON CONFLICT (id) DO UPDATE` で
最新値に揃う。別の id で同じ email/wallet が既に居る場合は exit 1 で安全側に停止。

## 5. storageState の運用 (expire 時の再生成)

`frontend/e2e/global-setup.ts` が credentials を使って `/auth/login` を 1 回叩き、

- `frontend/e2e/.auth/partner.json`      (legacy JWT cache、24h 有効)
- `frontend/e2e/.auth/storageState.json` (Playwright 標準形式)

を生成する。両ファイルは gitignored (`frontend/.gitignore` の `e2e/.auth/`)。

JWT が expire したら globalSetup を再実行 (= `npx playwright test` を 1 度走らせる
だけで再生成される)。手動削除も可: `rm -rf frontend/e2e/.auth/`。

## 6. credentials 未設定時の挙動

| 場面 | 挙動 |
|------|------|
| `global-setup.ts` | partner.json / storageState.json を**書かない**。`process.env.E2E_AUTH_SKIPPED='1'` を set。throw しない。 |
| `yamamoto-partner-flow.spec.ts` TC1 unauth | 実行される (login ページ形状確認のみ) |
| 同 TC1-TC7 認証必須 | `test.skip(!HAS_CREDENTIALS, ...)` で全 skip |
| `scripts/launch_gate/L3_e2e.sh` | 事前 env チェックで「SKIP-WITH-INSTRUCTIONS」として `gate_record SKIP` (PASS にしない) |
| L3 で credentials は有るが全 test が skip された場合 | `playwright-results.json` の `expected==0` を検出して **FAIL (NO TESTS RAN)** |

これにより、credentials 漏れで「skip だらけで緑」になる経路は完全に閉じる。
§7 「verify.sh 通過だけでクローズ禁止」原則の最後の砦。

## 7. 山本さん本人 credentials は使わない原則

- 山本さん user_id=11 は本番 (Hetzner production DB) にのみ存在。staging DB には居ない。
- e2e seed は **staging DB のみ** (`scripts/seed_e2e_user.sh` の二重ガード)。
- e2e user id=999998 は山本さん id=11 と数値領域が離れており、誤参照しても conflict すらしない。
- 影響ゼロ確認方法:

  ```bash
  # staging DB 側
  psql "${STAGING_DATABASE_URL}" -c \
    "SELECT id, email, role FROM users WHERE id IN (11, 999998) ORDER BY id"
  # → id=11 は存在しない (= staging 環境 / 衝突なし)
  # → id=999998 が partner / e2e-partner@... で存在

  # production DB 側 (人間担当 / dev からは触らない)
  # psql "${PRODUCTION_DATABASE_URL}" -c \
  #   "SELECT id, email, role FROM users WHERE id IN (11, 999998) ORDER BY id"
  # → id=11 は山本さん (変更されていない)
  # → id=999998 は存在しない (= seed は production には流れていない)
  ```

- seed script は production DB への接続を `--env=production` 拒否 +
  DB 名 "staging" 必須の二重ガードで遮断している。

## 8. 関連ファイル

- `scripts/seed_e2e_user.sh` — staging DB に id=999998 を冪等 seed
- `frontend/.env.e2e.example` — env テンプレート
- `frontend/e2e/global-setup.ts` — credentials なしで graceful skip
- `frontend/e2e/yamamoto-partner-flow.spec.ts` — TC1-TC7 (PARTNER_MOCK_USER.id=999998)
- `frontend/playwright.config.ts` — json reporter 出力
- `scripts/launch_gate/L3_e2e.sh` — skip-only を FAIL とする判定
