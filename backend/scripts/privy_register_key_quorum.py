#!/usr/bin/env python3
# Copyright (c) Ultra AutoTrade. All rights reserved.
# backend/scripts/privy_register_key_quorum.py
"""Privy key quorum 登録ツール（v4 Phase 2-D-B.2 / L0・1回実施）。

サーバ authorization 鍵（P-256）を Privy アプリに **key quorum** として登録し、返る
quorum ID（= ``SERVER_SIGNER_ID`` = signerId）を取得する。委譲署名フロー L0
（`docs/ops/v4_phase2d_consent_flow_design.md`）の唯一の手作業をスクリプト化したもの。

⚠️ これは Privy アプリ（"UAT" 等）への **設定変更**である。実施前に必ず小林さんに確認すること。

前提環境変数（dev VPS の creds など）::

    PRIVY_APP_ID                    必須
    PRIVY_APP_SECRET                必須（Basic auth）
    PRIVY_AUTHORIZATION_PRIVATE_KEY 任意（既存サーバ鍵 = PKCS8 DER の base64）

使い方::

    # 既存のサーバ鍵から公開鍵を導出して登録（推奨・spike 鍵を再利用）
    PRIVY_APP_ID=... PRIVY_APP_SECRET=... PRIVY_AUTHORIZATION_PRIVATE_KEY=... \
      python backend/scripts/privy_register_key_quorum.py --display-name "uata-server-signer"

    # 新しいサーバ鍵を生成して登録（生成された秘密鍵を env に保存する運用）
    PRIVY_APP_ID=... PRIVY_APP_SECRET=... \
      python backend/scripts/privy_register_key_quorum.py --generate --display-name "uata-server-signer"

    # 実際に投げる前に内容だけ確認
    ... python backend/scripts/privy_register_key_quorum.py --dry-run

秘密鍵は **標準出力にのみ** 1 度表示する（ログには出さない）。表示された秘密鍵は
``PRIVY_AUTHORIZATION_PRIVATE_KEY`` に保存し、**絶対にコミットしない**（.env は gitignore 済）。
"""

from __future__ import annotations

import argparse
import os
import sys

# backend/ を import パスに追加（リポジトリ直叩き実行に対応）
_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

from app.privy.rest_client import PrivyRestClient, PrivyRestError  # noqa: E402
from app.privy.server_keys import (  # noqa: E402
    derive_public_key_spki_b64,
    generate_server_authorization_keypair,
)


def _parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Register a Privy key quorum (L0).")
    p.add_argument(
        "--generate",
        action="store_true",
        help="新しいサーバ鍵を生成する（既定は env の PRIVY_AUTHORIZATION_PRIVATE_KEY を使う）",
    )
    p.add_argument(
        "--display-name",
        default="uata-server-signer",
        help="key quorum の表示名（監査用）",
    )
    p.add_argument(
        "--threshold",
        type=int,
        default=1,
        help="authorization_threshold（既定 1 = 単独サーバ signer）",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Privy に投げず、登録予定の公開鍵と body だけ表示する",
    )
    return p.parse_args(argv)


def main(argv: list[str]) -> int:
    args = _parse_args(argv)

    app_id = os.getenv("PRIVY_APP_ID", "")
    app_secret = os.getenv("PRIVY_APP_SECRET", "")
    if not app_id or not app_secret:
        print("ERROR: PRIVY_APP_ID / PRIVY_APP_SECRET が未設定です。", file=sys.stderr)
        return 2

    generated_private: str | None = None
    if args.generate:
        generated_private, public_key = generate_server_authorization_keypair()
    else:
        existing = os.getenv("PRIVY_AUTHORIZATION_PRIVATE_KEY", "")
        if not existing:
            print(
                "ERROR: PRIVY_AUTHORIZATION_PRIVATE_KEY が未設定です。"
                "（既存鍵を使わない場合は --generate を指定）",
                file=sys.stderr,
            )
            return 2
        try:
            public_key = derive_public_key_spki_b64(existing)
        except ValueError as exc:
            print(f"ERROR: 秘密鍵をロードできません: {exc}", file=sys.stderr)
            return 2

    print("=== Privy key quorum 登録 (L0) ===")
    print(f"display_name        : {args.display_name}")
    print(f"authorization_threshold: {args.threshold}")
    print(f"public_key (SPKI b64): {public_key}")

    if args.dry_run:
        print("\n[dry-run] Privy には投げていません。--dry-run を外すと実行します。")
        if generated_private is not None:
            _emit_generated_private(generated_private)
        return 0

    client = PrivyRestClient(app_id=app_id, app_secret=app_secret)
    try:
        result = client.create_key_quorum(
            public_keys=[public_key],
            authorization_threshold=args.threshold,
            display_name=args.display_name,
        )
    except PrivyRestError as exc:
        print(f"ERROR: key quorum 作成失敗: {exc}", file=sys.stderr)
        return 1

    signer_id = result.get("id", "")
    print("\n✅ 登録成功")
    print(f"SERVER_SIGNER_ID (=signerId): {signer_id}")
    print("→ backend env に PRIVY_SERVER_SIGNER_ID として保存してください。")

    if generated_private is not None:
        _emit_generated_private(generated_private)
    return 0


def _emit_generated_private(private_key_b64: str) -> None:
    """生成した秘密鍵を標準出力に 1 度だけ表示（ログ禁止・非コミット）。"""
    print("\n--- 生成された秘密鍵（1 度のみ表示・env に保存し絶対にコミットしない）---")
    print(f"PRIVY_AUTHORIZATION_PRIVATE_KEY={private_key_b64}")
    print("--- ここまで ---")


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
