#!/bin/bash

# Electron项目构建验证脚本
# 用于验证项目配置是否正确，能否成功构建

set -e

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;36m'
NC='\033[0m' # No Color

# 检查计数
TOTAL_CHECKS=0
PASSED_CHECKS=0

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}Electron项目构建验证${NC}"
echo -e "${BLUE}========================================${NC}\n"

# 检查函数
check_item() {
    TOTAL_CHECKS=$((TOTAL_CHECKS + 1))
    local name=$1
    local command=$2
    
    echo -ne "${YELLOW}检查: ${name}...${NC} "
    
    if eval "$command" > /dev/null 2>&1; then
        echo -e "${GREEN}✓ 通过${NC}"
        PASSED_CHECKS=$((PASSED_CHECKS + 1))
        return 0
    else
        echo -e "${RED}✗ 失败${NC}"
        return 1
    fi
}

check_file() {
    TOTAL_CHECKS=$((TOTAL_CHECKS + 1))
    local name=$1
    local file=$2
    
    echo -ne "${YELLOW}检查文件: ${name}...${NC} "
    
    if [ -f "$file" ]; then
        echo -e "${GREEN}✓ 存在${NC}"
        PASSED_CHECKS=$((PASSED_CHECKS + 1))
        return 0
    else
        echo -e "${RED}✗ 缺失${NC}"
        echo -e "${RED}  文件路径: ${file}${NC}"
        return 1
    fi
}

check_dir() {
    TOTAL_CHECKS=$((TOTAL_CHECKS + 1))
    local name=$1
    local dir=$2
    
    echo -ne "${YELLOW}检查目录: ${name}...${NC} "
    
    if [ -d "$dir" ]; then
        echo -e "${GREEN}✓ 存在${NC}"
        PASSED_CHECKS=$((PASSED_CHECKS + 1))
        return 0
    else
        echo -e "${RED}✗ 缺失${NC}"
        echo -e "${RED}  目录路径: ${dir}${NC}"
        return 1
    fi
}

# 1. 检查Node.js环境
echo -e "\n${BLUE}1. 环境检查${NC}"
check_item "Node.js" "command -v node"
check_item "npm" "command -v npm"

if command -v node > /dev/null 2>&1; then
    NODE_VERSION=$(node --version)
    echo -e "  Node版本: ${GREEN}${NODE_VERSION}${NC}"
fi

if command -v npm > /dev/null 2>&1; then
    NPM_VERSION=$(npm --version)
    echo -e "  npm版本: ${GREEN}${NPM_VERSION}${NC}"
fi

# 2. 检查项目文件
echo -e "\n${BLUE}2. 项目文件检查${NC}"
check_file "package.json" "package.json"
check_file "vite.config.js" "vite.config.js"
check_file "electron-builder.json" "electron-builder.json"
check_file "Electron主进程" "electron/main.js"
check_file "Preload脚本" "electron/preload.js"

# 3. 检查项目目录
echo -e "\n${BLUE}3. 项目目录检查${NC}"
check_dir "源码目录" "src"
check_dir "Electron目录" "electron"
check_dir "构建配置目录" "build"
check_dir "公共资源目录" "public"

# 4. 检查核心源文件
echo -e "\n${BLUE}4. 核心源文件检查${NC}"
check_file "主入口" "src/main.js"
check_file "App组件" "src/App.vue"
check_file "路由配置" "src/router/index.js"
check_file "配置管理" "src/config/index.js"
check_file "WebSocket工具" "src/utils/websocket.js"
check_file "日志工具" "src/utils/logger.js"

# 5. 检查服务文件
echo -e "\n${BLUE}5. 系统服务文件检查${NC}"
check_file "systemd服务" "build/zkxh-digitalhuman.service"
check_file "服务安装脚本" "build/install-service.sh"
check_file "安装后脚本" "build/after-install.sh"

# 6. 检查文档
echo -e "\n${BLUE}6. 文档检查${NC}"
check_file "README" "README.md"
check_file "部署文档" "ELECTRON_DEPLOYMENT.md"
check_file "快速开始" "QUICKSTART.md"
check_file "改造说明" "ELECTRON_REFACTOR.md"

