# HANDOFF.md — セッション引き継ぎ

## 現在のフェーズ
- Phase 1: staging テスター運用中（10人）
- Phase 2: PoC 完了（feature/phase2-protocols、devマージ待ち）

## ブランチ状況
- `dev`: staging 安定版（テスター使用中）
- `feature/phase2-protocols`: Lido + Pendle + AI Optimizer + Risk Engine（Codex+Opusレビュー済み）
- `main`: プロダクション（直接push禁止）

## 未完了タスク（優先度順）
1. Phase 2 → dev マージ（テスター完了後）
2. Phase 2 フロントエンド（U-09, A-10）
3. 多言語対応（C-03）

## 注意事項
- Cloudflare Tunnel: フロントエンド + バックエンドの2本が必要
- `NEXT_PUBLIC_*` はビルド時埋め込み — `export` してからビルドすること
- テストネットは Base Sepolia に統一
- Aave / セキュリティ変更は必ず Plan モードで

## Agent Teams 連絡先
- Slack: `#ultra-auto-project`
- Asana: プロジェクトGID 1213741124336104
