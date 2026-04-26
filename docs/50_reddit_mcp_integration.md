# Reddit MCP 統合設計書

**Asana:** GID 1214076983253101 (PoC) / GID 1214077229270464 (本番統合 Due 05-15)  
**ブランチ:** `feature/reddit-mcp-poc-1214076983253101`  
**作成日:** 2026-04-26  
**ステータス:** PoC 完了 / 本番統合は別タスク

---

## 1. 目的

FT Pipeline の AI 判定コンテキストに Reddit の市場センチメントを追加し、
ソーシャルシグナルを BUY/SELL/HOLD 判定の補助情報として活用する。

---

## 2. Reddit MCP 選定

### 2.1 候補比較

| 実装 | 方式 | 認証 | Python 互換 | ライセンス | メンテナンス |
|------|------|------|-------------|------------|-------------|
| **公開 JSON API** (採用) | HTTP GET | 不要 | ◎ `requests` | Reddit ToS | N/A (公式) |
| **PRAW** (本番推奨) | OAuth2 + REST | 要 | ◎ pip install | BSD-2 | 活発 (★5k+) |
| eliasbiondo/reddit-mcp-server | MCP stdio | 不要 | △ Node.js | MIT | 小規模 |
| Arindam200/reddit-mcp | MCP stdio | 要 (PRAW) | △ Node.js | MIT | 小規模 |
| GeLi2001/reddit-mcp | MCP stdio | 要 (官API) | △ Node.js | MIT | 小規模 |

### 2.2 PoC 採用: 公開 JSON API

- **理由:** 認証設定なしで即起動可能。PoC/試験導入フェーズに最適
- **制限:** 10 req/min（未認証）、ページネーション制限あり
- **ToS:** 非営利・ローボリューム利用は明示許可

### 2.3 本番推奨: PRAW (Python Reddit API Wrapper)

- **理由:** Python/FastAPI ネイティブ、60 req/min、OAuth2 で堅牢
- **ライセンス:** BSD-2 (商用利用可)
- **メンテナンス:** praw-dev/praw、活発な更新、3k+ issues 対応済み
- **インストール:** `pip install praw==7.x`（backend/requirements.txt への追加は本番統合タスクで）

---

## 3. 認証要件

### PoC フェーズ (現在)

```bash
# 環境変数 1 本のみ
REDDIT_USER_AGENT="ultra-autotrade-ft-pipeline/0.1 (contact: hkobayashi@mooores.com)"
```

### 本番フェーズ (GID 1214077229270464)

Reddit App を作成 → **Script App** タイプを選択:

```bash
# .env.production / .env.staging に追加
REDDIT_CLIENT_ID=xxxxxxxxxxxx         # App 作成後に取得
REDDIT_CLIENT_SECRET=xxxxxxxxxxxx     # App 作成後に取得
REDDIT_USER_AGENT="ultra-autotrade-ft-pipeline/1.0 (by /u/yourbot)"
REDDIT_USERNAME=your_reddit_account   # Script App 用
REDDIT_PASSWORD=your_reddit_password  # Script App 用 (bot 専用アカウント推奨)
```

**App 作成手順:**
1. https://www.reddit.com/prefs/apps → "create another app"
2. Type: "script"
3. redirect uri: `http://localhost:8080` (使用しないが必須入力)

---

## 4. レート制限

| フェーズ | 方式 | 上限 | 対策 |
|---------|------|------|------|
| PoC | 未認証 JSON API | ~10 req/min | REQUEST_DELAY=1.0秒 |
| 本番 | PRAW OAuth2 | 60 req/min | PRAW 自動バックオフ |

- 100 req/10min ウィンドウ（未認証）を超えると HTTP 429
- PRAW は`x-ratelimit-remaining` ヘッダーを読んで自動スリープ
- FT Pipeline は 1 時間ごと実行のため、60 req/min 制限で十分

---

## 5. PoC 実行結果 (2026-04-26)

**スクリプト:** `scripts/reddit_mcp_poc.py`

| subreddit | 直近24h posts | sentiment score | total_score |
|-----------|--------------|-----------------|-------------|
| r/ethereum | 3 | 0.209 | 47 |
| r/defi | 6 | 0.203 | 25 |
| r/cryptocurrency | 19 | 0.208 | 265 |

### r/defi サンプル (直近5投稿)

