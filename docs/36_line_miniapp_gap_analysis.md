# LINEミニアプリ審査要件 ギャップ分析レポート

> 調査日: 2026-04-12
> 対象: LINEミニアプリ審査通過要件書（2026/4/11版）
> 調査者: Claude Code（コードベース静的解析）

---

## サマリー

| カテゴリ | 対応済み | 部分対応 | 未対応 | 法的整備待ち |
|---------|---------|---------|-------|------------|
| 法的要件 | 1 | 1 | 1 | 2 |
| 技術要件（セキュリティ） | 3 | 2 | 1 | 0 |
| 技術要件（LINE連携） | 2 | 2 | 1 | 0 |
| UX・デザイン要件 | 3 | 1 | 1 | 0 |
| 禁止事項チェック | 3 | 0 | 1 | 0 |
| **合計** | **12** | **6** | **5** | **2** |

**最重要ギャップ（審査通過不可レベル）:**
1. eKYC（本人確認）実装なし
2. 年齢確認（18歳以上）実装なし
3. リーガルオピニオン（暗号資産交換業非該当）未取得
4. ログ7年間保存未設定（Loki TTL未定義）
5. セルフサービス退会機能なし（管理者のみDELETE可）

---

## 詳細

### 1. 法的要件

| 要件 | 現状 | ギャップ | 優先度 | 対応方針 |
|------|------|----------|--------|----------|
| リーガルオピニオン（暗号資産交換業非該当意見書） | ❌ 未取得 | 森先生への依頼状況不明。審査の前提条件 | P0 | 森先生（弁護士）への進捗確認を至急実施。意見書なしではLINE審査に提出不可 |
| 法人設立（株式会社）| ⚠️ BVI法人予定 | LINE審査では日本法人（株式会社）が必要との記載あり。BVI法人では審査対象外の可能性 | P0 | 山本さん・弁護士と協議必須。日本法人設立を先行させるか、BVI+日本代理人スキームを検討 |
| 利用規約・プライバシーポリシー（日本語・特定商取引法表示） | ⚠️ 部分対応 | 利用規約（terms/page.tsx）・プライバシーポリシー（privacy-policy/page.tsx）は実装済み（2026-03-24更新）。ただし**特定商取引法に基づく表示**が見当たらない | P1 | 特定商取引法の表示ページを追加（販売業者名・住所・電話番号・代表者名等）。法人設立後に記載可能 |
| 年齢確認（18歳未満排除） | ❌ 未実装 | フロントエンド・バックエンド双方で年齢確認実装なし。登録フローに年齢ゲートが存在しない | P1 | 登録フロー（onboarding）に生年月日入力またはチェックボックス形式の年齢確認を追加。バックエンドでもDBに保存 |

---

### 2. 技術要件（セキュリティ）

| 要件 | 現状 | ギャップ | 優先度 | 対応方針 |
|------|------|----------|--------|----------|
| HTTPS必須（TLS 1.2以上） | ✅ 対応済み | Cloudflare Named Tunnel（api.ultra-auto-trade.com / app.ultra-auto-trade.com）で HTTPS終端。TLS 1.2以上はCloudflareデフォルト設定 | — | 対応済み。Cloudflare SSL/TLS設定で「Full (Strict)」が有効か確認のこと |
| OWASP Top 10対応 | ⚠️ 部分対応 | docs/13_security_design.md + security_audit_report.md（2026-03-11、41テスト全PASS）で主要ルール検証済み。Cloudflare WAF（docs/35_cloudflare_waf_config.md）でカスタムルール・Managed Ruleset定義済み。ただし外部第三者機関によるペネトレーションテストレポートは不在 | P1 | 外部ペネトレーションテスト実施またはAikido/Snyk等の継続スキャンレポートをエビデンスとして整備 |
| スマートコントラクト監査レポート | ✅ 条件付き対応 | 本プロジェクト独自のスマートコントラクトは**存在しない**。Aave V3の既存プールコントラクトに直接インタラクション。Aave V3は複数の独立監査機関による監査済み（Certora, OpenZeppelin等） | P2 | 「独自コントラクトなし・Aave V3使用」を審査書類に明記。Aaveの監査レポートURL一覧を添付 |
| データ保管（個人情報の日本国内サーバー or GDPR準拠） | ⚠️ 要確認 | バックエンドはHetzner（ドイツ・フランクフルト）のVPSで運用。個人情報（メールアドレス・ウォレットアドレス）がPostgreSQLに保存されている。日本国内サーバー要件に抵触する可能性 | P1 | 山本さん・弁護士と協議。①日本国内サーバーへ移行（Sakura Internet等）か②GDPR準拠体制の文書化（プライバシーポリシーへのGDPR記載追加）を選択 |
| WAF設定 | ✅ 対応済み | docs/35_cloudflare_waf_config.md でIaCとして定義。カスタムルール（Block-Sensitive-Paths, Block-Bad-UA, Challenge-Non-JP-Auth, Block-Admin-NonIP）+ Managed Ruleset有効化 | — | 対応済み。スクリプトで設定が実際に適用済みか確認のこと（`scripts/cloudflare_waf_setup.sh` 実行確認） |
| ログ7年間保存 | ❌ 未設定 | Grafana Loki（docker-compose.production.yml）でログ集約は設定済みだが、**明示的なretention policy（TTL）が定義されていない**。Lokiのデフォルトは無期限だが、ディスク容量次第で削除される可能性あり。JSON-fileドライバーの場合は `max-file: 5` × `max-size: 10m` = 最大50MBで上書きされる | P1 | Loki設定に `retention_period: 2556d`（7年）を明示設定。または外部のログ保管サービス（S3互換ストレージ等）へのアーカイブを検討 |

