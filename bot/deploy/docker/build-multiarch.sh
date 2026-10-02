#!/bin/bash

# Vikingbot 多架構映象構建指令碼
# 功能：
# 1. 構建跨平臺 Docker 映象（linux/amd64 + linux/arm64）
# 2. 支援推送到遠端映象倉庫
# 3. 支援僅本地載入（不推送）

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

# 顏色輸出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# 預設配置
IMAGE_NAME=${IMAGE_NAME:-vikingbot}
IMAGE_TAG=${IMAGE_TAG:-latest}
DOCKERFILE=${DOCKERFILE:-deploy/docker/Dockerfile}
NO_CACHE=${NO_CACHE:-false}
# 平臺列表
PLATFORMS=${PLATFORMS:-linux/amd64,linux/arm64}
# 是否推送（預設僅本地載入）
PUSH=${PUSH:-false}
# 遠端倉庫地址（如需要推送）
REGISTRY=${REGISTRY:-}

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}  Vikingbot 多架構映象構建${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# 1. 檢查 Docker 是否安裝
echo -e "${GREEN}[1/6]${NC} 檢查 Docker..."
if ! command -v docker &> /dev/null; then
    echo -e "${RED}錯誤: Docker 未安裝${NC}"
    echo "請先安裝 Docker: https://www.docker.com/get-started"
    exit 1
fi
echo -e "  ${GREEN}✓${NC} Docker 已安裝"

# 2. 檢查 Docker Buildx
echo -e "${GREEN}[2/6]${NC} 檢查 Docker Buildx..."
if ! docker buildx version &> /dev/null; then
    echo -e "${RED}錯誤: Docker Buildx 不可用${NC}"
    echo "請確保使用 Docker Desktop 或啟用了 Buildx"
    exit 1
fi
echo -e "  ${GREEN}✓${NC} Docker Buildx 已就緒"

# 3. 檢查 Dockerfile 是否存在
echo -e "${GREEN}[3/6]${NC} 檢查 Dockerfile..."
if [ ! -f "$PROJECT_ROOT/$DOCKERFILE" ]; then
    echo -e "${RED}錯誤: Dockerfile 不存在${NC}"
    echo "路徑: $PROJECT_ROOT/$DOCKERFILE"
    exit 1
fi
echo -e "  ${GREEN}✓${NC} Dockerfile 存在"

# 4. 顯示構建配置
echo -e "${GREEN}[4/6]${NC} 構建配置:"
echo "  專案根目錄: $PROJECT_ROOT"
echo "  Dockerfile: $DOCKERFILE"

if [ -n "$REGISTRY" ]; then
    FULL_IMAGE_NAME="${REGISTRY}/${IMAGE_NAME}:${IMAGE_TAG}"
else
    FULL_IMAGE_NAME="${IMAGE_NAME}:${IMAGE_TAG}"
fi

echo "  映象名稱: ${FULL_IMAGE_NAME}"
echo "  目標平臺: ${PLATFORMS}"
echo "  不使用快取: ${NO_CACHE}"
echo "  推送至倉庫: ${PUSH}"

if [ "$PUSH" = "true" ] && [ -z "$REGISTRY" ]; then
    echo ""
    echo -e "${YELLOW}⚠️  警告: PUSH=true 但未指定 REGISTRY${NC}"
    echo -e "   映象將僅本地載入，不會推送${NC}"
    PUSH=false
fi

# 5. 建立/使用 builder 例項
echo -e "${GREEN}[5/6]${NC} 準備 Buildx builder..."
BUILDER_NAME="vikingbot-builder"

# 檢查 builder 是否存在
if ! docker buildx inspect "${BUILDER_NAME}" &> /dev/null; then
    echo "  建立新的 builder 例項..."
    docker buildx create --name "${BUILDER_NAME}" --use
else
    echo "  使用現有的 builder 例項..."
    docker buildx use "${BUILDER_NAME}"
fi
echo -e "  ${GREEN}✓${NC} Builder 已就緒"

# 6. 構建多架構映象
echo -e "${GREEN}[6/6]${NC} 開始構建多架構映象..."
echo ""

cd "$PROJECT_ROOT"

BUILD_ARGS=""
if [ "$NO_CACHE" = "true" ]; then
    BUILD_ARGS="--no-cache"
fi

if [ "$PUSH" = "true" ]; then
    # 推送模式：構建並推送
    echo "模式: 構建並推送至倉庫"
    echo "映象: ${FULL_IMAGE_NAME}"
    echo ""

    docker buildx build $BUILD_ARGS \
        -f "$DOCKERFILE" \
        -t "${FULL_IMAGE_NAME}" \
        --platform "${PLATFORMS}" \
        --push \
        .
else
    # 本地模式：構建並載入到本地（注意：buildx load 僅支援單架構）
    echo "模式: 構建並載入至本地"
    echo ""
    echo -e "${YELLOW}⚠️  注意: buildx load 僅支援單架構${NC}"
    echo -e "   正在構建本地架構映象...${NC}"
    echo ""

    # 檢測本地架構
    if [[ "$(uname -m)" == "arm64" ]] || [[ "$(uname -m)" == "aarch64" ]]; then
        LOCAL_PLATFORM="linux/arm64"
    else
        LOCAL_PLATFORM="linux/amd64"
    fi

    echo "本地架構: ${LOCAL_PLATFORM}"
    echo ""

    docker buildx build $BUILD_ARGS \
        -f "$DOCKERFILE" \
        -t "${FULL_IMAGE_NAME}" \
        --platform "${LOCAL_PLATFORM}" \
        --load \
        .
fi

echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  多架構映象構建完成!${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo "映象資訊:"
echo "  名稱: ${FULL_IMAGE_NAME}"
echo "  平臺: ${PLATFORMS}"
echo ""
echo "常用命令:"
echo "  檢視映象:            ${YELLOW}docker images ${IMAGE_NAME}${NC}"
if [ "$PUSH" != "true" ]; then
    echo "  測試本地映象:        ${YELLOW}docker run --rm ${FULL_IMAGE_NAME} status${NC}"
fi
echo ""
echo "跨平臺使用示例："
echo "  Windows/Mac/Linux (Intel):  使用 linux/amd64 映象"
echo "  Mac (Apple Silicon):        使用 linux/arm64 映象"
echo "  Linux ARM 伺服器:            使用 linux/arm64 映象"
echo ""
echo "推送到遠端倉庫示例："
echo "  REGISTRY=my-registry.com PUSH=true ./deploy/docker/build-multiarch.sh"
echo ""
