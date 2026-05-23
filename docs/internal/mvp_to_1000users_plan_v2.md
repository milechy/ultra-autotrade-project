# 企画書 v2: MVP〜1000人 スケール & ハードニング計画
**Date:** 2026-05-23 / **Scope:** MVP launch(5/24)→ Phase A〜D(〜1000人・6ヶ月)
**Predecessors:** v1(議論ベース・未PR) / 4 LLM crowdsource(ChatGPT/Gemini/Grok/Perplexity)
**Status:** v2 ドラフト・claude.ai レビュー後に確定

## 1. v1 → v2 の主要決定事項
1. **Manual UI = 本物の execution gate に**(a 採用、Full Auto 廃止)
   - 理由: 4/4 LLM が「fake UI は JP regulatory + LINE審査で Dangerous」と一致
   - 結果: AI 推奨 → user 承認 → 本人署名 → 執行 のフロー(Tier 0: ChatGPT Trust-tiered Automation の最下層)
   - 副次効果: discretionary management リスク大幅低減 / Privy server-side signing 不要(本人署名で完結)/ LINE審査通過率上昇 / Hermes 学習データ(approval pattern)が強力に
2. **staging/prod 物理分離 = launch 翌日(5/25)から開始**
   - 現状: 同一 Hetzner VPS(7.6GB)に同居・docker/CPU/RAM/swap 共有
   - 5/22 OOM の根本原因
   - 移行: 新規 Hetzner VPS(prod 専用・16GB)・5/26-27 完了目標
3. **法務 = 確認済(metadata は docs/internal/legal_review_status.md に記録予定)**
   - 構造変更((a) 採用)で discretionary 疑惑 大幅低減 → 4/4 LLM の警告レベルも下がる

## 2. 7本柱(v1 から維持)
H1 SSOT + drift / H2 isolation / H3 型・境界 / H4 テスト中段 / H5 失敗モード / H6 並行性 / H7 自動化

## 3. ツール採用 Wave(v2 確定)
### Wave 1(即採用)
uv / ruff / pnpm / **Serwist (next-pwa 置換 — 4/4 LLM consensus)** / OrbStack(Mac local)/ Doppler or SOPS / Renovate / gitleaks / semgrep / Sentry / Better Stack / Healthchecks.io / LiteLLM+Helicone / **@line/liff SDK + LINE Messaging API SDK + web-push** / **Cloudflare Turnstile (LIFF endpoint 保護・Gemini 提案)** / **Tenderly (Wave 2→1 格上げ、tx sim MVP 必須)** / **BrowserStack or LambdaTest (LIFF 実機テスト・ChatGPT 提案)**
### Wave 2(post-MVP)
Grafana Cloud / PgBouncer / arq(judgment queue)/ Atlas / Lighthouse CI / **OPA or Cedar (policy engine 強化・ChatGPT 提案)**
### Wave 3(200-1000人)
OpenTelemetry + Tempo / wal-g or pgBackRest / read replica / external security audit / **Aave Oracle monitoring の高度化(Perplexity 指摘 $27M 事故)**
### 採用しない / 触らない
Bun / Litestar / Fly.io / Supabase 直接 / k8s / 自前 KMS / **LINE Pay(2025/04 終了・Grok 指摘)** / Managed PaaS 移行(Gemini 提案だが Hetzner 維持でコスト優位、Phase C で再評価)

