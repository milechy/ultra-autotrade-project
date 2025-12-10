# 06_octobot_signal_flow.md
# OctoBot連携仕様

Ultra AutoTrade における  
**AI → OctoBot → Aave** のうち、  
本フェーズで扱う **AI → OctoBot（シグナル連携）** の仕様をまとめる。

---

## 1. シグナル構造（OctoBot 外部API向け・基本形）

OctoBot 外部シグナル API に送信されるペイロードの基本形は次のとおり：

```json
{
  "action": "BUY",
  "confidence": 85,
  "reason": "Positive market sentiment",
  "timestamp": "2025-01-01T00:00:00Z"
}
````

* `action`

  * BUY / SELL / HOLD
  * 判定ロジックは `docs/05_ai_judgement_rules.md` に従う。
* `confidence`

  * 0〜100 の信頼度スコア。
  * 低すぎる場合は「シグナルを送らない（HOLD扱い）」方向で扱う。
* `reason`

  * なぜそのアクションになったかの要約テキスト。
* `timestamp`

  * AI 判定時刻（ISO8601, UTC 推奨）。

---

## 2. コンポーネントと役割

### 2.1 AI モジュール（backend/app/ai）

* `/ai/analyze` エンドポイントを提供。
* 入力: `NotionNewsItem[]`（/notion/ingest の出力）。
* 出力: `AIAnalysisResult[]`

  * `id, url, action, confidence, sentiment, summary, reason, timestamp` など。

### 2.2 OctoBot シグナルAPI（backend/app/bots）

* `/octobot/signal` エンドポイントを提供。
* 入力: `AIAnalysisResult` をベースにしたシグナル配列。
* 処理:

  * 信頼度しきい値 / 連続トレード制限などの安全弁を適用。
  * 送信対象と判断されたシグナルのみ OctoBot 外部 API へ送信。
* 出力:

  * `success_count / skipped_count / failed_count` と、各シグナルのステータス詳細。

### 2.3 OctoBot 外部シグナルAPI

* 本システムからは `bots.client` 経由で HTTP 通信。
* 受け取ったシグナルを元に、戦略の切り替えやポジション調整を行う。

### 2.4 Aave 運用モジュール（別フェーズ）

* BUY → deposit, SELL → withdraw, HOLD → 何もしない
  というマッピングは `docs/07_aave_operation_logic.md` に定義。
* 本ドキュメントでは詳細ロジックには踏み込まず、
  「OctoBot のシグナルが Aave 操作に最終的に影響する」という前提のみ記載する。

---

## 3. データフロー詳細

### 3.1 Notion → AI

1. `/notion/ingest`

   * Notion DB から `Status = 未処理` のニュースを取得。
   * `NotionNewsItem[]` としてバックエンドに返す。
2. `/ai/analyze`

   * `NotionNewsItem[]` を入力として、ニュースごとに AI 判定を実施。
   * `AIAnalysisResult[]` を返す。

* `signals[*]` は `AIAnalysisResult` 相当。
* `id`, `url` は内部トレーサビリティ用の情報として扱う。

3. `/octobot/signal` 内部では `bots.service` が以下を行う：

   * 信頼度がしきい値未満のシグナル → 「skipped（送信しない）」判定。
   * 連続トレード制限・過剰取引ルールに抵触するシグナル → 「skipped」判定。
     （ルール詳細は `docs/08_automation_rules.md` を参照）
   * 送信対象になったシグナル → `bots.client` を通じて OctoBot 外部 API に送信。

### 3.2 AI → /octobot/signal

1. クライアント（もしくはバッチ処理）が `/ai/analyze` の結果 `AIAnalysisResult[]` を取得。
2. `/octobot/signal` に対して、次のようなボディでリクエストを送る：

```json
{
  "signals": [
    {
      "id": "notion-page-id-1",
      "url": "https://example.com/news1",
      "action": "BUY",
      "confidence": 80,
      "reason": "ポジティブなニュースが多く、市場全体の上昇トレンドが継続しているため",
      "timestamp": "2025-12-07T08:09:35.007682Z"
    }
  ],
  "count": 1
}
```
- 200: リクエスト自体は正常に処理された（success/skipped/failed の内訳は details 参照）。
- 400: count と signals.length が不整合など、クライアント入力エラー。
- 500: サーバ内部エラー（OctoBot APIのエラーなど詳細はログで追跡）。


---

### 1-3. `docs/06_octobot_signal_flow.md`

**更新対象**

- シグナル構造
- 処理フロー（安全弁の追加）

**修正案**

```md
## シグナル構造（AI → /octobot/signal）

