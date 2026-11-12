#!/bin/bash
# ZCode SessionStart 钩子：静默拉起菜单栏 TPS 监控（若未在运行）。
# 注意：本脚本绝不能向 stdout 输出任何内容，否则会被注入会话上下文。
DIR="$(cd "$(dirname "$0")" && pwd)"
PY="$DIR/venv/bin/python3"
[ -x "$PY" ] || PY="$(command -v python3)"
LOG="${TMPDIR:-/tmp}/zmenu_tps.log"

pgrep -f "zmenu_tps.py" >/dev/null 2>&1
if [ $? -ne 0 ]; then
  nohup "$PY" "$DIR/zmenu_tps.py" >> "$LOG" 2>&1 &
fi
exit 0
