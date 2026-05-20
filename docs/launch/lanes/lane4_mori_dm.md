# Lane 4: 森先生 (法務) DM 草案 — **5/22 deadline**

## メタ情報

| 項目 | 値 |
|---|---|
| Lane | 4 / Phase「ローンチ前 法務確認」 |
| Tier | **B** (`docs/legal/` 新規 markdown のみ) |
| auto-merge | **OK** (DoD 全通過時) |
| **deadline** | **2026-05-22 (本指示書起票 5/20 → 2 日後)** ← 4 Lane 中で唯一の deadline 強制 |
| night-mode 投入 | **22:00 以降** (想定所要 3-4 h、deadline 圧で最短ルート) |
| owner | Claude Code CLI bg lane (sonnet 4.6 で十分、コード変更なし) |
| 関連 roadmap | `docs/launch/roadmap_to_launch.md` §3 Lane 4 + §5 既知ブロッカー |

## /goal

**森先生 (法務顧問) に対して、Ultra AutoTrade のローンチ前 法務確認依頼の DM 草案を作成する。送信は claude.ai 文面禁止ルール (CLAUDE.md §10) に従い小林さん本人が行う。本 Lane は草案 markdown を `docs/legal/mori_dm_draft_2026-05-22.md` に出すまで。**

## 触るファイル (Tier 抵触チェック)

| ファイル | 種別 | Tier | 抵触 |
|---|---|---|---|
| `docs/legal/mori_dm_draft_2026-05-22.md` | 新規 | B | なし |
| `docs/legal/mori_dm_review_checklist.md` | 新規 | B | なし |
| `docs/legal/README.md` | 新規 (`docs/legal/` 配下の index) | B | なし |
| **コード変更** | — | — | **なし** (本 Lane は docs のみ) |

## 前提確認 (Lane 開始直後、10 min 以内)

```bash
cd /opt/ultra-autotrade/main

# 1. 既存 docs/legal/ 配下確認
ls -la docs/legal/ 2>&1

# 2. 既存の法務関連 docs 探索
grep -r "森\|法務\|legal\|kompli" docs/ --include="*.md" -l 2>/dev/null | head -10

# 3. 山本さん UAT との同期: 森先生 Asana タスクの GID と状態
# (Lane 内で Asana MCP は使えない場合 Slack 検索で代替)
# Slack 検索: 「森」「法務」 in:#ultra-auto-project

# 4. 過去の partner / tester 向け文面の参考
ls docs/*tester* docs/*partner* 2>/dev/null
```

**過去の partner / tester 通信記録 (`docs/23_partner_test_guide.md` / `docs/24_partner_test_guide.md` 等) を必ず読む** — 文体・粒度・送信前確認フローの慣習を踏襲。

## 実装手順

### Step 1: 確認対象の列挙 (45 min)

森先生に確認したい論点を `docs/legal/mori_dm_review_checklist.md` に列挙。**重要: 推測で「法務的論点」を列挙しない**。以下のソースのみから抽出:

| 抽出ソース | 該当する確認論点 |
|---|---|
| `docs/13_security_design.md` | 秘密鍵管理 / Aave 操作の善管注意義務 |
| `docs/22_production_release_checklist.md` | ローンチ前 法務 review 項目 |
| Slack 過去スレッド (`from:小林 法務 OR 森`) | 既往の論点 (要 Slack search) |
| 既存 partner / tester guide | 既存の同意フロー / 利用規約の有無 |
| handoff thread §既知ブロッカー | 7 日以上 overdue タスクの中に森先生関連がある可能性 |

論点が **既存 docs / Slack ログから取れない場合**、その項目は **草案に含めず**「小林さんが直接 claude.ai に追加依頼」とする (推測でリスク列挙すると法務的誤誘導になる)。

### Step 2: DM 草案構成設計 (30 min)

`docs/legal/mori_dm_draft_2026-05-22.md` 構成案:

```markdown
# 森先生宛 DM 草案 (2026-05-22 送信予定)

## メタ
- **送信は小林さん本人** (CLAUDE.md §10 — Claude 文面禁止)
- 想定チャネル: TBD (Slack DM / メール / Asana コメント)
- 想定文字数: TBD (Slack なら 1500 字以内、メールなら制限緩)

## 件名 (案)
"Ultra AutoTrade ローンチ前 法務確認 (2026-06-03 想定)"

## 本文 (草案)
1. 挨拶 + 状況サマリ (3-4 行)
2. ローンチ予定日 + パートナー範囲 + 取扱資金規模
3. 確認したい論点 (Step 1 で列挙したもの、3-5 件まで)
4. 期待する回答期限 + 形式 (書面 / 口頭 / Asana コメント)
5. 添付資料 (関連 docs リンク or Notion 共有リンク等、現状は GitHub link)

## 添付候補
| 資料 | パス | 公開可否 |
|---|---|---|
| ローンチロードマップ | `docs/launch/roadmap_to_launch.md` | 内部 |
| セキュリティ設計 | `docs/13_security_design.md` | 内部 |

## 送信前チェックリスト (小林さん用)
- [ ] 機密情報 (private key / RPC URL / DB password) が文面に含まれていないか
- [ ] 確認論点が「推測ベース」でなく「実装 / docs ベース」か
- [ ] 期待回答期限が森先生のスケジュールに合っているか
- [ ] 添付資料の公開範囲が適切か
- [ ] CLAUDE.md §10 (Claude 文面禁止) を遵守し、本人の言葉で書き直したか
```

### Step 3: 草案ドラフト (60 min)

Step 2 の構成に沿って実際の本文を書く。**鍵となる原則**:

1. **「お願い」ベースで書く**、「指示」ではない (法務顧問は外部、Ultra チームの一員ではない)
2. **論点数を 3-5 個に絞る** (DM 1 通で全部解決しようとしない、後続やり取りを想定)
3. **数字を入れる時は丸めずソース付き** (例: 「日次取引上限 30%」→ `docs/13_security_design.md §X.Y`)
4. **claude.ai 案の数字を鵜呑みにしない** (handoff §既知ブロッカー指摘: 「各条件の進捗が引継ぎパッケージの数字を鵜呑みにしただけ」のリスクが法務系にも適用)
5. **「想定リスク」を Lane が独自に列挙するのは禁止** (法務的に誤誘導の元、Step 1 で抽出したものだけ)

### Step 4: 送信前チェックリスト + index (30 min)

`docs/legal/README.md` を作成し、`mori_dm_draft_*.md` の管理ルールを書く:

```markdown
# docs/legal/ 配下の管理ルール

## 命名規則
- 草案: `<相手名>_dm_draft_YYYY-MM-DD.md`
- 確定済 (送信後): `<相手名>_dm_sent_YYYY-MM-DD.md` にリネーム
- 返信受領後: `<相手名>_dm_response_YYYY-MM-DD.md`

## 送信ルール
- **送信は必ず小林さん本人** (CLAUDE.md §10)
- Claude / claude.ai が「送信した」と称した場合は falsification の疑い、即停止
- 送信後は GitHub Issues / Asana に送信記録のみ (本文は legal docs に残す)

## 機密情報禁止
- private key / RPC URL / DB password / API token を含めない
- 含めた場合は **コミット前** に削除
- 既に push 済の場合 git history rewrite で削除 (Tier S 抵触のため上長承認)
```

## DoD

### A. 機能完了
- [ ] `docs/legal/mori_dm_review_checklist.md` 作成 (Step 1 結果)
- [ ] `docs/legal/mori_dm_draft_2026-05-22.md` 作成 (Step 3 結果)
- [ ] `docs/legal/README.md` 作成 (Step 4 結果)
- [ ] **送信前チェックリスト** が draft 末尾に埋め込まれている
- [ ] 草案内に「推測ベースの論点」が混入していないことを self review

