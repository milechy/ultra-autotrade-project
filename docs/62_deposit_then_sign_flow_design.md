# 設計ドキュメント: 承認 → 入金 → 署名フロー（残高不足を投資ファネルに変える）

> Status: Draft v0.1 / 2026-06-26 / 起案: 残高不足時の UX 改善
> 関連: `docs/61_*`(消費者提案額・案C) / 残高不足フロー調査 (本ドキュメント §1)
> 実装は本ドキュメントのレビュー後に別途（Plan モード → スライス実装）。

---

## 0. 一行サマリ

AI 提案（SUPPLY）に対しユーザーの USDC 残高が不足している場合、現状は **無言で署名まで進み on-chain revert** する。これを「**承認＝投資意図のキャプチャ → 不足分の入金導線 → 着金検知 → 署名・実行**」という非同期フローに変え、利回り目当ての投資意欲を捨てずに着金ラグを吸収する。

---

## 1. 背景・現状の課題（実コード調査結果）

| # | 現状 | ファイル参照 |
|---|---|---|
| G1 | 提案金額は allocation 経路では**実 wallet 残高と無関係**に決まる（残高0でも提案が出る） | `automation/ai_judgment_scheduler.py:150-161` (`_resolve_proposal_amount`) |
| G2 | `build-tx` / `build_deposit_txs` に **`balanceOf` 事前チェックが無い**（残高不足でも未署名 tx を返す） | `proposals/router.py:944-1066` / `aave/client.py:1271-1374` |
| G3 | 署名シートは残高で gate しない・残高表示も無い（承認ボタンは残高で disabled にならない） | `frontend/.../liff-chat/_components/ProposalSignSheet.tsx:84-183,269` |
| G4 | 残高不足は **on-chain revert** として顕在化し、submit-tx の receipt 検証(`status!=1`→400)で初めて検知。EOA approve revert は「残高・ガス代を確認してください」の汎用文言のみ | `proposals/router.py:1068-1129,1259-1263` / `messages/ja.json:671,1114` |
| G5 | partner/consumer 経路の revert は **proposal status を変えず（pending/approved のまま）・execution_attempts も増えず・通知も無い無言失敗**（`failed`遷移/`_record_failed_transaction`/通知は custodial サーバー鍵経路専用） | `proposals/router.py:339-599,1278` |
| G6 | 残高不足→入金への能動的導線が **SUPPLY フローに無い**（`insufficient_funds` ハンドリングは withdraw ページ専用） | `frontend/app/(user)/withdraw/page.tsx:119-120,...` |

→ 実害: **無駄ガス + 分かりにくいエラー + 失敗の不可視化**。安全装置（HARD_STOP/Oracle/onBehalfOf 検証）は機能しているが、残高 UX は穴。

---

## 2. ゴール / 非ゴール

### ゴール
- 残高不足のユーザーを **署名前にブロック**し、無駄ガス・revert を防ぐ。
- 「あといくら必要か」を明示し、**入金導線**（入金アドレス + SBI/取引所→送金ガイド）へ誘導。
- 入金は非同期なので **「入金待ち」状態**で提案を保持し、**着金を検知**したら署名可能化＋通知。
- 署名直前に **再見積もり**（APY/HF/gas/金額）して、着金ラグによる乖離を吸収。
- 既存の **無言失敗（G5）も同時に解消**（revert → `failed` 遷移 + 記録 + 通知を consumer/partner 経路に配線）。

### 非ゴール（今回スコープ外）
- クロスチェーン自動ブリッジの実装（**入金は Base Mainnet 限定**・memory/PR #788 で確定）。
- SBI/取引所 API 連携による自動購入（手動の送金ガイドに留める）。
- custodial（サーバー鍵）自動執行経路の変更。

---

## 3. 制約（設計前提）

1. **入金は非同期**: 取引所→Base USDC 着金は数分〜1時間。「購入してすぐ署名」は秒で完結しない → 「入金待ち」を挟む設計が必須。
2. **Base Mainnet 限定 / ブリッジ未実装**: SBI VCトレード等が Base USDC 出金に非対応なら、ユーザーは「Base 対応取引所で USDC 購入 → 出金」or 手動ブリッジが要る。導線ガイドはこの現実経路を案内する（誤った「自動変換」案内は禁止・PR #788 教訓）。
3. **非カストディアル維持**: 入金は本人操作。バックエンドは **残高検知のみ**（秘密鍵に触れない）。
4. **提案の鮮度**: APY/HF/gas/推奨額は時間で変わる。着金時点で再見積もりが要る。
5. **既存状態機械**: `proposals.status` は `String(20)` で **CHECK 制約なし**（`models.py:67`）→ 新状態追加は **migration 不要**（低コスト）。現状値: `pending / approved / executed / rejected / failed / expired / canceled`。

