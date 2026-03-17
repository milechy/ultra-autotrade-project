---
name: defi-security-audit
description: Run security audit checklist for Ultra AutoTrade. Use when reviewing Aikido/Snyk scan results, preparing for external security audit, checking code for vulnerabilities, or evaluating dependency updates.
---

# Security Audit Skill

## When to Use
- Aikido/Snyk スキャン結果の評価
- 外部監査準備
- 依存パッケージの脆弱性対応
- コードセキュリティレビュー

## Severity Classification

### 🔴 即修正必須（ブロッカー）
- Critical / High の脆弱性
- 認証・認可の欠陥（認証バイパス、JWT偽造）
- SQLインジェクション / XSS / SSRF
- 秘密鍵・APIキーのハードコード

### 🟡 次スプリントで対応
- Medium の脆弱性
- 依存パッケージの古いバージョン

### ⚪ 許容（理由を記録）
- Low / Informational
- OctoBot 内部コードの問題（Ultra AutoTrade非管轄）
- テストファイルのダミー値

## 対応済み既知脆弱性
- `python-jose` → `PyJWT` に移行済み（CVE-2024-33663 等）
- `elliptic` — overrides で 6.6.1 に固定
- `openai` — >=2.28.0（ログ漏洩対応）
- `pino` — overrides で ^9.0.0 に固定
- Flask debug=False、Cookie Secure 属性設定済み

## False Positive の分類
- `test_auth.py` 等のハードコードパスワード → テスト用ダミー値
- OctoBot の `configuration.py`, `tentacles_config.py` → Ultra AutoTrade 非管轄

## Security Rules チェック（CLAUDE.md 準拠）
- [ ] #1: Private keys — 環境変数のみ、ハードコード・ログ出力禁止
- [ ] #2: HF < 1.6 → 自動HARD_STOP
- [ ] #3: 単一取引上限 — 総資産の10%
- [ ] #4: 日次取引上限 — 総資産の30%
- [ ] #5: クールダウン — Aave操作間10分
- [ ] #6: emergency_stop — OR論理（手動停止は上書き不可）
- [ ] #7: .env.staging と .env.production で物理的に別キーを使用
- [ ] #8: ログのトークン/キーマスク（先頭6文字+末尾4文字）
- [ ] #9: main ブランチへの直接push禁止
- [ ] #10: LLM出力 — JSON Schema バリデーション必須
