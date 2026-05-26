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

各子项目的详细启动方式见对应目录下的 README。
