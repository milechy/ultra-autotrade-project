# Claude Code Agent View 運用 (2026-05-12 追加)

> 2026-05-21 refactor で `CLAUDE.md` から分離。

## 概要
Claude Code の並列セッションを 1 画面で管理する CLI ダッシュボード (Research Preview)。
tmux / 複数ターミナルタブ運用を置換する。
- 公式: https://claude.com/blog/agent-view-in-claude-code
- 要件: claude-code >= v2.1.139
- 対応プラン: Pro / Max / Team / Enterprise / Claude API

## UATa での運用ルール

1. **起動方法**
   - 既存セッション内: `←` (左矢印) で Agent View に切替
   - 新規起動: ターミナルで `claude agents`
   - 背景投入: 既存セッションを `/bg` で背景化、または `claude --bg "<prompt>"` で新規背景起動
   - フル復帰: 行を選択して `Enter` または `→`、概要のみ確認は `Space` で peek

2. **Tier B 並列 (3-5 レーン) は Agent View に統一**
   - claude.ai 側で生成した複数 CLI プロンプトを `claude --bg "<prompt>"` で順次背景起動
   - 状態把握 (working / waiting / completed / failed / idle / stopped) は Agent View 一覧で確認
   - tmux / 別タブ運用は段階的に廃止

3. **Lane T (終業時 Gate 4 回収) の標準フロー**
   - Agent View で全レーンの状態を一覧
   - waiting / failed のレーンを優先処理
   - 全レーン Playwright E2E (Gate 4) 結果取得後にマージ・Asana close 判定
   - verify.sh 単独通過での close 禁止は不変 (docs/14_test_strategy.md)

4. **Tier S 直列制約は不変**
   - main.py / CLAUDE.md / docker-compose / migrations / scheduled_tasks / monitoring_service / package.json / requirements.txt / nginx upstream は Agent View でも並列化しない
   - これらは前面セッションで 1 本ずつ実行

5. **アカウント切替の前提**
   - UATa 配下では sic.nozawa@gmail.com (Max) で起動 (§15 / direnv 自動切替)
   - Agent View 起動前に `echo "${CLAUDE_CODE_OAUTH_TOKEN:0:13}"` で `sk-ant-oat01-` を確認

6. **無効化 / 制約事項**
   - Org admin は `disableAgentView` managed setting で無効化可能
   - Research Preview 期間中はキーバインドが変更される可能性あり (公式 docs を都度参照)
   - 通常の rate limit が適用される (背景レーン乱立に注意)

7. **PR babysitter / 長時間ループジョブ**
   - スケジュール系プロンプトは Agent View に next run time が表示される
   - 終業時に Lane T で一括確認
