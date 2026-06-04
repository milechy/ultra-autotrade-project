# B-2 Slack 5連続FAIL → 電話エスカレーション — 実装状態 (2026-05-25)

> **Status: ALREADY IMPLEMENTED.** Asana B-2 (1214890458060567) のフォローアップ調査。

## TL;DR

- Asana タスク "B-2: Slack 5連続FAIL → 電話エスカレーション設計" の **実装本体は既に main にマージ済**:
  - `backend/app/notifications/escalation.py` (161 lines)
    - `EscalationState` — スレッドセーフな連続失敗カウンタ
    - `SlackEscalationSender` — Slack 失敗時に Twilio へ自動エスカレ
    - default `THRESHOLD=5` 連続 FAIL、`COOLDOWN=30 min`
    - オンコール時間帯定義 (JST 9-22 音声 / 22-9 SMS)
  - `backend/tests/test_escalation.py` (231 lines, **14 tests** カバー)
  - `backend/app/notifications/twilio_sender.py` (170 lines) も実装済

- 追加実装は不要。Asana B-2 は本ドキュメントを根拠に close 可能。

## 確認方法 (再実行可能)

```bash
cd /opt/ultra-autotrade/main
wc -l backend/app/notifications/escalation.py backend/tests/test_escalation.py backend/app/notifications/twilio_sender.py
# escalation.py: 161   test_escalation.py: 231   twilio_sender.py: 170
grep -cE "^def test_" backend/tests/test_escalation.py
# 14
```

## 既存実装のスコープ

| 機能 | 実装場所 | 備考 |
|---|---|---|
| 連続失敗カウンタ | `EscalationState.record_failure()` | thread-safe `threading.Lock` |
| 成功時リセット | `EscalationState.record_success()` | scheduler 復旧で即時 0 戻し |
| 閾値判定 | `EscalationState.try_escalate(cooldown_minutes)` | default 5 連続、30 min cooldown |
| Slack 送信失敗の判定 | `SlackEscalationSender._try_slack()` | network error / 4xx 5xx 共通捕捉 |
| Twilio 電話発信 | `notifications.twilio_sender.TwilioSender` | call / sms 経路あり |
| オンコール時間判定 | escalation.py コメント (実装内) | プライム帯=音声 / オフ帯=SMS |

## Open items (本 PR の対象外、別 Asana 推奨)

1. **B-1 Twilio API 契約 / 料金** (Asana 1214888619973261) — Twilio account / phone number / billing は人間タスク
2. **B-4 自動復旧との連携** — PR #407 (auto_recovery.sh 拡張) で `Pushover priority=2` 経路がある。電話と Pushover の **二重発火回避ルール** は別 PR で運用合意
3. **オンコール時間帯の env 化** — 現状コメントで定義。`docs/ops/oncall_policy.md` への移動 + env override 化は将来改善

## 参照

- Asana **B-2** (1214890458060567)
- `backend/app/notifications/escalation.py` / `tests/test_escalation.py`
- 関連 PR: B-4 系 (PR #407 — auto recovery scope expansion)
- `docs/ops/oncall_policy.md`
