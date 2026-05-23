// Copyright (c) Ultra AutoTrade. All rights reserved.
// Unauthorized copying or distribution is strictly prohibited.
"use client";

/**
 * LegalGate.tsx
 *
 * 法務 sign-off 前の「preview / display-only」状態を明示する banner。
 *
 * Launch gate:
 *   環境変数 NEXT_PUBLIC_LEGAL_SIGN_OFF_DONE === "true" になると本 banner は描画されない。
 *   = 法務 sign-off 完了で banner が消える == launch gate。
 *
 * 強調するメッセージ:
 *   1. 本サービスはノンカストディアル（秘密鍵を当社で扱わない）
 *   2. 法務 sign-off 前の preview であり、本機能は機能説明用
 *   3. 実取引は AI スケジューラが全自動で執行する
 *
 * 文言は **法務確認後に最終化** する前提のドラフト。
 */
export interface LegalGateProps {
  /** banner を画面のどの位置に置くかで余白の見た目を調整するための optional class */
  className?: string;
  /** compact 表示（リスト等の上に置く小さい banner）にしたい場合 */
  compact?: boolean;
}

export function LegalGate({ className, compact = false }: LegalGateProps) {
  const signedOff =
    typeof process !== "undefined" &&
    process.env.NEXT_PUBLIC_LEGAL_SIGN_OFF_DONE === "true";

  if (signedOff) {
    return null;
  }

  if (compact) {
    return (
      <div
        role="alert"
        aria-live="polite"
        data-testid="legal-gate-banner-compact"
        className={
          "rounded-lg border border-amber-700 bg-amber-950/30 px-3 py-2 text-xs text-amber-300 " +
          (className ?? "")
        }
      >
        <span className="font-semibold">[法務 sign-off 前 / preview]</span>{" "}
        本機能は機能説明用です。ノンカストディアル。実取引は AI が全自動で実行します。
      </div>
    );
  }

  return (
    <div
      role="alert"
      aria-live="polite"
      data-testid="legal-gate-banner"
      className={
        "rounded-xl border border-amber-700 bg-amber-950/30 p-4 space-y-2 " +
        (className ?? "")
      }
    >
      <div className="flex items-center gap-2">
        <span className="text-lg" aria-hidden="true">
          ⚠️
        </span>
        <h3 className="text-sm font-bold text-amber-300">
          法務 sign-off 前の preview です
        </h3>
      </div>
      <ul className="text-xs text-amber-200 space-y-1 pl-1">
        <li>
          本サービスは <strong>ノンカストディアル</strong>{" "}
          です。当社はあなたの秘密鍵を保管しません。
        </li>
        <li>
          本 UI は <strong>機能説明用 (display-only)</strong>{" "}
          であり、ボタン操作で実取引が発生することはありません。
        </li>
        <li>
          実取引は AI スケジューラが全自動で執行します。文言は法務確認後に最終化されます。
        </li>
      </ul>
    </div>
  );
}

export default LegalGate;
