# 孤立コード検出（Dead Code / Disconnected Safety Scan）

> 2026-05-21 refactor で `CLAUDE.md` から分離。

## 背景
爆速開発で安全装置やリスク管理のコードを実装しても、配線（呼び出し元）が切れているケースが発生する。
UIテスト（/chrome）やpytestでは検出できない。2026-04-01に StressController、record_price_change_24h、PENDLE_YTキャップ、execute_evacuation の4件が孤立していた。

## 実行タイミング
- PR作成前（Codex Review前に実行）— 新モジュール追加時は必須
- 大量タスク一括完了後 — 爆速開発後は特にリスクが高い
- DeFi安全系の変更時 — aave/, automation/, protocols/ の変更時

## 実行方法（Claude Codeプロンプト）
プロジェクト全体で「実装されているが呼ばれていない」孤立コードを検出して。
重点チェック対象: backend/app/aave/, automation/, protocols/, ai/
方法: 各モジュールのpublicクラス/関数をリストアップ → grep -r でアプリコード内（tests/除外）の参照確認 → 参照0件=孤立
出力: | ファイル | クラス/関数 | アプリコードからの参照 | 状態(孤立/接続済み) |

## 検出後の対応
- P0: 安全装置系の孤立 → 即修正（workflow.pyやscheduled_tasks.pyに配線）
- P1: リスク管理系の孤立 → 1-2日以内に修正
- P2: ユーティリティ系の孤立 → 将来使用予定なら許容、不要なら削除

## 前処理: repomix でコードベースを 1 ファイルに圧縮（2026-06-11 追加）

孤立コード検出は「各 module の public クラス/関数を grep で参照確認」する作業のため、
対象コードを Claude に一括で渡せると効率が上がる。`scripts/run_repomix.sh` で
リポジトリ（または特定サブツリー）を単一の XML ファイルにパックできる。

```bash
./scripts/run_repomix.sh backend            # backend/ 全体
./scripts/run_repomix.sh backend/app/aave   # 特定サブツリー（推奨）
./scripts/run_repomix.sh .                  # リポジトリ全体
```

- 出力: `repomix-output.xml`（リポジトリ root / `.gitignore` 済み）
- 設定: `repomix.config.json`（除外 `.env*` / `*.key` / `*.pem` / `node_modules` /
  `__pycache__` / `.venv` / `migrations/versions` / `*.lock` 等）
- `enableSecurityCheck: true` により secretlint が機密混入ファイルを**出力から自動除外**する
  （2026-06-11 実測: backend/ パック時に 2 ファイルが除外された）

**トークン量の注意（2026-06-11 実測）**: `backend/` 全体は **544 ファイル / 約 136 万トークン**
（o200k_base 換算）で、単一の Claude コンテキスト（200K）を大きく超える。孤立コード検出で
repomix を使う場合は **サブツリー単位**（`backend/app/aave` / `automation` / `protocols` / `ai`）で
パックするのが現実的。リポジトリ全体を一度に食わせる用途には向かない。

手順（サブツリー単位の Gate 5）:
1. `./scripts/run_repomix.sh backend/app/<module>` で当該 module をパック
2. 生成された `repomix-output.xml` を Claude に渡す
3. 上記「実行方法（Claude Code プロンプト）」の検出プロンプトを実行
4. 重点: `backend/app/aave/`, `automation/`, `protocols/`, `ai/`

## 追加パターン: 部分配線欠陥（factory が constructor 引数を供給しない）
2026-06-02: 「関数は呼ばれているが、生成 factory が必要な属性を供給しない」型の欠陥が
launch ブロッカーになった。`make_aave_client(chain_name=...)`（マルチチェーン経路）が
`Web3AaveClient` に `token_addresses` を渡さず（設定は `if settings is not None:` 経路のみ）、
`build_deposit_txs` / `build_withdraw_tx` が `hasattr(self,"token_addresses")` ガードで
`Unknown asset` を投げ、non-custodial partner build-tx が staging/production とも 500 だった。

**なぜ5ゲートをすり抜けたか（1行）**: unit test は settings 経路 client か mock を使い
マルチチェーン経路の token_addresses 欠落を一度も実行せず、E2E は build-tx 実経路に到達せず、
孤立検出は「参照0件」のみ見て「constructor 引数の供給漏れ」を見ないため、全ゲートが runtime-only
の配線欠陥を検出できなかった。

**検出観点の追加（grep だけでは出ない）**:
- 同一クラスに複数の生成経路（`make_*` factory / `settings` 経路 / 直接 new）がある場合、
  **全経路が同じ必須属性（例: `token_addresses`）を設定するか**を突き合わせる。
- `hasattr(self, "...")` ガードで分岐するメソッドは、その属性を**設定しない生成経路**が
  存在しないか確認（設定箇所と生成箇所の数が一致するか）。
- 重点: `backend/app/aave/client.py` の `make_aave_client` / `make_multi_chain_clients` /
  `get_default_aave_client` が `Web3AaveClient` に同じ属性群を渡しているか。
