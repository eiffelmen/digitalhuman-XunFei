#!/bin/bash

# ================= 配置区域 =================
# 仓库地址
REGISTRY="${REGISTRY:-registry.example.com:8099}"
# 项目名
PROJECT="digitalhuman"
# 应用名
APP_NAME="backend"

# 自动生成版本号 (优先使用 Git Short Hash，如果不是 git 仓库则使用时间戳)
if git rev-parse --git-dir > /dev/null 2>&1; then
    VERSION=$(git rev-parse --short HEAD)
else
    VERSION=$(date +%Y%m%d-%H%M)
fi

# 完整的基础镜像名 (不含 Tag)
IMAGE_BASE="${REGISTRY}/${PROJECT}/${APP_NAME}"

# ===========================================

# 颜色输出辅助函数
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

function show_help {
    echo -e "${YELLOW}用法: ./build.sh [模式]${NC}"
    echo ""
    echo "模式:"
    echo "  local   构建 x86 和 arm64 镜像并【加载到本地】 (使用不同后缀标签)"
    echo "  push    构建双架构镜像并【推送到仓库】 (使用统一标签)"
    echo "  clean   清理构建缓存 (可选)"
    echo ""
    echo "当前检测到的版本号: ${GREEN}${VERSION}${NC}"
}

# 1. 本地构建模式 (分开构建，因为 --load 不支持多架构)
function build_local {
    echo -e "${GREEN}>>> [Local Mode] 开始构建并加载到本地 Docker...${NC}"

    # --- 构建 ARM64 ---
    TAG_ARM="${IMAGE_BASE}:arm64-${VERSION}"
    echo -e "${YELLOW}正在构建 ARM64 版本 -> ${TAG_ARM} ...${NC}"
    docker buildx build --platform linux/arm64 -t "${TAG_ARM}" . --load
    
    if [ $? -eq 0 ]; then echo -e "${GREEN}✔ ARM64 构建成功${NC}"; else echo -e "${RED}✘ ARM64 构建失败${NC}"; exit 1; fi

    # --- 构建 AMD64 (x86) ---
    TAG_X86="${IMAGE_BASE}:amd64-${VERSION}"
    echo -e "${YELLOW}正在构建 AMD64 版本 -> ${TAG_X86} ...${NC}"
    docker buildx build --platform linux/amd64 -t "${TAG_X86}" . --load

    if [ $? -eq 0 ]; then echo -e "${GREEN}✔ AMD64 构建成功${NC}"; else echo -e "${RED}✘ AMD64 构建失败${NC}"; exit 1; fi

    echo -e "${GREEN}>>> 所有本地镜像构建完成！${NC}"
    echo "查看命令: docker images | grep ${APP_NAME}"
}

# 2. 推送模式 (合并构建，One Tag Multi Arch)
function build_and_push {
    echo -e "${GREEN}>>> [Push Mode] 开始构建双架构并推送到仓库...${NC}"
    
    # 统一的标签 (不带架构后缀)
    TAG_FULL="${IMAGE_BASE}:${VERSION}"
    
    echo -e "${YELLOW}目标镜像: ${TAG_FULL}${NC}"
    echo -e "${YELLOW}包含架构: linux/amd64, linux/arm64${NC}"

    # 使用 --push 直接推送
    docker buildx build --platform linux/amd64,linux/arm64 -t "${TAG_FULL}" . --push --allow security.insecure

    if [ $? -eq 0 ]; then
        echo -e "${GREEN}>>> 🎉 成功！双架构镜像已推送到: ${TAG_FULL}${NC}"
    else
        echo -e "${RED}>>> ❌ 构建或推送失败${NC}"
        exit 1
    fi
}

# 主逻辑判断
case "$1" in
    "local")
        build_local
        ;;
    "push")
        build_and_push
        ;;
    "clean")
        docker buildx prune -f
        ;;
    *)
        show_help
        exit 1
        ;;
esac
