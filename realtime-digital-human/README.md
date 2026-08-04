# 北京中科睿途科技有限公司开发数字人

补充文档索引见 [docs/README.md](docs/README.md)。旧版说明与历史记录已迁移到 [docs/archive/legacy-readme-notes.md](docs/archive/legacy-readme-notes.md)。

## 项目概览

当前仓库主要承载实时数字人后端服务，当前主入口是 `app_v2.py`，启动脚本是 `run_digitalman_server.sh`。

当前能力包括：

1. 基于 `wav2lip` 的实时数字人播报
2. WebRTC 推流
3. 多 LLM provider 切换
4. TTS 对接
5. 会话管理与中断控制

## 快速启动

### 环境要求

- Python `>=3.9`
- 已准备好 `.venv`
- GPU 与模型资源按部署环境准备

### 安装依赖

推荐使用 `uv`：

```bash
uv sync
```

首次部署完成后建议验证关键依赖：

```bash
uv run python -c "import torch; print(torch.__version__, torch.cuda.is_available())"
```

如果访问 Hugging Face 有问题，可在运行前设置：

```bash
export HF_ENDPOINT=https://hf-mirror.com
```

### 启动服务

```bash
bash run_digitalman_server.sh
```

当前脚本默认行为：

- 主入口：`app_v2.py`
- 默认端口：`8010`
- 默认 `LLM_PROVIDER=gongan`
- 可选 `LLM_PROVIDER`：`gongan`、`rag`、`chatgpt_oss`、`ratubrain`、`aliyun`、`iflytek`
- 默认 `CUDA_VISIBLE_DEVICES=1`

可通过环境变量覆盖：

```bash
LLM_PROVIDER=rag LISTEN_PORT=8010 CUDA_VISIBLE_DEVICES=0 bash run_digitalman_server.sh
```

### Wav2Lip TensorRT 加速

默认仍使用 PyTorch 推理；如果部署机已经安装好 NVIDIA 驱动、CUDA 与 TensorRT，可先生成 TensorRT engine，再通过环境变量启用。

先安装导出和构建需要的包：

```bash
uv pip install onnx tensorrt-cu12
uv run python -c "import tensorrt as trt; print(trt.__version__)"
```

1. 导出 ONNX：

```bash
uv run python scripts/export_wav2lip_onnx.py \
  --checkpoint ./wav2lip256/wav2lip.pth \
  --output ./wav2lip256/wav2lip_256.onnx
```

2. 检查 ONNX 输入输出：

```bash
uv run python scripts/inspect_wav2lip_onnx.py ./wav2lip256/wav2lip_256.onnx
```

3. 构建 TensorRT engine：

```bash
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

4. 启用 TensorRT：

```bash
WAV2LIP_BACKEND=tensorrt \
WAV2LIP_ENGINE_PATH=./wav2lip256/wav2lip_server_fp16.engine \
bash run_digitalman_server.sh
```

相关性能开关可放在 `.env` 中：

```bash
WAV2LIP_FAST_FIRST_FRAME=0
WAV2LIP_FIRST_BATCH_SIZE=8
WAV2LIP_SYNC_SPEECH_START_INDEX=1
WAV2LIP_SPEECH_START_BRIDGE_FRAMES=6
WEBRTC_VIDEO_FPS=25
WEBRTC_RENDER_FPS=25
WEBRTC_VIDEO_QUEUE_MAX=12
WEBRTC_VIDEO_KEEP_FRAMES=6
WEBRTC_VIDEO_BACKPRESSURE_FRAMES=8
WEBRTC_VIDEO_LAG_RESET_S=0.25
ASR_INPUT_QUEUE_MAX=250
ASR_OUTPUT_QUEUE_MAX=250
TTS_TEXT_QUEUE_MAX=32
PERF_LOG_ENABLED=1
```

没有生成 engine 时不要切到 `WAV2LIP_BACKEND=tensorrt`，否则服务会在加载模型阶段报错。需要先跑通服务时可临时使用：

```bash
WAV2LIP_BACKEND=pytorch bash run_digitalman_server.sh
```

常见报错：

- `ModuleNotFoundError: No module named 'torch'`：先执行 `uv sync`。
- `ModuleNotFoundError: No module named 'tensorrt'`：执行 `uv pip install tensorrt-cu12`。
- `TensorRT engine not found`：先按上面的步骤生成 `wav2lip_server_fp16.engine`。
- `exec: python: not found`：当前构建脚本已优先使用 `uv run --no-sync python`；如果仍遇到，确认已安装 `uv` 或 `python3`。

### 访问方式

启动后可使用 `web/` 下的页面进行联调，例如：

- `http://serverip/webrtcapi.html`
- `http://serverip/webrtcchat.html`

端口开放请参考实际部署配置，详细说明见 [DEPLOY.md](DEPLOY.md)。

## 相关文档

- [DEPLOY.md](DEPLOY.md): 部署与运维
- [docs/reference/api-list.md](docs/reference/api-list.md): 接口清单
- [docs/reference/api-docs.md](docs/reference/api-docs.md): 接口文档
- [docs/components/wav2lip256.md](docs/components/wav2lip256.md): `wav2lip256` 组件说明
- [docs/archive/legacy-readme-notes.md](docs/archive/legacy-readme-notes.md): 旧 README 迁移内容
