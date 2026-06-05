# digitalhuman-XunFei

讯飞数字人项目整理版。仓库保留源码、脚本、配置模板和轻量资源；运行所需的视频、数字人形象数据、Wav2Lip 权重和 TensorRT engine 等大文件不直接提交到 Git，需要从网盘下载后放到指定目录。

当前 `tensorrt` 分支已支持两种 Wav2Lip 推理后端：

- `pytorch`：默认后端，使用 `wav2lip.pth`。
- `tensorrt`：推荐在 Ubuntu + NVIDIA GPU 服务器上使用，加载 `.engine` 文件加速推理。

## 目录结构

| 目录 | 说明 |
| --- | --- |
| `realtime-digital-human/` | 实时数字人后端，负责 WebRTC、LLM、TTS、Wav2Lip 推理 |
| `device/` | 设备服务，提供静态资源、反诈视频和设备接口 |
| `zkxh-digitalhuman-front/` | 数字人前端，Docker 化部署后对外提供 80/443 访问 |
| `zkxh-3588-android-digitalhuman-service/` | Android 客户端工程 |
| `scripts/` | Ubuntu 环境准备、后台启动等脚本 |
| `LARGE_FILES.md` | 大文件说明 |

## 运行所需大文件

以下文件被 `.gitignore` 排除，不在仓库中保存。部署或本地运行前需要下载并放到对应目录。

