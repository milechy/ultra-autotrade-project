# Lesson Learned: 2026-05-02 mainnet 切替時の frontend 表示テキスト見落とし

## サマリ

2026-05-01 の Base Sepolia → Base Mainnet 切替時、backend env と RPC は移行されたが、
`frontend/app/page.tsx` 内の "Base Sepolia" / "テストネット" ハードコード表記が残存し、
山本さん (production tester) が「ネットワーク選択肢が testnet しかない」と報告 (2026-05-02 朝)。

## 何が起きたか

- 5/1 21:00 JST: backend mainnet 切替完了 (chain_id=8453, AAVE_NETWORK=base)
- 5/1 20:31 JST: frontend image 再ビルド (mainnet build.args)
- 5/1 22:30 JST: 山本さんに mainnet 切替完了 DM 送信
- 5/2 朝: 山本さんから「ネットワークが Sepolia (testnet) のみ表示」報告
- 原因: `frontend/app/page.tsx` に L64/L69/L136 の 3 箇所で "Base Sepolia" がハードコード

## なぜ起きたか

1. **docs/43_mainnet_wallet_switch_guide.md にユーザー表記チェックが完全欠落**
   - 技術設定 (env / RPC / Pool address) のチェックリストはあった
   - 「ユーザー目に触れる表示テキスト」のチェック項目がなかった

2. **5/1 検証で「frontend HTML chain_id 表示なし = build-time 焼き込み想定通り」と誤判定**
   - HTML レンダリング後のテキスト内容を `curl/grep` で確認していれば検出できた

3. **既存 E2E テストが画面遷移・ボタン操作のみテスト、表記内容を検証していなかった**
   - Gate 4 E2E 50/0 fail でも "Base Sepolia" 表記は通過した

## どう防ぐか (本 PR の対応)

- `docs/43` §2.5 に frontend 表示テキスト確認セクション新規追加
- `scripts/verify.sh` に Gate 0 として chain config consistency check 追加
- `frontend/e2e/landing-mainnet.spec.ts` 新規 (Sepolia 表記検出 E2E)
- `.github/PULL_REQUEST_TEMPLATE.md` にチェーン関連チェックリスト追加

## 教訓

1. **「build-time 焼き込み = 確認不能」は誤った前提**: HTML curl で確認可能
2. **Gate 4 E2E pass = 全て OK ではない**: 表記内容は別途検証必要
3. **チェックリストは「技術設定」と「ユーザー表記」の 2 軸でカバーすべき**
4. **chain ID の数値監視と画面表記テキスト監視は別レイヤー**

## 関連

- インシデント Asana: 1214462618475072
- 再発防止 Asana (本タスク): 1214462619161978
- 5/1 切替検証 (見落としタスク): 1214447554925211
- 5/1 切替実装: 1214445769180837
- docs/43: GID 1214115535703860