---

## 4. 画面遷移（liff-chat 消費者）

```
[提案カード]  AI JUDGMENT BUY 86% / 入金(Supply) USDC $1,000 / [見送る][承認する]
      │ 「承認する」= 投資意図キャプチャ
      ▼
[残高チェック]  必要額 vs wallet USDC 残高（build-tx 前 balanceOf）
      ├─ 足りる ───────────────► [署名シート] 現状フロー（再見積もり後に署名・実行）
      └─ 足りない
            ▼
[入金待ちカード]  「あと $X 必要です」
        ・必要額 / 現在残高 / 不足額
        ・入金アドレス（Base / コピー）
        ・SBI/取引所→Base 送金ガイド（所要時間の目安つき）
        ・[入金方法を見る]（DepositPanel へ）
        ・状態: 入金待ち（提案は保持・有効期限内）
            │ バックグラウンドで残高ポーリング
            ▼
[着金検知]  残高 >= 必要額 になった
        ・push/LINE/アプリ内バッジで「入金完了 → 署名できます」
            ▼
[再見積もり]  APY/HF/gas/金額を再取得（着金後の実残高ベースで金額再計算も可）
            ▼
[署名シート]  Privy 署名 → submit-tx → executed
```

---

## 5. proposal 状態機械

### 現状
```
pending ──承認──► approved ──execute──► executed
   │                  │
   │見送る            └─(revert)─► (無言失敗: pending/approved のまま) ← G5 課題
   ▼
rejected
（時間切れ→ expired / 取消→ canceled / attempts超過→ failed[custodialのみ]）
```

### 提案（新状態 `awaiting_funds` を追加）
```
pending ──承認──┬─[残高 OK]──► approved ──sign+execute──► executed
                │                                  └─(revert)─► failed (★G5配線)
                └─[残高不足]──► awaiting_funds
                                   │ 着金検知 (残高 >= 必要額)
                                   ├──► approved （再見積もり → 署名へ）
                                   │ 有効期限切れ
                                   └──► expired （入金催促リマインド: expiry_reminder_sent_at 流用）
awaiting_funds / approved ──見送る/取消──► rejected/canceled
```

- `awaiting_funds`: 承認済みだが入金待ち。提案は保持。
- 既存 `expires_at` / `expiry_reminder_sent_at`（`models.py:96-99`）を入金催促に流用可能。
- ★ revert → `failed` 遷移を consumer/partner 経路にも配線（G5 解消）。`error_message`/`execution_attempts` は既存項目を使用。

---

## 6. バックエンド変更点

| 変更 | 内容 | 対象 |
|---|---|---|
| B1 | **build-tx 前の残高チェック**: `build_deposit_txs` or `build-tx` で `balanceOf` を読み、必要額（amount + gas 余裕）未満なら **402/422 + 不足額**を返す（tx を返さない） | `proposals/router.py:944-1066` / `aave/client.py` |
| B2 | **`awaiting_funds` 状態 + 遷移**: 承認時に残高不足なら `pending→awaiting_funds`。新エンドポイント or approve の分岐 | `proposals/router.py:824-908` |
| B3 | **着金検知**: `awaiting_funds` の提案を対象に wallet USDC 残高を定期ポーリング（軽量 scheduled task / 既存 `_read_wallet_usdc_balance` 流用）。残高 >= 必要額 で `approved` 化 + 通知 | `automation/` 新 loop or 既存 scheduler に追加 |
| B4 | **着金検知の即時版**: フロントが「入金した」と push したら on-demand で残高再確認するエンドポイント（ポーリング待ちを短縮） | `proposals/router.py` 追加 |
| B5 | **再見積もり**: 署名直前（build-tx 時）に APY/HF/gas/推奨額を再計算し、乖離があれば提案を更新 or ユーザーに再確認 | `proposals/router.py` build-tx |
| B6 | **revert → failed 配線（G5）**: submit-tx の receipt 検証失敗時に proposal を `failed` + `error_message` 記録 + 通知。consumer/partner 経路にも適用 | `proposals/router.py:1068-1129,1259-1263` |
| B7 | **必要額メタの保持**: 「いくら不足か」をレスポンス/DB に持たせる（required_usd・detected_balance。新カラム or レスポンス計算） | model/schema |

> 金額精度: USD/USDC は Decimal（CLAUDE.md [CRITICAL] 11）。`balanceOf` の単位(6 decimals)に注意。

---

## 7. フロントエンド変更点（liff-chat）

