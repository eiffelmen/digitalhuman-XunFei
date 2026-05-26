# 项目构建检查清单

## 构建前检查

在开始打包Electron应用之前，请确保以下所有项目已完成：

### ✅ 环境准备

- [ ] Node.js已安装（v20或v22）
- [ ] npm可用
- [ ] 已克隆或下载项目代码

### ✅ 项目配置

- [ ] 运行 `npm install` 安装所有依赖
- [ ] 检查 `package.json` 中的版本号是否正确
- [ ] 确认 `electron/main.js` 和 `electron/preload.js` 存在

### ✅ 后端配置

- [ ] 编辑 `src/config/index.js`
- [ ] 配置所有后端服务器地址：
  - [ ] main (API服务器)
  - [ ] backend (后端服务器)
  - [ ] llm (大模型服务器)
  - [ ] asr (语音识别服务器)
  - [ ] 其他服务器...

### ✅ 应用图标

- [ ] 准备512x512的PNG图标
- [ ] 将图标保存为 `build/icon.png`
- [ ] 或参考 `build/README_ICON.md` 创建占位图标

### ✅ 文档确认

- [ ] 阅读 `ELECTRON_DEPLOYMENT.md` 了解完整部署流程
- [ ] 阅读 `QUICKSTART.md` 了解快速开始步骤

---

## 构建步骤

### 步骤1: 验证项目配置

```bash
# 运行验证脚本
./verify-build.sh

# 预期结果：所有检查通过
```

### 步骤2: 安装依赖

```bash
npm install

# 等待安装完成，注意是否有错误信息
```

### 步骤3: 构建前端

```bash
npm run build

# 检查dist目录是否生成
ls -la dist/
```

预期产物：
- `dist/index.html`
- `dist/assets/` 目录及其内容

### 步骤4: 打包Electron应用

```bash
# 完整打包（生成AppImage和deb）
npm run build:electron

# 或快速打包（仅目录，用于测试）
npm run build:electron:dir
```

预期产物（完整打包）：
- `dist-electron/ZKXH-DigitalHuman-3.0.2.AppImage`
- `dist-electron/zkxh-digitalhuman_3.0.2_amd64.deb`
- `dist-electron/zkxh-digitalhuman-3.0.2.tar.gz`

### 步骤5: 验证构建产物

```bash
# 检查文件大小和权限
ls -lh dist-electron/

# AppImage应该有执行权限
file dist-electron/*.AppImage
```

---

## 部署前检查

### Ubuntu系统要求

- [ ] Ubuntu 20.04 LTS 或更高版本
- [ ] 至少4GB内存
- [ ] 至少2GB可用磁盘空间
- [ ] 已安装图形界面（或配置虚拟显示）

### 网络要求

- [ ] 能够访问后端服务器
- [ ] 所需端口已开放（默认8000, 8010, 8011等）
- [ ] 防火墙配置正确

### 权限要求

- [ ] 有sudo权限（安装deb包需要）
- [ ] 可以访问/opt目录（应用安装位置）
- [ ] 可以配置systemd服务（开机自启需要）

---

## 部署步骤

### 方式A: DEB包安装（推荐）

1. [ ] 复制deb文件到目标Ubuntu系统
   ```bash
   scp dist-electron/zkxh-digitalhuman_*.deb user@target:/home/user/
   ```

2. [ ] 安装deb包
   ```bash
   sudo dpkg -i zkxh-digitalhuman_*.deb
   sudo apt-get install -f  # 修复依赖（如果需要）
   ```

3. [ ] 验证安装
   ```bash
   which zkxh-digitalhuman
   zkxh-digitalhuman --version
   ```

4. [ ] 配置开机自启
   ```bash
   # 复制服务文件
   scp -r build/* user@target:/home/user/build/
   
   # 在目标系统上安装服务
   cd build
   sudo ./install-service.sh install
   ```

5. [ ] 验证服务
   ```bash
   sudo systemctl status zkxh-digitalhuman
   ```

### 方式B: AppImage运行

1. [ ] 复制AppImage文件到目标系统
   ```bash
   scp dist-electron/*.AppImage user@target:/home/user/
   ```

2. [ ] 添加执行权限
   ```bash
   chmod +x ZKXH-DigitalHuman-*.AppImage
   ```

3. [ ] 运行应用
   ```bash
   ./ZKXH-DigitalHuman-*.AppImage
   ```

---

## 测试验证

### 功能测试清单

