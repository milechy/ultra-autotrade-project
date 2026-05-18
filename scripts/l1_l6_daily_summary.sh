#!/usr/bin/env bash
# scripts/l1_l6_daily_summary.sh
#
# healthcheck_l1_l6.sh のログから日次サマリーを集計し、
# 14日連続緑 (§2 評価指標 v1) のストリークを出力する。
#
# 使用方法:
#   bash scripts/l1_l6_daily_summary.sh [--log <path>] [--streak-only] [--days <N>]
#
# オプション:
#   --log <path>     ログファイルパス (default: /opt/ultra-autotrade/logs/healthcheck_l1_l6.log)
#   --streak-only    14日連続緑のストリーク数のみ出力
#   --days <N>       集計対象日数 (default: 14)
#   --tz <TZ>        タイムゾーン (default: Asia/Tokyo)
#
# ログ行フォーマット (grep 対象):
#   2026-05-18T02:05:00Z [healthcheck_l1_l6] 結果: L1=PASS L2=FAIL ... → PASS
#
# 判定基準 (docs/l1_l6_evaluation_v1.md §2):
#   日次緑 = pass_rate >= 0.95 AND total_runs >= 240

set -uo pipefail

# =============================================================================
# デフォルト設定
# =============================================================================
LOG_FILE="${LOG_FILE:-/opt/ultra-autotrade/logs/healthcheck_l1_l6.log}"
STREAK_ONLY=false
DAYS=14
TZ_NAME="${TZ_NAME:-Asia/Tokyo}"

# =============================================================================
# 引数パース
# =============================================================================
while [[ $# -gt 0 ]]; do
  case "$1" in
    --log)       LOG_FILE="$2"; shift 2 ;;
    --streak-only) STREAK_ONLY=true; shift ;;
    --days)      DAYS="$2"; shift 2 ;;
    --tz)        TZ_NAME="$2"; shift 2 ;;
    *) echo "Unknown option: $1" >&2; exit 1 ;;
  esac
done

# =============================================================================
# ログファイル確認
# =============================================================================
if [[ ! -f "${LOG_FILE}" ]]; then
  echo "ERROR: ログファイルが見つかりません: ${LOG_FILE}" >&2
  echo "streak: 0 / ${DAYS}"
  exit 1
fi

# =============================================================================
# Python3 で集計 (シェルの日付操作を単純化)
# =============================================================================
python3 - <<PYEOF
import sys
import re
import datetime
from collections import defaultdict

LOG_FILE    = "${LOG_FILE}"
DAYS        = ${DAYS}
STREAK_ONLY = "${STREAK_ONLY}" == "true"
TZ_NAME     = "${TZ_NAME}"

# タイムゾーン変換 (python3.9+ zoneinfo / fallback: UTC+9)
try:
    from zoneinfo import ZoneInfo
    tz = ZoneInfo(TZ_NAME)
except Exception:
    tz = datetime.timezone(datetime.timedelta(hours=9))

# ------------------------------------------------------------------
# ログ解析: "結果:" 行から overall ステータスを抽出
# ------------------------------------------------------------------
# 行例: 2026-05-18T02:05:00Z [healthcheck_l1_l6] 結果: L1=PASS L2=FAIL ... → PASS
RESULT_RE = re.compile(
    r'^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z)'
    r'\s+\[healthcheck_l1_l6\]\s+結果:.*→\s+(PASS|FAIL)',
    re.UNICODE
)

day_runs = defaultdict(lambda: {"total": 0, "pass": 0})

with open(LOG_FILE, "r", encoding="utf-8", errors="replace") as f:
    for line in f:
        m = RESULT_RE.match(line.rstrip())
        if not m:
            continue
        ts_str, overall = m.group(1), m.group(2)
        # UTC → JST
        dt_utc = datetime.datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
        dt_local = dt_utc.astimezone(tz)
        day_key = dt_local.date().isoformat()

        day_runs[day_key]["total"] += 1
        if overall == "PASS":
            day_runs[day_key]["pass"] += 1

# ------------------------------------------------------------------
# 日次緑判定 (§2 定義)
#   pass_rate >= 0.95 かつ total_runs >= 240
# ------------------------------------------------------------------
def is_daily_green(day_data):
    total = day_data["total"]
    pass_c = day_data["pass"]
    if total < 240:
        return False, "insufficient_data"
    rate = pass_c / total
    if rate < 0.95:
        return False, f"pass_rate={rate:.1%}"
    return True, "OK"

# ------------------------------------------------------------------
# 集計対象期間: 今日から DAYS 日前まで (JST)
# ------------------------------------------------------------------
today_jst = datetime.datetime.now(tz).date()
period = [today_jst - datetime.timedelta(days=i) for i in range(DAYS - 1, -1, -1)]

# ------------------------------------------------------------------
# 14日連続緑ストリーク計算
# ------------------------------------------------------------------
streak = 0
for d in period:
    day_key = d.isoformat()
    data = day_runs.get(day_key, {"total": 0, "pass": 0})
    green, _ = is_daily_green(data)
    if green:
        streak += 1
    else:
        streak = 0  # リセット

# ------------------------------------------------------------------
# 出力
# ------------------------------------------------------------------
if STREAK_ONLY:
    print(f"streak: {streak} / {DAYS}")
    sys.exit(0)

# テーブル形式で出力
header = f"{'日付':12s}  {'総ラン':>6}  {'PASS':>5}  {'FAIL':>5}  {'PASS率':>7}  日次状態"
print(header)
print("-" * len(header))

for d in period:
    day_key = d.isoformat()
    data = day_runs.get(day_key, {"total": 0, "pass": 0})
    total = data["total"]
    pass_c = data["pass"]
    fail_c = total - pass_c
    green, reason = is_daily_green(data)

    if total == 0:
        rate_str = "N/A"
        status_str = "NO_DATA"
    else:
        rate_str = f"{pass_c / total:.1%}"
        status_str = "GREEN ✓" if green else f"NOT_GREEN ({reason})"

    print(f"{day_key:12s}  {total:>6}  {pass_c:>5}  {fail_c:>5}  {rate_str:>7}  {status_str}")

print()
print(f"連続緑 streak: {streak} / {DAYS} 日")
if streak >= DAYS:
    print("🎉 14日連続緑達成！ローンチ条件 §17 クリア")
else:
    print(f"残り {DAYS - streak} 日で §17 達成")
PYEOF
