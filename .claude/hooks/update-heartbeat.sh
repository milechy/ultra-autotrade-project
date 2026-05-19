#!/usr/bin/env bash
# update-heartbeat.sh — PostToolUse hook: tool 実行ごとに heartbeat を更新
# uata-stuck-detector.sh がこのファイルの更新時刻を監視する
date +%s > /tmp/uata-heartbeat
