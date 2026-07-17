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
| `ALLOWED_RISK_MODES` (env) | 未設定 = `{conservative}` | aggressive を選択できるか | §5（**規制判断**） |
| `NEXT_PUBLIC_AGGRESSIVE_TIER_ENABLED` | `false` | フロントで aggressive 選択に同意モーダルを挟むか | §5 |

これら **すべてが揃わない限り** Pendle は 1 wei も動かない。1つでも欠ければ dry-run / 提案非生成 / 従来挙動に fallback。

---

## 1. 前提: コードを main → 本番へ

1. **PR #983 を main にマージ**（D3–D5b を main に集約）。※ #979–982 は stacked base ブランチにマージされ main 未反映のため #983 が正。
2. 通常デプロイフロー（ローカル merge → push → 本番 VPS `git pull origin main` → `deploy_production.sh`）。まず **staging-v4** で検証してから本番。

---

## 2. DB マイグレーション（手動 ALTER TABLE / Alembic autogenerate 禁止）

> **2026-07-17 実機確認: production / staging-v4 とも適用済み**（本番 users に `aggressive_ack_at` /
> `aggressive_ack_version` の 2 列が存在することを phase1 read-only 確認で実測）。
> **本節は実行不要**。まず下の確認コマンドで実態を見てから判断すること（「未適用前提」で流すと
> 重複エラーになる）。

D5b で User に列追加（`backend/app/auth/models.py` 冒頭コメント準拠）。**未適用の環境でのみ**実行:

```sql
ALTER TABLE users ADD COLUMN IF NOT EXISTS aggressive_ack_at TIMESTAMP WITH TIME ZONE NULL;
ALTER TABLE users ADD COLUMN IF NOT EXISTS aggressive_ack_version VARCHAR(20) NULL;
```

確認（**先にこれを実行する**）: `docker exec <postgres> psql -U ultra -d <db> -c "\d users" | grep aggressive`。

---

## 3. env 設定（staging-v4 → 本番の順）

> **[重要] 2026-07-17 訂正 — Pendle に testnet は存在しない。**
> Pendle API がサポートするのは **mainnet のみ**（`1, 56, 143, 999, 8453, 9745, 42161, 10, 146, 5000, 80094`）。
> Base Sepolia(84532) / Arbitrum Sepolia(421614) は `400 "Unsupported chain id"` で拒否される（実 API で確認）。
> **旧記述の `PENDLE_CHAIN=base_sepolia` では calldata を 1 本も生成できない**ため、staging-v4 での検証も
> `PENDLE_CHAIN=base`（実 market・実 calldata・**broadcast なしの dry-run**）で行う。
> 実 broadcast の検証経路は **Base mainnet の実資金しか無い**（§4）。

実値（Pendle API `core/v1/8453/markets` で確認済み 2026-07-17）:

```bash
PENDLE_CHAIN=base                    # testnet は存在しない（上記）
PENDLE_MARKET_ADDRESS=0x250c15e59a7572195e248f668636723cca20a2b8  # PT-yoUSD-24SEP2026 market
PENDLE_UNDERLYING_TOKEN_ADDRESS=0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913  # Base USDC
PENDLE_UNDERLYING_TOKEN_DECIMALS=6
PENDLE_PT_TOKEN_ADDRESS=0x1fec97ca2817da87f266fd1741bba61caf7cde29        # PT-yoUSD-24SEP2026
PENDLE_PT_TOKEN_DECIMALS=6           # **PT は 18 桁ではない**（誤ると SELL_PT の数量が 10^12 倍ズレる）
                                     # ※コード既定も 6。未設定でも 6 になるが、18桁 PT を扱う
                                     #   環境では明示必須（低すぎる側は dust を売って“成功”する）
                                     #   実 decimals とは流動性ガードが突合し不一致なら block
PENDLE_STABLE_UNDERLYING=true
# 流動性ガード（薄いプール保護・必須）
PENDLE_MAX_POOL_LIQUIDITY_PCT=0.05   # 1 投入 ≤ プール流動性の 5%
PENDLE_MAX_TRADE_USD_CAP=20          # 1 投入の絶対上限（コード既定も 20）。**これが事実上
                                     #   唯一の金額ガード**（§6 の H3 注記参照）。安易に上げない
```

> **落とし穴**: Pendle の用語で "underlyingAsset" は **yoUSD**（利回り vault トークン、`0x0000…8a65`）を指すが、
> 本 repo の `PENDLE_UNDERLYING_TOKEN_ADDRESS` は **BUY_PT で支払う入力トークン = USDC** を意味する。
> ここに yoUSD を入れないこと。また `PENDLE_MARKET_ADDRESS` と `PENDLE_PT_TOKEN_ADDRESS` が別 market の
> ものになると、**流動性ガードが別プールを見る**（swap は PT 側の market で成立する）ので必ず対で設定する。

