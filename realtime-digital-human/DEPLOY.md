# 部署指南

历史部署记录和 Docker 操作说明见 [docs/README.md](docs/README.md)。

## 日常开发工作流

**特性分支开发 → 本地验证 → 合并主分支 → 服务器拉取更新 → 重启服务**

### 第一步：特性分支开发

```bash
git checkout main
git pull origin main
git checkout -b feat/你的功能名

# 写代码...

# 本地跑测试
pytest tests -q

git add .
git commit -m "feat: 描述你做了什么"
git push origin feat/你的功能名
```

提交格式参考：
```
feat(tts): 添加 FlashTTS 支持
fix: 修复日志轮转问题
refactor(session): 提取会话清理逻辑
```

### 第二步：合并主分支

```bash
git checkout main
git merge feat/你的功能名
git push origin main
```

### 第三步：服务器拉取更新

```bash
git pull origin main

# 如果有新依赖
uv sync
```

### 第四步：重启服务

```bash
make stop   # 停止旧进程
make start  # 后台启动
```

前台运行（调试时用）：

```bash
bash run_digitalman_server.sh
```

---

## run_digitalman_server.sh 说明

这是服务的唯一启动入口，修改启动参数在这里改。当前配置：

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `LLM_PROVIDER` | `gongan` | LLM 提供商，可选 `rag`、`chatgpt_oss`、`ratubrain`、`aliyun`、`iflytek` |
| `LISTEN_PORT` | `8010` | 服务监听端口，可通过环境变量覆盖 |
| `CUDA_VISIBLE_DEVICES` | `1` | 使用的 GPU 编号，可通过环境变量覆盖 |
| `--max_session` | `10` | 最大并发会话数 |
| `--tts` | `sparktts` | TTS 提供商 |
| `--TTS_SERVER` | `http://localhost:8779` | TTS 服务地址 |
| `--wav2lip_size` | `256` | 模型输出尺寸 |
| `--transport` | `webrtc` | 推流协议 |

脚本中的变量均支持外部覆盖，生产环境无需修改脚本，在服务器上设置环境变量即可：

```bash
# 生产环境启动
LISTEN_PORT=8010 bash run_digitalman_server.sh

# 或提前 export
export LISTEN_PORT=8010
make start
```

---

## 环境初始化（首次部署）

```bash
# 安装依赖
uv sync

# TensorRT 部署需要额外安装
uv pip install onnx tensorrt-cu12

# 验证 CUDA / TensorRT Python 包
uv run python -c "import torch; print(torch.__version__, torch.cuda.is_available())"
uv run python -c "import tensorrt as trt; print(trt.__version__)"

# 启动前预检模型、data、torch、TensorRT/engine
bash scripts/check_deploy_ready.sh

# 复制环境变量配置
cp .env.template .env
# 编辑 .env，填入实际的 API Key 等配置
```

### 生成 TensorRT engine

TensorRT engine 必须在目标 GPU 服务器上生成，不能直接复用其他机器生成的文件。

```bash
cd /home/dsd/wz/digitalhuman-Xinjiang/realtime-digital-human

uv run python scripts/export_wav2lip_onnx.py \
  --checkpoint ./wav2lip256/wav2lip.pth \
  --output ./wav2lip256/wav2lip_256.onnx

PRECISION=fp16 \
ONNX_PATH=./wav2lip256/wav2lip_256.onnx \
ENGINE_PATH=./wav2lip256/wav2lip_server_fp16.engine \
MODEL_SIZE=256 \
MIN_BATCH=1 \
OPT_BATCH=16 \
MAX_BATCH=16 \
WORKSPACE_MIB=2048 \
bash scripts/build_wav2lip_tensorrt.sh
```

生成完成后在 `.env` 中启用：

```bash
WAV2LIP_BACKEND=tensorrt
WAV2LIP_ENGINE_PATH=./wav2lip256/wav2lip_server_fp16.engine
```

如果暂时没有生成 engine，可以先用 PyTorch 后端启动：

```bash
WAV2LIP_BACKEND=pytorch bash run_iflytek_server.sh
```

---

## 注意事项

- `.env` 不提交到 git，包含敏感配置
- `make start` 默认把启动日志写到 `logs/server.log`
- GPU 不够用时调小 `--max_session`
- `uv run` 默认会同步依赖；依赖已安装且需要快速重启时，可设置 `UV_NO_SYNC=1`
- `wav2lip.pth`、`*.onnx`、`*.engine`、`data/` 都是运行资产或生成产物，不提交到 GitHub

---

## 故障排查

```bash
# 查看实时日志
tail -f logs/server.log

# 确认进程在跑
ps aux | grep app_v2.py

# 确认端口在监听
ss -tlnp | grep 8010
```

常见部署报错：

| 报错 | 原因 | 处理 |
|------|------|------|
| `ModuleNotFoundError: No module named 'torch'` | 新 `.venv` 没有同步依赖 | `cd realtime-digital-human && uv sync` |
| `ModuleNotFoundError: No module named 'tensorrt'` | 当前环境缺 TensorRT Python 包 | `uv pip install tensorrt-cu12` |
| `TensorRT engine not found` | `.env` 开了 TensorRT，但 engine 文件不存在 | 按“生成 TensorRT engine”重新生成 |
| `exec: python: not found` | 系统没有 `python` 命令 | 构建脚本会优先使用 `uv run --no-sync python`；确认已安装 `uv` |
| `Failed to deserialize TensorRT engine` | engine 与当前 TensorRT/GPU/驱动环境不匹配 | 删除旧 engine，在当前服务器重新生成 |
