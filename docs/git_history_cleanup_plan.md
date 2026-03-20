# Git History Cleanup Plan

## Purpose

Remove personal identifiers and sensitive data from git history before production migration.

Total commits analyzed: 347 across all branches.

---

## Pre-cleanup Steps

1. Create full backup: `git bundle create ../ultra-autotrade-backup-$(date +%Y%m%d).bundle --all`
2. Notify all collaborators — force-push will break their local repos
3. Ensure clean working tree: `git status`

---

## Sensitive Data Found in History

### 1. Author Identity (present in ALL commits)

| Field | Value |
|-------|-------|
| Email | `hkobayashi@mooores.com` (present in majority of commits) |
| Name  | `milechy` |

These appear in the `Author:` line of every commit made by the primary developer. BFG cannot rewrite author metadata — this requires `git filter-repo`.

Other authors found (likely safe):
- `cursoragent@cursor.com` / `Cursor Agent`
- `deploy@ultra-autotrade` / `Deploy Bot`

### 2. Encrypted Session Key in `user/BrowsingDataProvider_data.json`

Committed in: `cb3365a` ("Initial commit - clean history without secrets")

The file `user/BrowsingDataProvider_data.json` contained a Fernet-encrypted session secret key (OctoBot browsing session). First 8 chars: `gAAAAABp`

Although this file was later removed from tracking in commit `c058693`, the encrypted value **remains in git history** and is recoverable via `git show cb3365a:user/BrowsingDataProvider_data.json`.

### 3. `user/config.json` — OctoBot Exchange Config (TradingView profile reference)

Committed in: `cb3365a`, removed in: `c058693`

The file contained:
- Exchange API key fields (values were placeholder strings `your-api-key-here` — no real keys detected)
- `"profile": "tradingview_trading"` reference
- A `community.local_data_identifier` hash (SHA-256, not a secret but identifies the OctoBot instance)

The security commit `c058693` correctly deleted the file and added it to `.gitignore`, but the content remains in history.

### 4. `user/config.json.bak` and `user/config.json.bak2`

Also committed in `cb3365a`, removed in `c058693`. Same concerns as above.

### 5. SLACK_WEBHOOK_URL

The webhook URL is read from `.env.staging` at runtime in scripts and is never hardcoded directly. No actual webhook URL value was detected in git history — only variable name references (`SLACK_WEBHOOK_URL=`). This is safe.

### 6. IP Address / Hostname

No Hetzner IP addresses (e.g. `77.42.46.x`) were found in git history diff content.

### 7. Example / Placeholder `.env` files (safe, no action needed)

The following `.env` example files were committed intentionally and contain only placeholder values:
- `.env.example`
- `.env.local.example`
- `.env.staging.example`
- `backend/.env.production.example`
- `backend/.env.staging.example`
- `backend/.env.test.example`
- `frontend/.env.local.example`

No actual secrets were detected in any of these files.

---

## Items Requiring Cleanup

| Priority | Item | Location in History | Action |
|----------|------|---------------------|--------|
| HIGH | Author email `hkobayashi@mooores.com` | All commits | `git filter-repo --email-callback` |
| HIGH | Author name `milechy` | All commits | `git filter-repo --name-callback` |
| MEDIUM | `user/BrowsingDataProvider_data.json` (encrypted session key) | `cb3365a` | BFG `--delete-files` |
| MEDIUM | `user/config.json` + `.bak` + `.bak2` | `cb3365a` | BFG `--delete-files` |

---

## BFG Repo-Cleaner Commands

**DO NOT RUN until team review and backup confirmed.**

```bash
# Step 0: Install tools
brew install bfg git-filter-repo

# Step 1: Full backup (MANDATORY before any history rewrite)
cd /Users/hkobayashi/projects
git bundle create ultra-autotrade-backup-$(date +%Y%m%d).bundle --all

# Step 2: Remove specific files from ALL history using BFG
cd /Users/hkobayashi/projects/ultra-autotrade
bfg --delete-files BrowsingDataProvider_data.json --no-blob-protection .
bfg --delete-files config.json --no-blob-protection .
bfg --delete-files config.json.bak --no-blob-protection .
bfg --delete-files config.json.bak2 --no-blob-protection .

# Step 3: Replace any string occurrences (create replacements.txt first)
# replacements.txt contents:
#   hkobayashi@mooores.com==>dev@example.com
#   milechy==>developer
bfg --replace-text replacements.txt --no-blob-protection .

# Step 4: Rewrite author metadata (BFG cannot do this — use git filter-repo)
git filter-repo \
  --email-callback 'return b"dev@example.com" if email == b"hkobayashi@mooores.com" else email' \
  --name-callback 'return b"developer" if name == b"milechy" else name'

# Step 5: Clean up refs
git reflog expire --expire=now --all
git gc --prune=now --aggressive
```

---

## Post-cleanup Verification

```bash
# 1. Author identity should be gone
git log --all --format="%ae %an" | sort -u
# Expected: only dev@example.com / developer, cursoragent@cursor.com, deploy@ultra-autotrade

# 2. Session key file should be gone
git log --all -- 'user/BrowsingDataProvider_data.json'
# Expected: no output

# 3. No traces of personal identifiers in diffs
git log --all -p | grep -iE "hkobayashi|milechy|mooores" | wc -l
# Expected: 0

# 4. BrowsingDataProvider session key should be gone
git log --all -p | grep "gAAAAABp" | wc -l
# Expected: 0
```

---

## Force-push (LAST STEP — requires team coordination)

```bash
git push --force --all origin
git push --force --tags origin
```

All collaborators must run after force-push:
```bash
git fetch origin
git reset --hard origin/$(git branch --show-current)
```

---

## Rollback

If anything goes wrong:
```bash
# Option A: from remote (if not yet force-pushed)
git fetch origin && git reset --hard origin/main

# Option B: restore from bundle
cd /Users/hkobayashi/projects
git clone ultra-autotrade-backup-YYYYMMDD.bundle ultra-autotrade-restored
```

---

## Summary

The history is relatively clean. No live API keys, no plaintext passwords, and no Hetzner IP addresses were found in git diff content. The main concerns are:

1. **Author identity** (`hkobayashi@mooores.com` / `milechy`) — present in all ~347 commits. Requires `git filter-repo` to rewrite.
2. **OctoBot session/config files** — committed in the initial commit, deleted later but still in history. Requires BFG to purge blobs.

The `.env` example files are safe (placeholder values only) and do not require cleanup.