`printf '\nKEY=VALUE\n' >> .env.*`（前行連結防止 / CLAUDE.lessons）。反映は `docker compose up -d --no-deps <service>`。

### 3.5 dry-run 実機確認（実資金なし・ここまでは Claude 実行可）

`PENDLE_ENABLE_ONCHAIN_WRITE` を **false のまま**にすれば broadcast されない。この状態で:

- 実 API 契約テスト（無料・鍵不要・送信なし）:
  `PENDLE_LIVE_API_TEST=1 pytest tests/protocols/test_pendle/test_pendle_convert_api_contract.py`
- BUY_PT proposal → `PendleDryRunNotBroadcast`(501) で **approved 据え置き**、ログに実 calldata が出ること
- 流動性ガード: `amount > tvl×5%` / `> 絶対上限` / market_info 取得失敗 で **block** されること

ここまでで「SDK 統合・market 解決・calldata・宛先 allowlist・ガード」は検証できる。**未検証で残るのは
Privy 署名 + on-chain 着金のみ**で、その機構自体は Aave SUPPLY で本番実証済み。

---

## 4. 実 broadcast 検証（**Base mainnet 実資金のみ**・human-in-the-loop・Claude 実行不可）

> **testnet が無いため「安全に試す」選択肢は存在しない**。少額でも実資金がリスクの下限になる。
> 実行判断は hkobayashi（Tier S / HUMAN-REVIEW-REQUIRED / 法務 GO と同時）。

test wallet + Privy creds を用意し、§3 に加えて:

```bash
PENDLE_ENABLE_ONCHAIN_WRITE=true
DELEGATION_PRIVY_POLICY_ENABLED=true
PRIVY_SERVER_SIGNER_ID=<L0 signer id>
PRIVY_APP_ID=<...>
PRIVY_APP_SECRET=<...>
PENDLE_MAX_TRADE_USD_CAP=20          # 初回は極小に絞る
```

手順:
1. test user に `allowed_protocols=["pendle"]` の有効 grant を作成（Privy policy = RouterV4 + USDC + PT の 3 宛先 allowlist）。
2. test wallet に **少額の実 USDC**（$10〜20）を用意。
3. BUY_PT proposal を approve → **SCW broadcast** → **receipt status=1 / PT-yoUSD 残高増** を確認。
4. SELL_PT は満期（**2026-09-24**）前は二次市場価格での売却になる（1:1 redeem は満期後）。満期前に出口を
   確認する場合、PT 価格ディスカウント分の目減りを許容できる額で行うこと。
5. 流動性ガード動作確認: `amount > tvl×5%` / `> 絶対上限` / market_info 取得失敗 で **block（approved 据え置き）** されること。

診断: 「提案が出ない/実行されない」は `docker exec <backend> python -m app.diagnostics.proposal_chain`（提案チェーン ゲートトレーサ）で切り分け。

---

## 5. aggressive 有効化（**規制判断を含む・最後**）

**この段階は日本の無登録投資運用業規制（森先生判断: Auto/aggressive は無登録運用業に該当し得る）に直結する product 判断を伴う。** コードだけでは有効化されない:

1. **`ALLOWED_RISK_MODES=conservative,aggressive` を対象環境の env に設定**（← **法務 GO 後のみ**）。
   2026-07-17 に env 化した（旧: `backend/app/auth/models.py` のハードコード定数）。**理由: ハードコードのままだと
   staging だけ開けようとしても同じコードが本番に入り本番も同時に開いてしまうため**。未設定なら従来どおり
   conservative のみ。設定すると `PUT /auth/risk-mode` の 412 同意必須ガードが有効化され、`aggressive_ack_at`
   未記録のユーザーは選択不可（defense-in-depth）。typo は無視され解禁は広がらない（fail-safe）。
   **注意: 本定数は module import 時に評価される**ため、env の追加・削除は **backend の再起動**で反映する
   （`docker compose up -d --no-deps <backend>`）。プロセスを再起動しない限り即時には効かない。
2. フロント: `NEXT_PUBLIC_AGGRESSIVE_TIER_ENABLED=true` → **再ビルド**（build-time 埋め込み）。aggressive 選択時に満期ロック/裏付け/スリッページ同意モーダルが必須になる。
3. `AI_OPTIMIZER_MULTIPROTOCOL_ENABLED=true` → aggressive ユーザーの BUY で routing が `(BUY_PT, PT-yoUSD, pendle)` を生成（optimizer は実 APY を使用）。
4. 消費者 `/liff-chat` の aggressive 選択パネル（運用方針セレクタ: 安全重視 / 利回り重視）は
   **PR #993 で実装済み**（`NEXT_PUBLIC_AGGRESSIVE_TIER_ENABLED` 既定 false で dormant）。
   同 PR で「Pendle 委譲は開示同意必須(412)」「dummy アドレス fail-closed」も追加済み。
   セレクタの真実源は `risk_mode` で、委譲枠 `allowed_protocols` と**両方**が Pendle を許して初めて実効になる。

