# Branch Protection 設定手順

## ブランチ戦略

```
feature/* (各Stream担当) → dev (統合) → staging (最終レビュー) → main (本番)
```

---

## 保護対象ブランチと設定値

### `main` ブランチ (最高レベル保護)

| 設定項目 | 値 |
|---------|-----|
| Require a pull request before merging | ✅ ON |
| Required approvals | **2** |
| Dismiss stale pull request approvals | ✅ ON |
| Require review from Code Owners | ✅ ON |
| Require status checks to pass | ✅ ON |
| Required status checks | `lint`, `test`, `security-check` |
| Require branches to be up to date | ✅ ON |
| Require conversation resolution | ✅ ON |
| Restrict who can push | ✅ ON (管理者のみ) |
| Allow force pushes | ❌ OFF |
| Allow deletions | ❌ OFF |
| Block direct pushes | ✅ ON |

### `staging` ブランチ

| 設定項目 | 値 |
|---------|-----|
| Require a pull request before merging | ✅ ON |
| Required approvals | **1** |
| Require status checks to pass | ✅ ON |
| Required status checks | `lint`, `test`, `security-check` |
| Require branches to be up to date | ✅ ON |
| Allow force pushes | ❌ OFF |
| Allow deletions | ❌ OFF |
| Block direct pushes | ✅ ON |

### `dev` ブランチ

| 設定項目 | 値 |
|---------|-----|
| Require a pull request before merging | ✅ ON |
| Required approvals | **1** |
| Require status checks to pass | ✅ ON |
| Required status checks | `lint`, `test` |
| Allow force pushes | ❌ OFF |
| Allow deletions | ❌ OFF |
| Block direct pushes | ✅ ON |

---

## GitHub UI での設定手順

1. GitHub リポジトリ → **Settings** → **Branches**
2. **Add branch protection rule** をクリック
3. **Branch name pattern** に対象ブランチ名を入力 (例: `main`)
4. 上記テーブルの設定値を入力
5. **Create** をクリック

同じ手順を `staging`、`dev` に対して繰り返す。

---

## CODEOWNERS 設定

`.github/CODEOWNERS` ファイルでコードオーナーを指定する:

```
# デフォルトオーナー
*                           @team-lead

# セキュリティ関連
docs/13_security_design.md  @security-team @team-lead
backend/app/aave/           @security-team

# インフラ関連
.github/workflows/          @devops-team
docker-compose*.yml         @devops-team
Dockerfile*                 @devops-team

# AIロジック
backend/app/ai/             @ai-team
```

---

## ワークフロー定義 (PRマージ経路)

```
feature/*
    │
    │ PR (1 approval required, CI必須)
    ▼
   dev ─── 統合テスト実行
    │
    │ PR (1 approval required, CI + security必須)
    ▼
 staging ── E2E テスト + Codex レビュー
    │
    │ PR (2 approvals required, 全CI必須)
    ▼
  main ───── 本番デプロイ
```

---

## 直接push禁止の徹底

以下のブランチへの直接 push は CI で `path-check.yml` によっても検出されます:
- `main` への直接 push → 自動ブロック
- `staging` への直接 push → 自動ブロック

`feature/` ブランチから必ずPR経由でマージしてください。

---

## gh api コマンド草案 (hkobayashi 確認後に実行)

> **注意:** 以下コマンドは `admin:repo` 権限が必要。実行前に hkobayashi が確認・承認すること。
> `required_status_checks` に指定するチェック名は `CI / {job_name}` 形式 (GitHub Actions の場合)。
> 新ジョブは少なくとも 1 回 CI 実行後でないと GitHub 側にコンテキストが登録されない。

### main ブランチ

```bash
gh api \
  --method PUT \
  -H "Accept: application/vnd.github+json" \
  /repos/milechy/ultra-autotrade-project/branches/main/protection \
  --input - << 'EOF'
{
  "required_status_checks": {
    "strict": true,
    "checks": [
      {"context": "CI / Lint (ruff + mypy)",        "app_id": -1},
      {"context": "CI / Test (pytest + coverage)",  "app_id": -1},
      {"context": "CI / Security Check",            "app_id": -1},
      {"context": "CI / Frontend (tsc + build)",    "app_id": -1},
      {"context": "Secret Scan (gitleaks) / gitleaks", "app_id": -1}
    ]
  },
  "enforce_admins": true,
  "required_pull_request_reviews": {
    "required_approving_review_count": 2,
    "dismiss_stale_reviews": true,
    "require_code_owner_reviews": false
  },
  "restrictions": null,
  "allow_force_pushes": false,
  "allow_deletions": false,
  "required_conversation_resolution": true
}
EOF
```

### staging ブランチ

```bash
gh api \
  --method PUT \
  -H "Accept: application/vnd.github+json" \
  /repos/milechy/ultra-autotrade-project/branches/staging/protection \
  --input - << 'EOF'
{
  "required_status_checks": {
    "strict": true,
    "checks": [
      {"context": "CI / Lint (ruff + mypy)",        "app_id": -1},
      {"context": "CI / Test (pytest + coverage)",  "app_id": -1},
      {"context": "CI / Security Check",            "app_id": -1},
      {"context": "CI / Frontend (tsc + build)",    "app_id": -1},
      {"context": "Secret Scan (gitleaks) / gitleaks", "app_id": -1}
    ]
  },
  "enforce_admins": false,
  "required_pull_request_reviews": {
    "required_approving_review_count": 1,
    "dismiss_stale_reviews": false,
    "require_code_owner_reviews": false
  },
  "restrictions": null,
  "allow_force_pushes": false,
  "allow_deletions": false,
  "required_conversation_resolution": false
}
EOF
```

### dev ブランチ

```bash
gh api \
  --method PUT \
  -H "Accept: application/vnd.github+json" \
  /repos/milechy/ultra-autotrade-project/branches/dev/protection \
  --input - << 'EOF'
{
  "required_status_checks": {
    "strict": true,
    "checks": [
      {"context": "CI / Lint (ruff + mypy)",       "app_id": -1},
      {"context": "CI / Test (pytest + coverage)", "app_id": -1},
      {"context": "CI / Frontend (tsc + build)",   "app_id": -1}
    ]
  },
  "enforce_admins": false,
  "required_pull_request_reviews": {
    "required_approving_review_count": 1,
    "dismiss_stale_reviews": false,
    "require_code_owner_reviews": false
  },
  "restrictions": null,
  "allow_force_pushes": false,
  "allow_deletions": false,
  "required_conversation_resolution": false
}
EOF
```

### 設定確認コマンド

```bash
# 設定後の確認 (各ブランチ)
gh api /repos/milechy/ultra-autotrade-project/branches/main/protection \
  | python3 -m json.tool | grep -A30 required_status

gh api /repos/milechy/ultra-autotrade-project/branches/dev/protection \
  | python3 -m json.tool | grep -A30 required_status

gh api /repos/milechy/ultra-autotrade-project/branches/staging/protection \
  | python3 -m json.tool | grep -A30 required_status
```

---

## 緊急時の手順 (Break-glass)

本番障害など緊急時に直接 main へ push が必要な場合:

1. Slack `#incident` チャンネルに宣言
2. 管理者が一時的に Branch Protection を無効化
3. 修正 push + 即座にタグ打ち (`git tag hotfix/YYYYMMDD-description`)
4. Branch Protection を即座に再有効化
5. 事後 postmortem を GitHub Issue に記録

> **注意:** Break-glass は月1回以下を目安。乱用しないこと。
