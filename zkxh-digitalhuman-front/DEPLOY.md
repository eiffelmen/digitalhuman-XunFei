# 部署指南

## 日常开发工作流

**特性分支开发 → 本地验证 → 合并主分支 → 构建推送镜像 → 部署生效**

### 第一步：特性分支开发

```bash
git checkout main
git pull origin main
git checkout -b feat/你的功能名

# 写代码...
npm run dev    # 本地开发验证（端口 3000）
npm run lint   # 检查代码规范

git add src/...
git commit -m "feat: 描述你做了什么"
git push origin feat/你的功能名
```

### 第二步：本地 Docker 验证（可选但推荐）

合并前先用 Docker 跑一遍，确认构建没问题：

```bash
docker build -t front:test .
docker run --rm -p 8080:80 -e BACKEND_HOST=36.103.180.159 front:test
# 浏览器访问 http://localhost:8080 验证功能
```

### 第三步：合并主分支

```bash
git checkout main
git merge feat/你的功能名
git push origin main
```

### 第四步：构建并推送镜像（开发机执行）

```bash
bash push_image.sh
# 可选：手动指定版本号
bash push_image.sh v1.2.0
```

推送后镜像仓库会有两个 tag：
- `front:20260327143000`（带时间戳，用于回滚）
- `front:latest`（始终指向最新版本）

### 第五步：部署（部署服务器执行）

```bash
bash deploy.sh
# 可选：指定版本号
bash deploy.sh v1.2.0
```

### 回滚

```bash
# 查看可用的历史版本
docker images 36.103.180.159:8099/digitalhuman/front

# 切换到指定版本
bash deploy.sh 20260326120000
```

---

## 部署服务器目录结构

```
/data/prod/fe/
├── deploy.sh       # 部署脚本
└── certs/
    ├── service.pem
    └── service-key.pem
```

证书文件需手动放置，不随镜像分发。

---

## 注意事项

- 确保 `certs/` 下有有效的 SSL 证书（`service.pem` 和 `service-key.pem`）
- 确保服务器 80 和 443 端口未被占用
- `deploy.sh` 需在 `/data/prod/fe/` 目录下执行，或确认脚本内证书路径正确

---

## 故障排查

```bash
# 查看容器日志
docker logs -f frontend

# 检查环境变量是否生效
docker exec frontend env | grep BACKEND_HOST

# 检查 nginx 配置
docker exec frontend cat /etc/nginx/nginx.conf | grep proxy_pass

# 进入容器排查
docker exec -it frontend sh
```