| 変更 | 内容 | 対象 |
|---|---|---|
| F1 | **承認→残高チェック分岐**: 承認時に build-tx を試み、402/422(残高不足) なら署名シートでなく **入金待ちカード**を表示 | `ProposalActionCard.tsx` / `ProposalSignSheet.tsx` |
| F2 | **入金待ちカード UI**: 必要額/現残高/不足額・入金アドレス・送金ガイド・所要時間・DepositPanel 導線 | 新コンポーネント |
| F3 | **着金検知 UX**: ポーリング（`useUsdcBalance` 流用）or B4 push → 「署名できます」へ状態遷移・通知バッジ | `liff-chat/page.tsx:131,511-519` |
| F4 | **署名シートに残高・必要額表示 + gate**: 残高 < 必要額なら署名ボタン disabled（現状は `isBusy` のみ） | `ProposalSignSheet.tsx:269` |
| F5 | **revert/失敗の文言改善**: 残高不足を明示し入金へ誘導（汎用「残高・ガス代を確認」から具体化） | `messages/ja.json,en.json` |
| F6 | **i18n**: 全文言 ja/en 両対応（CLAUDE.md 標準チェックリスト） | messages |

---

## 8. 再見積もりポリシー（論点）

着金には数分〜1h かかり、その間に状況が変わる。署名直前に：
- **APY / HF after / gas**: 再取得（提案カードの値は参考、実行値は build-tx 時点で再計算）。
- **推奨額**: 着金後の **実残高ベースで再計算**するか、提案額固定か。
  - 案a: 提案額固定（$X）。ユーザーが $X 入れたら署名。シンプル。
  - 案b: 着金後の実残高 × ratio で再算出（多めに入れたら提案額も増える）。柔軟だが UX 複雑。
  - **推奨: 案a（提案額固定）をデフォルト**、将来 b を opt-in。
- **乖離が大きい場合**（APY 低下/HF 悪化）: 署名前に再確認ダイアログ or 提案を再生成。

---

## 9. 通知設計
- `awaiting_funds` 化時: 「入金してください（あと $X）」（liff-chat/LINE）。
- 着金検知時: 「入金完了 → 署名できます」（push/LINE/アプリ内バッジ）。
- 期限接近: 既存 `expiry_reminder_sent_at` を流用した催促。
- 既存 AI判定 WebSocket(wss) / 通知基盤（memory: CSP wss）と整合。

---

## 10. 段階的実装スライス

| スライス | 内容 | 価値 | リスク |
|---|---|---|---|
| **S1 (MVP/守り)** | B1 残高チェック + B6 revert→failed配線 + F4 署名 gate + F5 文言。**残高不足を署名前にブロックし、失敗を可視化** | 無駄ガス・無言失敗を即解消 | 低（金融ロジックなので Plan + テスト） |
| **S2 (導線)** | B2 awaiting_funds + F1/F2 入金待ちカード + F3 ポーリング着金検知 + 入金導線 | 投資ファネル化（意図キャプチャ→入金） | 中（状態機械追加） |
| **S3 (磨き)** | B4 即時着金確認 + B5 再見積もり + B3 サーバー側ポーリング + 通知 | UX 完成・自動化 | 中 |

> **推奨: S1 を先に出す**（守りの穴を即塞ぐ）。S2/S3 は UX 本体。

---

## 11. リスク・未解決論点
1. **SBI→Base の実経路**: SBI VCトレードが Base USDC 出金に対応しているか要確認。非対応なら「対応取引所で購入→Base出金」or ブリッジ手順を案内（誤誘導は PR #788 教訓で厳禁）。所要時間が UX を大きく左右。
2. **有効期限 vs 着金ラグ**: 72h（`_PROPOSAL_EXPIRES_HOURS`）で足りるか。入金待ち中は期限延長 or 再生成のポリシーが要る。
3. **ガス代**: SUPPLY は approve+supply の2tx。残高チェックは USDC だけでなく **ガス用 ETH(Base)** も要確認（sponsor paymaster 有無で変わる・memory: paymaster スライス）。
4. **二重入金/競合**: ポーリングと手動 push の競合、同一提案の多重署名防止（既存 submit-tx ガード活用）。
5. **金額基準（§8 案a/b）** の決定。

---

## 12. DoD / テスト
- pytest: 残高不足→402、awaiting_funds 遷移、着金検知→approved、revert→failed の各分岐。
- Playwright（headed 可視）: 残高不足ユーザーで入金待ちカード表示 → (残高付与) → 署名可能化。
- 金融計算は Decimal、i18n ja/en、RBAC（自己提案限定 VIEWER）維持。
- 安全装置（HARD_STOP/Oracle/onBehalfOf）非回帰。

---

## 13. 次アクション
1. 本ドキュメントのレビュー（§8 金額基準・§11 SBI/Base 経路の意思決定）。
2. **S1（守りの穴埋め）から Plan モードで実装**（残高チェック + revert→failed + 文言）。
3. S2/S3 は S1 マージ後に順次。
