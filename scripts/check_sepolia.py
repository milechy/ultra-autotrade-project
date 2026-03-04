# scripts/check_sepolia.py
"""
Sepolia RPC 接続 + Health Factor 取得の動作確認スクリプト。
本番コードには含めない（scripts/ に置く）。

Usage:
    cd /path/to/ultra-autotrade
    python scripts/check_sepolia.py
"""

import os
import sys
from decimal import Decimal
from pathlib import Path

from dotenv import load_dotenv

# .env.staging から環境変数を読み込む
load_dotenv(".env.staging")

rpc_url = os.environ.get("AAVE_RPC_URL", "")
wallet = os.environ.get("AAVE_WALLET_ADDRESS", "")

if not rpc_url:
    print("ERROR: AAVE_RPC_URL is not set in .env.staging")
    sys.exit(1)
if not wallet:
    print("ERROR: AAVE_WALLET_ADDRESS is not set in .env.staging")
    print("  -> ウォレットの公開アドレス（秘密鍵ではない）を設定してください")
    sys.exit(1)

# backend をパスに追加
sys.path.insert(0, str(Path(__file__).parent / ".." / "backend"))

from app.aave.client import AaveClientError, Web3AaveClient  # noqa: E402

print(f"RPC: {rpc_url[:30]}...")
print(f"Wallet: {wallet[:6]}...{wallet[-4:]}")
print()

try:
    client = Web3AaveClient(rpc_url=rpc_url)
    print("RPC 接続: OK")

    hf = client.get_health_factor(wallet)
    print(f"Health Factor: {hf}")

    if hf == Decimal("inf"):
        print("  -> ポジションなし（担保未設定 or 借入なし）")
    elif hf < Decimal("1.6"):
        print("  WARNING: HF < 1.6 — HARD_STOP 閾値以下！")
    elif hf < Decimal("1.8"):
        print("  WARNING: HF < 1.8 — WARNING 閾値")
    else:
        print("  -> 安全範囲")

    print()
    print("check_sepolia 完了")

except AaveClientError as e:
    print(f"AaveClientError: {e}")
    sys.exit(1)
except Exception as e:
    print(f"Unexpected error: {e}")
    sys.exit(1)