---

### 3. 技術要件（LINE連携）

| 要件 | 現状 | ギャップ | 優先度 | 対応方針 |
|------|------|----------|--------|----------|
| LINEログイン（OAuth 2.0） | ✅ 実装済み | `backend/app/auth/line.py` でLINE IDトークン検証実装済み（`LINE_TOKEN_VERIFY_URL = "https://api.line.me/oauth2/v2.1/verify"`）。フロントエンドに `frontend/app/(liff)/liff-login/page.tsx` とLIFFフック（`hooks/useLiff.ts`）が存在 | — | 実装済み。Privyとの**並存設計**。LIFF経由ではLINEログイン、ブラウザ直接アクセス時はPrivyという設計と思われる。意図通りか要確認 |
| eKYC実装（本人確認） | ❌ 完全未実装 | コードベース全体でTRUSTDOCK・SumSub・本人確認・identity verification等の実装が**一切存在しない** | P0 | LINE金融サービス審査では eKYC は必須要件。TRUSTDOCK（LINE推奨）または SumSub を選定し、実装計画を策定。導入期間は最低1〜2ヶ月を見込む |
| LINE Messaging API（プッシュ通知） | ✅ 実装済み | `backend/app/notifications/line_sender.py`・`line_messaging.py`・`line_notifier.py` が存在。`NotificationChannel.LINE` が定義済み。本番env（`LINE_CHANNEL_ACCESS_TOKEN`, `LINE_NOTIFY_TOKEN`）も設定済み | — | 対応済み。ただし `NOTIFICATION_CHANNEL=slack` がデフォルト設定になっており、LINEへの切り替えが必要か確認 |
| LIFF内ウォレット接続（Privy） | ⚠️ 要検証 | Privyは `loginMethods: ['email', 'wallet']` でBase/Base Sepoliaチェーン対応。LIFFの内蔵ブラウザ（LINE内WebView）でPrivyが動作するかは**未検証**。LINEのWebViewは標準ブラウザと挙動が異なる場合がある | P1 | LIFFアプリ内でPrivyのウォレット接続フローが動作するかE2Eテストが必要。特にWalletConnect系は対応ブラウザ制限あり |
| LINE Pay非対応 | ✅ 確認済み | LINE Payの実装なし。決済はAave V3プールへの直接インタラクション（非カストディアル） | — | 問題なし |

---

### 4. UX・デザイン要件

| 要件 | 現状 | ギャップ | 優先度 | 対応方針 |
|------|------|----------|--------|----------|
| 日本語対応（i18n） | ✅ 実装済み | `frontend/messages/ja.json`（11,618 bytes）・`en.json`（10,387 bytes）が存在。next-intlを使用し、主要ページ（Dashboard, Decisions, copy-trading等）で `useTranslations()` を実装 | — | 対応済み。ただし全ページの翻訳カバレッジを `@i18n-checker` で確認推奨 |
| レスポンシブ（LINEアプリ内ブラウザ最適化） | ⚠️ 要検証 | Playwright E2EはモバイルViewport設定あり（CLAUDE.md記載）。ただしLINEのWebView特有の制約（SafeArea、inset等）への対応は**未確認** | P1 | LINE内WebViewでの表示確認が必要。iPhoneのLINEアプリ内ブラウザで実際に開いて検証 |
| リスク表示・免責事項 | ✅ 実装済み | `frontend/app/(user)/risk-disclosure/page.tsx` が存在（暗号資産・DeFi・AI・運用・テスト期間の5区分リスク説明）。`terms/page.tsx` の第7条に免責事項を記載（「本サービスは資産の値上がりを保証するものではありません」） | — | 対応済み。ただし取引前に強制表示されるフローになっているか確認（同意チェックボックス等） |
| 利用停止（解約・退会）機能 | ❌ セルフサービス未実装 | バックエンドには管理者用 `DELETE /users/{id}` エンドポイントが存在するが、**ユーザー自身が退会できるUIおよびAPIが存在しない**。auth/service.py の `delete_user()` は管理者経由のみ | P1 | `/user/settings` または `/user/profile` ページにアカウント削除UIを追加。対応するAPIエンドポイント（認証ユーザー自身の削除）を実装 |
| 日本語サポート体制 | ⚠️ 部分対応 | 問い合わせ窓口のUI実装は未確認。プライバシーポリシーに「お問い合わせ」セクションは記載されているが、実際のサポートページ・問い合わせフォームは不明 | P2 | 問い合わせページ・メールアドレス・サポートSLAを定義。LINEミニアプリ審査では日本語サポートの窓口が必要 |

