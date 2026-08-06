# production スキーマドリフト調査 (2026-08-06)

## 背景

`execution_policy` のデフォルト値修正 (PR #1027) を production で確認する過程で、
「`alembic_version` が head を指しているのに、個々の migration の効果が実際には
反映されていない」という事象が見つかった。本ドキュメントはその根本原因調査と、
`alembic check` が検出した全ドリフトの分類結果をまとめる。

## 根本原因

production の `users` テーブルほか全テーブルは、alembic migration を1本ずつ
実行して作られたものではなく、**ある時点の `models.py` に対して
`Base.metadata.create_all()` を実行し、その後 `alembic stamp head` で
「migration は全部適用済み」と偽装した状態**である。

### 証拠

1. **`pg_class.oid` が全テーブルでアルファベット順に連番**になっている。
   個別に `CREATE TABLE` を都度実行した場合、実行順（=マイグレーション追加順、
   時系列）に OID が振られるはずだが、実際は `create_all()` が内部で
   テーブル名アルファベット順に一括発行した痕跡と一致する。
2. **`alembic_version` テーブルが1行のみ**で、`stamp` 特有の状態と一致する
   (通常の migration 履歴なら複数回の `INSERT`/`UPDATE` の形跡が残ることがあるが、
   本番は一貫して単発)。
3. `execution_policy` のデフォルト値修正 migration (`g7h8i9j0k1l2`) は
   `alembic history` 上で head の祖先として存在するにもかかわらず、
   production の実際のカラムデフォルトは変更されていなかった
   (`create_all()` が使ったスナップショット時点の `models.py` には
   まだこの修正が入っていなかったため)。

### 影響

`alembic_version` が head を指していることは、「migration ファイル群を
実行した」ことの証明にならない。個々の migration が実際に本番へ反映されて
いるかは、DB の実スキーマを直接確認しない限り判断できない。

## `alembic check` 全指摘の分類

上記発覚を受け、`alembic check` (autogenerate 相当の diff検出) を production
相当のスキーマに対して実行し、全指摘を以下の基準で分類した。

| 分類 | 対応 | 件数 |
|---|---|---|
| 実害があり修正が必要 | 本 PR で対応 | 1件 (`ix_users_wallet_address`) |
| 命名規約の違いのみ、機能的には既存 | 触らない | 複数 (`idx_*` ↔ `ix_*` 等) |
| DB 側を削除すると後退する制約 | 触らない | 複数 (`fund_allocations_allocated_amount_usd_check` 等) |
| モデル側が実態と異なる (JSON→JSONB提案等) | 別途モデル側修正 (本件対象外) | 1件 (`ai_decision_features.deterministic_breakdown`) |
| 要判断で保留 | 個別に判断 (本件対象外) | 1件 (`smart_wallet_address` 二重 UNIQUE) |

### 1. 実害あり: `users.wallet_address` に UNIQUE index が無い

`wallet_address` に UNIQUE 制約が存在せず、**同一ウォレットアドレスを持つ
ユーザーが複数作成できる**状態だった。資産の帰属に直結するため、唯一
「今すぐ直すべき」実害と判断。

→ `alembic/versions/b9c0d1e2f3a4_add_missing_wallet_address_unique_index.py`
で `ix_users_wallet_address` (UNIQUE) を追加。既存データへの変更なし
(重複ゼロを実測済み)。

### 2. 触らない: 命名規約の違いのみ

`alembic check` は一部の index/制約名を `idx_*` → `ix_*` のようなリネームとして
提示するが、機能的な差分は無い (対象カラム・UNIQUE性・部分index条件が同一)。
リネームは一瞬 index/制約が消える窓を作るだけで得るものがなく、対応しない。

### 3. 触らない: DB 側を削除すると後退する制約

`alembic check` が「モデルに存在しないので削除」と提示した中に、
`fund_allocations_allocated_amount_usd_check` のような **DB 側にのみ存在し、
実際にデータ整合性を守っている CHECK 制約**が含まれていた。
`alembic check` の "remove" 指示に機械的に従うと安全機構を後退させてしまうため、
対応しない。

### 4. 別途対応: モデル側の型不一致

`ai_decision_features.deterministic_breakdown` について、`alembic check` は
DB 側 (`JSON`) をモデル側 (`JSONB` 提案) に合わせるよう提示しているが、
調査の結果 **DB 側 (`JSON`) が正しく、モデル定義側を直すべき**と判断した。
本 PR の対象外とし、別途モデル修正で対応する。

### 5. 要判断で保留: `smart_wallet_address` の二重 UNIQUE 制約

`users.smart_wallet_address` に `uq_users_smart_wallet_address`
(UNIQUE 制約) と `ix_users_smart_wallet_address` (UNIQUE index) が
**両方とも全行に対する UNIQUE** として存在している。

一方 `models.py` の手動 SQL コメントは、`smart_wallet_address` が
`NULL` を許容するカラムであることを踏まえ、**部分 index
(`WHERE smart_wallet_address IS NOT NULL`)** を意図した記述になっており、
実態 (全行 UNIQUE) と食い違っている。

どちらが正しい意図かは要件・運用（SCW未割当ユーザーが複数存在できるべきか）
に関わる判断が必要なため、本 PR では対応せず、個別に判断する。

## 対応方針まとめ

今回は上記5分類のうち **1. のみ**を修正する
(`fix/prod-schema-drift-wallet-address-unique-index` ブランチ)。
2〜5 は本ドキュメントに記録し、将来個別に判断・対応する。
