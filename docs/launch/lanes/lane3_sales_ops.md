# Lane 3: 営業チーム運用 docs (SOP / 顧客対応フロー)

## メタ情報

| 項目 | 値 |
|---|---|
| Lane | 3 / Phase「ローンチ前 営業オペレーション準備」 |
| Tier | **B** (`docs/sales/` 新規 markdown のみ) |
| auto-merge | **OK** (DoD 全通過時) |
| night-mode 投入 | **22:00 以降 〜 翌 03:00** (想定所要 4-5 h) |
| owner | Claude Code CLI bg lane (sonnet 4.6) |
| 関連 roadmap | `docs/launch/roadmap_to_launch.md` §3 Lane 3 + handoff §既知ブロッカー「営業チーム運用 docs」 |

## 🚀 営業デモ環境 (2026-05-21 完成)

**URL**: **https://demo.ultra-auto-trade.com** (Cloudflare Pages、Custom domain 設定済)

ログイン不要、URL を開けば自動的に partner 視点で全画面閲覧可能。営業先への展開は本日から可能。

**詳細**: `docs/sales/demo_url_guide.md` (営業向けガイド: 5 + パートナー専用 5 画面のトーク例、FAQ、案内テンプレ)

**営業展開時の制約 (必ず把握)**:

- ログイン不要、URL を開けばパートナー視点で全画面閲覧可能 (デモ用 partner ユーザーで自動ログイン状態)
- 日本語のみ (国際化 en は無効)
- 招待リンク `/r/<code>` は静的画面のため機能しない (代替: `/auth/register?ref=xxx` 直叩き)
- リアルタイム更新なし (mock データの静的表示、再読み込みで値は変わらない)
- データは全て架空 (sample data、本番実データは一切含まれない)
- 本番への影響なし (デモ操作は本番 backend / DB に届かない)

**関連 PR / commit**:
- PR #326 (`demo/frontend-mock`): MOCK_MODE 基盤実装
- PR #335 (`demo/frontend-static`): Cloudflare Pages static export 対応
- commit `0e33c34`: useAuth bypass (login 不要化)
- commit `db5d03f`: partner 5 画面のデータ表示 + テスター管理 white screen 解消

## /goal

**Ultra AutoTrade のローンチ後を見据えた営業チーム運用 SOP と顧客対応フローを `docs/sales/` 配下に整備する。** ローンチ時点で営業チーム (現状: 小林さん + 想定パートナー営業) が困らないオペレーション基盤を作る。**機能仕様書ではなく、運用 SOP** (誰が・いつ・何を・どう操作するか) に scope を絞る。

## 触るファイル (Tier 抵触チェック)

| ファイル | 種別 | Tier | 抵触 |
|---|---|---|---|
| `docs/sales/README.md` | 新規 (index) | B | なし |
| `docs/sales/customer_onboarding_sop.md` | 新規 | B | なし |
| `docs/sales/incident_response_for_sales.md` | 新規 | B | なし |
| `docs/sales/escalation_matrix.md` | 新規 (誰に何をエスカレ) | B | なし |
| `docs/sales/faq_for_customers.md` | 新規 | B | なし |
| `docs/sales/role_responsibilities.md` | 新規 (営業 / 開発 / 法務の役割分担) | B | なし |
| **コード変更** | — | — | **なし** (docs のみ) |

## 前提確認 (Lane 開始直後、15 min 以内)

```bash
cd /opt/ultra-autotrade/main

# 1. 既存営業 / 運用関連 docs の探索
find docs -name "*sales*" -o -name "*operation*" -o -name "*onboarding*" -o -name "*customer*" 2>/dev/null

# 2. 既存 partner / tester guide の通読対象確認
ls docs/*partner* docs/*tester* docs/2*_partner* docs/2*_tester* 2>/dev/null

# 3. 既存 incident response 関連
ls docs/15_rollback_procedures.md docs/29_tunnel_ops_guide.md docs/postmortems/ 2>/dev/null

# 4. オンコールポリシー (CLAUDE.md §オンコールポリシー)
grep -A 30 "オンコールポリシー" CLAUDE.md | head -40
```

**既存 docs を必ず通読**: 重複作成を避け、営業 docs はあくまで「営業視点の navigation 層」として実装する。技術詳細は既存 docs に link する。

## 実装手順

### Step 1: 営業チームの想定構成と現状把握 (45 min)

`docs/sales/role_responsibilities.md` に以下を明文化:

| 役割 | 想定担当者 | 主な責務 |
|---|---|---|
| 営業 (代表) | 小林さん | 顧客窓口 / 契約 / 入金確認 |
| 営業 (パートナー) | TBD (Asana 「partner」検索結果) | パートナー経由の顧客紹介 |
| 開発 (実装) | 開発チーム (Claude Code Lane 含む) | システム改修 / 障害対応 |
| 法務 | 森先生 (Lane 4 連携) | 契約レビュー / コンプライアンス |
| 監視 (オンコール) | 小林さん (1 人プロジェクト、CLAUDE.md §オンコールポリシー) | コアタイム 09:00-22:00 / 夜間ベストエフォート |

