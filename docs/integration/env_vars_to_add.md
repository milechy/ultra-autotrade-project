# 環境変数追加申請

## Aave Arbitrum Sepolia 接続（feature/aave-arbitrum-poc）

### 新規追加が必要な環境変数

| 環境変数名 | デフォルト値 | 説明 |
|---|---|---|
| `AAVE_NETWORK` | `base_sepolia` | Aave 接続ネットワーク。`base_sepolia` / `arbitrum_sepolia` / `arbitrum` など |
| `ALCHEMY_RPC_URL_ARBITRUM_SEPOLIA` | なし（必須） | Arbitrum Sepolia の RPC URL（Alchemy 推奨） |
| `ALCHEMY_RPC_URL_BASE_SEPOLIA` | なし（オプション） | Base Sepolia の RPC URL |
| `AAVE_WALLET_ADDRESS` | なし（検証スクリプト用） | 読み取り専用確認用ウォレットアドレス |

### 備考
- 秘密鍵は `AAVE_WALLET_PRIVATE_KEY` 環境変数を使用（既存）
- テストネット用 RPC URL は Alchemy の無料プランで取得可能
- `AAVE_NETWORK` は既存の `get_aave_settings()` で読み込まれる（既存変数の用途変更）