| 文件 | 网盘链接 | 提取码 | 源码目录放置位置 | 服务器部署位置 |
| --- | --- | --- | --- | --- |
| `反诈视频.mp4` | [下载](https://pan.baidu.com/s/1VleBdTUAKjl6COVOFHbctA?pwd=8y9j) | `8y9j` | `device/resources/反诈视频.mp4` | `/opt/digitalhuman/device/resources/反诈视频.mp4` |
| `wav2lip.pth` | [下载](https://pan.baidu.com/s/1Sm5NpQOa9Ue_No4gm_pVeA?pwd=pfq1) | `pfq1` | `realtime-digital-human/wav2lip256/wav2lip.pth` | `/opt/digitalhuman/be/wav2lip256/wav2lip.pth` |
| `data.zip` | [下载](https://pan.baidu.com/s/1FtGG3WoNOXHZdwBWKc-yJw?pwd=fhnq) | `fhnq` | 解压到 `realtime-digital-human/data/` | 解压到 `/opt/digitalhuman/be/data/` |
| `wav2lip_trt11_fp32.engine` | [下载](https://pan.baidu.com/s/19tyqN-F4MLExFHsmF13OmQ?pwd=1644) | `1644` | `realtime-digital-human/wav2lip256/wav2lip_trt11_fp32.engine` | `/opt/digitalhuman/be/wav2lip256/wav2lip_trt11_fp32.engine` |

> 说明：`wav2lip_trt11_fp32.engine` 是 TensorRT 11 环境下生成的 Wav2Lip engine，已在 NVIDIA GeForce RTX 3060 上验证。TensorRT engine 与 TensorRT 版本、GPU 架构、CUDA 环境相关；如果目标机器无法加载该 engine，请在目标服务器上使用本仓库脚本重新生成。

下载完成后，建议检查这些路径：

```bash
ls -lh realtime-digital-human/wav2lip256/wav2lip.pth
ls -lh realtime-digital-human/wav2lip256/wav2lip_trt11_fp32.engine
ls -lh realtime-digital-human/data/avatars/wav2lip_avatar11/coords.pkl
ls -lh realtime-digital-human/data/customimage/4.png
ls -lh device/resources/反诈视频.mp4
```

部署到 `/opt/digitalhuman` 后，对应检查命令：

```bash
ls -lh /opt/digitalhuman/be/wav2lip256/wav2lip.pth
ls -lh /opt/digitalhuman/be/wav2lip256/wav2lip_trt11_fp32.engine
ls -lh /opt/digitalhuman/be/data/avatars/wav2lip_avatar11/coords.pkl
ls -lh /opt/digitalhuman/be/data/customimage/4.png
ls -lh /opt/digitalhuman/device/resources/反诈视频.mp4
```

## 全新 Ubuntu 环境准备

仓库提供 `scripts/bootstrap_ubuntu.sh`，用于在全新的 Ubuntu 服务器上准备运行环境。脚本会安装系统依赖、安装 `uv`、创建 `/opt/digitalhuman` 兼容目录、安装后端和设备服务 Python 依赖、生成前端证书，并放置运行大文件。

推荐先把大文件下载到服务器某个目录，例如 `/tmp/digitalhuman-assets`，再执行：

```bash
sudo mkdir -p /opt/digitalhuman
sudo chown -R $USER:$USER /opt/digitalhuman

git clone -b tensorrt https://github.com/eiffelmen/digitalhuman-XunFei.git /opt/digitalhuman/src
cd /opt/digitalhuman/src

ASSET_SOURCE_DIR=/tmp/digitalhuman-assets bash scripts/bootstrap_ubuntu.sh
```

如果不使用 `/opt/digitalhuman`，也可以在当前源码目录启动，启动时通过环境变量指定路径，见“后台启动”章节。

百度网盘分享链接不是普通直链，`curl`/`wget` 通常不能直接下载。建议手动下载，或放到一个可直接访问的 HTTP 文件服务器后再交给脚本处理。

## 后端 `.env` 配置

实时数字人后端配置文件位于：

```bash
/opt/digitalhuman/be/.env
```

首次部署时复制模板：

```bash
cd /opt/digitalhuman/be
cp .env.template .env
nano .env
```

### 讯飞 LLM + 讯飞 TTS 示例

```bash
LLM_PROVIDER=iflytek
LISTEN_PORT=8010

IFLYTEK_WS_URL=wss://aiui.xf-yun.com/v3/aiint/sos
IFLYTEK_APPID=your-iflytek-appid
IFLYTEK_API_KEY=your-iflytek-api-key
IFLYTEK_API_SECRET=your-iflytek-api-secret
IFLYTEK_SCENE=main_box
IFLYTEK_TIMEOUT=30

IFLY_APP_ID=${IFLYTEK_APPID}
IFLY_API_KEY=${IFLYTEK_API_KEY}
IFLY_API_SECRET=${IFLYTEK_API_SECRET}

TTS_TYPE=iflytts
TTS_SERVER=http://127.0.0.1:8779
TTS_SERVICE=http://127.0.0.1:8779
IFLYTEK_TTS_VCN=xiaoyan
IFLYTEK_TTS_FALLBACK_VCN=xiaoyan

PERF_LOG_ENABLED=1
LLM_STREAM_TTS_ENABLED=0
LLM_FRONTEND_STREAM_TEXT_ENABLED=0
CUDA_VISIBLE_DEVICES=0
```

### TensorRT Wav2Lip 配置

使用 TensorRT engine 时，在 `.env` 中增加或修改：

```bash
WAV2LIP_BACKEND=tensorrt
WAV2LIP_ENGINE_PATH=./wav2lip256/wav2lip_trt11_fp32.engine
CUDA_VISIBLE_DEVICES=0
```

使用 PyTorch 权重时：

```bash
WAV2LIP_BACKEND=pytorch
CUDA_VISIBLE_DEVICES=0
```

## TensorRT engine 重新生成

如果下载的 `wav2lip_trt11_fp32.engine` 无法在目标服务器加载，可在目标 Ubuntu GPU 服务器上重新导出 ONNX 并生成 engine。

```bash
cd /opt/digitalhuman/be
source .venv/bin/activate

python scripts/export_wav2lip_onnx.py \
  --checkpoint ./wav2lip256/wav2lip.pth \
  --output ./wav2lip256/wav2lip_256.onnx

ENGINE_PATH=./wav2lip256/wav2lip_trt11_fp32.engine \
PRECISION=fp32 \
bash scripts/build_wav2lip_tensorrt.sh
```

生成后确认：

```bash
ls -lh ./wav2lip256/wav2lip_trt11_fp32.engine
python -c "import tensorrt as trt; print(trt.__version__)"
```

## 后台启动

环境准备完成、`.env` 填写完成、大文件放置完成后，启动全部服务：

```bash
cd /opt/digitalhuman/src
bash scripts/start_services.sh
```

脚本会启动：

- 实时数字人后端：默认 `8010`
- device 服务：默认 `8000`
- 前端 Docker 容器：默认 `80` 和 `443`

如果项目不在 `/opt/digitalhuman`，例如位于 `/home/xinhe/Desktop/wz/dhtrt`，可这样启动：

```bash
cd /home/xinhe/Desktop/wz/dhtrt

PROJECT_ROOT=/home/xinhe/Desktop/wz/dhtrt \
BACKEND_DIR=/home/xinhe/Desktop/wz/dhtrt/realtime-digital-human \
DEVICE_DIR=/home/xinhe/Desktop/wz/dhtrt/device \
FRONTEND_DIR=/home/xinhe/Desktop/wz/dhtrt/zkxh-digitalhuman-front \
LOG_DIR=/home/xinhe/Desktop/wz/dhtrt/logs \
RUN_DIR=/home/xinhe/Desktop/wz/dhtrt/run \
BACKEND_HOST=host.docker.internal \
FRONTEND_IMAGE=digitalhuman-frontend-xunfei:tensorrt \
FRONTEND_CONTAINER=digitalhuman-front-tensorrt \
BUILD_FRONTEND_IMAGE=auto \
bash scripts/start_services.sh
```

## 服务验证

启动完成后，执行：

```bash
curl http://127.0.0.1:8010/ready
curl http://127.0.0.1:8000/ready
curl http://127.0.0.1/backend/ready
curl http://127.0.0.1/api/ready
```

查看端口：

```bash
sudo ss -tlnp | grep -E ':80|:443|:8000|:8010|:10095'
```

查看前端容器：

```bash
sudo docker ps -a | grep -E 'digitalhuman|front|frontend'
```

确认 GPU 和 CUDA：

```bash
nvidia-smi
python - <<'PY'
import torch
print("torch =", torch.__version__)
print("cuda available =", torch.cuda.is_available())
print("device count =", torch.cuda.device_count())
print("gpu =", torch.cuda.get_device_name(0) if torch.cuda.is_available() else "none")
PY
```

## 查看日志

如果使用 `scripts/start_services.sh` 启动：

```bash
tail -f /opt/digitalhuman/logs/realtime.log
tail -f /opt/digitalhuman/logs/device.log
docker logs -f frontend
```

自定义目录启动时，将路径替换为启动时指定的 `LOG_DIR` 和容器名，例如：

```bash
tail -f /home/xinhe/Desktop/wz/dhtrt/logs/realtime.log
tail -f /home/xinhe/Desktop/wz/dhtrt/logs/device.log
docker logs -f digitalhuman-front-tensorrt
```

只看性能耗时：

```bash
grep '\[PERF\]' /opt/digitalhuman/logs/realtime.log
tail -f /opt/digitalhuman/logs/realtime.log | grep '\[PERF\]'
```

只看 TensorRT / Wav2Lip：

```bash
grep -E 'TensorRT|wav2lip|WAV2LIP|正在使用cuda|backend=tensorrt' /opt/digitalhuman/logs/realtime.log
```

只看一次会话链路：

```bash
grep 'trace_id=' /opt/digitalhuman/logs/realtime.log
```

如果使用 systemd 方式启动旧版服务，可查看：

```bash
sudo systemctl status digitalhuman-realtime --no-pager
sudo journalctl -u digitalhuman-realtime -f
sudo journalctl -u digitalhuman-realtime -n 200 --no-pager
```

## 停止与重启

脚本启动方式：

```bash
kill $(cat /opt/digitalhuman/run/digitalhuman-realtime.pid) 2>/dev/null || true
kill $(cat /opt/digitalhuman/run/digitalhuman-device.pid) 2>/dev/null || true
docker rm -f frontend 2>/dev/null || true
```

自定义目录启动方式：

```bash
kill $(cat /home/xinhe/Desktop/wz/dhtrt/run/digitalhuman-realtime.pid) 2>/dev/null || true
kill $(cat /home/xinhe/Desktop/wz/dhtrt/run/digitalhuman-device.pid) 2>/dev/null || true
docker rm -f digitalhuman-front-tensorrt 2>/dev/null || true
```

端口被占用时：

```bash
sudo fuser -k 8010/tcp 8000/tcp
sudo docker ps -a
sudo docker rm -f <container-name>
```

systemd 旧服务清理：

```bash
sudo systemctl stop digitalhuman-realtime.service digitalhuman-device.service
sudo systemctl disable digitalhuman-realtime.service digitalhuman-device.service
sudo systemctl daemon-reload
```

## TensorRT 版性能数据

以下数据来自 Ubuntu GPU 服务器测试环境：

- GPU：NVIDIA GeForce RTX 3060
- Wav2Lip backend：TensorRT
- Engine：`wav2lip_trt11_fp32.engine`
- Wav2Lip 输入尺寸：256
- batch size：16
- WebRTC 输出：约 25 FPS

### 启动与实例化

| 阶段 | 耗时 |
| --- | ---: |
| 加载 TensorRT engine | 约 507 ms |
| Wav2Lip 预热 | 约 160 ms |
| 创建数字人实例 `build_nerfreal` | 约 639-670 ms |
| offer / WebRTC 建连总耗时 | 约 834-864 ms |

### 对话到开始说话

稳定状态下，从接收到一次对话到数字人开始说话/首帧口型输出：

| 指标 | 耗时 |
| --- | ---: |
| 首轮可能耗时 | 约 2.33 s |
| 稳定平均耗时 | 约 1.35 s |
| 常见范围 | 约 1.3-1.4 s |

模块拆分：

| 模块 | 典型耗时 | 说明 |
| --- | ---: | --- |
| 业务校验 / 分发 | 0-2 ms | 基本可忽略 |
| LLM 首字返回 | 约 0.7 s | 外部讯飞 AIUI 响应 |
| LLM 完整回复 | 约 1.7 s | 取决于回复长度和网络 |
| TTS 首段音频返回 | 约 0.4 s | 外部讯飞 TTS |
| 音频进入 Wav2Lip 到首帧输出 | 约 0.24 s | 已做首帧快速输出优化 |
| Wav2Lip 首帧推理 | 约 0.10 s | TensorRT 首批推理 |
| Wav2Lip 完整段推理 | 约 1.09 s | 约 112-114 帧 |
| Wav2Lip 推理 FPS | 约 103 FPS | TensorRT + CUDA |
| WebRTC 输出 FPS | 约 25-26 FPS | 播放端稳定帧率 |

结论：TensorRT 版中，Wav2Lip 已不是主要瓶颈。当前端到端响应主要受 LLM 首字返回和 TTS 首段音频返回影响。

## 常见问题

### 1. 日志显示 `appid is empty`

说明 `.env` 没有被正确加载，或缺少 `IFLYTEK_APPID` / `IFLY_APP_ID`。检查：

```bash
cd /opt/digitalhuman/be
sed -i 's/\r$//' .env
set -a
source .env
set +a
echo "$IFLYTEK_APPID"
echo "$IFLY_APP_ID"
```

### 2. 日志显示 `address already in use`

说明端口被旧服务占用：

```bash
sudo ss -tlnp | grep -E ':80|:443|:8000|:8010'
sudo fuser -k 8010/tcp 8000/tcp
sudo docker ps -a
```

### 3. 数字人背景黑色

通常是背景图缺失，检查：

```bash
ls -lh /opt/digitalhuman/be/data/customimage/4.png
```

如果缺失，重新解压 `data.zip` 到 `/opt/digitalhuman/be/data/`。

### 4. TensorRT engine 加载失败

engine 可能与服务器 TensorRT/CUDA/GPU 不兼容。解决方式：

```bash
cd /opt/digitalhuman/be
source .venv/bin/activate
python scripts/export_wav2lip_onnx.py --checkpoint ./wav2lip256/wav2lip.pth --output ./wav2lip256/wav2lip_256.onnx
ENGINE_PATH=./wav2lip256/wav2lip_trt11_fp32.engine PRECISION=fp32 bash scripts/build_wav2lip_tensorrt.sh
```

### 5. WebRTC 帧率低

先确认 Wav2Lip 是否在 GPU/TensorRT 上运行：

```bash
grep -E 'backend=tensorrt|device=cuda|actual avg final fps|render_frames' /opt/digitalhuman/logs/realtime.log
nvidia-smi
top
```

正常情况下，WebRTC 输出约 25 FPS，Wav2Lip TensorRT 推理约 100 FPS。

## 其他说明

- 前端反诈视频通过 `/static/反诈视频.mp4` 访问，对应文件来自 `device/resources/`。
- 后端默认数字人形象为 `wav2lip_avatar11`，资源来自 `data/avatars/wav2lip_avatar11/`。
- `node_modules/`、`.venv/`、`dist/`、Android `build/`、压缩包、APK、模型权重和 TensorRT engine 均不作为源码提交。
- 各子项目更细的说明可查看对应目录下的 README。
