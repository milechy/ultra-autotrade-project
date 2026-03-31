# 01_requirements.md
# 要件定義（Requirements）

## 機能要件

### 1. 情報入力（Notion）
- ニュースURLをNotionに貼ると自動で取得する
- AI判断の結果をNotionに書き戻す

### 2. AI判断
- ニュース本文を取得・解析
- BUY / SELL / HOLD を決定
- 信頼度スコア（0〜100）付与
- 判定根拠の要約

### 3. OctoBot連携
- AI判断を外部シグナルとして送信
- OctoBotが判断に従って戦略を選択可能にする

### 4. Aave自動運用
- BUY → 預け入れ増加
- SELL → 引き出し処理
- HOLD → 何もしない
- 安全性チェック（LTV、残高）

### 5. 自動化・保守性
- データ自動バックアップ
- 24時間監視
- 障害時にLINE通知
- 日次レポート自動生成

### 6. 管理画面
- AI判断履歴
- 運用実績
- Aave残高
- エラーログ

## 非機能要件
- 安定稼働
- エラー耐性
- コード可読性
- セキュリティ（秘密鍵管理）

## 優先度
- P1：Notion→AI判断→OctoBot→Aave の基本連携
- P2：自動化（監視・通知）
- P3：管理画面
- P4：高度分析・最適化
## ユーザー運用モード（2026-03-23追加）

### モード定義

| UI表示 | user_mode | execution_policy | 動作 |
|--------|-----------|------------------|------|
| 完全おまかせ | `managed` | `auto_execute` | AI判定→リスクチェック→Aave自動実行→LINE通知 |
| アクティブ | `active` | `require_approval` | AI判定→提案作成→ユーザー承認待ち→Aave実行 |
| Pro（将来） | `pro` | `proposal_only` | AI判定→提案作成のみ（実行しない） |

### 設計原則

- `user_mode`（UI層）と `execution_policy`（オーケストレーション層）を分離
- モード変更時に `execution_policy` は自動連動（API側で強制）
- HF < 1.6 の緊急時は `execution_policy` に関わらず `auto_execute` 強制
- 提案タイムアウト: 1時間経過で自動キャンセル

### API

- `GET /api/user/settings` — `user_mode`, `execution_policy` を返す
- `PUT /api/user/settings` — `{ user_mode: "managed" | "active" }` でモード変更

### オンボーディング

- 初回: `/user/onboarding` でモード選択（2カード形式）
- 選択後: `/user/dashboard` にリダイレクト
