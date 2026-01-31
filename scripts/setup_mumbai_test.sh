#!/bin/bash
# scripts/setup_mumbai_test.sh
#
# Mumbai E2E テスト環境セットアップスクリプト
#
# Usage:
#     bash scripts/setup_mumbai_test.sh
#     bash scripts/setup_mumbai_test.sh --non-interactive
#
# Security:
#     - 秘密鍵は絶対にコミットしない
#     - .env.test は .gitignore に含まれている

set -euo pipefail

# カラー定義
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# プロジェクトルートディレクトリ
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# デフォルト値
ENV_FILE="$PROJECT_ROOT/backend/.env.test"
ENV_EXAMPLE="$PROJECT_ROOT/backend/.env.test.example"

# ========================================
# ユーティリティ関数
# ========================================

print_header() {
    echo -e "${BLUE}"
    echo "╔══════════════════════════════════════════════════════════════════════╗"
    echo "║              Mumbai E2E Test Environment Setup                       ║"
    echo "╚══════════════════════════════════════════════════════════════════════╝"
    echo -e "${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

print_error() {
    echo -e "${RED}❌ $1${NC}"
}

print_success() {
    echo -e "${GREEN}✅ $1${NC}"
}

print_info() {
    echo -e "${BLUE}ℹ️  $1${NC}"
}

print_security_warning() {
    echo -e "${RED}"
    echo "╔══════════════════════════════════════════════════════════════════════╗"
    echo "║                        ⚠️  セキュリティ警告  ⚠️                         ║"
    echo "╠══════════════════════════════════════════════════════════════════════╣"
    echo "║                                                                      ║"
    echo "║  このスクリプトで生成される .env.test には秘密鍵が含まれます         ║"
    echo "║                                                                      ║"
    echo "║  ❌ .env.test を絶対にコミットしないでください                       ║"
    echo "║  ❌ 秘密鍵を他人と共有しないでください                               ║"
    echo "║  ❌ 本番環境では使用しないでください                                 ║"
    echo "║                                                                      ║"
    echo "╚══════════════════════════════════════════════════════════════════════╝"
    echo -e "${NC}"
}

# ========================================
# セットアップ関数
# ========================================

check_prerequisites() {
    echo "📋 前提条件を確認中..."
    echo ""

    # Python チェック
    if command -v python3 &> /dev/null; then
        print_success "Python3: $(python3 --version)"
    else
        print_error "Python3 が見つかりません"
        exit 1
    fi

    # pip パッケージチェック
    if python3 -c "import eth_account" 2>/dev/null; then
        print_success "eth-account: インストール済み"
    else
        print_warning "eth-account: 未インストール"
        echo "    インストール: pip install eth-account"
    fi

    if python3 -c "import web3" 2>/dev/null; then
        print_success "web3: インストール済み"
    else
        print_warning "web3: 未インストール"
        echo "    インストール: pip install web3"
    fi

    echo ""
}

check_gitignore() {
    echo "📋 .gitignore を確認中..."

    # git check-ignore で実際の除外状態を確認（.env.* パターンも検出可能）
    if git -C "$PROJECT_ROOT" check-ignore -q "backend/.env.test" 2>/dev/null; then
        print_success "backend/.env.test は git で除外されています"
    else
        print_warning "backend/.env.test が git で除外されていません"
        echo "    追加してください: echo 'backend/.env.test' >> .gitignore"
    fi
    echo ""
}

generate_wallet() {
    echo "🔑 テストウォレットを生成中..."

    if [ -f "$SCRIPT_DIR/generate_test_wallet.py" ]; then
        python3 "$SCRIPT_DIR/generate_test_wallet.py" --output "$ENV_FILE" --quiet
        print_success "ウォレットを生成しました"
    else
        print_error "generate_test_wallet.py が見つかりません"
        exit 1
    fi
    echo ""
}

show_faucet_info() {
    echo "💧 Faucet 情報:"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""
    echo "1. Mumbai MATIC Faucet（ガス代用）:"
    echo -e "   ${BLUE}https://faucet.polygon.technology/${NC}"
    echo ""
    echo "2. Aave Test USDC Faucet（テストトークン）:"
    echo -e "   ${BLUE}https://app.aave.com/faucet/${NC}"
    echo "   ※ Mumbai ネットワークを選択してください"
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""
}

show_verification_links() {
    if [ -f "$ENV_FILE" ]; then
        # .env.test からアドレスを抽出
        local address
        address=$(grep "AAVE_WALLET_ADDRESS=" "$ENV_FILE" | cut -d'=' -f2)

        if [ -n "$address" ]; then
            echo "🔍 ウォレット確認リンク:"
            echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
            echo ""
            echo "PolygonScan (Mumbai):"
            echo -e "   ${BLUE}https://mumbai.polygonscan.com/address/${address}${NC}"
            echo ""
            echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
            echo ""
        fi
    fi
}

show_checklist() {
    echo "📝 セキュリティチェックリスト:"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""
    echo "  [ ] .env.test が .gitignore に含まれている"
    echo "  [ ] 秘密鍵をコミットしていない"
    echo "  [ ] テストウォレットに本物の資金を送っていない"
    echo "  [ ] 本番環境で使用していない"
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""
}

show_next_steps() {
    echo "📌 次のステップ:"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""
    echo "1. Faucet でトークンを取得:"
    echo "   - Mumbai MATIC（ガス代）"
    echo "   - Test USDC（Aave テスト）"
    echo ""
    echo "2. ウォレット残高を確認:"
    echo "   - PolygonScan で確認"
    echo ""
    echo "3. E2E テストを実行:"
    echo -e "   ${GREEN}source backend/.env.test${NC}"
    echo -e "   ${GREEN}pytest backend/tests/ -m e2e -v${NC}"
    echo ""
    echo "   または:"
    echo -e "   ${GREEN}RUN_E2E_TESTS=1 pytest backend/tests/ -m e2e -v${NC}"
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""
}

# ========================================
# メイン処理
# ========================================

main() {
    print_header
    print_security_warning

    # 前提条件確認
    check_prerequisites
    check_gitignore

    # 既存の .env.test を確認
    if [ -f "$ENV_FILE" ]; then
        print_warning ".env.test が既に存在します"
        read -p "上書きしますか？ (y/N): " confirm
        if [[ ! "$confirm" =~ ^[Yy]$ ]]; then
            print_info "セットアップをスキップしました"
            exit 0
        fi
    fi

    # ウォレット生成
    generate_wallet

    # 情報表示
    show_faucet_info
    show_verification_links
    show_checklist
    show_next_steps

    print_success "セットアップが完了しました！"
    echo ""
    echo "生成されたファイル: $ENV_FILE"
    echo ""
}

# 非対話モードオプション
if [[ "${1:-}" == "--non-interactive" ]]; then
    print_header
    check_prerequisites
    generate_wallet
    show_faucet_info
    show_verification_links
    print_success "セットアップが完了しました！"
    exit 0
fi

main
