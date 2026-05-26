FROM node:22-alpine AS builder
WORKDIR /app
COPY package*.json ./
RUN echo "registry=https://mirrors.cloud.tencent.com/npm/" > /root/.npmrc
RUN echo "electron_mirror=https://mirrors.huaweicloud.com/electron/" >> /root/.npmrc
RUN npm ci && npm cache clean --force
COPY . .
RUN npm run build

FROM nginx:alpine
# 安装 gettext（包含 envsubst 命令）
RUN apk add --no-cache gettext

# 创建证书目录和应用目录
RUN mkdir -p /certs /app /etc/nginx/templates

# 复制构建产物和配置文件模板
COPY --from=builder /app/dist /app
COPY nginx-prod-docker.conf.template /etc/nginx/templates/

# 设置适当的权限
RUN chown -R nginx:nginx /app && \
    chmod -R 755 /app

# 暴露HTTP和HTTPS端口
EXPOSE 80 443

# 使用HTTPS端口做健康检查
HEALTHCHECK --interval=30s --timeout=3s CMD wget -q --spider https://localhost:443/ --no-check-certificate

# 使用启动脚本替换环境变量并启动 nginx
CMD ["/bin/sh", "-c", "envsubst '$BACKEND_HOST' < /etc/nginx/templates/nginx-prod-docker.conf.template > /etc/nginx/nginx.conf && nginx -g 'daemon off;'"]
