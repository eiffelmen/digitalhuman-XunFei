# ZKXH 数字人交互系统 - Electron版打包与部署文档

## 项目概述

本项目已成功改造为Electron应用，可以在Ubuntu系统中作为桌面应用运行，支持开机自启动。

**版本**: 3.0.2  
**基础框架**: Vue3 + Vite + Electron  
**目标平台**: Ubuntu Linux (x64)

---

## 一、开发环境准备

### 1.1 系统要求

- **操作系统**: Ubuntu 20.04 LTS 或更高版本
- **Node.js**: v20 或 v22
- **内存**: 至少 4GB RAM
- **磁盘空间**: 至少 2GB 可用空间

### 1.2 安装Node.js环境

使用nvm安装Node.js（推荐）:

```bash
# 安装nvm
curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.0/install.sh | bash

# 重新加载shell配置
source ~/.bashrc

# 安装Node.js 20
nvm install 20
nvm use 20

# 验证安装
node --version
npm --version
```

### 1.3 安装项目依赖

```bash
# 进入项目目录
cd zkxh-digitalhuman-front

# 安装依赖（首次或依赖更新后执行）
npm install
```

---

## 二、项目打包

### 2.1 打包前准备

#### 2.1.1 配置后端服务器地址

编辑 `src/config/index.js` 文件，配置后端服务器地址：

```javascript
const DEFAULT_BACKEND_CONFIG = {
  apiServers: {
    main: 'YOUR_SERVER_IP:8000',      // 主API服务器
    backend: 'YOUR_SERVER_IP:8010',   // 后端服务器
    llm: 'YOUR_SERVER_IP:8011',       // LLM服务器
    // ... 其他服务器配置
  },
};
```

#### 2.1.2 准备应用图标

将应用图标文件放置到 `build/icon.png` (建议尺寸: 512x512 PNG格式)

如果没有图标，可以使用以下命令创建占位图标：

```bash
# 需要先安装ImageMagick
sudo apt-get install imagemagick

# 创建蓝色方块图标
convert -size 512x512 xc:#1976D2 build/icon.png
```

### 2.2 构建前端资源

```bash
# 构建Vue应用
npm run build
```

构建完成后，会在 `dist` 目录生成前端静态资源。

### 2.3 打包Electron应用

#### 方式一：打包为AppImage和deb包（推荐）

```bash
# 打包Linux应用（AppImage + deb）
npm run build:electron
```

打包完成后，产物在 `dist-electron` 目录：
- `*.AppImage` - AppImage格式（无需安装，直接运行）
- `*.deb` - Debian安装包（Ubuntu标准安装包）
- `*.tar.gz` - 压缩包格式

#### 方式二：仅打包目录（用于测试）

```bash
# 仅打包目录，不生成安装包
npm run build:electron:dir
```

打包结果在 `dist-electron/linux-unpacked/` 目录。

### 2.4 打包时间估算

- 首次打包：约 3-5 分钟（需要下载Electron二进制文件）
- 后续打包：约 1-2 分钟

---

## 三、应用部署

### 3.1 部署方式选择

根据使用场景，提供三种部署方式：

| 部署方式 | 适用场景 | 是否需要安装 | 开机自启 |
|---------|---------|------------|---------|
| AppImage | 测试、演示 | 否 | 需手动配置 |
| DEB包安装 | 生产环境 | 是 | 支持 |
| 手动部署 | 开发调试 | 否 | 需手动配置 |

### 3.2 方式一：使用AppImage（最简单）

#### 3.2.1 复制文件到目标系统

```bash
# 将AppImage文件复制到Ubuntu系统
scp dist-electron/ZKXH-DigitalHuman-*.AppImage user@target-host:/home/user/
```

#### 3.2.2 添加执行权限

```bash
chmod +x ZKXH-DigitalHuman-*.AppImage
```

#### 3.2.3 运行应用

```bash
# 直接运行
./ZKXH-DigitalHuman-*.AppImage

# 或者后台运行
nohup ./ZKXH-DigitalHuman-*.AppImage &
```

### 3.3 方式二：使用DEB包安装（推荐生产环境）

#### 3.3.1 复制DEB包到目标系统

```bash
scp dist-electron/zkxh-digitalhuman_*.deb user@target-host:/home/user/
```

#### 3.3.2 安装DEB包

```bash
# 在目标Ubuntu系统上执行
sudo dpkg -i zkxh-digitalhuman_*.deb

# 如果提示依赖问题，执行
sudo apt-get install -f
```

#### 3.3.3 验证安装

```bash
# 检查是否安装成功
dpkg -l | grep zkxh-digitalhuman

# 查看安装位置
which zkxh-digitalhuman
```

应用将被安装到 `/opt/ZKXH-DigitalHuman/` 目录。

#### 3.3.4 启动应用

```bash
# 方式1: 直接命令启动
zkxh-digitalhuman

# 方式2: 完整路径启动
/opt/ZKXH-DigitalHuman/zkxh-digitalhuman

# 方式3: 从应用程序菜单启动
# 在Ubuntu应用程序菜单中搜索 "ZKXH DigitalHuman"
```

