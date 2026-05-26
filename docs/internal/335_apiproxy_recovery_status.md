# #335 frontend api proxy route — 要否確認結果 (2026-05-25)

> **Status: NO ACTION NEEDED.** Asana 1215028941466200 のフォローアップ調査。

## TL;DR

- PR #335 (demo/frontend-static) は **demo 専用 branch 向け**で、PR description で「main 影響なし」と明記されていた。
- しかし `17a0eec` (2026-05-20) で誤って main にマージされ、**frontend/app/api/{aave,ai,auth,automation,exchange,portfolio,proposals,transactions,transparency,user}/[...path]/route.ts の 10 個が削除された**。
- 翌日 `40f6175` / `50b957d` (2026-05-21) の **revert で 10 個全部復活**。
- 2026-05-25 現在の `origin/main` に **10 routes 全て存在**:

```
frontend/app/api/aave/[...path]/route.ts
frontend/app/api/ai/[...path]/route.ts
frontend/app/api/auth/[...path]/route.ts
frontend/app/api/automation/[...path]/route.ts
frontend/app/api/exchange/[...path]/route.ts
frontend/app/api/portfolio/[...path]/route.ts
frontend/app/api/proposals/[...path]/route.ts
frontend/app/api/transactions/[...path]/route.ts
frontend/app/api/transparency/[...path]/route.ts
frontend/app/api/user/[...path]/route.ts
```

- 追加の作業は **不要**。Asana タスク 1215028941466200 は本ドキュメントを根拠に close 可能。

## 確認方法 (再実行可能)

```bash
cd /opt/ultra-autotrade/main
git ls-tree -r origin/main --name-only | grep -E 'frontend/app/api/.*\[\.\.\.path\]' | wc -l
# 期待: 10
```

## 再発防止

revert で復活はしたが、**「demo 専用 branch の変更が main にマージされた」根本原因**は別レイヤの問題:

- PR description が「main 影響なし」と書かれていても、CI / レビューでブロックする仕組みは無かった
- demo branch (`demo/frontend-static`) と main の `output:` 設定が排他関係にあること自体は frozen-files-guard (#139) のような mechanism で守るのが望ましい

→ 別タスク (recommended): `docs/build-isolation-rules` (PR #383) と関連付け、demo branch の物理 isolation rule を文書化。**本 PR では対応せず**、re-issue は別 Asana タスクで。

## タイムライン (commit ベース)

| 日時 | commit | 出来事 |
|---|---|---|
| 2026-05-20 | `17a0eec` | PR #335 main にマージ → 10 api routes 削除 |
| 2026-05-21 | `50b957d` → `40f6175` | revert → 10 api routes 復活 |
| 2026-05-25 | (本日) | 確認: 10 routes 全部存在、no-op |

## 参照

- Asana 1215028941466200 (本タスク)
- PR #335 (`demo/frontend-static` Cloudflare Pages static export)
- commits `17a0eec` / `40f6175` / `50b957d`
- `frozen-files-guard` (#139) — 凍結ファイル変更ガード機構
