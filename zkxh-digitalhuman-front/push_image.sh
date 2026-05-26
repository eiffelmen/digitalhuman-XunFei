#!/bin/bash
set -e  # 任何命令失败立即退出

REGISTRY_HOST=36.103.180.159
REGISTRY_PORT=8099
IMAGE_NAME=digitalhuman/front
VERSION=${1:-$(date +%Y%m%d%H%M%S)}  # 支持手动传入版本号，默认用时间戳
FULL_IMAGE=$REGISTRY_HOST:$REGISTRY_PORT/$IMAGE_NAME

echo ">>> 构建镜像: $FULL_IMAGE:$VERSION"
docker build -t $FULL_IMAGE:$VERSION .

echo ">>> 同时打 latest 标签"
docker tag $FULL_IMAGE:$VERSION $FULL_IMAGE:latest

echo ">>> 推送镜像"
docker push $FULL_IMAGE:$VERSION
docker push $FULL_IMAGE:latest

echo ">>> 完成: $FULL_IMAGE:$VERSION"