- [ ] **应用启动**
  - [ ] 应用能正常启动
  - [ ] 没有崩溃或错误弹窗
  - [ ] 窗口显示正常

- [ ] **设备ID获取**
  - [ ] 打开开发者工具（F12）
  - [ ] 查看Console，确认设备ID已正确获取
  - [ ] 设备ID格式正确

- [ ] **WebSocket连接**
  - [ ] 能连接到后端WebSocket服务器
  - [ ] 心跳机制正常工作
  - [ ] 断线能自动重连

- [ ] **核心功能**
  - [ ] 语音识别功能正常
  - [ ] 大模型对话正常
  - [ ] 数字人视频播放正常
  - [ ] TTS语音合成正常

- [ ] **系统服务**（如已配置）
  - [ ] 服务能正常启动：`sudo systemctl start zkxh-digitalhuman`
  - [ ] 服务能正常停止：`sudo systemctl stop zkxh-digitalhuman`
  - [ ] 查看服务日志无错误：`sudo journalctl -u zkxh-digitalhuman -f`
  - [ ] 重启系统后服务自动启动

---

## 故障排查

### 常见问题及解决方案

#### 问题1: npm install失败

**可能原因**：
- 网络问题
- npm源速度慢

**解决方案**：
```bash
# 使用国内镜像源
npm config set registry https://registry.npmmirror.com

# 重新安装
rm -rf node_modules package-lock.json
npm install
```

#### 问题2: 构建失败 - Electron下载超时

**解决方案**：
```bash
# 设置Electron镜像
export ELECTRON_MIRROR="https://npmmirror.com/mirrors/electron/"

# 重新构建
npm run build:electron
```

#### 问题3: 应用无法启动

**检查项**：
```bash
# 检查依赖
ldd /opt/ZKXH-DigitalHuman/zkxh-digitalhuman

# 安装缺失的库
sudo apt-get install libgtk-3-0 libnotify4 libnss3 libxtst6

# 使用no-sandbox模式启动
/opt/ZKXH-DigitalHuman/zkxh-digitalhuman --no-sandbox
```

#### 问题4: systemd服务启动失败

**检查步骤**：
```bash
# 1. 查看详细错误日志
sudo journalctl -u zkxh-digitalhuman -xe

# 2. 检查DISPLAY环境变量
echo $DISPLAY

# 3. 检查应用是否能手动启动
/opt/ZKXH-DigitalHuman/zkxh-digitalhuman --no-sandbox

# 4. 如果是无头服务器，安装虚拟显示
sudo apt-get install xvfb
# 修改服务文件使用xvfb-run启动
```

---

## 版本管理

### 当前版本信息

- **项目版本**: 3.0.2
- **Electron版本**: ^28.0.0
- **Vue版本**: ^3.4.29
- **Node.js要求**: v20 或 v22

### 版本号规则

修改版本号时需要更新以下文件：
- `package.json` - version字段
- `src/views/DigitalHumanView.vue` - 显示的版本号

---

## 打包产物说明

### 文件清单

构建完成后，`dist-electron/` 目录包含：

| 文件类型 | 文件名示例 | 大小估算 | 用途 |
|---------|-----------|---------|------|
| AppImage | ZKXH-DigitalHuman-3.0.2.AppImage | ~200MB | 免安装运行 |
| DEB包 | zkxh-digitalhuman_3.0.2_amd64.deb | ~180MB | Ubuntu安装包 |
| 压缩包 | zkxh-digitalhuman-3.0.2.tar.gz | ~180MB | 手动部署 |
| 目录 | linux-unpacked/ | ~200MB | 开发调试 |

### 分发建议

- **生产环境**: 使用DEB包
- **演示/测试**: 使用AppImage
- **CI/CD**: 使用tar.gz压缩包

---

## 最终检查清单

部署完成后，请确认：

- [ ] 应用能正常启动和运行
- [ ] 所有核心功能正常
- [ ] 日志无异常错误
- [ ] 性能表现符合预期
- [ ] （可选）开机自启动正常
- [ ] 文档已交付给运维团队

---

## 联系与支持

如遇到问题，请参考：

1. **详细文档**: `ELECTRON_DEPLOYMENT.md`
2. **快速指南**: `QUICKSTART.md`
3. **改造说明**: `ELECTRON_REFACTOR.md`
4. **验证脚本**: `./verify-build.sh`

---

**检查清单版本**: 1.0  
**最后更新**: 2024-11-04
