# digitalhuman-XunFei

讯飞数字人项目代码整理版。仓库中保留源码、配置示例和轻量资源，运行所需的大模型权重、视频素材和数字人形象数据不直接提交到 Git，需要从网盘下载后放到指定目录。

## 项目结构

- `zkxh-digitalhuman-front/`: 数字人 Web/Electron 前端
- `realtime-digital-human/`: 实时数字人后端服务
- `device/`: 设备端服务，提供静态资源与设备接口
- `zkxh-3588-android-digitalhuman-service/`: Android 客户端工程

## 运行所需大文件

以下文件被 `.gitignore` 排除，不在仓库中保存。部署或本地运行前需要先下载并放置到对应目录。

| 文件 | 网盘链接 | 提取码 | 源码运行放置位置 | 服务器部署位置 |
| --- | --- | --- | --- | --- |
| `反诈视频.mp4` | [下载](https://pan.baidu.com/s/1VleBdTUAKjl6COVOFHbctA?pwd=8y9j) | `8y9j` | `device/resources/反诈视频.mp4` | `/opt/digitalhuman/device/resources/反诈视频.mp4` |
| `wav2lip.pth` | [下载](https://pan.baidu.com/s/1Sm5NpQOa9Ue_No4gm_pVeA?pwd=pfq1) | `pfq1` | `realtime-digital-human/wav2lip256/wav2lip.pth` | `/opt/digitalhuman/be/wav2lip256/wav2lip.pth` |
| `data.zip` | [下载](https://pan.baidu.com/s/1FtGG3WoNOXHZdwBWKc-yJw?pwd=fhnq) | `fhnq` | 解压到 `realtime-digital-human/data/`，确保存在 `data/avatars/wav2lip_avatar11/` | 解压到 `/opt/digitalhuman/be/data/` |

放置完成后，建议确认下面几个路径存在：

```bash
ls -lh device/resources/反诈视频.mp4
ls -lh realtime-digital-human/wav2lip256/wav2lip.pth
ls -lh realtime-digital-human/data/avatars/wav2lip_avatar11/coords.pkl
```

部署到服务器后，可用下面的路径检查：

```bash
ls -lh /opt/digitalhuman/device/resources/反诈视频.mp4
ls -lh /opt/digitalhuman/be/wav2lip256/wav2lip.pth
ls -lh /opt/digitalhuman/be/data/avatars/wav2lip_avatar11/coords.pkl
```

## 说明

- 前端反诈视频通过 `/static/反诈视频.mp4` 访问，对应文件来自 `device/resources/`。
- 后端默认加载 `./wav2lip256/wav2lip.pth` 作为 Wav2Lip 模型权重。
- 后端默认数字人形象为 `wav2lip_avatar11`，资源来自 `data/avatars/wav2lip_avatar11/`。
- `node_modules/`、`.venv/`、`dist/`、Android `build/`、压缩包和 APK 都不作为源码提交，需要时重新安装或重新构建。

## 全新 Ubuntu 环境准备脚本

仓库提供了 `scripts/bootstrap_ubuntu.sh`，用于在全新的 Ubuntu 服务器上准备运行环境。脚本会安装系统依赖、安装 `uv`、拉取/更新项目代码、创建 `/opt/digitalhuman` 兼容目录、安装后端和设备服务的 Python 依赖、生成前端容器使用的自签名证书，并放置三个运行大文件。

推荐先把三个大文件下载到服务器某个目录，例如 `/tmp/digitalhuman-assets`，再执行：

```bash
sudo mkdir -p /opt/digitalhuman
sudo chown -R $USER:$USER /opt/digitalhuman
git clone https://github.com/eiffelmen/digitalhuman-XunFei.git /opt/digitalhuman/src
cd /opt/digitalhuman/src
ASSET_SOURCE_DIR=/tmp/digitalhuman-assets bash scripts/bootstrap_ubuntu.sh
```

也可以提供普通 HTTP 文件目录或单文件直链：

```bash
ASSET_BASE_URL=http://your-file-server/digitalhuman-assets bash scripts/bootstrap_ubuntu.sh

VIDEO_URL=http://your-file-server/反诈视频.mp4 \
WAV2LIP_URL=http://your-file-server/wav2lip.pth \
DATA_ZIP_URL=http://your-file-server/data.zip \
bash scripts/bootstrap_ubuntu.sh
```

如果使用私有 GitHub 仓库，可通过 `GITHUB_TOKEN` 授权拉取代码：

```bash
GITHUB_TOKEN=<your-github-token> bash scripts/bootstrap_ubuntu.sh
```

百度网盘分享链接不是普通直链，`curl`/`wget` 通常无法直接下载。脚本会在检测到已安装并已登录的 `BaiduPCS-Go` 时尝试通过网盘分享链接下载；否则请先手动下载三个文件，或放到一个可直接访问的 HTTP 文件服务器。

## 后台启动脚本

环境准备完成，并填写 `/opt/digitalhuman/be/.env` 后，可执行后台启动脚本：

```bash
cd /opt/digitalhuman/src
bash scripts/start_services.sh
```

脚本会后台启动实时数字人后端、device 服务，并构建/启动前端 Docker 容器。默认日志位置：

```bash
tail -f /opt/digitalhuman/logs/realtime.log
tail -f /opt/digitalhuman/logs/device.log
docker logs -f frontend
```

如需使用已有前端镜像而不是本机构建，可指定：

```bash
FRONTEND_IMAGE=your-registry.example.com/digitalhuman/front:latest \
PULL_FRONTEND_IMAGE=1 \
BACKEND_HOST=host.docker.internal \
bash scripts/start_services.sh
```

各子项目的详细启动方式见对应目录下的 README。
