# Chaos Test Run N — YYYY-MM-DD

> 本ファイルは `scripts/chaos_test_3day_runner.sh` が自動上書き生成する。
> 手動編集する場合は別ファイルにコピーしてから編集すること。

## メタ情報

- 実行時刻 (UTC): `YYYY-MM-DDTHH:MM:SSZ`
- DRY_RUN: `false`
- 経過秒: `NNN`
- chaos_test_staging.sh rc: `0`

## PASS 判定 4 軸 (docs/launch_decision_criteria_v2.md §2.2)

| 軸 | 判定 | 備考 |
|---|---|---|
| ① kill 後 5 分以内自動再起動 | PASS | chaos_test_staging.sh が判定 |
| ② 再起動後 2 分以内 /health 200 | PASS | chaos_test_staging.sh の Final Health Check |
| ③ Loki に Exited + Started 記録 | `ready` (docker events 併用) | docker events 出力は下段参照 |
| ④ chaos 前後で ai_decisions 継続生成 | PASS | pre=N post=N |

## docker events (chaos 開始 15 分窓、staging-new のみ)

```
1685000000 die ultra-autotrade-loki-staging-new
1685000005 start ultra-autotrade-loki-staging-new
...
```

## chaos_test_staging.sh log (抜粋)

```
[PASS] 復旧成功: 12 秒 (ultra-autotrade-loki-staging-new)
[PASS] Chaos Test PASS
```

## 最終判定

**PASS** — 4 軸全通過 (DRY_RUN=false)