### B. Gate 全通過
- [ ] Gate 1-3: `./scripts/verify.sh` — **docs のみなので markdown lint で代替可** (pyproject 該当なし)
- [ ] Gate 4-7: **N/A** (UI / コード / deploy なし)
- [ ] Gate 5: 孤立コード検出 — **N/A**
- [ ] Gate 6: Codex Review — **N/A** (法務文面のため、Codex でなく小林さん review)
- [ ] **追加 Gate**: 機密情報 grep (`grep -rEi "(private[_-]?key|api[_-]?token|password)" docs/legal/`) → 0 件

### C. 教訓記録
- [ ] Step 1 で論点抽出時の「推測したくなった項目」と「思いとどまった項目」を CLAUDE.md「教訓-2026-05-2X」に追記 (法務系の falsification を防ぐ実例として残す)

### D. Asana 連携
- [ ] PR description に Asana GID (森先生関連タスクが既存ならそれ、なければ新規起票)
- [ ] Lane 完了時 notes に PR link

### E. Slack JSON 通知
```json
{
  "lane": "4",
  "phase": "ローンチ前 法務確認",
  "status": "completed",
  "tier": "B",
  "deadline": "2026-05-22",
  "deliverables": [
    "docs/legal/mori_dm_review_checklist.md",
    "docs/legal/mori_dm_draft_2026-05-22.md",
    "docs/legal/README.md"
  ],
  "gate_results": {
    "1-3_verify": "pass (markdown lint)",
    "4-7": "n/a",
    "secrets_grep": "0 hits"
  },
  "pr_url": "...",
  "next_action": "小林さん review → 5/22 中に本人送信"
}
```

### F. claude.ai 引継ぎ
- [ ] PR URL / 草案本文要約 / 「論点抽出ソース」のリスト
- [ ] 小林さんが追加したい論点があれば claude.ai セッションで追記してから本人送信する旨

## 制約 (絶対遵守)

1. **送信は小林さん本人** (CLAUDE.md §10、Claude 文面禁止)
2. **法務的論点を推測で列挙しない** (誤誘導リスク)
3. **機密情報を文面に含めない** (秘密鍵 / RPC URL / DB password / API token)
4. **送信代行を称さない** (Claude / claude.ai が「送信完了」と言ったら falsification、即停止)
5. **deadline 5/22 厳守** (deadline 過ぎたら HUMAN-REVIEW-REQUIRED で claude.ai へエスカレ)
6. **本 Lane は docs/legal/ のみ touch** (他ディレクトリへの波及禁止)

## 失敗時のフォールバック

deadline 5/22 までに本 Lane が完了しない場合:
1. **partial_complete で PR 出す** (Step 1-2 まで完了、Step 3 草案が未完成でも構造だけ残す)
2. claude.ai に「論点抽出は済み、草案本文は小林さんが書く」と handoff
3. 5/22 までに本人が草案を書けるよう、Step 1 のチェックリストだけは確実に渡す

## References

- `CLAUDE.md` §10 (Claude 文面禁止、本人送信ルール)
- `docs/13_security_design.md` (法務確認の primary source)
- `docs/22_production_release_checklist.md` (ローンチ前 review 項目)
- `docs/23_partner_test_guide.md` / `docs/24_partner_test_guide.md` (過去の通信記録)
- handoff §既知ブロッカー (7 日以上 overdue タスクの中の法務関連有無)

## 推定所要時間内訳

| 工程 | 想定 |
|---|---|
| 前提確認 + 既存 docs 通読 | 30 min |
| Step 1 論点列挙 (慎重に) | 45 min |
| Step 2 構成設計 | 30 min |
| Step 3 ドラフト | 60 min |
| Step 4 README + 送信前チェック | 30 min |
| Gate + PR + Slack | 45 min |
| **合計** | **3-4 h** (deadline 圧で最短ルート) |