## 4. フェーズ別実装プラン(v2 改訂)
### Phase 0(今〜5/24 MVP launch)
- (a) 採用後の MVP design: AI 推奨 + user 承認 + 本人署名
- 既存 PR 完走: #376/#377/#378/#379/#381/#382 merge → prod pull
- Asana 19 + 6 タスク並列実行(master prompt v2 で 8-12 PR 起票)
- 安全4点 + 新規 P0-7 (policy engine) / P0-10 (LINE Messaging API 承認通知) / P0-11 (Oracle monitoring) / P0-12 (ITP wipe re-auth)
- 法務確認内容を P0-9 で記録
### Phase A(launch 翌日 5/25 開始・1-2週)
- ★ staging/prod 物理ホスト分離(P0-8)= 最優先
- uvicorn workers 増(compose の `--workers` 修正)
- DB pool tuning(pool_size=20, max_overflow=40)
- CF Pages 切出し開始(#380 設計→実装)
- LiteLLM + Helicone 統合(LLM コスト最適化)
- pre-commit + drift detection cron
- Bot 接続点設計(統合は Phase B)
### Phase B(50-200人・1-2ヶ月)
- AI judgment loop asyncio + Semaphore 並列化 → arq queue 化
- async SQLAlchemy 段階移行 / PgBouncer / read replica
- Grafana Cloud 移行
- LINE Bot 統合(再エンゲージ rail)
- 失敗モード taxonomy 全パス展開
- Trust-tier 1: bounded rebalance(opt-in でユーザーが部分自動化を選択可)に拡張
### Phase C(200-1000人・3-6ヶ月)
- LLM tier 別最適化 / dedicated RPC(Alchemy 等 + secondary)
- SRE プロセス / 外部 audit
- OpenTelemetry trace
- Trust-tier 2 評価
### Phase D(1000人+)
- ホットパス分離 / multi-region 必要時 / Trust-tier 3 評価

## 5. セキュリティ最低ライン(v2 強化)
- Privy 非カストディ + **本人署名(scoped delegated 不要に変更・(a) 採用効果)**
- Doppler/SOPS / Tenderly tx sim / semgrep+Trivy+gitleaks CI / PITR backups
- **emergency_stop + HF<1.6 自動 + Oracle 異常自動 pause(P0-11)**
- **Policy engine による pre-sign checks(P0-7)= 4/4 LLM consensus の最大 missing piece**
- **7日 ITP wipe 対応 re-auth フロー(P0-12)**
- launch 後規模拡大時に外部 audit + Type II 業者パートナー検討(Phase C-D)

## 6. コスト試算(v2 確定)
| 段階 | 月額 | 支配項目 |
|---|---|---|
| MVP(10人) | $30-80 | VPS + LLM(少) |
| 100人 | $200-800 | LLM + Privy MAU + LINE Messaging API |
| 1000人 | $2000-11000 | LLM 70-80%(最適化で 30-50% 減可) |

## 7. 4 LLM Crowdsource からの追加採用 / 不採用
### 採用(consensus 4/4)
- Manual UI = 本物に gate / staging/prod 物理分離 / Transaction Policy Engine / AI と signer の分離 / next-pwa → Serwist / LINE審査リスク認識 / Web Push 主軸でない / WKWebView 7日 ITP wipe / LINE Pay 諦め / dedicated RPC 早期化
### 採用(単独 LLM 高 signal)
- Aave Oracle monitoring(Perplexity・$27M 実例)/ Degradation matrix(ChatGPT)/ Synthetic portfolio replay(ChatGPT)/ Operational explainability(ChatGPT)/ JS bundle 200KB(ChatGPT)/ Localized JP onramp(Gemini)/ Cloudflare Turnstile(Gemini)/ ITP wipe 対応(Gemini)/ Trust-tier 段階(ChatGPT)
### 不採用 + 理由
- Node/Go rewrite(Grok 単独 1/4)→ 残り 3 LLM は言語変更を勧めず・前回議論で確定
- Managed PaaS 全面移行(Gemini)→ コスト 5-10倍、ユーザー指定「コスト極小化」と矛盾、Phase C 再評価
- Type II Financial Instruments License(Grok)→ (a) 採用で discretionary 疑惑減・法務確認済の上で運用、規模拡大時に再評価

## 8. 既存 Asana タスクとの対応マップ
- [OPS] PR #382 merge / 5/23 21:19 deploy = Phase 0 完走
- [MVP-P0-1〜6] 安全4点 + 学習データ schema = Phase 0
- [MVP-P0-7〜12] 新規(v2) = Phase 0
- [MVP-P1〜P5] = Phase 0 実装(P5 は (a) 反映で「本物の gate」に書換要)
- [MVP-P3-PoC] = (a) 採用で Phase B/不要に
- [MVP-P3] = (a) 採用で「user 承認型 execution」に書換要
- [MVP-P6] = launch 前 法務 metadata 記録(P0-9)
- [OBS-BACKEND/OPERATIONS] = Phase A〜継続

## 9. リスク・避けるべき罠
1. **「気をつける」依存**(本セッション §25 失敗パターン・3回発生)
2. rewrite で全部解決(言語変更)
3. vendor lock-in 軽視
4. VPS コストばかり気にして LLM コスト放置
5. セキュリティを「後で audit」
6. Lane 要約を承認扱い(memory: paste-verbatim-not-summary)
7. prod 状態を実機未確認で「完了」と書く(memory: prod-steps-not-done-until-verified)

## 10. メモリ参照
- disable-scheduler-flag-inverted / prod-steps-not-done-until-verified / paste-verbatim-not-summary

## 11. 次アクション
1. master prompt v2(本日 chat 出力)で 8-12 PR 並列起票(Claude Code TUI + --dangerously-skip-permissions)
2. 5/24 朝までに Phase 0 完了
3. 5/24 夜 MVP launch(現単一ホスト + 安全策で運用)
4. 5/25-27 で staging/prod 物理分離
5. soak 期間中に [OBS-BACKEND][OBS-OPERATIONS] 立ち上げ
