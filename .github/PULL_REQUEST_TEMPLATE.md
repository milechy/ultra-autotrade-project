# 🔀 Pull Request Template

## 📝 このPRの目的
（何を実装 / 修正したかを明確に説明）

---

## 🔧 変更内容（概要）
- （主要な変更点を箇条書き）
- 
---

## 📁 変更したファイル
（例）
- backend/app/ai/analyzer.py
- docs/05_ai_judgement_rules.md

---

## 🧪 動作確認
- [ ] ローカルテスト済み
- [ ] フェーズ要件に沿っている
- [ ] .mdとコードの整合性チェック済み
- [ ] 破壊的変更なし

---

## 📘 関連Issue
例：Closes #23

---

## 📚 ドキュメント更新
- [ ] docs/*.md 更新済み  
- [ ] 変更内容が仕様書と一致している

---

## ⚠ 注意事項
- 要件変更が含まれていないこと
- フェーズ範囲外の作業をしていないこと
- 仕様書（.md）が最新と一致していること

---

## チェーン設定関連 (チェーン関連の PR のみ)

本 PR は **チェーン (mainnet/testnet) の切替** または **chain ID 設定** を含みますか?

- [ ] いいえ (チェーン設定の変更なし)
- [ ] はい — 以下のチェックを実施

チェーン関連 PR の場合は以下を確認:
- [ ] `grep -rn "Sepolia" frontend/` の出力をすべて確認・修正済み
- [ ] `.env.production` の `NEXT_PUBLIC_*` チェーン設定を本番値に更新済み
- [ ] `frontend/components/PrivyProvider.tsx` の chain config 確認済み
- [ ] post-deploy `curl <production URL> | grep -i "sepolia"` で出力ゼロ確認済み
- [ ] ブラウザで実機ランディング目視確認済み (スクリーンショット添付)

参照:
- docs/43_mainnet_wallet_switch_guide.md §2.5 (frontend 表示テキスト確認)
- 2026-05-02 インシデント: Asana GID 1214462619161978
