# 06_octobot_signal_flow.md
# OctoBot連携仕様

## シグナル構造
{
  "action": "BUY",
  "confidence": 85,
  "reason": "Positive market sentiment",
  "timestamp": ""
}

## 処理フロー
1. AIからの判定を受け取る
2. OctoBotの外部シグナルAPIへ送信
3. OctoBotは戦略を切り替えまたはポジション調整
4. ログを記録