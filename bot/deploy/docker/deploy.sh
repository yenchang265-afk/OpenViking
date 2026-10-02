#!/bin/bash
# Vikingbot 本地一鍵部署指令碼
# ~/.vikingbot 會掛載到容器的 /root/.vikingbot（bridge 首次啟動時自動初始化）
# 用法: ./deploy/docker/deploy.sh
# 變數: CONTAINER_NAME, IMAGE_NAME, IMAGE_TAG, HOST_PORT, CONTAINER_PORT, COMMAND, AUTO_BUILD, PLATFORM

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

RED=$'\033[0;31m'
GREEN=$'\033[0;32m'
YELLOW=$'\033[1;33m'
BLUE=$'\033[0;34m'
NC=$'\033[0m'

CONTAINER_NAME=${CONTAINER_NAME:-vikingbot}
IMAGE_NAME=${IMAGE_NAME:-vikingbot}
IMAGE_TAG=${IMAGE_TAG:-latest}
HOST_PORT=${HOST_PORT:-18791}
CONTAINER_PORT=${CONTAINER_PORT:-18791}
COMMAND=${COMMAND:-gateway}
AUTO_BUILD=${AUTO_BUILD:-true}
# openviking 只有 linux/amd64 wheel，固定使用 amd64（Apple Silicon 由 Docker Desktop Rosetta 模擬）
PLATFORM=${PLATFORM:-linux/amd64}
VIKINGBOT_DIR=${VIKINGBOT_DIR:-"$HOME/.vikingbot"}

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}  Vikingbot 本地部署${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# 1. 檢查 Docker
echo -e "${GREEN}[1/6]${NC} 檢查 Docker..."
if ! command -v docker &> /dev/null; then
    echo -e "${RED}錯誤: Docker 未安裝${NC}"
    echo "請先安裝 Docker: https://www.docker.com/get-started"
    exit 1
fi
echo -e "  ${GREEN}✓${NC} Docker 已安裝，平臺: ${PLATFORM}"

# 2. 檢查/構建映象
echo -e "${GREEN}[2/6]${NC} 檢查映象 ${IMAGE_NAME}:${IMAGE_TAG}..."
if ! docker images --format "{{.Repository}}:{{.Tag}}" | grep -q "^${IMAGE_NAME}:${IMAGE_TAG}$"; then
    if [ "$AUTO_BUILD" = "true" ]; then
        echo -e "  ${YELLOW}映象不存在，開始自動構建...${NC}"
        PLATFORM="$PLATFORM" IMAGE_NAME="$IMAGE_NAME" IMAGE_TAG="$IMAGE_TAG" \
            "$SCRIPT_DIR/build-image.sh"
    else
        echo -e "${RED}錯誤: 映象不存在。請先執行 build-image.sh${NC}"
        exit 1
    fi
else
    echo -e "  ${GREEN}✓${NC} 映象已存在"
fi

# 3. 初始化 ~/.vikingbot 目錄
echo -e "${GREEN}[3/6]${NC} 初始化 ${VIKINGBOT_DIR}..."
mkdir -p "$VIKINGBOT_DIR/workspace" "$VIKINGBOT_DIR/sessions" "$VIKINGBOT_DIR/sandboxes" "$VIKINGBOT_DIR/bridge"
echo -e "  ${GREEN}✓${NC} 目錄已就緒"

# 4. 檢查配置檔案
echo -e "${GREEN}[4/6]${NC} 檢查配置檔案..."
CONFIG_FILE="$VIKINGBOT_DIR/ov.conf"
if [ ! -s "$CONFIG_FILE" ]; then
    echo -e "  ${YELLOW}配置檔案不存在，建立預設配置...${NC}"
    if command -v openssl &> /dev/null; then
        GATEWAY_TOKEN=$(openssl rand -hex 32)
    else
        GATEWAY_TOKEN=$(dd if=/dev/urandom bs=32 count=1 2>/dev/null | od -An -tx1 | tr -d ' \n')
    fi
    cat > "$CONFIG_FILE" << EOF
{
  "bot": {
    "agents": {
      "provider": "openrouter",
      "model": "openrouter/anthropic/claude-3.5-sonnet",
      "api_key": ""
    },
    "gateway": {
      "host": "0.0.0.0",
      "port": ${CONTAINER_PORT},
      "token": "${GATEWAY_TOKEN}"
    }
  }
}
EOF
    echo ""
    echo -e "${YELLOW}  ⚠  請先編輯配置檔案填入 API Keys，再重新執行此指令碼:${NC}"
    echo -e "     ${YELLOW}$CONFIG_FILE${NC}"
    echo ""
    exit 1
else
    if ! command -v python3 &> /dev/null; then
        echo -e "${RED}錯誤: 驗證現有配置需要 python3${NC}"
        exit 1
    fi

    if ! CONFIG_ERROR=$(python3 - "$CONFIG_FILE" "$CONTAINER_PORT" <<'PYEOF'
import json
import sys

config_path, expected_port = sys.argv[1], int(sys.argv[2])

try:
    with open(config_path, encoding="utf-8") as config_file:
        config = json.load(config_file)
except (OSError, json.JSONDecodeError) as exc:
    print(f"無法讀取有效 JSON: {exc}")
    raise SystemExit(1)

bot = config.get("bot")
if not isinstance(bot, dict):
    print("缺少 bot 配置物件")
    raise SystemExit(1)

gateway = bot.get("gateway")
if not isinstance(gateway, dict):
    print("缺少 bot.gateway 配置物件")
    raise SystemExit(1)

port = gateway.get("port")
if isinstance(port, bool) or not isinstance(port, int):
    print("bot.gateway.port 必須是整數")
    raise SystemExit(1)
if port != expected_port:
    print(
        f"bot.gateway.port ({port}) 與 CONTAINER_PORT ({expected_port}) 不一致"
    )
    raise SystemExit(1)
PYEOF
    ); then
        echo -e "${RED}錯誤: 配置檔案無效: ${CONFIG_ERROR}${NC}"
        echo -e "請修復 ${YELLOW}$CONFIG_FILE${NC} 後重新執行"
        exit 1
    fi

    echo -e "  ${GREEN}✓${NC} 配置文件已存在且端口配置有效"
fi

# 5. 清理舊容器
echo -e "${GREEN}[5/6]${NC} 清理舊容器..."
if docker ps -aq -f "name=^/${CONTAINER_NAME}$" | grep -q .; then
    docker rm -f "${CONTAINER_NAME}" > /dev/null
    echo -e "  ${GREEN}✓${NC} 舊容器已刪除"
else
    echo -e "  ${GREEN}✓${NC} 無舊容器"
fi

# 6. 啟動容器
echo -e "${GREEN}[6/6]${NC} 啟動容器..."
echo "  容器名: ${CONTAINER_NAME}"
echo "  映象:   ${IMAGE_NAME}:${IMAGE_TAG}"
echo "  命令:   vikingbot ${COMMAND}"
echo "  端口:   ${HOST_PORT} → ${CONTAINER_PORT}"
echo "  掛載:   ${VIKINGBOT_DIR} → /root/.vikingbot"
echo ""

docker run -d \
    --name "${CONTAINER_NAME}" \
    --restart unless-stopped \
    --platform "${PLATFORM}" \
    -v "${VIKINGBOT_DIR}:/root/.vikingbot" \
    -p "${HOST_PORT}:${CONTAINER_PORT}" \
    -e OPENVIKING_CONFIG_FILE=/root/.vikingbot/ov.conf \
    "${IMAGE_NAME}:${IMAGE_TAG}" \
    "${COMMAND}"

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  部署成功!${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo "  控制台: ${YELLOW}http://localhost:${HOST_PORT}${NC}"
echo ""
echo "常用命令:"
echo "  檢視日誌:  ${YELLOW}docker logs -f ${CONTAINER_NAME}${NC}"
echo "  進入容器:  ${YELLOW}docker exec -it ${CONTAINER_NAME} bash${NC}"
echo "  重啟:      ${YELLOW}docker restart ${CONTAINER_NAME}${NC}"
echo "  停止:      ${YELLOW}./deploy/docker/stop.sh${NC}"
echo ""
echo "正在輸出日誌 (Ctrl+C 退出)..."
echo "----------------------------------------"
docker logs --tail 20 -f "${CONTAINER_NAME}"