### 3.4 方式三：手动部署（开发调试）

#### 3.4.1 解压打包目录

```bash
# 复制打包目录到目标系统
scp -r dist-electron/linux-unpacked user@target-host:/opt/zkxh-digitalhuman

# 在目标系统上添加执行权限
cd /opt/zkxh-digitalhuman
chmod +x zkxh-digitalhuman
```

#### 3.4.2 运行应用

```bash
cd /opt/zkxh-digitalhuman
./zkxh-digitalhuman --no-sandbox
```

---

## 四、配置开机自启动

### 4.1 使用systemd服务（推荐）

项目提供了完整的systemd服务配置文件和安装脚本。

#### 4.1.1 准备服务文件

服务相关文件位于 `build/` 目录：
- `zkxh-digitalhuman.service` - systemd服务配置
- `install-service.sh` - 自动化安装脚本

#### 4.1.2 安装系统服务

```bash
# 方式1: 使用自动化脚本（推荐）
cd build
chmod +x install-service.sh
sudo ./install-service.sh install

# 方式2: 手动安装
sudo cp build/zkxh-digitalhuman.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable zkxh-digitalhuman
sudo systemctl start zkxh-digitalhuman
```

#### 4.1.3 验证服务状态

```bash
# 查看服务状态
sudo systemctl status zkxh-digitalhuman

# 查看服务日志
sudo journalctl -u zkxh-digitalhuman -f
```

#### 4.1.4 服务管理命令

```bash
# 启动服务
sudo systemctl start zkxh-digitalhuman

# 停止服务
sudo systemctl stop zkxh-digitalhuman

# 重启服务
sudo systemctl restart zkxh-digitalhuman

# 禁用开机自启
sudo systemctl disable zkxh-digitalhuman

# 启用开机自启
sudo systemctl enable zkxh-digitalhuman

# 卸载服务
cd build
sudo ./install-service.sh uninstall
```

### 4.2 配置X11显示权限

如果应用运行在无显示器的服务器上，需要配置虚拟显示：

```bash
# 安装虚拟显示服务
sudo apt-get install xvfb

# 修改服务文件，添加Xvfb
sudo nano /etc/systemd/system/zkxh-digitalhuman.service
```

修改 `ExecStart` 行：
```ini
ExecStart=/usr/bin/xvfb-run -a /opt/ZKXH-DigitalHuman/zkxh-digitalhuman --no-sandbox
```

重新加载并重启服务：
```bash
sudo systemctl daemon-reload
sudo systemctl restart zkxh-digitalhuman
```

---

## 五、后端服务器配置

### 5.1 Electron环境下的后端连接

在Electron环境中，应用会直接连接到配置的后端服务器，不再依赖Vite开发服务器的代理。

### 5.2 运行时配置后端地址

应用运行后，后端配置保存在localStorage中，可以通过以下方式修改：

1. 打开开发者工具（Electron菜单 -> View -> Toggle Developer Tools）
2. 在Console中执行：

```javascript
// 查看当前配置
localStorage.getItem('backendConfig')

// 修改配置
const config = {
  apiServers: {
    main: 'NEW_IP:8000',
    backend: 'NEW_IP:8010',
    // ... 其他配置
  }
};
localStorage.setItem('backendConfig', JSON.stringify(config));

// 重启应用使配置生效
```

---

## 六、故障排查

### 6.1 常见问题

#### 问题1: 应用无法启动

**症状**: 双击应用无反应或闪退

**解决方案**:
```bash
# 检查依赖
sudo apt-get install libgtk-3-0 libnotify4 libnss3 libxtst6

# 使用--no-sandbox参数启动
/opt/ZKXH-DigitalHuman/zkxh-digitalhuman --no-sandbox

# 查看详细错误日志
/opt/ZKXH-DigitalHuman/zkxh-digitalhuman --enable-logging
```

#### 问题2: WebSocket连接失败

**症状**: 无法连接到后端服务器

**检查项**:
1. 确认后端服务器IP和端口配置正确
2. 检查防火墙是否开放相应端口
3. 查看浏览器控制台WebSocket连接日志

```bash
# 测试后端连接
curl http://YOUR_SERVER_IP:8000/api/health
```

#### 问题3: 服务无法开机自启

**症状**: 系统重启后服务未运行

**检查项**:
```bash
# 检查服务是否启用
systemctl is-enabled zkxh-digitalhuman

# 查看服务失败原因
sudo journalctl -u zkxh-digitalhuman -b

# 检查DISPLAY环境变量
echo $DISPLAY

# 检查X11权限
xhost +local:
```

#### 问题4: 打包失败

**症状**: npm run build:electron 报错

**解决方案**:
```bash
# 清理缓存
rm -rf node_modules dist dist-electron
npm cache clean --force

# 重新安装依赖
npm install

# 重新打包
npm run build:electron
```

### 6.2 日志查看

```bash
# 查看应用日志（systemd服务）
sudo journalctl -u zkxh-digitalhuman -f

# 查看应用日志（手动运行）
# 日志输出在终端

# Electron调试
# 在应用中按 F12 打开开发者工具
```

