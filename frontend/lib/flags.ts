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
