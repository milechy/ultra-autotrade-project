# 利用規約改定時の再同意フロー仕様 (Asana 1215263804573649)

作成: 2026-06-02  
対象: Ultra AutoTrade (BtoB PWA + BtoC LIFF 共通)

---

## 1. 概要

利用規約を改定した場合、既存ユーザーは新バージョンへの同意を完了するまで
主要機能（AI 提案・資金操作）を利用できなくする。

同意完了まではブロック画面を表示し、同意後は通常利用に復帰する。

---

## 2. ToS バージョン管理

| 項目 | 仕様 |
|------|------|
| バージョン形式 | `v<major>.<minor>` — 例: `v1.0`, `v1.1`, `v2.0` |
| 現行バージョン | backend 環境変数 `CURRENT_TOS_VERSION` で管理 |
| 判定 | user の最新 `tos_consents.tos_version` ≠ `CURRENT_TOS_VERSION` → 再同意必要 |

```bash
# .env に追記
CURRENT_TOS_VERSION=v1.0
```

minor 改定 (軽微な文言整備) → バージョン上げるかどうかは野澤さん判断。  
major 改定 (権利義務の実質的変更) → 必ずバージョンアップし再同意を強制する。

---

## 3. バックエンド実装

### 3-1. 同意状態チェック API

```
GET /api/v1/tos/check
Authorization: Bearer <token>
```

**Response**

```json
{
  "required": true,
  "current_version": "v1.1",
  "consented_version": "v1.0",
  "deadline": "2026-07-01T00:00:00+09:00"  // null = 猶予なし即時ブロック
}
```

### 3-2. ミドルウェア (FastAPI dependency)

```python
async def require_tos_consent(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> User:
    """未同意ユーザーを 403 でブロックする dependency。"""
    current_version = settings.CURRENT_TOS_VERSION
    latest = (
        db.query(ToSConsent)
        .filter(ToSConsent.user_id == current_user.id,
                ToSConsent.tos_version == current_version)
        .first()
    )
    if latest is None:
        raise HTTPException(
            status_code=403,
            detail={"code": "TOS_CONSENT_REQUIRED", "version": current_version}
        )
    return current_user
```

適用対象 endpoint:
- `POST /api/v1/proposals/{id}/approve`
- `POST /api/v1/proposals/{id}/reject`
- `PATCH /api/v1/users/{id}/risk-mode`
- `POST /api/v1/aave/*` (資金操作系)

適用除外 (同意画面表示に必要):
- `GET /api/v1/tos/*` (同意チェック / 同意記録)
- `GET /api/v1/users/me`
- `GET /api/v1/proposals` (閲覧のみ)
- `GET /health`, `GET /api/v1/auth/*`

### 3-3. 同意記録 API (既存 `/api/v1/tos/consent` を流用)

```
POST /api/v1/tos/consent
{
  "tos_version": "v1.1",
  "is_demo_ack": true
}
```

→ `tos_consents` に新行追加。同一ユーザーが同バージョンを重複 POST しても冪等。

---

## 4. フロントエンド実装

### 4-1. 再同意必要フラグの伝播

`/api/v1/users/me` レスポンスに `tos_consent_required: bool` を追加し、
`AuthProvider` / `useAuth` hook が保持する。

```ts
// frontend/lib/auth.ts
interface CurrentUser {
  // ...既存フィールド
  tosConsentRequired: boolean;
  tosCurrentVersion: string;
}
```

### 4-2. PWA (BtoB) での再同意画面

`AuthProvider` が `tosConsentRequired === true` を検知したら
`/tos-re-consent` ページへリダイレクト（現在の URL を `?next=` で保持）。

`/tos-re-consent` ページ:
1. 新 ToS 全文をスクロール可能エリアで表示
2. スクロール末尾到達 + チェックボックス同意で「同意して続行」ボタンが有効化
3. `POST /api/v1/tos/consent` 成功後、`?next=` の URL へリダイレクト

### 4-3. LIFF (BtoC) での再同意画面

LIFF セッション開始時に `tosConsentRequired` を確認。
True なら `liff-approve` / `liff-history` をブロックし、
LIFF 内に再同意コンポーネントを表示する（別ページではなく overlay）。

---

## 5. 通知フロー

改定発効 **7日前** に以下の通知を送信する (手動トリガー または monthly_line_report_loop 流用):

| チャネル | 対象 | 内容 |
|---------|------|------|
| LINE Push | `line_monthly_opt_in=true` の全ユーザー | 「利用規約改定のお知らせ」Flex Message |
| PWA WebPush | push 登録済みユーザー | 「利用規約が更新されました」 |
| メール | 全ユーザー | システム通知メール |

通知 Flex Message のテンプレートは `backend/app/notifications/templates.py` に追加。

---

## 6. 猶予期間 (grace period)

| 改定種別 | 猶予期間 | 期間中の挙動 |
|---------|---------|------------|
| major 改定 | 7日間 | 再同意バナー表示のみ、機能はブロックしない |
| major 改定 (期間後) | なし | 403 ブロック |
| minor 改定 | なし (任意同意) | バナー表示のみ、機能はブロックしない |

猶予期間は `tos_consents` の `deadline` フィールド (nullable) で管理。  
`deadline is null` = 猶予なし即時ブロック。  
バックエンドの `require_tos_consent` dependency が `deadline` を確認する。

---

## 7. デプロイ手順

1. 新 ToS 文言を `frontend/app/(user)/terms/page.tsx` に反映
2. backend `.env` の `CURRENT_TOS_VERSION` を新バージョンに更新
3. deploy_staging.sh → staging 確認
4. 猶予期間を設ける場合は `deadline` を `tos_consents` 管理テーブルに設定
5. staging / production deploy 後、7日前通知を手動 or スケジューラから発火

---

## 8. 実装 TODO (次回 Lane で着手可能)

| # | タスク | 規模 | 前提 |
|---|--------|------|------|
| 1 | `GET /api/v1/tos/check` endpoint 追加 | XS | PR #425 merge 後 |
| 2 | `require_tos_consent` FastAPI dependency 実装 | S | PR #425 merge 後 |
| 3 | `CURRENT_TOS_VERSION` env var を settings.py に追加 | XS | PR #425 merge 後 |
| 4 | frontend `/tos-re-consent` ページ実装 | M | ① ② 完了後 |
| 5 | LIFF 再同意 overlay コンポーネント | M | ④ と並行可 |
| 6 | 通知テンプレート追加 | S | 独立 |
| 7 | 猶予期間ロジック追加 | S | ② の拡張 |

---

*参照: Asana 1215263804573649 / ToS model: `.claude/worktrees/lane-j-tos-consent/backend/app/tos/`*
