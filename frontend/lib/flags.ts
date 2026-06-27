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
 */
export function isPublicRegistrationEnabled(): boolean {
  return process.env.NEXT_PUBLIC_PUBLIC_REGISTRATION_ENABLED === 'true'
}

/**
 * 「おまかせ（Auto / managed）」運用モードを UI に表示するか。
 *
 * 既定 false（非表示）。おまかせは AI が事前条件の範囲内で売買を自動執行する
 * 一任運用に該当し、日本では投資運用業（金商法）の登録なしに提供できない
 * （森先生 法務判断 2026-06-26）。
 *
 * このフラグを true にしてよいのは「時間が経過したから」ではなく、次のいずれかが
 * 満たされたときのみ:
 *   1. 投資運用業の登録を取得した、または
 *   2. 一任に当たらない設計へ作り変え、法務（森先生）が明示的にクリアした。
 * 上記なしに true にすると無登録投資運用業（刑事罰対象）になるため、安易に
 * フラグを反転しないこと。backend の user_mode 自体は実装済（code-ready-behind-flag）。
 */
export function isAutoModeEnabled(): boolean {
  return process.env.NEXT_PUBLIC_AUTO_MODE_ENABLED === 'true'
}
