# Postmortem: 本番 transactions 0件事案 RCA

**発見日時:** 2026-05-15 夜  
**RCA 完了:** 2026-05-18  
**影響範囲:** 本番全ユーザー (id=1,11,16) — AI 提案が届かず取引実行 0件  
**重大度:** High (5/31 ローンチ判断に直結)  
**担当 Lane:** Lane S id=21 (本番運用実体化)

---

## 事象サマリー

5/15 夜に「本番 transactions が 0 件」と発見された。  
調査の結果、AI 判定エンジンは正常動作していたが、**5/7 以降ほぼ全ての AI 判定が HOLD** であり、  
提案 (proposals) が生成されず取引実行経路が完全停止していたことが判明した。

---

## 5/14–5/18 実績データ (本番 postgres 確認値)

| テーブル | 件数 | 備考 |
|---------|------|------|
| ai_decisions (5/7–5/18) | 133 件 | HOLD:132 / BUY:1 |
| proposals (全期間) | 6 件 | 全て `expired` status |
| transactions (全期間) | **0 件** | — |

### ai_decisions 日次件数 (5/11–5/18)

| 日付 | 件数 |
|------|------|
| 2026-05-18 | 6 (調査時点) |
| 2026-05-17 | 10 |
| 2026-05-16 | 1 |
| 2026-05-15 | 12 |
| 2026-05-14 | 15 |
| 2026-05-13 | 15 |
| 2026-05-12 | 11 |
| 2026-05-11 | 4 |

---

## 真因構造

### 原因 A【主因】: AI が HOLD を選び続けている = 取引経路全体が停止

5/7 以降の ai_decisions:
- HOLD: 132 件 (99.2%)
- BUY: 1 件 (5/7 19:57 JST の id=267、同日 proposals を生成)

**AI 判定の実態:**
- Claude (Sonnet 4.6) と GPT-4o の両 LLM が全合意で HOLD
- 理由: "Mixed signals", "low confidence", "bearish signals"
- 平均信頼度: 53.7% (HOLD) / 52.0% (唯一の BUY)
- HOWL エージェント自身が警告: `"AI is overly conservative: 9/10 judgments were HOLD. Consider lowering confidence thresholds or adjusting risk parameters."`

**proposals が作られない理由 (設計通り):**
- `ai_judgment_scheduler.py` は BUY/SELL 時のみ proposals を作成
- HOLD → proposals 作成なし → transactions 実行なし
- これはシステムの正常動作だが **過保守設定** が原因

**AI_MIN_CONFIDENCE_THRESHOLD の現在値:**
- デフォルト: `40` (コード: `backend/app/ai/config.py:131`)
- 本番環境変数 `AI_MIN_CONFIDENCE_THRESHOLD`: **未設定** (デフォルト 40 が適用)
- 本番環境変数 `AI_CROSS_VALIDATION_ENABLED`: `true`
- 本番環境変数 `AI_SHADOW_MODE`: 未設定 (= `false`)
- 本番環境変数 `AI_CLAUDE_MODEL`: 未設定 (= `claude-sonnet-4-6`)

> **段階2 (明日 5/19 Tier S) での Threshold 調整参照用:**
> 現在の HOLD 判定の平均信頼度は 53.7%。HOLD の信頼度が BUY の信頼度より高い状態。  
> Threshold を下げるより prompt の保守性を調整する方向が有効の可能性あり。

---

### 原因 B【副因1】: Perplexity Finance データ検証エラー = AI 品質低下

**エラーログ (本番 backend-blue-production):**
```
Perplexity Finance fetch failed: 5 validation errors for FinanceFeedResult
  Input should be a valid string [type=string_type,
    input_value={'name': 'USDT + USDC mar...‑through to holders.'}, ...]
  Input should be a valid string [type=string_type,
    input_value={'indicator': 'Aave / DeFi activity', ...}, ...]
```

**原因:**  
Perplexity Sonar Pro API が `key_indicators` を `list[str]` ではなく `list[dict]` で返すように変更された。  
`FinanceFeedResult` の pydantic バリデーションが失敗し、常に `"Finance data fetch failed."` にフォールバック。  
Finance context (FED stance / stablecoin risk / key indicators) が AI 判定の market context から欠落し続けていた。

**影響:**  
Perplexity Finance データなしで AI が判断 → リスク評価に使えるマクロ情報が不足 → 保守的 HOLD bias が強化

**修正 (本 PR):** `finance_feed.py:155–163`  
- `key_indicators` を dict の場合は `"name: value"` 形式の文字列に coerce
- `macro_summary` も `str()` で明示キャスト

---

### 原因 C【副因2・別経路】: `rebalance_check_loop` の module エラー = 運用ノイズ

**エラーログ:**
```
Error in rebalance check loop: No module named 'app.notifications.composite'
```

**原因:**  
`backend/app/automation/rebalance_job.py:60` が存在しないモジュール  
`app.notifications.composite.CompositeNotificationService` を import していた。  
`CompositeNotificationService` は実際には `app.notifications.service` に存在し、  
`app.notifications.factory.get_notification_service()` で取得するのが正しい。

**影響:**  
- `rebalance_check_loop` が 10 分ごとにクラッシュ・再試行ループ
- **ただし AI 判定 → proposal 作成の主経路 (`ai_judgment_scheduler.py`) には直接影響しない**
- 運用ノイズ + allocation drift の Slack 通知が届かない状態

