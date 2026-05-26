.PHONY: dev build push deploy docker certfile electron electron-dev electron-build install-service

# Web开发模式
dev:
	npm run dev

# Web构建
build:
	npm run build

# 构建并推送镜像到镜像仓库
push:
	bash push_image.sh

# 在部署服务器上拉取最新镜像并重启
deploy:
	bash deploy.sh

# Electron开发模式（需要先启动web dev服务器）
electron-dev:
	npm run dev:electron

# Electron完整构建（打包为AppImage和deb）
electron-build:
	npm run build:electron

# Electron快速构建（仅打包目录）
electron-build-dir:
	npm run build:electron:dir

# 安装systemd服务（需要在Ubuntu系统上执行）
install-service:
	cd build && sudo ./install-service.sh install

# 卸载systemd服务
uninstall-service:
	cd build && sudo ./install-service.sh uninstall

# Docker方式启动（Web版本）
docker:
	docker-compose up -d --build

# 生成本地证书（Web HTTPS开发用）
certfile:
	mkcert -cert-file certs/service.pem -key-file certs/service-key.pem example.com myapp.dev localhost 127.0.0.1 ::1

# 帮助信息
help:
	@echo "可用的命令:"
	@echo "  make dev                - 启动Web开发服务器"
	@echo "  make build              - 构建Web生产版本"
	@echo "  make push               - 构建并推送镜像到镜像仓库"
	@echo "  make deploy             - 拉取最新镜像并重启服务"
	@echo "  make electron-dev       - 启动Electron开发模式"
	@echo "  make electron-build     - 打包Electron应用（AppImage+deb）"
	@echo "  make electron-build-dir - 快速打包Electron（仅目录）"
	@echo "  make install-service    - 安装systemd服务（Ubuntu）"
	@echo "  make uninstall-service  - 卸载systemd服务"
	@echo "  make docker             - 使用Docker启动Web版本"
	@echo "  make certfile           - 生成HTTPS证书"
