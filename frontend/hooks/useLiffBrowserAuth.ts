// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.
// frontend/hooks/useLiffBrowserAuth.ts
//
// ブラウザ PWA モード (NEXT_PUBLIC_LIFF_ID 未設定 = LIFF degrade) で、LINE idToken に
// 依存せず JWT を取得するためのフック。partner 本人の Privy embedded wallet で
// SIWE 風メッセージに署名し、POST /auth/wallet/connect で JWT を発行する。
// 署名・onBehalfOf は build-tx 側でサーバー強制されるため、本フックは「認証」のみを担う。
"use client";

import { useCallback, useState } from "react";
import { usePrivy, useWallets } from "@privy-io/react-auth";
import { ethers } from "ethers";
import { walletConnect } from "@/lib/api/auth";

// ── token key 橋渡し (2 PR 整合: GID 1215441139765963 で ultra_auth_token に一本化予定) ──
// 本 PR: LIFF ページの read key (auth_token) と canonical key (ultra_auth_token) の両方へ
//        同一 JWT を書き込む (dual-write)。
// 一本化 PR: LIFF ページの read を ultra_auth_token に移行し、auth_token 書き込みを除去する。
//            両キーは常に同値のため、移行に伴う localStorage 不整合・gap は発生しない。
// 必ず「本 PR を先に merge → 一本化 PR」を守ること (順序逆転すると LIFF read key が空になる)。
const LIFF_TOKEN_KEY = "auth_token";
const CANONICAL_TOKEN_KEY = "ultra_auth_token";
const CANONICAL_EXPIRES_KEY = "ultra_auth_token_expires";

// lib/auth.ts loginWithWallet と完全同一のメッセージ (バックエンド署名検証と一致させる)。
function siweMessage(address: string): string {
  return `Sign in to Ultra AutoTrade\nAddress: ${address}`;
}

/** `signIn()` の結果。単なる true/false ではなく「なぜ false か」を区別する。 */
export type LiffSignInResult =
  | { ok: true }
  /** Privy 未ログイン → メールモーダルを開いた。エラーではない（呼び出し側は静かに待つ）。 */
  | { ok: false; reason: "login-opened" }
  /** ユーザーが署名を明示的に拒否した（EIP-1193 4001）。 */
  | { ok: false; reason: "rejected" }
  /** それ以外の失敗（通信・wallet 未準備など）。 */
  | { ok: false; reason: "error" };

export interface LiffBrowserAuthResult {
  /** Privy wallet で署名し JWT を発行・保存する。結果の種別は `LiffSignInResult`。 */
  signIn: () => Promise<LiffSignInResult>;
  signingIn: boolean;
  error: string | null;
}

/** EIP-1193 の user-rejected (4001) を厳密判定する。文字列 includes だけに頼らない。 */
function isUserRejection(err: unknown): boolean {
  const code = (err as { code?: unknown })?.code;
  if (code === 4001 || code === "ACTION_REJECTED") return true;
  const msg = (err instanceof Error ? err.message : String(err)).toLowerCase();
  return msg.includes("user rejected") || msg.includes("user denied");
}

export function useLiffBrowserAuth(): LiffBrowserAuthResult {
  const { login } = usePrivy();
  const { wallets } = useWallets();
  const [signingIn, setSigningIn] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const signIn = useCallback(async (): Promise<LiffSignInResult> => {
    setError(null);

    // embedded wallet (Privy TEE) のみ使用。外部 wallet は秘密鍵管理の懸念で除外。
    const wallet = wallets.find((w) => w.walletClientType === "privy");
    if (!wallet) {
      // Privy 未ログイン → メールログイン用モーダルを開く。**これは失敗ではない**。
      // モーダル完了後に wallets が更新され、ユーザーが再度ボタンを押すと下の署名フローへ進む。
      // ここで setSigningIn(true) や catch に入ると、モーダルを開いただけで
      // 「署名がキャンセルされました」を誤表示してしまう（テスター報告 2026-07-17 の不具合）。
      // 署名処理には一切入らないので、エラー文言も spinner も出さず静かにモーダルへ委ねる。
      await login();
      return { ok: false, reason: "login-opened" };
    }

    setSigningIn(true);
    try {
      const address = wallet.address;
      const eip1193 = await wallet.getEthereumProvider();
      const ethProvider = new ethers.BrowserProvider(
        eip1193 as unknown as ethers.Eip1193Provider
      );
      const signer = await ethProvider.getSigner();
      const message = siweMessage(address);
      const signature = await signer.signMessage(message);

      const res = await walletConnect({
        wallet_address: address,
        message,
        signature,
      });

      // dual-write (上記コメント参照)
      localStorage.setItem(CANONICAL_TOKEN_KEY, res.access_token);
      localStorage.setItem(
        CANONICAL_EXPIRES_KEY,
        String(Date.now() + res.expires_in * 1000)
      );
      localStorage.setItem(LIFF_TOKEN_KEY, res.access_token);
      return { ok: true };
    } catch (err) {
      // 「署名がキャンセルされました」は **実際にユーザーが署名を拒否したときだけ** 出す
      // （EIP-1193 4001 で厳密判定。過渡状態の別エラーをキャンセルと誤表示しない）。
      if (isUserRejection(err)) {
        setError("署名がキャンセルされました。もう一度お試しください。");
        return { ok: false, reason: "rejected" };
      }
      setError(
        "ログインに失敗しました。通信環境を確認して、もう一度お試しください。"
      );
      return { ok: false, reason: "error" };
    } finally {
      setSigningIn(false);
    }
  }, [wallets, login]);

  return { signIn, signingIn, error };
}
