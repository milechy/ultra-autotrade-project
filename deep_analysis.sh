#!/bin/bash

OUTPUT="deep_project_analysis.txt"

echo "=== DEEP PROJECT ANALYSIS ===" > $OUTPUT
echo "" >> $OUTPUT

# 全てのPythonファイルをリストアップ
echo "## Python Files" >> $OUTPUT
find . -name "*.py" -not -path "*/node_modules/*" -not -path "*/.git/*" >> $OUTPUT
echo -e "\n" >> $OUTPUT

# 各ドキュメントの内容
echo "## All Documentation" >> $OUTPUT
for doc in docs/*.md; do
    echo "### $doc" >> $OUTPUT
    cat "$doc" >> $OUTPUT
    echo -e "\n---\n" >> $OUTPUT
done

# backend全体の構造
echo "## Backend Structure Detail" >> $OUTPUT
tree backend -I '__pycache__|*.pyc' >> $OUTPUT 2>/dev/null || find backend -type f >> $OUTPUT
echo -e "\n" >> $OUTPUT

# frontend全体の構造
echo "## Frontend Structure Detail" >> $OUTPUT
tree frontend -I 'node_modules|.next|build|dist' >> $OUTPUT 2>/dev/null || find frontend -type f >> $OUTPUT
echo -e "\n" >> $OUTPUT

# スクリプトファイルの内容
echo "## Scripts Content" >> $OUTPUT
for script in scripts/*.sh; do
    echo "### $script" >> $OUTPUT
    cat "$script" >> $OUTPUT
    echo -e "\n---\n" >> $OUTPUT
done

# 設定ファイルの検索
echo "## Config Files" >> $OUTPUT
find . -name "*.json" -o -name "*.yaml" -o -name "*.yml" -o -name "*.toml" -o -name "*.env.example" -o -name ".env.template" | grep -v node_modules | grep -v .git >> $OUTPUT
echo -e "\n" >> $OUTPUT

# READMEファイル全て
echo "## All READMEs" >> $OUTPUT
find . -name "README.md" -o -name "readme.md" | while read readme; do
    echo "### $readme" >> $OUTPUT
    cat "$readme" >> $OUTPUT
    echo -e "\n---\n" >> $OUTPUT
done

echo "詳細分析完了: $OUTPUT"
