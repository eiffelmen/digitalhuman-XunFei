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
- 默认 `CUDA_VISIBLE_DEVICES=0`
- 默认 `WAV2LIP_BACKEND=pytorch`

可通过环境变量覆盖：

```bash
LLM_PROVIDER=rag LISTEN_PORT=8010 CUDA_VISIBLE_DEVICES=0 bash run_digitalman_server.sh
```

### Wav2Lip TensorRT 加速

Mac 本机可以完成 `.pth` 到 `.onnx` 的导出和检查；TensorRT `.engine` 需要在 NVIDIA GPU 的 Ubuntu 服务器上生成。

1. 在 Mac 或服务器上导出 ONNX：

```bash
python scripts/export_wav2lip_onnx.py \
  --checkpoint ./wav2lip256/wav2lip.pth \
  --output ./wav2lip256/wav2lip_256.onnx
```

2. 检查 ONNX 输入输出：

```bash
python scripts/inspect_wav2lip_onnx.py ./wav2lip256/wav2lip_256.onnx
```

期望输入输出名称：

- `mel`: `[batch, 1, 80, 16]`
- `face`: `[batch, 6, 256, 256]`
- `pred`: `[batch, 3, 256, 256]`

3. 在 Ubuntu GPU 服务器上生成 TensorRT engine：

```bash
bash scripts/build_wav2lip_tensorrt.sh
```

4. 在服务器 `.env` 中切换到 TensorRT：

```bash
WAV2LIP_BACKEND=tensorrt
WAV2LIP_ENGINE_PATH=./wav2lip256/wav2lip_fp16.engine
CUDA_VISIBLE_DEVICES=0
```

不填写这两个 TensorRT 配置时，服务会继续使用原来的 PyTorch 推理方式。

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