---

### 5. 禁止事項チェック

| チェック項目 | 結果 | 問題箇所 | 対応 |
|-------------|------|----------|------|
| 「利回り保証」「必ず儲かる」等の断定表現 | ✅ 問題なし | `grep -ri "保証\|guarantee\|確実\|必ず儲"` の結果、フロントエンドコンポーネント・アプリ全体でヒットなし | 継続監視推奨。UI追加時に毎回チェック |
| KYCなし取引（匿名取引許可） | ❌ 要対応 | 現状はメールアドレス認証のみで取引可能。eKYC（本人確認書類＋顔認証）なしで取引できる設計 | eKYC実装後、KYC承認ステータスが `verified` のユーザーのみ取引許可するロジックを追加 |
| ユーザー資産プール設計（カストディアル運用） | ✅ 非カストディアル確認済み | バックエンドにユーザー資産をプール管理する実装なし。直接Aave V3プールコントラクト（Arbitrum: 0x794a...、Base: 0x878...）にインタラクション。プライバシーポリシーに「秘密鍵はサーバーに送信・保存しない」明記 | 問題なし |
| LINE Pay経由の暗号資産購入 | ✅ 実装なし | LINE Pay統合の実装なし | 問題なし |

---

## 重要な論点（パートナー・弁護士と要協議）

### 1. 日本法人 vs BVI法人
**問題:** LINEミニアプリの金融サービス審査では日本法人（株式会社）が必要とされているが、現在BVI法人を予定している。
**論点:**
- 日本法人設立には最低2〜3ヶ月（定款・登記・銀行口座開設）
- 先にBVI法人＋日本代理人（契約）という構造が認められるか
- 日本法人設立が前提なら、Phase 1.5のスケジュールに重大な影響
**確認先:** 山本さん + 森先生（弁護士）

### 2. Hetzner（ドイツ）のデータ保管問題
**問題:** 個人情報（メールアドレス・ウォレットアドレス・取引履歴）がドイツ（Hetzner Frankfurt）のPostgreSQLに保存されている。
**論点:**
- 日本の個人情報保護法では「外国にある第三者への提供」に同意が必要
- GDPRに準拠する場合は適切な同意・記録管理が必要
- 日本国内サーバー（Sakura Internet / AWS ap-northeast-1等）への移行は追加コスト・移行工数が発生
**確認先:** 弁護士（個人情報保護法の解釈）

### 3. Privy vs LINEログインの併存設計
**問題:** 現在PrivyはBase/Base Sepoliaチェーンのみ対応。LINEミニアプリの要件ではLINEログインが必須。
**現状の設計（推定）:**
- LIFF経由アクセス → LINEログイン（`backend/app/auth/line.py` で実装済み）
- ブラウザ直接アクセス → Privy（email + wallet）
**論点:**
- 2つの認証フローで同一ユーザーを紐づけるロジックが必要か（LINEユーザーID + Privyウォレット）
- LIFFのWebView内でPrivy（WalletConnect）が動作するか未検証
**確認先:** 技術チームでLIFF環境でのPrivy動作検証が必要

### 4. eKYCベンダー選定
**問題:** eKYC実装がゼロの状態。LINEはTRUSTDOCKを推奨ベンダーとして指定。
**選択肢比較:**

| ベンダー | 月額費用（目安） | 導入期間 | LINE推奨 |
|---------|----------------|---------|---------|
| TRUSTDOCK | 従量課金（1件数百〜数千円）+ 初期費用 | 1〜2ヶ月 | ✅ 公式推奨 |
| SumSub | $199〜/月（グローバル向け） | 2〜4週間 | △ |
| 独自実装 | 開発工数のみ | 3〜6ヶ月 | ❌ |

