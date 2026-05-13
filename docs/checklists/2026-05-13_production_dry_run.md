# 5/13 12:30-13:30 Production Dry Run (test-partner-001 / id=16)

## 目的
山本さん UAT 14:00 開始前に、production で 1 サイクル運用の全パスが
動作することを小林さん本人で実機確認。

## 前提
- 5 PR(A/B/C/D/E)production 反映完了(11:30 frontend / 12:00 backend deploy)
- 焼き込み確認済(各 PR の実装文字列 grep)
- /health 5 連続 200 確認済

## アカウント
- email: test-partner-001@example.com (production / id=16)
- パスワード: 1Password / yamamoto_password_*.txt の隣に保管想定
- role: partner / execution_policy: require_approval / risk_mode: conservative

## 1. ログイン (12:30-12:35)

- [ ] https://app.ultra-auto-trade.com にアクセス
- [ ] ログイン画面が表示される(白画面でない)
- [ ] email + password でログイン
- [ ] /partner/dashboard へ遷移
- [ ] エラートースト無し
- [ ] UserHeader に email + Wallet badge "未接続" 表示

### NG 時の即時対応
- 白画面 → backend /health 確認 + nginx log 確認
- ログアウト無反応 → PR #210 焼き込み失敗の可能性 → frontend deploy 再実行検討
- ログイン 401 → backend /auth/login response 確認

## 2. 設定画面 (12:35-12:45 / ストリーム E 確認)

- [ ] /partner/settings 遷移
- [ ] execution_policy 表示: 「手動承認」(require_approval 想定)
- [ ] トグルボタン押下 → 「自動実行」に変更
- [ ] PUT /api/user/settings → 200
- [ ] DB users.execution_policy が auto_execute になる
- [ ] 再度トグル → require_approval に戻す + DB 確認

### 検証 SQL
```sql
ssh ultra@77.42.46.155 docker exec ultra-autotrade-postgres-production \
  psql -U ultra -d ultra_autotrade -c \
  "SELECT id, email, execution_policy FROM users WHERE id = 16;"
```

## 3. Wallet 接続 (12:45-12:55 / ストリーム A 確認 / 最重要)

- [ ] MetaMask 接続(Base Mainnet 8453)
- [ ] /partner/settings#wallet で「ウォレット接続」ボタン押下
- [ ] Privy + MetaMask 接続フロー完走
- [ ] toast "Wallet 接続完了"
- [ ] DB users.wallet_address が更新される
- [ ] DB users.privy_did が更新される
- [ ] UserHeader Wallet badge "接続済" に変化

### 検証 SQL
```sql
SELECT id, email, wallet_address, privy_did FROM users WHERE id = 16;
```

## 4. Dashboard 3 endpoint (12:55-13:05 / ストリーム B 確認)

- [ ] /partner/dashboard 表示
- [ ] /users(紹介者管理): エラー無し / ReferralUserItem 型整合
- [ ] /ai/accuracy: 数値表示(0% でも値が出ていればOK)
- [ ] allocation_service Aave RPC fallback: total_supply=0 でも 999 fallback で表示
- [ ] console error 無し
- [ ] Network tab で 3 endpoint いずれも 200

## 5. AI 提案画面 (13:05-13:15 / ストリーム C+D 確認)

- [ ] /partner/approve 遷移
- [ ] 「承認待ち提案」表示の有無確認
- [ ] 既存 proposal あれば内容確認
- [ ] 無ければ強制 trigger(staging-new で確認済の SQL or CLI)
  - 例: `docker exec ... python -m app.scripts.force_ai_judgment`
- [ ] 通知ログ確認: notification_logs に user_id=16 紐付き行追加
- [ ] LINE 通知有無(設定済なら)

### 検証 SQL
```sql
SELECT id, user_id, kind, status, sent_at FROM notification_logs 
WHERE user_id = 16 ORDER BY id DESC LIMIT 5;

SELECT id, user_id, status, proposal_type, created_at FROM proposals
WHERE user_id = 16 ORDER BY id DESC LIMIT 5;
```

## 6. USDC 入金 + Aave Supply (13:15-13:25 / 任意)

- [ ] BaseScan で test-partner-001 wallet 残高確認
- [ ] $10-50 USDC 入金 (小林さんの test wallet から)
- [ ] AI 提案 BUY が出現するか(または既存提案を承認)
- [ ] 承認 → Aave SUPPLY 実行
- [ ] proposals.status = executed
- [ ] portfolio に supply 反映

## 6.5 wallet address 露出確認 (12:30-13:30 / 必須追加 / 5/13 緊急)

PR #226 (9d2462e) の TC-K-1/K-2 が skip / mock 不整合のため、本日 dry run で人間目視確認。
docs/13_security_design.md L311 はログマスク要件のみ明文化、UI 露出禁止は未明文化。

- [ ] /partner/users 表示状態で view source
- [ ] HTML 上で grep "0x[a-fA-F0-9]{40}" / grep "tx_hash" 確認
- [ ] Network tab で /api/partner/users response 内容確認
  - wallet_address フィールドが含まれていない or マスクされているか
- [ ] UserDetailModal 開いて wallet 露出有無確認

露出あり → 即 rollback + 5/14 再対応 (TC-K-1 mock route 正常化 + 法務要件明文化)
露出なし → 山本 UAT GO

## 7. 総合判定 (13:25-13:30)

- [ ] 上記 1-5(必須)全 PASS → 山本さん UAT 14:00 GO 判定
- [ ] 6 (任意) PASS なら万全
- [ ] NG 項目があれば対応判定:
  - 軽微(表示崩れ等)→ 山本さんに事前共有して UAT 進行
  - 中度(API エラー)→ 14:00 順延 30 分 + hotfix
  - 重大(ログイン不可・Wallet 接続不可)→ 5/14 順延(2 回目)+ rollback 判定

## 失敗時の rollback プロトコル

- ストリーム A NG → PR #221 revert + 旧 frontend image deploy
- ストリーム B NG → backend allocation_service revert
- ストリーム C NG → main.py 旧版 revert(scheduled_tasks 一時停止)
- ストリーム D NG → templates.py 通知配線 revert
- ストリーム E NG → execution_policy 表示 revert(機能停止)

docs/15_rollback_procedures.md 参照(F-17a 期間留意あり)

## 山本さん DM トリガー (13:30)

dry run 1-5 全 PASS → 13:30 に小林さん本人で山本さん DM 送信
「本日 14:00 から UAT 1 サイクル運用可能になりました」(§10 で claude.ai は文案作成しない)

## ファクトシート参照
詳細は Asana GID 1214697096968528 (山本さん伝達ファクトシート)
