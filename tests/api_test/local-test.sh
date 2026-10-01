#!/bin/bash
# OpenViking API 測試 - 本地測試指令碼
# 模擬 GitHub Actions 流水線的執行流程

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  OpenViking API 測試 - 本地執行${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""

# 1. 檢查 Python 版本
echo -e "${YELLOW}[1/7] 檢查 Python 版本...${NC}"
PYTHON_VERSION=$(python3 --version | awk '{print $2}')
echo "Python 版本: $PYTHON_VERSION"
python3 -c "import sys; assert sys.version_info >= (3, 10), 'Python 3.10+ required'"
echo -e "${GREEN}✓ Python 版本檢查通過${NC}"
echo ""

# 2. 安裝 OpenViking
echo -e "${YELLOW}[2/7] 安裝 OpenViking...${NC}"
cd "$(dirname "$0")/../.."
pip install -e .
echo -e "${GREEN}✓ OpenViking 安裝成功${NC}"
echo ""

# 3. 安裝測試依賴
echo -e "${YELLOW}[3/7] 安裝測試依賴...${NC}"
cd tests/api_test
pip install -r requirements.txt
echo -e "${GREEN}✓ 測試依賴安裝成功${NC}"
echo ""

# 4. 建立 OpenViking 配置檔案
echo -e "${YELLOW}[4/8] 建立 OpenViking 配置檔案...${NC}"
mkdir -p ~/.openviking
cat > ~/.openviking/ov.conf << EOF
{
  "server": {
    "root_api_key": "test-root-api-key"
  },
  "vlm": {
    "provider": "volcengine",
    "api_key": "dummy-vlm-api-key",
    "model": "doubao-seed-2-0-mini-260215",
    "api_base": "https://ark.cn-beijing.volces.com/api/v3",
    "temperature": 0.1,
    "max_retries": 3
  },
  "embedding": {
    "dense": {
      "provider": "volcengine",
      "api_key": "dummy-embedding-api-key",
      "model": "doubao-embedding-vision-251215",
      "api_base": "https://ark.cn-beijing.volces.com/api/v3",
      "dimension": 1024,
      "input": "multimodal"
    }
  }
}
EOF
echo -e "${GREEN}✓ 配置檔案建立成功${NC}"
echo ""

# 5. 找到可用端口
echo -e "${YELLOW}[5/8] 查找可用端口...${NC}"
find_available_port() {
    local port=1933
    while true; do
        if ! lsof -Pi :$port -sTCP:LISTEN -t >/dev/null 2>&1; then
            echo $port
            return
        fi
        port=$((port + 1))
    done
}
SERVER_PORT=$(find_available_port)
echo "使用端口: $SERVER_PORT"
echo -e "${GREEN}✓ 找到可用端口${NC}"
echo ""

# 6. 啟動 OpenViking Server
echo -e "${YELLOW}[6/8] 啟動 OpenViking Server...${NC}"
export ROOT_API_KEY=test-root-api-key
export SERVER_PORT=$SERVER_PORT
nohup python -m openviking.server.bootstrap > openviking-server.log 2>&1 &
SERVER_PID=$!
echo $SERVER_PID > openviking-server.pid
echo "Server PID: $SERVER_PID"

# 等待服務啟動
echo "等待服務啟動..."
for i in {1..30}; do
    if curl -s http://127.0.0.1:$SERVER_PORT/health | grep -q '"healthy":true'; then
        echo -e "${GREEN}✓ 服務已就緒！${NC}"
        break
    fi
    echo "等待... ($i/30)"
    sleep 2
done

# 檢查服務是否啟動成功
if ! curl -s http://127.0.0.1:$SERVER_PORT/health | grep -q '"healthy":true'; then
    echo -e "${RED}✗ 服務啟動失敗！${NC}"
    echo "服務日誌："
    cat openviking-server.log
    exit 1
fi
echo ""

# 7. 執行 API 測試
echo -e "${YELLOW}[7/8] 執行 API 測試...${NC}"
export OPENVIKING_API_KEY=test-root-api-key
export SERVER_URL=http://127.0.0.1:$SERVER_PORT
python -m pytest . -v --html=api-test-report.html --self-contained-html --ignore=retrieval/ --ignore=resources/test_pack.py --ignore=resources/test_wait_processed.py
TEST_RESULT=$?
echo ""

# 8. 停止服務
echo -e "${YELLOW}[8/8] 停止 OpenViking Server...${NC}"
if [ -f openviking-server.pid ]; then
    kill $SERVER_PID 2>/dev/null || true
    pkill -f "openviking.server.bootstrap" 2>/dev/null || true
    rm -f openviking-server.pid
fi
echo -e "${GREEN}✓ 服務已停止${NC}"
echo ""

# 總結
echo -e "${GREEN}========================================${NC}"
if [ $TEST_RESULT -eq 0 ]; then
    echo -e "${GREEN}  ✓ 所有測試通過！${NC}"
else
    echo -e "${RED}  ✗ 部分測試失敗${NC}"
fi
echo -e "${GREEN}========================================${NC}"
echo ""
echo "測試報告: tests/api_test/api-test-report.html"
echo "服務日誌: tests/api_test/openviking-server.log"
echo ""

exit $TEST_RESULT
