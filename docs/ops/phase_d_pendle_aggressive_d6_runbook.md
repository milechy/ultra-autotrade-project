# Phase-D D6 有効化ランブック — Pendle aggressive tier (PT-yoUSD)

> Phase-D は D2–D5b（PR #978–982 / main 集約 #983）で **実行層・出口・流動性ガード・routing・同意基盤・実APY**
> を **全て dormant（既定 OFF）** で実装済み。本ランブックは D6 = **段階的な有効化**の手順。
> 実資金移動 = **Tier S / HUMAN-REVIEW-REQUIRED / Opus 安全レビュー必須**（CLAUDE.md 鉄則10）。
> Claude は本ランブックの **read-only 部分（コード確認）まで**。フラグ切替・DB write・実 broadcast・
> 本番反映は **人間主導**（3段プロトコル: phase1-investigator / phase2-implementer / phase3-deployer）。

関連: `memory: project_pendle_aggressive_tier_phase_d` / `docs/34_phase2_protocols_guide.md` /
Asana 親 1216418585178727（D1–D6）。

---

## 0. 現状（全て dormant）— 有効化しない限り一切 broadcast しない

| ガード / フラグ | 既定 | 意味 | 有効化ステップ |
|---|---|---|---|
| `AI_OPTIMIZER_MULTIPROTOCOL_ENABLED` | `false` | routing が pendle 提案を生成するか | §5 |
| `PENDLE_STABLE_UNDERLYING` | `false` | amount_usd を USDC 1:1 数量として扱う（stablecoin PT 前提） | §3 |
| `PENDLE_ENABLE_ONCHAIN_WRITE` | `false` | broadcast 二段ガードの1段目 | §4 |
| `DELEGATION_PRIVY_POLICY_ENABLED` (+ signer/creds) | 未設定 | 委譲 SCW 実行が非 dormant か | §4 |
| grant `allowed_protocols` に `"pendle"` | 無 | ユーザーが pendle 委譲済みか | §4 |
| `PHASE_1_ALLOWED_RISK_MODES` | `{conservative}` | aggressive を選択できるか | §5（**規制判断**） |
| `NEXT_PUBLIC_AGGRESSIVE_TIER_ENABLED` | `false` | フロントで aggressive 選択に同意モーダルを挟むか | §5 |

これら **すべてが揃わない限り** Pendle は 1 wei も動かない。1つでも欠ければ dry-run / 提案非生成 / 従来挙動に fallback。

---

## 1. 前提: コードを main → 本番へ

1. **PR #983 を main にマージ**（D3–D5b を main に集約）。※ #979–982 は stacked base ブランチにマージされ main 未反映のため #983 が正。
2. 通常デプロイフロー（ローカル merge → push → 本番 VPS `git pull origin main` → `deploy_production.sh`）。まず **staging-v4** で検証してから本番。

---

## 2. DB マイグレーション（手動 ALTER TABLE / Alembic autogenerate 禁止）

D5b で User に列追加（`backend/app/auth/models.py` 冒頭コメント準拠）。staging / production 両方で実行:

```sql
ALTER TABLE users ADD COLUMN IF NOT EXISTS aggressive_ack_at TIMESTAMP WITH TIME ZONE NULL;
ALTER TABLE users ADD COLUMN IF NOT EXISTS aggressive_ack_version VARCHAR(20) NULL;
```

確認: `docker exec <postgres> psql -U ultra -d <db> -c "\d users" | grep aggressive`。

---

## 3. env 設定（staging-v4 → 本番の順）

Pendle 市場を実値に設定。market address は **実装時に Pendle API（chainId 8453 / core/v1）で取得**した yoUSD 市場アドレスを使う（`memory` の yoUSD 裏付けアドレス `0x0000…8a65` は**裏付け vault** であって market address ではない点に注意）。

```bash
# stablecoin PT 前提（amount_usd を USDC 1:1 で使う）
PENDLE_CHAIN=base_sepolia            # 検証時。本番は base
PENDLE_MARKET_ADDRESS=<yoUSD market> # Pendle API で取得
PENDLE_UNDERLYING_TOKEN_ADDRESS=<USDC>          # 本番 Base USDC = 0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913
PENDLE_UNDERLYING_TOKEN_DECIMALS=6
PENDLE_PT_TOKEN_ADDRESS=<PT-yoUSD token>        # SELL_PT の approve 宛先（Privy policy allowlist）
PENDLE_STABLE_UNDERLYING=true
# 流動性ガード（薄いプール保護・必須）
PENDLE_MAX_POOL_LIQUIDITY_PCT=0.05   # 1 投入 ≤ プール流動性の 5%
PENDLE_MAX_TRADE_USD_CAP=5000        # 1 投入の絶対上限（初期は小さく）
```

