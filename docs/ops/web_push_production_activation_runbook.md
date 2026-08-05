# Web Push 本番有効化 Runbook (2026-08-05)

到達経路（クラスタB）の実装が main に揃ったため、本番で実際に通知を届けるための手順。
**実機到達確認（受け入れ条件 B-1 / B-7）はこの手順を完了しないと開始できない。**

> 前提: production VPS の操作は 3 段階プロトコル
> （phase1-investigator → phase2-implementer → phase3-deployer）経由。
> `.env.production` は hook で保護されている（`guard-env-files.sh`）。
> 本 runbook は**人間が実行する手順書**であり、CLI が自動実行してよい範囲ではない。

---

## 0. 現状（なぜ今まで届かなかったか）

| 要素 | 状態 |
|---|---|
| 購読の永続化 | ✅ `push_subscriptions` テーブル（#1021） |
| 購読 UI / 購読作成 | ✅ フロントエンド配線済み（#1016） |
| 提案時の実配信 | ✅ 配線済み（#1017） |
| 通知設定の尊重 | ✅ `push_enabled` / `preferences.ai_proposal`（#1019） |
| **VAPID 鍵** | ❌ **本番未設定** ← 唯一の残ブロッカー |

`get_vapid_config()` が `None` を返す間、配信は静かにスキップされる（意図的な fail-open）。
つまり**鍵を設定するまで、他が全部揃っていても 1 通も届かない**。

---

## 1. VAPID 鍵の生成（ローカルで実施 / 検証済み手順）

```bash
cd backend && source .venv/bin/activate
cd /tmp && vapid --gen          # private_key.pem / public_key.pem が生成される

python - <<'EOF'
from py_vapid import Vapid01
from cryptography.hazmat.primitives import serialization
import base64
v = Vapid01.from_file("/tmp/private_key.pem")
b64u = lambda b: base64.urlsafe_b64encode(b).decode().rstrip("=")
pub = b64u(v.public_key.public_bytes(serialization.Encoding.X962,
                                     serialization.PublicFormat.UncompressedPoint))
priv = b64u(v.private_key.private_numbers().private_value.to_bytes(32, "big"))
print("VAPID_PUBLIC_KEY=" + pub)          # 87 文字
print("VAPID_PRIVATE_KEY=" + priv)        # 43 文字
EOF

rm -f /tmp/private_key.pem /tmp/public_key.pem   # 出力を控えたら PEM は消す
```

**桁数チェック（違ったらやり直し）**: 公開鍵 87 文字 / 秘密鍵 43 文字。
形式が不正だとフロントの `atob` が `InvalidCharacterError` で落ち、購読自体が作れない。

> 🔑 秘密鍵は環境変数のみ。**コミット禁止・ログ出力禁止**（CLAUDE.md セキュリティルール 1）。
> staging と production で**物理的に異なる鍵**を使うこと（同ルール 7）。

---

## 2. `.env.production` へ設定

```bash
# 追記は必ず printf で改行を保証する（sed -i 禁止 / 前行連結バグ）
printf '\nVAPID_PUBLIC_KEY=<87文字>\n'  >> .env.production
printf 'VAPID_PRIVATE_KEY=<43文字>\n'   >> .env.production
printf 'VAPID_MAILTO=mailto:<運用者メール>\n' >> .env.production
printf 'NEXT_PUBLIC_VAPID_PUBLIC_KEY=<87文字（公開鍵と同じ値）>\n' >> .env.production
```

**4 つ必要**な理由:

| 変数 | 用途 | 反映タイミング |
|---|---|---|
| `VAPID_PUBLIC_KEY` / `VAPID_PRIVATE_KEY` / `VAPID_MAILTO` | backend の送信（`env_file: .env.production` で runtime 注入） | コンテナ再作成 |
| `NEXT_PUBLIC_VAPID_PUBLIC_KEY` | frontend の購読作成（**build-arg**。`--env-file` 経由で置換） | **フロント再ビルド必須** |

> ⚠️ `NEXT_PUBLIC_*` は build-time 埋め込み。env に足しただけでは反映されない。
> **これが今回の障害の根本原因そのもの**。必ず再ビルドすること。

---

## 3. DB マイグレーション（新テーブル）

```bash
docker exec <backend-container> alembic current      # 適用前を記録
docker exec <backend-container> alembic upgrade head
docker exec <backend-container> alembic current      # z7a8b9c0d1e2 になること
```

`push_subscriptions` テーブルが作られる。既存 JSON からの backfill も走るが、
本番は購読 0 件のため 0 件移行になるはず（ログに `backfill: N 件` が出る）。

