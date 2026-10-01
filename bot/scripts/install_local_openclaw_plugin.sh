#!/bin/bash
set -e

# 安裝本地 OpenClaw OpenViking 外掛
# 用法: ./install_local_openclaw_plugin.sh [--rebuild]
#
# 選項:
#   --rebuild   只重新編譯，不重新複製檔案

REBUILD=false
if [[ "$1" == "--rebuild" ]]; then
  REBUILD=true
fi

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# 源目錄：openviking 根目錄下的 examples/openclaw-plugin
OPENCLAW_PLUGIN_SOURCE="$(dirname "$SCRIPT_DIR")/../examples/openclaw-plugin"
OPENCLAW_PLUGIN_DIR="$HOME/.openclaw/extensions/openviking"

echo "=== 安裝本地 OpenClaw OpenViking 外掛 ==="
echo "源目錄: $OPENCLAW_PLUGIN_SOURCE"
echo "目標目錄: $OPENCLAW_PLUGIN_DIR"

# 檢查源目錄是否存在
if [[ ! -d "$OPENCLAW_PLUGIN_SOURCE" ]]; then
  echo "錯誤: 源目錄不存在: $OPENCLAW_PLUGIN_SOURCE"
  exit 1
fi

# 刪除舊的外掛目錄
if [[ "$REBUILD" == "false" ]]; then
  echo "刪除舊外掛目錄..."
  rm -rf "$OPENCLAW_PLUGIN_DIR"

  # 複製原始檔到外掛目錄
  echo "複製原始檔..."
  cp -r "$OPENCLAW_PLUGIN_SOURCE" "$OPENCLAW_PLUGIN_DIR"

  # 複製 tsconfig.json
  echo "複製 tsconfig.json..."
  cp "$OPENCLAW_PLUGIN_SOURCE/tsconfig.json" "$OPENCLAW_PLUGIN_DIR/"

  # 安裝依賴
  echo "安裝依賴..."
  cd "$OPENCLAW_PLUGIN_DIR"
  npm install --include=dev
fi

# 編譯 TypeScript
echo "編譯 TypeScript..."
cd "$OPENCLAW_PLUGIN_DIR"
npx -p typescript tsc -p tsconfig.json

# 重啟 OpenClaw
echo "重啟 OpenClaw..."
if command -v openclaw &> /dev/null; then
  openclaw gateway restart
  sleep 2
  echo ""
  echo "=== 等待外掛載入，按 Ctrl+C 退出日誌 ==="
  openclaw logs --follow | grep -E "openviking|context-engine|error.*plugin" | head -10
else
  echo "警告: openclaw 命令未找到，請手動重啟 OpenClaw"
fi