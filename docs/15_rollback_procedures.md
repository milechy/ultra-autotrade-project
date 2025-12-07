# 15_rollback_procedures.md  
Ultra AutoTrade – ロールバック手順

---

# 1. ロールバックの目的
誤作動・暴落・通信障害などで  
資金損失を防ぐための“即時復旧”手順。

---

# 2. 取引ステップ別ロールバック

## 2.1 Notion → AI
失敗時は Notion の該当ブロックを “再処理キュー” に移動。

## 2.2 AI → OctoBot
OctoBot API失敗時：

- 3回リトライ  
- 失敗時は “HOLD 判定” 処理に切り替え  
- 同時に手動確認通知

## 2.3 OctoBot → Aave
Aave deposit 失敗時：

- ガスリトライ  
- ガス高騰時は自動キャンセル  
- 失敗ログを Notion に保存  

withdraw 失敗時：

- Gas不足でない場合は即緊急通知

---

# 3. 本番環境のロールバック

## Aave 運用ロールバック

1. 自動運用停止  
2. 資金をステーブルコインに変換  
3. ウォレットへ退避  
4. LINE/Slack通知

---

# 4. バージョン管理ロールバック
GitHub：

- `main` のタグ管理  
- `rollback/vX.Y.Z` ブランチの作成  
- 前バージョンをデプロイ可能

---

# 5. 緊急停止（Emergency Mode）

### 発火条件例
- 価格変動 > 20%  
- ヘルスファクター < 1.6  
- OctoBot応答なし  
- AI API失敗率 > 20%  

### 発動後
- 全処理停止  
- Aave withdraw  
- 通知