# 07_aave_operation_logic.md
# Aave自動運用ロジック

## BUY時
- 預け入れ比率を増やす
- 少額の追加depositを実行

## SELL時
- 一部引き出し
- 安全性チェック（ヘルスファクター）

## HOLD時
- 何も変更しない

## 重要パラメータ
- deposit_amount
- withdraw_amount
- safety_threshold