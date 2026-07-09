// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.
/**
 * ビルド時フィーチャーフラグ。
 *
 * NEXT_PUBLIC_* は build-time inline なので、値を変えたら frontend 再ビルドが必須。
 */

/**
 * 一般公開（partner 招待不要の自己登録）が有効か。
 *
 * 既定 false。実公開は法務（non-custodial S-5）・LINE 審査・KYC ベンダー判断が
 * 揃ってからフラグを true にして再ビルドする（code-ready-behind-flag）。
 * backend POST /auth/register-open 自体は常時実装済だが、フロント側の到達経路を
 * このフラグで gate する。
 *
 * 2026-07-03: hkobayashi が法務(non-custodial S-5)・KYC ベンダー判断は既に揃って
 * いると確認し、PWA 配布（LINE 審査を経由しない経路）側では true にすることを決定。
 * LINE 審査を経由する配布（staging-v4 / LINE production 版）は審査通過まで false を
 * 維持する（審査中に見せる内容を審査終了前に変えるとレビュー撹乱になるため）。
 * env var は PWA 系(.env.staging-new / PWA 用 .env.production)にのみ設定し、
 * LINE 系(.env.staging-v4)には設定しないこと。
 */
export function isPublicRegistrationEnabled(): boolean {
  return process.env.NEXT_PUBLIC_PUBLIC_REGISTRATION_ENABLED === 'true'
}

/**
 * 「おまかせ（Auto / managed）」運用モードを UI に表示するか。
 *
 * 背景: おまかせは AI が事前条件の範囲内で売買を自動執行する一任運用に該当し、
 * 日本では投資運用業（金商法）の登録なしに提供すると無登録営業（刑事罰対象）
 * になり得る（森先生 法務判断 2026-06-26）。登録取得・設計変更による法務クリア
 * のいずれも満たさないまま有効化することは非推奨。
 *
 * 2026-07-03: hkobayashi が上記リスクを認識した上で「Auto モードも含め全ユーザーに
 * 今すぐ全機能を開放する」と明示決定（法務再クリアを待たない事業判断）。
 * このフラグの既定値をリポジトリ側で true に変更することはしない
 * （production への反映は .env.production 側で NEXT_PUBLIC_AUTO_MODE_ENABLED=true
 * を設定 + frontend 再ビルドで行う。3段プロトコル / 本番デプロイ手順に従うこと）。
 * 詳細: memory `project_jp_auto_mode_open_decision_2026_07_03`。
 */
export function isAutoModeEnabled(): boolean {
  return process.env.NEXT_PUBLIC_AUTO_MODE_ENABLED === 'true'
}

/**
 * 友達紹介プログラムを UI に表示するか。
 *
 * 既定 false（非表示）。「紹介した友達の実利益の N% を継続的に支払う」という
 * 利益連動の金銭リワードは、LINE ミニアプリ審査でマルチ商法的訴求と見なされる
 * リスクがあるため、審査期間中はフラグで非表示にする。審査通過後に文言を
 * 利益非連動の設計へ整備したうえで true にして再ビルドする（code-ready-behind-flag）。
 *
 * 2026-07-03: この理由は LINE 審査リスクのみ（法務ブロッカーとは無関係）と確認済み。
 * hkobayashi の決定により、PWA 配布（LINE 審査を経由しない経路）側では true にする。
 * LINE 審査を経由する配布（staging-v4 / LINE production 版）は審査通過まで false を
 * 維持する。env var は PWA 系(.env.staging-new / PWA 用 .env.production)にのみ設定し、
 * LINE 系(.env.staging-v4)には設定しないこと。
 */
export function isReferralEnabled(): boolean {
  return process.env.NEXT_PUBLIC_REFERRAL_ENABLED === 'true'
}

/**
 * 手数料（月額利用料）の徴収 UI を表示するか。
 *
 * 既定 false。2026-07-09 に「月額徴収自体を撤廃・当面無料（収益モデルなし）」と決定
 * （hkobayashi）。徴収 UI（Stripe カード登録 / on-chain allowance 承認 / 支払い方法設定
 * への導線）はこのフラグで gate し、既定で非表示にする。
 *
 * バックエンド側の徴収も既定 OFF（`ENABLE_MONTHLY_FEE_BATCH` 既定 0 /
 * `FEE_TRANSFER_ENABLED` 既定 false）。将来、料率・法務・決済が整い徴収を再開する場合は、
 * env `NEXT_PUBLIC_FEE_COLLECTION_ENABLED=true` + フロント再ビルド + バックエンド徴収フラグ
 * を同時に有効化する（code-ready-behind-flag）。コードは残置＝可逆。
 */
export function isFeeCollectionEnabled(): boolean {
  return process.env.NEXT_PUBLIC_FEE_COLLECTION_ENABLED === 'true'
}
