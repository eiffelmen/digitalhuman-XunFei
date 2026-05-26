# FROM nvidia/cuda:12.9.1-runtime-ubuntu22.04
# FROM your-server-host:8099/digitalhuman/nvidia/cuda:12.4.1-devel-ubuntu22.04

# cuda向后兼容，这里python安装cuda12.6的pytorch，宿主机的cuda环境大于等于12.6即可
FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.8.15 /uv /uvx /bin/

# 设置工作目录
WORKDIR /app

COPY ./pyproject.toml .
COPY ./.python-version .
COPY ./uv.lock .

RUN uv python install 3.12 --mirror https://python-standalone.org/mirror/astral-sh/python-build-standalone

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked

RUN sed -i 's/self.url_map.add(Rule(rule, endpoint=f))/self.url_map.add(Rule(rule, endpoint=f, websocket=True))/' .venv/lib/python3.12/site-packages/flask_sockets.py


# 复制应用代码
COPY . .

# 暴露端口
EXPOSE 8010
EXPOSE 8011

# 环境变量配置
# TTS_SERVICE: TTS 服务地址
# TTS_TYPE: TTS 类型 (edgetts, gpt-sovits, gpt-sovits-v2, cosyvoice, fishtts, sparktts, flashtts)
# AVATAR_ID: 数字人头像ID (例如: wav2lip_avatar2, wav2lip_avatar5)
ENV TTS_SERVICE=http://tts-service:8778
ENV TTS_TYPE=flashtts
ENV AVATAR_ID=wav2lip_avatar5

CMD bash docker_run_digitalman_server.sh