```
[  3pt] 2026-04-26T04:32 — Decentralized way to swap
[  4pt] 2026-04-25T17:49 — Warning: Deribit silently patches critical security flaws and ghosts t
[  0pt] 2026-04-25T16:27 — understanding single-wallet pumps vs multi-wallet organic volume on pu
[  7pt] 2026-04-25T16:14 — Apple rejects my self-custodial wallet for DEX swaps while MetaMask, T
[  6pt] 2026-04-25T15:46 — How I almost got scammed out of $4000
```

---

## 6. FT Pipeline 統合ポイント設計

### 6.1 統合アーキテクチャ

```
FT Pipeline (~/ft-automation/)
└── ft-pipeline.sh
    └── [新] reddit_sentiment.py       # 本タスクのPoC実装を移植
        ↓ JSON (posts + sentiment score)
    └── [既存] AI 判定プロンプト構築
        └── reddit_context block を追加
            ↓
        Claude / GPT-4o → BUY/SELL/HOLD
```

### 6.2 プロンプトへの組み込みイメージ

```python
# ft-automation/scripts/build_context.py (新規)
reddit_block = f"""
## Reddit 市場センチメント (直近24h)
- r/ethereum: {posts_eth}件, sentiment={score_eth}
- r/defi: {posts_defi}件, sentiment={score_defi}
- r/cryptocurrency: {posts_crypto}件, sentiment={score_crypto}

注目トピック:
{top_titles_formatted}
"""
```

### 6.3 実行タイミング

- **現在の FT Pipeline 実行間隔:** `ft-pipeline.sh` (設定: `EVAL_INTERVAL=30秒`)
- **Reddit fetch 推奨間隔:** 60分ごと（レート制限 + Reddit の投稿頻度を考慮）
- **キャッシュ:** `/tmp/reddit_cache_{timestamp}.json` に 55分キャッシュ

### 6.4 データフロー

```
[Reddit API] → reddit_mcp_poc.py → JSON cache
                                      ↓
                              [55min 以内ならキャッシュ読み取り]
                                      ↓
                              ft-pipeline.sh の AI コンテキストに注入
                                      ↓
                              backend/app/ai/service.py → judge_with_rag()
```

### 6.5 Knowledge Hub への保存 (本番統合タスクで)

```
POST /knowledge/items
{
  "source": "reddit",
  "content": "<title> | score:<n> | r/<subreddit>",
  "metadata": {"subreddit": "defi", "score": 7, "created_utc": 1745670369}
}
```

これにより Knowledge Hub の pgvector 検索で Reddit 投稿を RAG コンテキストとして活用可能。

---

## 7. 本番統合 (GID 1214077229270464) の前提条件

本タスク (PoC) 完了後、本番統合タスクに着手する前に以下が必要:

- [ ] Reddit Bot アカウント作成 (bot 専用、通常アカウントと分離)
- [ ] Reddit Script App 登録 → `REDDIT_CLIENT_ID` / `REDDIT_CLIENT_SECRET` 取得
- [ ] `.env.staging` / `.env.production` に認証情報追加
- [ ] `backend/requirements.txt` に `praw>=7.7.0` 追加
- [ ] `scripts/reddit_mcp_poc.py` を PRAW ベースに書き換え
- [ ] `ft-automation/scripts/reddit_sentiment.py` 作成 (キャッシュ機能付き)
- [ ] `ft-pipeline.sh` に `reddit_sentiment.py` 呼び出し追加
- [ ] `backend/app/ai/service.py` の `judge_with_rag()` に reddit_context パラメータ追加
- [ ] pytest でモック/VCR テスト追加
- [ ] E2E: Reddit センチメント付き AI 判定を Bybit Sandbox で検証

---

## 8. 残課題・リスク

| 課題 | 重要度 | 対応 |
|------|--------|------|
| 週末・祝日は投稿数が少なく感度が低下 | Medium | 投稿数 < 5 件の場合はセンチメントをニュートラル (0.5) に固定 |
| 市場操作目的のスパム投稿 | Medium | スコア < 0 の投稿を除外、bot アカウントフィルタ |
| Reddit API ポリシー変更 (2023実績あり) | Low | フォールバックとして Pushshift / Reddit JASON 公開 API を維持 |
| 日本語コンテンツが少ない | Low | 現フェーズは英語圏センチメントのみ。将来的に r/JapanFinance 追加検討 |
