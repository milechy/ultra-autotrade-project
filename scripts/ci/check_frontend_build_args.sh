#!/usr/bin/env bash
# Ultra AutoTrade — frontend build-arg ドリフト検出 CI guard
#
# 目的:
#   `NEXT_PUBLIC_*` フラグは Next.js の **build-time 埋め込み**。3 箇所が揃わないと
#   「.env で true にしても frontend に届かず常に false のまま焼かれる」サイレント不具合になる:
#     (1) frontend/lib/flags.ts 等が `process.env.NEXT_PUBLIC_X` を読む
#     (2) frontend/Dockerfile に `ARG NEXT_PUBLIC_X` + `ENV NEXT_PUBLIC_X=${...}`
#     (3) 各 docker-compose.<env>.yml の build.args に `NEXT_PUBLIC_X: ${...:-...}`
#
#   過去に同型のドリフトを繰り返している:
#     - WITHDRAW_ENABLED（2026-07-07・Dockerfile コメントに戒めあり）
#     - AGGRESSIVE_TIER_ENABLED / FEE_COLLECTION_ENABLED（2026-07-19・本 guard 追加の契機）
#     - staging / staging-v4 の同型ドリフト（2026-07-23・本 guard が production だけを見ており
#       staging 側を素通ししていた。staging-v4 で「利回り重視」セレクタを検証できなかった）
#   人間の注意力では防げないので機械で突合する。
#
# 判定（fail-closed）:
#   Dockerfile が宣言する各 `ARG NEXT_PUBLIC_*` が、**全 compose ファイル**の build.args に
#   存在しなければ FAIL。逆（compose にあるが Dockerfile に無い）も、届かないため FAIL。
#   staging を検査対象から外すと「本番だけ整合・staging で検証不能」が再発するため全環境を見る。
#
# 終了コード: 0=整合 / 1=ドリフトあり
set -euo pipefail

DOCKERFILE="frontend/Dockerfile"
COMPOSE_FILES=(
  "docker-compose.production.yml"
  "docker-compose.staging.yml"
  "docker-compose.staging-v4.yml"
)

for f in "$DOCKERFILE" "${COMPOSE_FILES[@]}"; do
  if [[ ! -f "$f" ]]; then
    echo "❌ 見つかりません: $f"
    exit 1
  fi
done

# Dockerfile の `ARG NEXT_PUBLIC_XXX` 一覧。
mapfile -t DOCKER_ARGS < <(
  grep -oE '^ARG[[:space:]]+NEXT_PUBLIC_[A-Z0-9_]+' "$DOCKERFILE" \
    | awk '{print $2}' | sort -u
)

_contains() {
  local needle="$1"; shift
  local x
  for x in "$@"; do [[ "$x" == "$needle" ]] && return 0; done
  return 1
}

# compose の **build.args ブロック限定**で `NEXT_PUBLIC_XXX:` を抽出する。
# `environment:` セクションにも NEXT_PUBLIC_* があり得るため、範囲を絞らないと誤整合になる
# （environment の key を build-arg と誤認して「整合」と判定してしまう）。
# `args:` 行の次行から、同インデントの次キー（`environment:` 等）の手前までを対象にする。
_compose_args() {
  awk '
    /^[[:space:]]*args:[[:space:]]*$/ { inargs=1; argindent=match($0, /[^ ]/); next }
    inargs {
      # 空行/コメントは無視して継続
      if ($0 ~ /^[[:space:]]*$/ || $0 ~ /^[[:space:]]*#/) next
      # args: と同じかそれより浅いインデントのキーが来たらブロック終了
      ind = match($0, /[^ ]/)
      if (ind <= argindent) { inargs=0; next }
      print
    }
  ' "$1" \
    | grep -oE 'NEXT_PUBLIC_[A-Z0-9_]+:' | tr -d ' :' | sort -u
}

failed=0

for COMPOSE in "${COMPOSE_FILES[@]}"; do
  mapfile -t COMPOSE_ARGS < <(_compose_args "$COMPOSE")

  missing_in_compose=()
  for a in "${DOCKER_ARGS[@]}"; do
    _contains "$a" "${COMPOSE_ARGS[@]:-}" || missing_in_compose+=("$a")
  done

  missing_in_dockerfile=()
  for a in "${COMPOSE_ARGS[@]}"; do
    _contains "$a" "${DOCKER_ARGS[@]:-}" || missing_in_dockerfile+=("$a")
  done

  if [[ ${#missing_in_compose[@]} -eq 0 && ${#missing_in_dockerfile[@]} -eq 0 ]]; then
    echo "✅ frontend build-arg 整合: Dockerfile(${#DOCKER_ARGS[@]}) と ${COMPOSE} の build.args が一致。"
    continue
  fi

  failed=1
  echo "❌ FAIL: ${COMPOSE} で frontend build-arg ドリフトを検出しました。"
  echo ""
  if [[ ${#missing_in_compose[@]} -gt 0 ]]; then
    echo "  ${COMPOSE} の build.args に不足（Dockerfile に ARG はあるが compose に無い）:"
    printf '    - %s\n' "${missing_in_compose[@]}"
    echo "    → build.args に 'NAME: \${NAME:-<既定>}' を追加してください。"
  fi
  if [[ ${#missing_in_dockerfile[@]} -gt 0 ]]; then
    echo "  ${DOCKERFILE} の ARG に不足（compose に build.args はあるが Dockerfile に無い）:"
    printf '    - %s\n' "${missing_in_dockerfile[@]}"
    echo "    → Dockerfile に 'ARG NAME' + 'ENV NAME=\${NAME}' を追加してください。"
  fi
  echo ""
done

if [[ $failed -ne 0 ]]; then
  echo "  背景: NEXT_PUBLIC_* は build-time 埋め込みのため、3点(flags.ts / Dockerfile / compose)が"
  echo "  揃わないと .env で true にしても届かず常に false のまま焼かれます（サイレント不具合）。"
  exit 1
fi

exit 0