`printf '\nKEY=VALUE\n' >> .env.*`（前行連結防止 / CLAUDE.lessons）。反映は `docker compose up -d --no-deps <service>`。

---

## 4. 実 broadcast 検証（Base Sepolia・human-in-the-loop・Claude 実行不可）

test wallet + Privy creds を用意し、上記に加えて:

```bash
PENDLE_ENABLE_ONCHAIN_WRITE=true
DELEGATION_PRIVY_POLICY_ENABLED=true
PRIVY_SERVER_SIGNER_ID=<L0 signer id>
PRIVY_APP_ID=<...>
PRIVY_APP_SECRET=<...>
```

手順:
1. test user に `allowed_protocols=["pendle"]` の有効 grant を作成（Privy policy = RouterV4 + USDC + PT の 3 宛先 allowlist）。
2. BUY_PT proposal を approve → **SCW broadcast** → **receipt status=1 / PT-yoUSD 残高増** を確認。
3. SELL_PT（満期出口）→ **PT→USDC 着金** を確認（満期後は 1:1 redeem）。
4. 流動性ガード動作確認: `amount > tvl×5%` / `> 絶対上限` / market_info 取得失敗 で **block（approved 据え置き）** されること。

診断: 「提案が出ない/実行されない」は `docker exec <backend> python -m app.diagnostics.proposal_chain`（提案チェーン ゲートトレーサ）で切り分け。

---

## 5. aggressive 有効化（**規制判断を含む・最後**）

**この段階は日本の無登録投資運用業規制（森先生判断: Auto/aggressive は無登録運用業に該当し得る）に直結する product 判断を伴う。** コードだけでは有効化されない:

1. **`PHASE_1_ALLOWED_RISK_MODES` に AGGRESSIVE を追加**（`backend/app/auth/models.py`）。← **法務 GO 後のみ**。追加すると `PUT /auth/risk-mode` の 412 同意必須ガードが有効化され、`aggressive_ack_at` 未記録のユーザーは選択不可（defense-in-depth）。
2. フロント: `NEXT_PUBLIC_AGGRESSIVE_TIER_ENABLED=true` → **再ビルド**（build-time 埋め込み）。aggressive 選択時に満期ロック/裏付け/スリッページ同意モーダルが必須になる。
3. `AI_OPTIMIZER_MULTIPROTOCOL_ENABLED=true` → aggressive ユーザーの BUY で routing が `(BUY_PT, PT-yoUSD, pendle)` を生成（optimizer は実 APY を使用）。
4. 消費者 `/liff-chat` の aggressive 選択パネルは**別 product スライス**（現状 admin `RiskModeSelector` のみ）。同意モーダル/endpoint は再利用可能に実装済み。

---

## 6. 段階解放 & 安全確認

- **少額・少人数から**。`PENDLE_MAX_TRADE_USD_CAP` を小さく開始し、実績を見て緩める。
- 監視: proposal → SCW receipt → PT 残高。流動性ガード block / HARD_STOP の Slack 通知。
- 安全ネット（有効時も効く）: 二段ガード / HARD_STOP・risk_limiter（`_pendle_execution_blocked`）/ 流動性ガード（fail-closed）/ Privy policy 宛先 allowlist / broadcast 済み後の failed 化防止（二重送信防止）/ 非カストディアル不変（SCW 本人着金）。

## 7. ロールバック

各フラグを個別に `false` / env 除去で即 dormant 化（コード revert 不要）。`PENDLE_ENABLE_ONCHAIN_WRITE=false` で broadcast 停止、`AI_OPTIMIZER_MULTIPROTOCOL_ENABLED=false` で pendle 提案生成停止、`PHASE_1` から AGGRESSIVE 除去で選択停止。

---

## Opus 安全レビュー チェックリスト（本番反映前）

- [ ] amount 換算: stablecoin PT のみ USDC 1:1（`PENDLE_STABLE_UNDERLYING`）。非 stablecoin は fail-closed か
- [ ] 流動性ガード: `tvl<=0`/取得失敗で fail-closed（block）か。%・絶対上限が薄いプールに対し妥当か
- [ ] Privy policy: RouterV4 + USDC + PT の 3 宛先のみ allowlist か（over-broad でないか）
- [ ] HARD_STOP/risk_limiter が Pendle broadcast 経路でも通るか（Gap A）
- [ ] broadcast 済み後の bookkeeping 例外で failed 化 → 二重送信しないか
- [ ] 非カストディアル: サーバー鍵不参照・PT/USDC は SCW 本人着金か
- [ ] routing: risk_mode eligibility（pendle=aggressive のみ）。conservative が掴まないか
- [ ] aggressive 同意: `PUT /auth/risk-mode` の 412 ガードが `PHASE_1` 緩和後に効くか
- [ ] 規制: `PHASE_1` 緩和は法務 GO 済みか（森先生判断）
