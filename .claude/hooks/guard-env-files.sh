#!/usr/bin/env bash
# .claude/hooks/guard-env-files.sh
# 役割: UATa §12 環境分離 + production_operation_checklist.md を物理ブロック
# 由来: 棚卸し 2026-05-13 / 2026-05-03 PR #191 同型再発防止
# 配備: settings.local.json の PreToolUse matcher: Bash
# bypass: UATA_HOOK_BYPASS=1 (全) / UATA_HOOK_BYPASS_R<N>=1 (個別 / N=1-5)
# self-test: bash .claude/hooks/guard-env-files.sh --self-test
set -euo pipefail

log_block() {
  local rule_id="$1"; shift
  local reason="$1"; shift
  local snippet="$1"; shift
  local advice="$1"; shift
  cat >&2 <<EOF
[guard-env-files] BLOCKED ($rule_id): $reason
  Snippet : $snippet
  Advice  : $advice
  Bypass  : UATA_HOOK_BYPASS_${rule_id}=1 (個別) or UATA_HOOK_BYPASS=1 (全)
EOF
}

is_bypassed() {
  local rule_id="$1"
  if [[ "${UATA_HOOK_BYPASS:-0}" == "1" ]]; then
    echo "[guard-env-files] WARN: UATA_HOOK_BYPASS=1 で全ルール bypass" >&2
    return 0
  fi
  local var="UATA_HOOK_BYPASS_${rule_id}"
  if [[ "${!var:-0}" == "1" ]]; then
    echo "[guard-env-files] WARN: $var=1 で $rule_id を bypass" >&2
    return 0
  fi
  return 1
}

check_cmd() {
  local cmd="$1"

  # R1: .env.staging 単独参照(旧ファイル)
  if [[ "$cmd" =~ \.env\.staging($|[^-]) ]]; then
    if ! is_bypassed "R1"; then
      log_block "R1" \
        ".env.staging は旧ファイル / 使用禁止 (§12)" \
        "$cmd" \
        "正しいファイルは .env.staging-new"
      return 2
    fi
  fi

  # R2: .env.production と .env.staging-new を書込で両方参照
  local has_prod=0 has_staging_new=0 is_write=0
  if [[ "$cmd" =~ \.env\.production ]]; then has_prod=1; fi
  if [[ "$cmd" =~ \.env\.staging-new ]]; then has_staging_new=1; fi
  if [[ "$cmd" =~ sed[[:space:]]+-i ]] \
     || [[ "$cmd" =~ (awk|tee|cp|mv).*\.env\.(production|staging-new) ]] \
     || [[ "$cmd" =~ \>[[:space:]]*\.env\.(production|staging-new) ]]; then
    is_write=1
  fi
  if [[ $has_prod -eq 1 && $has_staging_new -eq 1 && $is_write -eq 1 ]]; then
    if ! is_bypassed "R2"; then
      log_block "R2" \
        ".env.production と .env.staging-new を同一コマンドで書込 (§12 環境分離崩壊)" \
        "$cmd" \
        "ファイル単位で別コマンドに分割"
      return 2
    fi
  fi

  # R3: docker compose ... build 単体(--env-file 抜けの起点)
  if [[ "$cmd" =~ docker[[:space:]]+compose ]] && [[ "$cmd" =~ [[:space:]]build([[:space:]]|$) ]]; then
    if [[ ! "$cmd" =~ --env-file ]]; then
      if ! is_bypassed "R3"; then
        log_block "R3" \
          "docker compose build 単体 (--env-file 抜け / 2026-05-03 PR #191 同型)" \
          "$cmd" \
          "deploy_production.sh / deploy_staging.sh 経由を使う"
        return 2
      fi
    fi
  fi

  # R4: docker compose up + --force-recreate + --no-deps 不在
  if [[ "$cmd" =~ docker[[:space:]]+compose ]] \
     && [[ "$cmd" =~ --force-recreate ]] \
     && [[ ! "$cmd" =~ --no-deps ]]; then
    if ! is_bypassed "R4"; then
      log_block "R4" \
        "docker compose --force-recreate without --no-deps (Blue/Green 全再起動リスク)" \
        "$cmd" \
        "--no-deps を追加 / または個別 service 名のみ指定"
      return 2
    fi
  fi

  # R5: production への直接書込(production_operation_checklist.md 違反)
  if [[ "$cmd" =~ ssh.*ultra@77\.42\.46\.155 ]] \
     && [[ "$cmd" =~ \.env\.production ]] \
     && { [[ "$cmd" =~ sed[[:space:]]+-i ]] \
          || [[ "$cmd" =~ (awk|tee).*\.env\.production ]] \
          || [[ "$cmd" =~ \>[[:space:]]*.*\.env\.production ]] \
          || [[ "$cmd" =~ cp.*\.env\.production ]]; }; then
    if ! is_bypassed "R5"; then
      log_block "R5" \
        "ssh production への .env.production 直接書込 (production_operation_checklist.md ゲート 3 違反)" \
        "$cmd" \
        "ローカルで編集 → scp → 必ずバックアップ + Phase 3 承認後"
      return 2
    fi
  fi

  return 0
}

