#!/bin/bash
# Vikingbot 映象構建指令碼
# 用法: ./deploy/docker/build-image.sh
# 變數: IMAGE_NAME, IMAGE_TAG, PLATFORM, NO_CACHE, PUSH, REGISTRY

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

RED=$'\033[0;31m'
GREEN=$'\033[0;32m'
YELLOW=$'\033[1;33m'
BLUE=$'\033[0;34m'
NC=$'\033[0m'

IMAGE_NAME=${IMAGE_NAME:-vikingbot}
IMAGE_TAG=${IMAGE_TAG:-latest}
DOCKERFILE=${DOCKERFILE:-deploy/docker/Dockerfile}
NO_CACHE=${NO_CACHE:-false}
PUSH=${PUSH:-false}
REGISTRY=${REGISTRY:-}
# openviking 只有 linux/amd64 wheel，固定使用 amd64（Apple Silicon 由 Docker Desktop Rosetta 模擬）
PLATFORM=${PLATFORM:-linux/amd64}

# 完整映象名
if [ -n "$REGISTRY" ]; then
    FULL_IMAGE="${REGISTRY}/${IMAGE_NAME}:${IMAGE_TAG}"
else
    FULL_IMAGE="${IMAGE_NAME}:${IMAGE_TAG}"
fi

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}  Vikingbot 構建映象${NC}"
echo -e "${BLUE}========================================${NC}"
echo "  映象: ${FULL_IMAGE}"
echo "  平臺: ${PLATFORM}"
echo "  Dockerfile: ${DOCKERFILE}"
echo ""

if ! command -v docker &> /dev/null; then
    echo -e "${RED}錯誤: Docker 未安裝${NC}"
    exit 1
fi

if [ ! -f "$PROJECT_ROOT/$DOCKERFILE" ]; then
    echo -e "${RED}錯誤: Dockerfile 不存在: $PROJECT_ROOT/$DOCKERFILE${NC}"
    exit 1
fi

cd "$PROJECT_ROOT"

BUILD_ARGS="--platform ${PLATFORM}"
[ "$NO_CACHE" = "true" ] && BUILD_ARGS="$BUILD_ARGS --no-cache"
[ "$PUSH" = "true"     ] && BUILD_ARGS="$BUILD_ARGS --push" || BUILD_ARGS="$BUILD_ARGS --load"

echo -e "${GREEN}開始構建...${NC}"
docker buildx build $BUILD_ARGS \
    -f "$DOCKERFILE" \
    -t "${FULL_IMAGE}" \
    .

echo ""
echo -e "${GREEN}構建完成: ${FULL_IMAGE}${NC}"
echo ""
echo "常用命令:"
echo "  測試: ${YELLOW}docker run --rm ${FULL_IMAGE} status${NC}"
echo "  部署: ${YELLOW}./deploy/docker/deploy.sh${NC}"
echo "  多架構推送示例:"
echo "    ${YELLOW}PUSH=true REGISTRY=my-registry.com ./deploy/docker/build-image.sh${NC}"
