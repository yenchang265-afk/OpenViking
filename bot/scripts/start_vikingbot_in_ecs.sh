#!/bin/bash
# VikingBot Gateway 啟動指令碼

# 獲取指令碼所在目錄
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_ROOT"
# 啟用虛擬環境
echo "Uv sync..."
uv sync

# 啟用虛擬環境
echo "Activating virtual environment..."
source "$PROJECT_ROOT/.venv/bin/activate"

# 確保日誌目錄存在
LOG_DIR="$HOME/logs"
mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/output.log"

# 查詢並 kill vikingbot gateway 程序
echo "Killing existing vikingbot gateway processes..."
pkill -f "vikingbot gateway" || true
pkill -f "uvicorn" || true
pkill -f "agfs" || true

# 等待程序結束
sleep 1

# 啟動 vikingbot gateway
echo "Starting vikingbot gateway..."
nohup vikingbot gateway > "$LOG_FILE" 2>&1 &
PID=$!

echo "VikingBot gateway started with PID: $PID"
echo "Log file: $LOG_FILE"
echo ""
echo "Tailing log file (Ctrl+C to exit)..."
echo "========================================"

# tail 日誌檔案
tail -f "$LOG_FILE"
