# 快速开始指南

## 项目打包（3步完成）

### 步骤1: 安装依赖
```bash
npm install
```

### 步骤2: 构建应用
```bash
npm run build:electron
```

### 步骤3: 获取安装包
打包完成后，在 `dist-electron/` 目录找到：
- `*.deb` - Ubuntu安装包
- `*.AppImage` - 免安装版本

---

## Ubuntu系统部署（2步完成）

### 方式A: 使用DEB包（推荐）

```bash
# 1. 安装应用
sudo dpkg -i zkxh-digitalhuman_*.deb

# 2. 配置开机自启
cd build
sudo ./install-service.sh install
```

### 方式B: 使用AppImage

```bash
# 1. 添加执行权限
chmod +x ZKXH-DigitalHuman-*.AppImage

# 2. 运行应用
./ZKXH-DigitalHuman-*.AppImage
```

---

## 服务管理

```bash
# 启动服务
sudo systemctl start zkxh-digitalhuman

# 停止服务
sudo systemctl stop zkxh-digitalhuman

# 查看状态
sudo systemctl status zkxh-digitalhuman

# 查看日志
sudo journalctl -u zkxh-digitalhuman -f
```

---

## 常见问题

**Q: 应用无法启动？**
```bash
# 安装依赖
sudo apt-get install libgtk-3-0 libnotify4 libnss3 libxtst6

# 使用no-sandbox模式
/opt/ZKXH-DigitalHuman/zkxh-digitalhuman --no-sandbox
```

**Q: 如何配置后端服务器地址？**

编辑 `src/config/index.js` 文件，修改 `DEFAULT_BACKEND_CONFIG` 中的服务器地址，然后重新打包。

**Q: 如何卸载？**
```bash
# DEB包方式
sudo dpkg -r zkxh-digitalhuman

# 服务卸载
cd build
sudo ./install-service.sh uninstall
```

---

## 更多信息

详细文档请参考: [ELECTRON_DEPLOYMENT.md](./ELECTRON_DEPLOYMENT.md)
