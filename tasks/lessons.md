# Lessons Learned

ミスパターンを蓄積し、3回発生したらCLAUDE.mdのDoDに昇格する。

## Format

| 日付 | カテゴリ | パターン | 発生回数 | 対策 |
|------|---------|---------|---------|------|
| 2026-03-04 | CI | ruff format 未実行でpush → CI失敗 | 2 | verify コマンドで事前チェック |
| 2026-03-04 | CI | pytest-asyncio 未インストール → async テスト全滅 | 1 | requirements-dev.txt に明記 |
| 2026-03-04 | CI | 未使用import (F401) でpush → lint失敗 | 2 | ruff check --fix を習慣化 |
| 2026-03-04 | Security | settings.json に deny なし → 危険操作が素通り | 1 | deny リスト追加 |

## 昇格ルール

- 発生回数が **3回** に達したパターンは CLAUDE.md の DoD セクションに昇格
- 昇格後はこのテーブルから「✅ 昇格済み」マークを付ける
