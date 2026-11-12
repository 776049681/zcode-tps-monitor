#!/bin/bash
# zcode-tps-monitor 一键安装：建 venv、装依赖、（可选）写入 SessionStart 钩子。
#   ./install.sh          # 只建环境
#   ./install.sh --hook   # 建环境并把钩子合并进 ~/.zcode/cli/config.json（先备份）
set -e
DIR="$(cd "$(dirname "$0")" && pwd)"

if [ ! -x "$DIR/venv/bin/python3" ]; then
  echo "==> 创建虚拟环境 venv/"
  python3 -m venv "$DIR/venv"
fi
echo "==> 安装依赖 pyobjc-framework-Cocoa"
"$DIR/venv/bin/python3" -m pip install -q -r "$DIR/requirements.txt"

if [ "${1:-}" = "--hook" ]; then
  CFG="$HOME/.zcode/cli/config.json"
  HOOK_PATH="$DIR/zmenu_tps_launcher.sh"
  chmod +x "$HOOK_PATH"
  echo "==> 合并 SessionStart 钩子到 $CFG（原文件备份为 config.json.bak）"
  "$DIR/venv/bin/python3" - "$CFG" "$HOOK_PATH" << 'PYEOF'
import json, shutil, sys
cfg_path, hook_path = sys.argv[1], sys.argv[2]
shutil.copyfile(cfg_path, cfg_path + ".bak")
try:
    cfg = json.load(open(cfg_path))
except Exception:
    cfg = {}
hooks = cfg.setdefault("hooks", {})
hooks["enabled"] = True
entries = hooks.setdefault("SessionStart", [])
entry = {"matcher": "startup|resume|clear",
         "hooks": [{"type": "command", "command": hook_path, "timeout": 5}]}
if entry not in entries:
    entries.append(entry)
json.dump(cfg, open(cfg_path, "w"), indent=2, ensure_ascii=False)
print("钩子已写入，下次启动 ZCode 会话时监控自动拉起。")
PYEOF
else
  chmod +x "$DIR/zmenu_tps_launcher.sh"
  echo "==> 完成。想开机跟随 ZCode 自动启动的话，运行: $0 --hook"
  echo "    或手动运行: $DIR/venv/bin/python3 $DIR/zmenu_tps.py"
fi
