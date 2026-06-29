# LINE審査 デモ準備手順（審査担当者に「機能が動く」と見せる）

> 背景: 実機調査(2026-06-29)で、LINE審査担当者が staging-v4 を触っても
> **「残高$0・提案なし・データなし」の空画面**になることを確認。crypto系は
> 実機ハンズオンで確認されるため、空画面＝「サービス内容が確認できない」で却下リスク大。
>
> 真因: 審査担当者は毎回「自分のLINEアカウント」でログイン＝毎回まっさらな新規ユーザー。
> 新規ユーザーは fund_allocation 無し → 提案生成の対象外 → 提案ゼロ。提案取得は self-only
> RBAC のため他人(user 3/10)の提案も見えない。

## 対策（2本立て）

### ① デモ自動シード（実機で見せる）— PR #901
新規LINEユーザー作成時に **サンプルAI判定(BUY 86%)＋保留中提案(SUPPLY USDC 1000)** を
自動投入。審査担当者が初回ログイン直後にホームで「AIが運用提案を出す」挙動を確認できる。

**デプロイ手順（staging-v4・審査前）:**
```bash
# 本番VPS staging-v4 backend に env を追加して再作成（本番には設定しない）
cd /opt/ultra-autotrade
# .env.staging-v4 に追記（printf で改行保証 / sed -i 禁止）
printf '\nSTAGING_REVIEW_DEMO_SEED=true\n' >> .env.staging-v4
docker compose -p ultra-autotrade-staging-v4 -f docker-compose.staging-v4.yml \
  up -d --no-deps --force-recreate backend
# 検証: 新規LINEログイン → ホームに AI判定 + 保留中提案が出ること
```
※ 二重ガードで `APP_ENV=production` では仮に設定されても no-op。本番は無設定でよい。
※ 実行(on-chain tx)はサンプルのため発生しない。CURRENT ASSET(オンチェーン残高)は$0のまま
（入金導線は別途「入金してください」で見せる）。

### ② 説明資料の添付（事前相談 / 審査に同梱）— フォームが明示的に許容
実機が空でも「何ができるか」を示す資料。user 3/10（提案データ有り）or デモシード後の画面で撮影。

**撮影する画面/フロー（スクショ + 任意で短い画面録画）:**
1. LINEログイン → 6項目の同意ゲート（規約/リスク/非カストディアル/年齢18+）
2. ホーム: AI判定カード（BUY/HOLD + 確信度 + 理由）
3. ホーム: 保留中AI提案カード（SUPPLY USDC + 金額）
4. 提案を「承認」→ 自己署名 → 実行（自分のウォレットで実行される非カストディアルの流れ）
5. 入金パネル（Privy fundWallet）/ MyWallet（Non-Custodialバッジ・自分のアドレス）
6. 規約・プライバシー・特定商取引法ページ

各スクショに「AIは提案のみ・実行は利用者が都度承認・資産は利用者のウォレットに保持」を注記。

## Perplexity 400（参考・後続改善）
- Macro Agent が依存する Perplexity API が **一過性400**（200と6分おき交互。モデル名
  `sonar-pro`/`sonar`は正しい・401クォータ切れではない）。retry 4回が全部一過性400を引くと
  macro が空→60分HOLD固着。
- 審査デモには **staging relax フラグ + デモシードで BUY/提案が出る**ので、Perplexity は
  審査ブロッカーではない。本番ローンチ前に「標準A: fetch失敗時に前回成功キャッシュを保持
  （空フォールバック回避）」で恒久対応推奨（`data_feeds/finance_feed.py`）。

## 審査前チェックリスト
- [ ] PR #901 main マージ → staging-v4 へデプロイ + `STAGING_REVIEW_DEMO_SEED=true`
- [ ] 新規LINEログインでホームに AI判定+提案が出ることを実機確認
- [ ] 説明資料（スクショ/録画）作成
- [ ] PR #900（法務/リジェクト対策）main マージ → staging-v4 反映
- [ ] 審査用LIFF(2010494865)で frontend 再ビルド（提出直前の最後の1手）
- [ ] LINE事前相談フォーム提出（docs/63）

> 関連: docs/63（事前相談フォーム記入）/ MEMORY `project_staging_v4_proposals_always_hold`,
> `project_line_miniapp_review_readiness`
