#!/bin/bash

REGISTRY_HOST=${REGISTRY_HOST:-registry.example.com}
REGISTRY_PORT=${REGISTRY_PORT:-8099}
IMAGE=$REGISTRY_HOST:$REGISTRY_PORT/digitalhuman/front:${1:-latest}
CONTAINER_NAME=frontend
CERTS_DIR=${CERTS_DIR:-/data/prod/fe/certs}
BACKEND_HOST=${BACKEND_HOST:-localhost}

# 停止并删除旧容器
docker stop $CONTAINER_NAME 2>/dev/null && echo "停止旧容器: $CONTAINER_NAME"
docker rm $CONTAINER_NAME 2>/dev/null && echo "删除旧容器: $CONTAINER_NAME"

# 拉取镜像
echo ">>> 拉取镜像: $IMAGE"
docker pull $IMAGE

# 启动新容器
docker run -d \
  --name $CONTAINER_NAME \
  --restart unless-stopped \
  -p 80:80 \
  -p 443:443 \
  -e BACKEND_HOST=$BACKEND_HOST \
  -v $CERTS_DIR:/certs:ro \
  $IMAGE

echo ">>> 完成: $CONTAINER_NAME ($IMAGE), backend: $BACKEND_HOST"