self_test() {
  local pass=0 fail=0
  declare -a tests=(
    "BLOCK|R1|cat /opt/ultra-autotrade/.env.staging"
    "PASS||cat /opt/ultra-autotrade/.env.staging-new"
    "BLOCK|R2|sed -i 's/foo/bar/' .env.production .env.staging-new"
    "PASS||diff .env.production .env.staging-new"
    "BLOCK|R3|docker compose -f docker-compose.production.yml build backend"
    "PASS||docker compose --env-file .env.production -f docker-compose.production.yml build backend"
    "BLOCK|R4|docker compose -f docker-compose.production.yml up -d --force-recreate"
    "PASS||docker compose -f docker-compose.production.yml up -d --force-recreate --no-deps backend-blue"
    'BLOCK|R5|ssh -i ~/.ssh/hetzner_staging ultra@77.42.46.155 "sed -i s/old/new/ /opt/ultra-autotrade/.env.production"'
    'PASS||ssh -i ~/.ssh/hetzner_staging ultra@77.42.46.155 "cat /opt/ultra-autotrade/.env.production | grep API_KEY"'
    "PASS||ls -la /opt/ultra-autotrade/"
    "BYPASS_R1|PASS|cat /opt/ultra-autotrade/.env.staging"
  )

  echo "=== guard-env-files.sh self-test ==="
  for t in "${tests[@]}"; do
    IFS='|' read -r expected rule_id cmd <<< "$t"
    local actual_exit=0

    if [[ "$expected" == "BYPASS_R1" ]]; then
      UATA_HOOK_BYPASS_R1=1 check_cmd "$cmd" >/dev/null 2>&1 || actual_exit=$?
      expected="PASS"
    else
      check_cmd "$cmd" >/dev/null 2>&1 || actual_exit=$?
    fi

    local result="?"
    if [[ "$expected" == "BLOCK" && $actual_exit -eq 2 ]]; then
      result="PASS"; pass=$((pass+1))
    elif [[ "$expected" == "PASS" && $actual_exit -eq 0 ]]; then
      result="PASS"; pass=$((pass+1))
    else
      result="FAIL (expected=$expected rule=$rule_id actual_exit=$actual_exit)"
      fail=$((fail+1))
    fi
    printf "  [%s] %s\n" "$result" "$cmd"
  done

  echo "=== Result: $pass PASS / $fail FAIL ==="
  [[ $fail -eq 0 ]]
}

if [[ "${1:-}" == "--self-test" ]]; then
  self_test
  exit $?
fi

if ! command -v jq >/dev/null 2>&1; then
  echo "[guard-env-files] ERROR: jq 未インストール(brew install jq)" >&2
  exit 1
fi

input=$(cat)
tool_name=$(echo "$input" | jq -r '.tool_name // ""')
command=$(echo "$input" | jq -r '.tool_input.command // ""')

if [[ "$tool_name" != "Bash" ]]; then
  exit 0
fi
if [[ -z "$command" ]]; then
  exit 0
fi

check_cmd "$command"
exit $?
