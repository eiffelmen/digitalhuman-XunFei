# 使用Python 3.12 slim镜像
FROM python:3.12-slim

# 安装uv
COPY --from=ghcr.io/astral-sh/uv:0.8.15 /uv /uvx /bin/

# 设置工作目录
WORKDIR /app

# 复制依赖文件
COPY pyproject.toml uv.lock /app/

# 安装依赖
RUN uv sync --locked

# 复制应用代码
COPY . .

# 暴露端口
EXPOSE 8000

# 健康检查
HEALTHCHECK --interval=30s --timeout=3s \
  CMD curl -f http://localhost:8000/health || exit 1

# 启动命令
CMD ["uv","run","fastapi","run","app/main.py","--host","0.0.0.0","--port","8000"]