---

## 6. 段階解放 & 安全確認

- **少額・少人数から**。`PENDLE_MAX_TRADE_USD_CAP` を小さく開始し、実績を見て緩める（既定 20）。
- 監視: proposal → SCW receipt → PT 残高。流動性ガード block / HARD_STOP の Slack 通知。
- 安全ネット（有効時も効く）: 二段ガード / HARD_STOP（`_pendle_execution_blocked`）/ 流動性ガード
  （fail-closed・market↔PT 対応検証・PT decimals 突合を含む）/ approve の token/amount 厳密一致 /
  Privy policy 宛先 allowlist / broadcast 済み後の failed 化防止（二重送信防止）/ 非カストディアル不変。

> **[重要] 金額ガードの実態（2026-07-17 安全レビュー H3）**
> Pendle 経路では **CLAUDE.md Rule 3/4（単一 10% / 日次 30%・ABSOLUTE）が実際には効いていない**。
> `_pendle_execution_blocked` が risk_limiter に `total_assets=None` を渡しており、risk_limiter は
> 両方の % 判定を `total_assets_usd is not None and > 0` でガードしているため。Pendle 単独ユーザーは
> HF も取得できず HF floor も効かない（Aave SCW 経路も同じ既存状態）。
> ⇒ **金額の歯止めは実質「プール流動性 % と `PENDLE_MAX_TRADE_USD_CAP`」だけ**。この cap を
> 「大きめにして様子を見る」という運用はしないこと。恒久対応（total_assets 配線）は別課題。

## 7. ロールバック

各フラグを個別に `false` / env 除去で dormant 化（コード revert 不要）。
`PENDLE_ENABLE_ONCHAIN_WRITE=false` で broadcast 停止、`AI_OPTIMIZER_MULTIPROTOCOL_ENABLED=false` で
pendle 提案生成停止、**`ALLOWED_RISK_MODES` を未設定に戻す**（旧記述の「`PHASE_1` から AGGRESSIVE 除去」＝
コード編集 は §5 の env 化で不要になった）で aggressive 選択停止。

> **「即 dormant」ではない**: `ALLOWED_RISK_MODES` は module import 時評価、`NEXT_PUBLIC_*` は
> build-time 埋め込み。前者は **backend 再起動**、後者は **frontend 再ビルド**が要る。
> 最速で broadcast だけを止めたい場合は `PENDLE_ENABLE_ONCHAIN_WRITE=false` + backend 再起動が最短
> （`get_pendle_config()` は毎回 env を読み直すため、再起動すれば即反映される）。

---

## Opus 安全レビュー チェックリスト（本番反映前）

- [ ] **SDK 契約**: `PENDLE_LIVE_API_TEST=1` の契約テストが green か（実 API と実装がズレていないか）。
      2026-07-17 に「実装が実在しない API に対して書かれていた」事故があり、mock だけでは検出できない
- [ ] **decimals**: `PENDLE_PT_TOKEN_DECIMALS` が対象 PT の実桁と一致するか（PT-yoUSD は 6。
      誤ると **SELL_PT の売却数量が 10^12 倍ズレる**）
- [ ] **market と PT の対応**: `PENDLE_MARKET_ADDRESS` と `PENDLE_PT_TOKEN_ADDRESS` が同一 market のものか
      （ズレると流動性ガードが別プールを見る）
- [ ] amount 換算: stablecoin PT のみ USDC 1:1（`PENDLE_STABLE_UNDERLYING`）。非 stablecoin は fail-closed か
- [ ] 流動性ガード: `tvl<=0`/取得失敗で fail-closed（block）か。%・絶対上限が薄いプールに対し妥当か
- [ ] Privy policy: RouterV4 + USDC + PT の 3 宛先のみ allowlist か（over-broad でないか）
- [ ] HARD_STOP/risk_limiter が Pendle broadcast 経路でも通るか（Gap A）
- [ ] broadcast 済み後の bookkeeping 例外で failed 化 → 二重送信しないか
- [ ] 非カストディアル: サーバー鍵不参照・PT/USDC は SCW 本人着金か
- [ ] routing: risk_mode eligibility（pendle=aggressive のみ）。conservative が掴まないか
- [ ] aggressive 同意: `PUT /auth/risk-mode` の 412 ガードが `ALLOWED_RISK_MODES` 設定後に効くか
- [ ] 規制: `ALLOWED_RISK_MODES` への aggressive 追加は法務 GO 済みか（森先生判断）