---

## 4. デプロイ

backend / frontend 双方に変更があるため **full デプロイ**（`--frontend-only` は不可）。

```bash
./scripts/deploy_production.sh
```

> 手打ちの `docker compose build` は禁止（CLAUDE.md / ultra-deploy skill）。

---

## 5. 配線確認（実機テストの前に）

```bash
# (a) backend が鍵を読めているか — null なら失敗、キー文字列が返れば成功
curl -s https://api.ultra-auto-trade.com/notifications/push/vapid-key

# (b) frontend に鍵が焼き込まれたか — ビルド成果物に含まれるか
docker exec <frontend-container> sh -c "grep -rlo '<公開鍵の先頭8文字>' .next | head -3"

# (c) 購読テーブルの存在
docker exec <postgres-container> psql -U ultra -d ultra_autotrade \
  -c "\d push_subscriptions"
```

(a) が `{"publicKey": null}` のままなら**ここで止まる**。先に進んでも届かない。

---

## 6. 実機到達確認（受け入れ条件 B-1 / B-7）

> **静的テストでは代替できない項目。** ここだけは実機が要る。

### iOS（B-7 の核心）

iOS の Web Push は**ホーム画面に追加した PWA でのみ動作する**。Safari のタブから
購読しようとしても失敗する。手順:

1. Safari で本番 URL を開く → 共有 → **ホーム画面に追加**
2. ホーム画面のアイコンから起動（Safari タブからではない）
3. 通知設定タブ → プッシュ通知トグル ON → OS の許可ダイアログで許可
4. 「テスト通知」ボタン → **実機に着信することをスクリーンショットで記録**

**ホーム画面追加を経ずに購読しようとした場合の挙動**が定義され、ユーザーに伝わるか
を併せて確認する（B-7）。現状はエラーメッセージが出るのみで、導線の案内は未実装
（オンボーディング設計として別途検討が必要）。

### Android

1. Chrome で本番 URL を開く（ホーム画面追加は不要）
2. 同上 3〜4

### 確認クエリ

```sql
-- 購読が保存されたか
SELECT id, user_id, left(endpoint, 40) AS endpoint, created_at FROM push_subscriptions;

-- 到達が記録されたか（delivered が「送信した」ではなく「到達した」を表す）
SELECT channel, delivered, count(*) FROM notification_logs
WHERE channel = 'push' GROUP BY channel, delivered;
```

### 再起動をまたぐ永続化（B-2）

```bash
docker compose -f docker-compose.production.yml restart backend-<active>
# 再起動後に購読が残っていること
docker exec <postgres-container> psql -U ultra -d ultra_autotrade \
  -c "SELECT count(*) FROM push_subscriptions;"
```

---

## 7. ロールバック

| 状況 | 対応 |
|---|---|
| 配信が暴走 / 誤配信 | `.env.production` から `VAPID_PRIVATE_KEY` を削除 → backend 再作成。`get_vapid_config()` が `None` を返し**再デプロイなしで即停止**（kill switch 性） |
| テーブルに問題 | `alembic downgrade -1`。JSON 側に旧データが残してあるため情報は失われない |
| フロント側の問題 | 前バージョンイメージへ切り戻し |

---

## 8. 完了条件チェックリスト

- [ ] `/notifications/push/vapid-key` が公開鍵を返す（null でない）
- [ ] `alembic current` = `z7a8b9c0d1e2`
- [ ] iOS 実機に着信（スクリーンショット）— B-1
- [ ] Android 実機に着信（スクリーンショット）— B-1
- [ ] ホーム画面追加なしの iOS 挙動を確認・記録 — B-7
- [ ] backend 再起動後も購読が残る — B-2
- [ ] `notification_logs` に `channel='push'` かつ `delivered=true` の行 — B-3
- [ ] 通知設定を OFF にすると届かなくなる — B-N4
- [ ] 購読解除後は届かない — B-N3

> 完了宣言には実機の出力（クエリ結果・スクリーンショット）を貼ること。
> 型チェック / lint / unit test の通過だけを根拠に「完了」と書かない（CLAUDE.md）。

---

## 関連

- 要件定義: `docs/internal/2026-08-04_execution_pipeline_requirements.md`
- テーブル定義: `docs/ops/02_db_tables.md` の `push_subscriptions`
- デプロイ手順: `docs/ops/03_deploy_procedures.md`
- 実装 PR: #1015 / #1016 / #1017 / #1019 / #1021 / #1022