---

## 七、更新与维护

### 7.1 应用更新流程

1. **停止当前服务**
```bash
sudo systemctl stop zkxh-digitalhuman
```

2. **备份配置**
```bash
# 备份用户配置（如果需要）
cp -r ~/.config/ZKXH-DigitalHuman ~/.config/ZKXH-DigitalHuman.bak
```

3. **卸载旧版本**（DEB包方式）
```bash
sudo dpkg -r zkxh-digitalhuman
```

4. **安装新版本**
```bash
sudo dpkg -i zkxh-digitalhuman_NEW_VERSION.deb
```

5. **重启服务**
```bash
sudo systemctl start zkxh-digitalhuman
```

### 7.2 配置文件位置

- **用户配置**: `~/.config/ZKXH-DigitalHuman/`
- **应用日志**: 通过 `journalctl` 查看
- **本地存储**: 浏览器localStorage（应用内部）

---

## 八、性能优化建议

### 8.1 系统资源

- **推荐配置**: 4核CPU, 8GB内存
- **最低配置**: 2核CPU, 4GB内存

### 8.2 网络优化

- 确保与后端服务器的网络延迟 < 50ms
- WebSocket连接保持稳定
- 带宽建议 > 10Mbps

### 8.3 显示优化

- 使用硬件加速（默认启用）
- 推荐分辨率: 1920x1080 或更高

---

## 九、安全注意事项

### 9.1 网络安全

- 建议在内网环境中部署
- 如需公网访问，请配置防火墙和SSL证书
- 定期更新系统和依赖包

### 9.2 权限控制

- systemd服务默认以root权限运行（因需要访问显示器）
- 生产环境建议创建专用用户运行应用

---

## 十、技术支持

### 10.1 项目结构说明

```
zkxh-digitalhuman-front/
├── electron/              # Electron主进程文件
│   ├── main.js           # 主进程入口
│   └── preload.js        # 预加载脚本
├── src/                  # Vue3前端源码
│   ├── api/             # API接口
│   ├── components/      # 组件
│   ├── config/          # 配置文件
│   ├── utils/           # 工具函数
│   └── views/           # 页面视图
├── build/               # 构建相关文件
│   ├── zkxh-digitalhuman.service  # systemd服务文件
│   └── install-service.sh         # 服务安装脚本
├── dist/                # Vue构建产物
├── dist-electron/       # Electron打包产物
└── package.json         # 项目配置
```

### 10.2 相关文档

- [Electron官方文档](https://www.electronjs.org/docs)
- [Vue3官方文档](https://vuejs.org/)
- [systemd服务文档](https://www.freedesktop.org/software/systemd/man/systemd.service.html)

---

## 附录

### A. 完整的打包和部署命令清单

```bash
# === 开发环境 ===
# 安装依赖
npm install

# 开发调试（Web模式）
npm run dev

# === 打包 ===
# 构建前端
npm run build

# 打包Electron应用
npm run build:electron

# === 部署 ===
# 方式1: AppImage
chmod +x dist-electron/ZKXH-DigitalHuman-*.AppImage
./dist-electron/ZKXH-DigitalHuman-*.AppImage

# 方式2: DEB包
sudo dpkg -i dist-electron/zkxh-digitalhuman_*.deb

# === 配置自启动 ===
cd build
chmod +x install-service.sh
sudo ./install-service.sh install

# === 服务管理 ===
sudo systemctl status zkxh-digitalhuman
sudo systemctl restart zkxh-digitalhuman
sudo journalctl -u zkxh-digitalhuman -f
```

---

**文档版本**: 1.0  
**最后更新**: 2024-11-04  
**维护者**: ZKXH Team

---

## 十一、本地人脸检测数据接入

自 v3.0.2 起，Electron 主进程会在本地启动“人脸数据桥”，用于接收 C++ 端（如 `main_streaming`）推送的人脸识别结果，并在渲染进程内触发 UI 状态切换。

### 11.1 默认端口

| 通道 | 默认地址 | 说明 |
|------|-----------|------|
| HTTP | `http://127.0.0.1:3100/face` | C++ 通过 POST 推送 JSON 数据 |
| WebSocket | `ws://127.0.0.1:3200` | C++ 作为客户端连接后持续发送 JSON 文本 |

可通过下列环境变量覆盖：

- `FACE_HTTP_PORT` / `FACE_HTTP_PATH`
- `FACE_WS_PORT`

### 11.2 JSON 格式

```json
{
  "timestamp": 1730456789012,
  "faces": [
    { "x": 120, "y": 300, "w": 320, "h": 320, "mouthOcc": false }
  ]
}
```

### 11.3 C++ 端示例

```bash
# 通过 HTTP 推送
FACE_HTTP_URL=http://127.0.0.1:3100/face ./main_streaming

# 通过 WebSocket 推送
FACE_WS_URL=ws://127.0.0.1:3200 ./main_streaming
```

Electron 收到数据后会自动让 UI 退出待机状态；若长时间无脸，则恢复到待机模式。