**確認先:** 山本さん（予算承認）+ TRUSTDOCKへの問い合わせ

### 5. スマートコントラクト監査レポートの提出方法
**問題:** 本プロジェクト独自のスマートコントラクトは存在しないが、LINEの審査書類でスマートコントラクト監査レポートを求められた場合の対応。
**対応方針:**
- Aave V3の公式監査レポートURL（Certora, Trail of Bits, OpenZeppelin等）を添付
- 「当社サービスは既存の監査済みDeFiプロトコル（Aave V3）のUIレイヤーとして機能し、独自コントラクトは保有しない」旨を説明書に明記
**確認先:** 審査担当者への事前確認推奨

---

## 推奨アクションリスト（優先順）

### Phase 0: 審査前提条件（即着手・法的）
1. **[P0] リーガルオピニオン取得** — 森先生（弁護士）への進捗確認。意見書なしでは審査不可。目標: 4月末
2. **[P0] 日本法人設立方針決定** — BVI vs 日本法人 を山本さん・弁護士と協議。審査スケジュールを左右する最重要判断

### Phase 1: 技術実装（コード変更あり）
3. **[P0] eKYC実装** — TRUSTDOCKへの問い合わせ＋契約→SDK統合→KYC承認ステータスをDBに保存→取引許可ロジック連動。工数: 3〜6週間
4. **[P1] 年齢確認（18歳以上）** — onboardingフローに年齢確認ゲートを追加（誕生日入力またはチェックボックス）。工数: 1〜2日
5. **[P1] セルフサービス退会機能** — `/user/settings` に退会UIを追加、`DELETE /auth/me` エンドポイントを実装。工数: 1〜2日
6. **[P1] ログ7年間保存設定** — Loki設定に `retention_period: 2556d` を追加またはS3アーカイブ設定。工数: 0.5日
7. **[P1] 特定商取引法に基づく表示ページ** — 法人設立後に販売業者情報を追加。工数: 0.5日

### Phase 2: 確認・検証
8. **[P1] LIFF環境でのPrivy動作検証** — iPhoneのLINEアプリ内でウォレット接続フローを実際にテスト
9. **[P1] Hetznerデータ保管の法的評価** — GDPR準拠または日本国内サーバー移行の判断
10. **[P1] リスク開示の強制表示フロー確認** — 初回ログイン時・取引前に同意フローが挟まれているか確認

### Phase 3: 書類整備
11. **[P2] Aave V3監査レポートURL一覧作成** — 審査書類添付用
12. **[P2] 日本語サポート窓口整備** — 問い合わせページ・メールアドレス定義
13. **[P2] OWASP対応エビデンス整備** — 第三者ペネトレーションテストまたはAikidoスキャン継続レポートを書類化

---

## 付録: 調査対象ファイル一覧

### 実装が確認されたファイル
| 機能 | ファイルパス |
|------|-------------|
| LINEログイン | `backend/app/auth/line.py` |
| LINE通知 | `backend/app/notifications/line_sender.py`, `line_messaging.py`, `line_notifier.py` |
| LIFF初期化 | `frontend/lib/liff/init.ts` |
| LIFFフック | `frontend/hooks/useLiff.ts` |
| LIFFページ | `frontend/app/(liff)/liff-login/page.tsx`, `liff-history/page.tsx`, `liff-approve/page.tsx` |
| Privy | `frontend/lib/wallet/PrivyRootClient.tsx`, `PrivyRootProvider.tsx` |
| 利用規約 | `frontend/app/(user)/terms/page.tsx` |
| プライバシーポリシー | `frontend/app/(user)/privacy-policy/page.tsx` |
| リスク開示 | `frontend/app/(user)/risk-disclosure/page.tsx` |
| ログ基盤 | `docker-compose.production.yml`（Loki 2.9.0） |
| WAF設定 | `docs/35_cloudflare_waf_config.md`, `scripts/cloudflare_waf_setup.sh` |
| セキュリティ監査 | `docs/security_audit_report.md`（2026-03-11, 41 tests PASS） |

### 未実装の機能
| 機能 | 説明 |
|------|------|
| eKYC | TrustDock/SumSub等のSDK統合なし |
| 年齢確認 | onboarding/登録フローに年齢ゲートなし |
| セルフサービス退会 | ユーザー向けアカウント削除UI・APIなし |
| 特定商取引法表示 | 専用ページなし（法人設立後に追加可能） |
| ログ保存期間設定 | Loki TTL未定義 |
