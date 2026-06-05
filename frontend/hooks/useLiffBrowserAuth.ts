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

export interface LiffBrowserAuthResult {
  /** Privy wallet で署名し JWT を発行・保存する。成功時 true。Privy 未ログイン時は login() を開いて false。 */
  signIn: () => Promise<boolean>;
  signingIn: boolean;
  error: string | null;
}

export function useLiffBrowserAuth(): LiffBrowserAuthResult {
  const { login } = usePrivy();
  const { wallets } = useWallets();
  const [signingIn, setSigningIn] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const signIn = useCallback(async (): Promise<boolean> => {
    setError(null);
    setSigningIn(true);
    try {
      // embedded wallet (Privy TEE) のみ使用。外部 wallet は秘密鍵管理の懸念で除外。
      const wallet = wallets.find((w) => w.walletClientType === "privy");
      if (!wallet) {
        // Privy 未ログイン → メールログイン用モーダルを開く。完了後ユーザーが再度ボタンを押す。
        await login();
        return false;
      }

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
      return true;
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      if (msg.includes("User rejected") || msg.includes("user rejected")) {
        setError("署名がキャンセルされました。もう一度お試しください。");
      } else {
        setError(
          "ログインに失敗しました。通信環境を確認して、もう一度お試しください。"
        );
      }
      return false;
    } finally {
      setSigningIn(false);
    }
  }, [wallets, login]);

  return { signIn, signingIn, error };
}