**山本さん**は「テスター」であって営業ではない。混同しないよう明示。

### Step 2: 顧客オンボーディング SOP (60 min)

`docs/sales/customer_onboarding_sop.md`:

```markdown
# 顧客オンボーディング SOP (v1, 2026-05-20)

## 適用範囲
- パートナー経由の新規顧客
- ローンチ後 (2026-06-03 想定) のフロー

## フロー
1. 問い合わせ受領
   - チャネル: TBD (メール / Slack / Asana)
   - 一次受付: 営業 (代表)
2. 適合性確認 (KYC / risk profile)
   - チェックリスト: docs/legal/ 配下 (Lane 4 連携)
   - 法務的 NG なら森先生にエスカレ (escalation_matrix.md 参照)
3. 契約 (法務確定後)
4. アカウント作成
   - 手順: docs/23_partner_test_guide.md または最新版を参照
   - admin 操作: 小林さんのみ
5. 初期入金確認
6. UAT 期間 (14 日想定、roadmap §1 条件 4 と同じ)
7. 本番運用開始

## 各ステップで使う docs
| Step | 参照先 |
|---|---|
| 1-2 | docs/sales/faq_for_customers.md |
| 3 | docs/legal/ (Lane 4) |
| 4-5 | docs/23_partner_test_guide.md |
| 6 | docs/14_test_strategy.md §UAT |
| 7 | docs/22_production_release_checklist.md |
```

### Step 3: 障害対応フロー (営業視点) (60 min)

`docs/sales/incident_response_for_sales.md`:

```markdown
# 障害対応 (営業視点) SOP

## 営業が「障害かも」と感じたとき

1. 顧客から「使えない」「金額が変」「アラート来た」等の連絡受領
2. ステータス確認:
   - https://api.ultra-auto-trade.com/health で外形確認
   - Slack #ultra-auto-project の直近通知を見る
3. 判定:
   - 既知障害 (Slack 通知 / postmortem あり) → 顧客に「対応中」を 30 分以内に返信
   - 未知障害 → 開発エスカレ (escalation_matrix.md)
4. 報告: 顧客対応の記録を Asana に残す

## やってはいけないこと (営業側)
- 顧客に「private key を教えてください」と言わない (Ultra は秘密鍵を顧客から預からない)
- 顧客の wallet 操作を代行しない (法務リスク)
- Aave / Lido / Pendle の操作を独断で行わない (HF < 1.6 ハード停止等のため)
- 「すぐに復旧します」と確約しない (障害の規模が分かる前)

## 既知障害 docs (関連 postmortem への link)
- 2026-05-09 staging api 502
- 2026-05-12 uat blocker full day failure
- 2026-05-12 nginx upstream ip pin
- 2026-05-17 loki postgres cascade
- 2026-05-17 backup silent failure
```

### Step 4: エスカレーション matrix (30 min)

`docs/sales/escalation_matrix.md`:

| 事象種別 | 第一報告先 | 第二エスカレ | SLA |
|---|---|---|---|
| 顧客苦情 (機能) | 開発 (Slack) | 小林さん | コアタイム 30 min |
| 顧客苦情 (法務) | 森先生 (DM) | 小林さん | 24 h |
| システム障害 (P0) | Slack #ultra-auto-project 自動通知 | Pushover High | コアタイム 30 min / 夜間翌朝 |
| 資金関連 (HF / 損失) | 緊急停止フラグ自動発動 | 小林さん即時連絡 | 即時 |
| パートナー営業対応 | 小林さん | (パートナー営業担当 TBD) | 24 h |
| 法務文書 / 規約改訂 | 森先生 | 小林さん | 5 営業日 |

### Step 5: 顧客向け FAQ (60 min)

`docs/sales/faq_for_customers.md` 構成案:

```markdown
# 顧客向け FAQ (v1, 2026-05-20)

## サービス概要
- Q. Ultra AutoTrade は何をしますか?
  - A. (1-2 行で、過大広告にならない範囲)
- Q. 私の資金はどこに置かれますか?
  - A. wallet は自分で管理。Aave V3 (Polygon/Arbitrum 等) で運用

## セキュリティ
- Q. 秘密鍵は預けますか?
  - A. 預けません (CLAUDE.md §Security Rules)
- Q. ハッキングされたらどうなりますか?
  - A. (現実的な答え、Aave V3 自体のリスクと Ultra 固有のリスクを区別)

## 運用
- Q. HOLD ばかりで取引が走らないのですが?
  - A. (HOLD bias v4 と 5/19 PR #302 の文脈)
- Q. AI が自動で勝手に取引するのですか?
  - A. (人間承認フロー / approval_rate / Slack approval bot の説明)

## 解約 / 引き出し
- Q. すぐに引き出せますか?
  - A. (Aave の cooldown / liquidity の制約)

## 推測しないこと
- 数字 (運用利回り、収益見込み、損失上限) は **本番運用データが出るまで一切記載しない**
- 「絶対安全」「必ず儲かる」等の表現を含めない (景表法 / 金商法 リスク)
```

### Step 6: README + 全体 navigation (30 min)

`docs/sales/README.md`:

