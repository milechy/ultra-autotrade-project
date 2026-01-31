#!/bin/bash

# リポジトリの構造を取得
tree -L 3 -I 'node_modules|.git' > repo_structure.txt

# package.jsonの内容を取得
cat package.json > package_info.txt 2>/dev/null || echo "No package.json found"

echo "リポジトリ構造とpackage.jsonを取得しました"
echo "これらのファイルをClaude.aiにアップロードして分析を依頼してください"