**修正 (本 PR):** `rebalance_job.py:60–62, 102–110`  
- `from app.notifications.composite import ...` → `from app.notifications.factory import get_notification_service`
- `notification_service.notify(message)` → `notification_service.send(NotificationMessage(...))`

---

### 原因 D【過去事象】: 5/7 以前の proposals が承認されずに expire

5/6〜5/7 に作成された 6 件の proposals (users 1, 11, 16 × 2日分) が  
24 時間窓で expire した。承認されなかった。

**重要:** これは「5/7 以降 AI が HOLD になってから」は副次的問題に格下げされる。  
5/8 以降は proposals 自体が作成されていないため、expire の問題は発生していない。  
**本事案の主因ではない。**

---

## 修復方針 (3段階)

### 段階1【本日 5/18 night-mode、Tier B、本 PR 内】
1. Perplexity Finance pydantic fix (原因 B 修正) ✅
2. rebalance_job.py composite import fix (原因 C 修正) ✅
- `.env.production` 編集なし
- 本番 deploy は別タスク (本 PR は staging 経由の通常フロー)

### 段階2【明日 5/19、Tier S、別 Lane で claude.ai が起票】
3. AI HOLD bias 調整 (AI_MIN_CONFIDENCE_THRESHOLD / prompt 保守性)
- **山本さんへの事前 DM 必須 (hkobayashi 対応)**
- Aave 設定変更を伴うため Tier S・別 Lane
- 参照: 上記「AI_MIN_CONFIDENCE_THRESHOLD 現在値」セクション

### 段階3【段階2 後、効果観測してから、別 Lane】
4. `proposals.expires_at` 24h → 72h 延長 (Lane A-4 由来、派生タスク3)
- 段階2 で AI が BUY を出すようになってから効果観測
- 本日 night-mode では apply しない

---

## proposals.expires_at 24h 制限について (Lane A-4 との整合)

Lane A-4 は「proposals が expire している」を真因と推定していた。  
本 RCA により「5/7 以前の 6 件が expire した」は **過去事象 (原因 D)** であり、  
5/7 以降は proposals そのものが作成されていないため派生的問題に格下げされた。

`expires_at` の 24h → 72h 延長は **段階3** とし、段階2 の効果観測後に判断する。

---

## ユーザー影響

| ユーザー | 影響 |
|---------|------|
| id=11 山本さん (partner, require_approval) | 承認依頼が 5/7 以降届いていない |
| id=1 hkobayashi (admin, require_approval) | 同上 |
| id=16 test-partner-001 (partner, require_approval) | 同上 |
| id=7,8,17 (auto_execute) | execution_policy が auto_execute でも HOLD なので取引なし |

---

## 山本さんへの状況報告 DM テンプレート (hkobayashi 送信用)

> ※ 実際の DM 送信は hkobayashi の判断。本タスクは案を提供するのみ。

```
山本さん、お疲れさまです。

UAT 状況を共有します。5/7 以降、AI が市場を慎重に見て HOLD を選択し続けているため、
新規の承認依頼が届いていません。これはシステムが過保守設定になっていると判明したため、
明日以降に AI の判定閾値を調整します。調整後、また承認依頼が始まる見込みです。

ご不便をおかけして申し訳ありません。引き続きよろしくお願いいたします。
```

---

## 修正ファイル一覧

| ファイル | 変更内容 |
|---------|---------|
| `backend/app/data_feeds/finance_feed.py` | key_indicators dict→str coerce (原因 B) |
| `backend/app/automation/rebalance_job.py` | notifications.composite → factory.get_notification_service (原因 C) |
| `backend/tests/data_feeds/test_finance_feed.py` | 新規テスト (dict 形式 key_indicators の regression) |
| `backend/tests/automation/test_rebalance_job.py` | 新規テスト (import 解決確認 + 通知パス検証) |
| `docs/postmortems/2026-05-18_transactions_zero_rca.md` | 本ファイル |

---

## 再発防止策

1. **Perplexity API レスポンス形式変更の検出:** `FinanceFeedResult` の検証エラーを Slack 通知化 (既存 best-effort ログには残るが観測しにくい)
2. **rebalance_check_loop の import を mypy で検出:** `# type: ignore[import-not-found]` があったため CI で通過していた → 今後は `# type: ignore` を使わず実在モジュールを import する
3. **AI HOLD 率の週次監視:** HOWL agent が既に警告しているが、dashboard KPI として可視化
4. **proposals expiry 前通知:** 段階3 の `expires_at` 延長と合わせて実装

---

## タイムライン

| 日時 | 事象 |
|------|------|
| 2026-05-06 23:56 JST | proposals 3件作成 (users 1, 11, 16) — SUPPLY 1000 USD |
| 2026-05-07 19:57 JST | proposals 3件作成 (同上) — BUY id=267 がトリガー |
| 2026-05-07 23:56 JST | 5/6 分 proposals expire |
| 2026-05-08 19:57 JST | 5/7 分 proposals expire — 以降 proposals 0件 |
| 2026-05-08〜 | AI HOLD 連続 (Perplexity Finance エラー継続) |
| 2026-05-15 夜 | transactions 0件事案 発見 |
| 2026-05-18 | RCA 完了、Tier B 修正 2件 PR 作成 |
| 2026-05-19 (予定) | 段階2: AI HOLD bias 調整 (Tier S 別 Lane) |