```json
{
  "action": "BUY",
  "confidence": 85,
  "reason": "Positive market sentiment",
  "timestamp": "2025-01-01T00:00:00Z"
}

※ 実際のリクエストボディでは、これに加えて id, url を含む signals[] 配列として送信する。
処理フロー
1. /octobot/signal エンドポイントが AI からの判定結果（signals[]）を受け取る
2. OctoBotService が以下の安全弁を適用
- 信頼度しきい値チェック（confidence < min_confidence は SKIPPED）
- 1時間以内の同一アクション回数チェック（max_same_action_per_hour を超過した分は SKIPPED）
3. 送信対象のシグナルのみ OctoBot 外部シグナルAPIへ送信
4. 送信結果を success/skipped/failed に集計し、レスポンスとして返す
5. 主要なイベント（送信成功/失敗、スキップ理由）はログに記録される想定


---

### 1-4. `docs/08_automation_rules.md`

**更新対象アイデア**

- 「過剰取引制御」の項目に、現状実装されているレート制限ルールを明文化。

**追記案（イメージ）**

```md
### 2. 過剰取引制御（OctoBotシグナル生成側）

- 信頼度しきい値
  - `confidence < min_confidence` のシグナルは `/octobot/signal` 側で SKIPPED とする。
- 連続トレード制限（Phase3実装）
  - 1時間以内に同一アクション（BUY / SELL / HOLD）が `max_same_action_per_hour` 回を超える場合、
    それ以降のシグナルは `/octobot/signal` 側で SKIPPED とする。
  - Phase3 のデフォルト値: `max_same_action_per_hour = 3`

### 3.3 /octobot/signal → OctoBot 外部API

* `bots.client` は `config.py` で定義された

  * `OCTOBOT_API_BASE_URL`
  * `OCTOBOT_API_KEY`
  * `OCTOBOT_TIMEOUT_SECONDS`
    を用いて外部 API を呼び出す。
* OctoBot には、基本形 `{action, confidence, reason, timestamp}` の JSON を POST する。
* OctoBot 側はこのシグナルをトリガに

  * ストラテジ切り替え
  * 新規ポジション/クローズ
    などを行う（詳細は OctoBot 側の戦略設定に依存）。

---

## 4. AIAnalysisResult からシグナルへのマッピング

`AIAnalysisResult` から OctoBot シグナル構造への対応表：

| AIAnalysisResult フィールド | OctoBot シグナル フィールド | 備考                      |
| ---------------------- | ------------------ | ----------------------- |
| action                 | action             | BUY / SELL / HOLD       |
| confidence             | confidence         | 0〜100 のスコアをそのまま利用       |
| reason                 | reason             | なぜその action になったかの要約    |
| timestamp              | timestamp          | AI 判定時刻（ISO8601, UTC推奨） |
| id                     | （内部のみ）             | ログ・トレース用。外部には送られない場合あり  |
| url                    | （内部のみ）             | デバッグや検証時に参照するための補助情報    |

---

## 5. エラー時の扱い（概要）

### 5.1 安全弁ロジック（送信前）

* 信頼度が内部しきい値未満、または
  `docs/05_ai_judgement_rules.md` / `docs/08_automation_rules.md` で定義された
  過剰取引・連続トレード制限に抵触する場合：

  * `/octobot/signal` 内部で「skipped」として扱い、外部 API には送信しない。
  * レスポンスの `skipped_count` と `details[*].status = "skipped"` に反映する。

### 5.2 外部APIエラー

* OctoBot 外部シグナル API が 4xx/5xx を返却、またはタイムアウトした場合：

  * 対象シグナルは「failed」として扱う。
  * `/octobot/signal` のレスポンスで

    * `failed_count` のカウント増加
    * `details[*].status = "failed"`
    * `details[*].message` にエラー内容（機密情報を含まない要約）を格納。
  * 具体的なリトライ回数・連続エラー時の停止ルールは
    `docs/08_automation_rules.md` と `docs/15_rollback_procedures.md` に従って設計・実装する。

### 5.3 致命的エラー

* バックエンド内部で予期しない例外が発生した場合：

  * `/octobot/signal` は 500 系のエラーを返却。
  * ログにはスタックトレースを記録するが、レスポンスには詳細を含めない。
  * ロールバック／緊急停止条件は `docs/15_rollback_procedures.md` に従う。

---

## 6. ログと監視

* 送信成功・スキップ・失敗それぞれについて、最低限次の情報をログに残す：

  * シグナル ID（`AIAnalysisResult.id`）
  * action / confidence
  * status（sent / skipped / failed）
  * OctoBot からのレスポンスコード（可能な範囲で）
* ログを元に、`docs/08_automation_rules.md` で定義された

  * エラー率
  * 応答時間
  * 連続エラー回数
    などの監視指標を集計し、アラート／緊急停止をトリガする。