```markdown
# docs/sales/ — 営業チーム運用 docs

## 目的
ローンチ後の営業オペレーションを支える navigation 層。技術詳細は既存 docs に link する。

## 主な docs
- [顧客オンボーディング SOP](customer_onboarding_sop.md)
- [障害対応 (営業視点) SOP](incident_response_for_sales.md)
- [エスカレーション matrix](escalation_matrix.md)
- [顧客向け FAQ](faq_for_customers.md)
- [役割分担](role_responsibilities.md)

## 関連 (外部)
- ローンチロードマップ: ../launch/roadmap_to_launch.md
- 法務 (森先生): ../legal/
- セキュリティ設計: ../13_security_design.md
- パートナーテスト: ../23_partner_test_guide.md
- オンコールポリシー: ../../CLAUDE.md (§オンコールポリシー)

## 更新ルール
- ローンチ前 (現在): 推測ベースの数字は記載禁止
- ローンチ後: 実運用データを 1 ヶ月以上集めてから FAQ の数字部分を更新
- 顧客苦情パターン: 30 日に 1 度集計して FAQ に追記
```

## DoD

### A. 機能完了
- [ ] 6 docs (`README.md` / `customer_onboarding_sop.md` / `incident_response_for_sales.md` / `escalation_matrix.md` / `faq_for_customers.md` / `role_responsibilities.md`) すべて作成
- [ ] 既存 docs への link が break していない (`grep -E "\]\(\.\./" docs/sales/*.md` で確認)
- [ ] 推測ベースの数字 (収益率 / 損失上限 / 利回り) が含まれていない self review

### B. Gate 全通過
- [ ] Gate 1-3: `./scripts/verify.sh` — **docs のみ**
- [ ] Gate 4-7: **N/A**
- [ ] Gate 5: 孤立コード検出 — **N/A**
- [ ] Gate 6: Codex Review — **任意** (docs のみだが文体チェックで実行可)
- [ ] 追加 Gate: link 切れ check (`scripts/link_check.sh` があれば実行、なければ手動 grep)

### C. 教訓記録
- [ ] 営業 docs 作成中に「推測で書きたくなった項目」を CLAUDE.md「教訓-2026-05-2X」に追記 (法務系 Lane 4 と同様、推測 falsification 防止の実例)

### D. Asana 連携
- [ ] PR description に Asana GID (営業 docs タスクが既存なら、なければ新規起票)

### E. Slack JSON 通知
```json
{
  "lane": "3",
  "phase": "ローンチ前 営業オペレーション準備",
  "status": "completed",
  "tier": "B",
  "deliverables": [
    "docs/sales/README.md",
    "docs/sales/customer_onboarding_sop.md",
    "docs/sales/incident_response_for_sales.md",
    "docs/sales/escalation_matrix.md",
    "docs/sales/faq_for_customers.md",
    "docs/sales/role_responsibilities.md"
  ],
  "gate_results": {
    "1-3_verify": "pass",
    "4-7": "n/a",
    "link_check": "pass"
  },
  "pr_url": "...",
  "next_action": "小林さん review → ローンチ前にチーム共有"
}
```

### F. claude.ai 引継ぎ
- [ ] PR URL / 全 6 docs の URL / 「推測ベースで書きたくなったが思いとどまった項目」リスト
- [ ] FAQ の「数字部分」をいつ・どの実機データで埋めるか claude.ai に相談

## 制約 (絶対遵守)

1. **推測ベースの数字を書かない** (収益率 / 損失上限 / 利回り / 顧客数等は実機データが出るまで TBD)
2. **景表法 / 金商法 系の表現を含めない** (「絶対安全」「必ず儲かる」等)
3. **法務的判断は Lane 4 (森先生 DM) に委ねる** (本 Lane は SOP の navigation のみ)
4. **顧客情報・個人情報をサンプルに含めない** (架空のサンプルでも実在しそうな名前 / 住所は禁止)
5. **既存 docs への link は相対パスで** (`../launch/...` 形式)
6. **本 Lane は docs/sales/ のみ touch**

## References

- `docs/launch/roadmap_to_launch.md` §3 Lane 3
- `docs/22_production_release_checklist.md` (運用前チェックリスト)
- `docs/23_partner_test_guide.md` / `docs/24_partner_test_guide.md` (パートナー文書の文体参考)
- `docs/15_rollback_procedures.md` (障害対応)
- `docs/postmortems/` (既知障害 link)
- `CLAUDE.md` §オンコールポリシー
- `CLAUDE.md` §2026-04-21 教訓 (memory からの推論拡大禁止 — 営業 docs にも適用)

## 推定所要時間内訳

| 工程 | 想定 |
|---|---|
| 前提確認 + 既存 docs 通読 | 45 min |
| Step 1 役割分担 | 45 min |
| Step 2 onboarding SOP | 60 min |
| Step 3 incident response | 60 min |
| Step 4 escalation matrix | 30 min |
| Step 5 FAQ | 60 min |
| Step 6 README + link 整備 | 30 min |
| Gate + PR + Slack | 30 min |
| **合計** | **5-6 h** |
