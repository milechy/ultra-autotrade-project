# 本番デプロイ手順書 — 2026-06-25 リリース (#874 / #875 / #876)

> 対象 PR: #874 (i18n provider 修正) / #875 (提案フロー可視化 + protocol 露出) / #876 (消費者 wallet 残高で提案金額解決)
> 実施環境: 本番 Hetzner VPS (`77.42.46.155`)、`scripts/deploy_production.sh`(full = frontend + backend)
> 種別: **frontend + backend 両方** + **DB migration 1 件 (pp20260624 = proposals.protocol 追加)**

---

## 0. このリリースの中身と本番への影響

| PR | 層 | 内容 | 本番影響 |
|---|---|---|---|
| #874 | frontend | ネスト NextIntlClientProvider の messages 部分指定修正 | (user)/(admin)/(partner) のナビ・モーダルの i18n 生キー表示が解消。frontend 再ビルド必須 |
| #875 | frontend+backend | liff-chat の fetch 失敗可視化 / `ProposalResponse.protocol` 露出 | `/api/proposals/pending` が `protocol` を返すようになる。**backend が protocol を SELECT するため pp20260624 migration が前提** |
| #876 | backend | `_resolve_proposal_amount` に wallet 残高 fallback | **提案サイジングの挙動変更**(下記 §5 要確認) |

### migration の安全性
- pp20260624 は `proposals` に `protocol VARCHAR(50) NULL` を**追加するだけ**(非破壊・後方互換)。
- 本番 alembic は現在 `dg20260619`(= pp20260624 の親)。`alembic upgrade head` で pp20260624 が 1 件だけ適用される。
- `deploy_production.sh` は **旧 backend が traffic を受けている間に新イメージの使い捨てコンテナで migration を先行適用** → その後 blue/green 切替(line 660-664)。additive migration のため旧コードは新列増加に無影響。**順序問題は script が解決済**。

---

## 1. 事前確認 (read-only / デプロイ前)

```bash
# 本番 VPS で実行
cd /opt/ultra-autotrade

# (a) 現在の alembic / protocol カラム不在を確認 (期待値)
docker exec ultra-autotrade-backend-green-production sh -c 'cd /app/backend && alembic current'
#   → dg20260619 (head)   ← 旧イメージ視点の head
docker exec ultra-autotrade-postgres-production psql -U ultra -d ultra_autotrade -c \
  "SELECT column_name FROM information_schema.columns WHERE table_name='proposals' AND column_name='protocol';"
#   → 0 rows (protocol 無し = 正常。migration で追加される)

# (b) 本番 Base RPC が有効か (#876 wallet 残高読取が使う)
docker exec ultra-autotrade-backend-green-production sh -c \
  'curl -s -o /dev/null -w "%{http_code}\n" -X POST $AAVE_RPC_URL_BASE -H "Content-Type: application/json" \
   -d "{\"jsonrpc\":\"2.0\",\"method\":\"eth_chainId\",\"params\":[],\"id\":1}" --max-time 8'
#   → 200 (有効。2026-06-25 時点 確認済)

# (c) DB バックアップ (本番手順の標準。scripts/ の backup を使用)
#   → docs/31_backup_restore_procedures.md に従う
```

**中止条件**: protocol カラムが既に存在する / alembic が dg20260619 でない場合は、状態が想定と異なるため deploy を止めて調査。

---

## 2. デプロイ実行 (Hetzner 上 / HUMAN-REVIEW)

```bash
# ローカル Mac で main を push 済 (#874-876 merged) → 本番 VPS で pull only
cd /opt/ultra-autotrade
git pull origin main          # a529a697 以降。nginx upstream.*.conf のローカル変更は保持される

# full デプロイ (frontend + backend + migration)。手打ち build は禁止 (script に集約)。
./scripts/deploy_production.sh
```

`deploy_production.sh` が内部で行うこと(このリリースに関係する部分):
1. 環境分離チェック (`check_env_separation.sh`)
2. 新 frontend/backend イメージ build(`NEXT_PUBLIC_APP_VERSION` を build ARG 埋め込み)
3. **新イメージの使い捨てコンテナで `alembic upgrade head` を先行実行**(→ pp20260624 = protocol 追加)。失敗時は切替中止
4. `check_db_migration_gap.sh`
5. blue/green で新 backend/frontend へ traffic 切替

---

## 3. デプロイ後検証 (必須)

```bash
# (a) migration 適用確認
docker exec ultra-autotrade-backend-<active>-production sh -c 'cd /app/backend && alembic current'
#   → pp20260624 (head)
docker exec ultra-autotrade-postgres-production psql -U ultra -d ultra_autotrade -c \
  "SELECT column_name FROM information_schema.columns WHERE table_name='proposals' AND column_name='protocol';"
#   → protocol が 1 行

# (b) #875: /api/proposals/pending が 500 にならず protocol を返す
#   (認証トークンは実ユーザー or テスト用。500 = migration 未適用を意味する)
curl -s -o /dev/null -w "%{http_code}\n" https://api.ultra-auto-trade.com/api/proposals/pending -H "Authorization: Bearer <token>"
#   → 200 (401 でも DB エラーではない。500 なら NG)

# (c) #874: i18n 生キーが出ない
#   /connect (PWA) のナビに "UserHeader.viewerNav.*" 等の生キーが無いこと
#   → frontend/e2e/i18n-provider-regression.spec.ts を STAGING_URL=https://app.ultra-auto-trade.com で実行

# (d) /health
curl -s https://api.ultra-auto-trade.com/health | jq '.status'
```

---

## 4. ロールバック

- blue/green のため、問題時は **旧 backend/frontend コンテナへ traffic を戻す**(`deploy_production.sh` のロールバック手順 / `docs/15_rollback_procedures.md`)。
- pp20260624 の protocol カラムは **additive・NULL 許容**のため、ロールバックしても**残して問題ない**(旧コードは新列を無視)。`alembic downgrade` は不要。

---

## 5. #876 の挙動変更 — デプロイ後モニタリング (重要)

`_resolve_proposal_amount` の fallback により、**fund_allocation を持たないが wallet 設定済の消費者(VIEWER)に、wallet USDC 残高 × `PROPOSAL_AMOUNT_RATIO`(既定 10%)の提案が新規に生成されるようになる**。これは従来「$0 で skip」だった層への挙動変更。

確認・監視:
- env `PROPOSAL_AMOUNT_RATIO` / `PROPOSAL_AMOUNT_MIN_USD`(既定 $50) / `PROPOSAL_AMOUNT_MAX_USD`(既定 $2000)が本番意図値か確認。
- デプロイ後しばらく、消費者向け proposal の生成件数・金額分布をモニタ(意図せぬ大量生成・過大金額が無いか)。
- 安全側設計: 残高0 / RPC失敗 / 10% が min 未満 は引き続き skip(過大 supply を出さない)。fund_allocation 保有ユーザーは従来通り(優先・不変)。

---

## 参照
- 設計: `docs/61_consumer_proposal_amount_design.md`
- staging-v4 実機検証(本リリースを 2026-06-25 に staging-v4 で完走): 提案 表示→承認→署名シート→build-tx(200)→見送り、i18n 生キー0、protocol 露出、alembic head 整合
- `docs/15_rollback_procedures.md` / `docs/22_production_release_checklist.md` / `docs/31_backup_restore_procedures.md`