# 7. 检查依赖
echo -e "\n${BLUE}7. 依赖检查${NC}"
if [ -d "node_modules" ]; then
    echo -e "${GREEN}✓ node_modules已安装${NC}"
    PASSED_CHECKS=$((PASSED_CHECKS + 1))
    TOTAL_CHECKS=$((TOTAL_CHECKS + 1))
    
    # 检查关键依赖
    check_dir "Electron" "node_modules/electron"
    check_dir "electron-builder" "node_modules/electron-builder"
    check_dir "Vue" "node_modules/vue"
    check_dir "Vite" "node_modules/vite"
else
    echo -e "${RED}✗ node_modules未安装${NC}"
    echo -e "${YELLOW}  请运行: npm install${NC}"
    TOTAL_CHECKS=$((TOTAL_CHECKS + 1))
fi

# 8. 尝试验证package.json配置
echo -e "\n${BLUE}8. package.json配置验证${NC}"
if [ -f "package.json" ]; then
    # 检查main字段
    if grep -q '"main": "electron/main.js"' package.json; then
        echo -e "${GREEN}✓ main字段配置正确${NC}"
        PASSED_CHECKS=$((PASSED_CHECKS + 1))
    else
        echo -e "${RED}✗ main字段未配置或不正确${NC}"
    fi
    TOTAL_CHECKS=$((TOTAL_CHECKS + 1))
    
    # 检查scripts
    if grep -q '"build:electron"' package.json; then
        echo -e "${GREEN}✓ build:electron脚本已配置${NC}"
        PASSED_CHECKS=$((PASSED_CHECKS + 1))
    else
        echo -e "${RED}✗ build:electron脚本未配置${NC}"
    fi
    TOTAL_CHECKS=$((TOTAL_CHECKS + 1))
fi

# 9. 检查构建产物（如果存在）
echo -e "\n${BLUE}9. 构建产物检查（可选）${NC}"
if [ -d "dist" ]; then
    echo -e "${GREEN}✓ dist目录存在${NC}"
    if [ -f "dist/index.html" ]; then
        echo -e "${GREEN}✓ 前端构建产物存在${NC}"
    fi
fi

if [ -d "dist-electron" ]; then
    echo -e "${GREEN}✓ dist-electron目录存在${NC}"
    
    # 查找AppImage文件
    if ls dist-electron/*.AppImage 1> /dev/null 2>&1; then
        echo -e "${GREEN}✓ 找到AppImage文件${NC}"
    fi
    
    # 查找deb文件
    if ls dist-electron/*.deb 1> /dev/null 2>&1; then
        echo -e "${GREEN}✓ 找到deb安装包${NC}"
    fi
fi

# 输出总结
echo -e "\n${BLUE}========================================${NC}"
echo -e "${BLUE}验证结果总结${NC}"
echo -e "${BLUE}========================================${NC}"
echo -e "总检查项: ${TOTAL_CHECKS}"
echo -e "通过: ${GREEN}${PASSED_CHECKS}${NC}"
echo -e "失败: ${RED}$((TOTAL_CHECKS - PASSED_CHECKS))${NC}"

if [ $PASSED_CHECKS -eq $TOTAL_CHECKS ]; then
    echo -e "\n${GREEN}✓ 所有检查通过！项目已准备就绪。${NC}"
    echo -e "\n${BLUE}下一步操作:${NC}"
    echo -e "  1. 如果node_modules未安装: ${YELLOW}npm install${NC}"
    echo -e "  2. 构建前端: ${YELLOW}npm run build${NC}"
    echo -e "  3. 打包应用: ${YELLOW}npm run build:electron${NC}"
    exit 0
else
    echo -e "\n${YELLOW}⚠ 部分检查未通过，请检查缺失项。${NC}"
    echo -e "\n${BLUE}常见问题解决:${NC}"
    echo -e "  1. 依赖未安装: ${YELLOW}npm install${NC}"
    echo -e "  2. 缺少应用图标: 参考 ${YELLOW}build/README_ICON.md${NC}"
    exit 1
fi
