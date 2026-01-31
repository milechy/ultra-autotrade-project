#!/bin/bash

echo "=== PROJECT DETAILS ===" > project_details.txt
echo "" >> project_details.txt

echo "## README.md" >> project_details.txt
cat README.md >> project_details.txt 2>/dev/null || echo "No README found" >> project_details.txt
echo -e "\n\n" >> project_details.txt

echo "## Backend Requirements" >> project_details.txt
cat backend/requirements.txt >> project_details.txt 2>/dev/null || echo "No requirements.txt" >> project_details.txt
echo -e "\n\n" >> project_details.txt

echo "## Main Backend Code" >> project_details.txt
cat backend/app/main.py >> project_details.txt 2>/dev/null || echo "No main.py" >> project_details.txt
echo -e "\n\n" >> project_details.txt

echo "## Documentation Overview" >> project_details.txt
cat docs/00_overview.md >> project_details.txt 2>/dev/null || echo "No overview" >> project_details.txt
echo -e "\n\n" >> project_details.txt

echo "## Requirements Doc" >> project_details.txt
cat docs/01_requirements.md >> project_details.txt 2>/dev/null || echo "No requirements doc" >> project_details.txt

echo "詳細情報を取得しました: project_details.txt"
