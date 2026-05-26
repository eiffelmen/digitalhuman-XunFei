# 项目Electron改造说明

## 改造概述

本文档记录了将Vue3 Web项目改造为Electron桌面应用的完整过程和技术细节。

## 改造内容总结

### 1. 核心架构改造

#### 1.1 添加Electron支持
- ✅ 安装Electron及相关依赖（electron, electron-builder, node-machine-id）
- ✅ 创建Electron主进程文件 `electron/main.js`
- ✅ 创建预加载脚本 `electron/preload.js`
- ✅ 配置electron-builder用于打包

#### 1.2 Vite配置优化
- ✅ 添加Electron环境检测
- ✅ 配置相对路径资源引用（base: './'）
- ✅ 优化构建输出目录和文件命名
- ✅ 区分开发/生产环境的console处理

### 2. 功能优化

#### 2.1 设备ID管理
**原实现问题**:
- 仅支持Android WebView的DeviceBridge接口
- 浏览器环境使用随机UUID，每次刷新会变

**改造方案**:
- 在Electron环境使用`node-machine-id`获取硬件唯一ID
- 通过preload脚本安全地暴露API给渲染进程
- 保持向后兼容Android和浏览器环境

**代码位置**:
- `electron/main.js` - 主进程IPC处理
- `electron/preload.js` - 安全API暴露
- `src/views/DigitalHumanView.vue` - 设备ID获取逻辑

#### 2.2 WebSocket连接管理
**原实现问题**:
- WebSocket连接逻辑分散在组件中
- 手动管理心跳和重连，代码冗长
- 错误处理不统一

**改造方案**:
- 创建统一的WebSocket管理类 `src/utils/websocket.js`
- 封装心跳、重连、错误处理逻辑
- 支持配置化的连接参数

**核心特性**:
```javascript
const wsManager = new WebSocketManager(url, {
  heartbeatInterval: 5000,      // 心跳间隔
  heartbeatTimeout: 10000,      // 心跳超时
  reconnectDelay: 3000,         // 重连延迟
  maxReconnectAttempts: 5,      // 最大重连次数
  onOpen, onMessage, onClose    // 事件回调
});
```

#### 2.3 后端配置管理
**原实现问题**:
- 后端服务器地址硬编码在Vite配置中
- Electron环境无法使用Vite开发服务器代理

**改造方案**:
- 创建配置管理模块 `src/config/index.js`
- 支持运行时配置后端地址（localStorage）
- 自动检测Electron/浏览器环境，构建正确的URL

**使用示例**:
```javascript
import { buildWsUrl, buildApiUrl } from '@/config';

// 自动处理Electron/浏览器环境差异
const wsUrl = buildWsUrl('main', '/api/ws?type=web&id=' + deviceId);
const apiUrl = buildApiUrl('backend', '/api/users');
```

#### 2.4 日志管理
**改造内容**:
- 创建统一日志工具 `src/utils/logger.js`
- 支持日志级别（debug, info, warn, error）
- Electron环境下日志可发送到主进程

### 3. Bug修复

#### 3.1 localStorage拼写错误
**位置**: `src/App.vue`
```javascript
// 修复前
if (localStorage.getItem("inited") !== "ture")  // 拼写错误

// 修复后
if (localStorage.getItem("inited") !== "true")
```

#### 3.2 Console日志清理
- 开发环境保留console输出
- 生产环境自动移除console和debugger
- 配置在 `vite.config.js` 的 esbuild.drop 选项

### 4. 代码重构

按照面向对象思维和单一职责原则进行重构：

#### 4.1 提取工具类
- `WebSocketManager` - WebSocket连接管理
- `Logger` - 日志管理
- `config/index.js` - 配置管理

#### 4.2 改进错误处理
- 统一的try-catch包装
- 明确的错误信息提示
- 优雅的降级方案

#### 4.3 代码简化
通过工具类封装，减少重复代码：
- `DigitalHumanView.vue` 中WebSocket相关代码从100+行减少到30行
- 提高可维护性和可测试性

### 5. 打包配置

#### 5.1 package.json配置
```json
{
  "main": "electron/main.js",
  "scripts": {
    "dev:electron": "electron .",
    "build:electron": "vite build && electron-builder --linux",
    "build:electron:dir": "vite build && electron-builder --linux --dir"
  }
}
```

#### 5.2 electron-builder配置
创建 `electron-builder.json`:
- 支持AppImage、deb、tar.gz三种格式
- 配置Linux桌面文件
- 设置应用元数据和图标

#### 5.3 构建产物
```
dist-electron/
├── ZKXH-DigitalHuman-3.0.2.AppImage    # 免安装版
├── zkxh-digitalhuman_3.0.2_amd64.deb  # Debian安装包
└── zkxh-digitalhuman-3.0.2.tar.gz     # 压缩包
```

### 6. 系统服务配置

#### 6.1 systemd服务文件
创建 `build/zkxh-digitalhuman.service`:
- 配置开机自启动
- 设置正确的环境变量（DISPLAY, XAUTHORITY）
- 启用自动重启机制

#### 6.2 自动化安装脚本
创建 `build/install-service.sh`:
- 一键安装/卸载服务
- 服务状态检查
- 彩色输出和错误处理

### 7. 文档完善

创建详细的文档体系：

| 文档 | 用途 |
|------|------|
| ELECTRON_DEPLOYMENT.md | 完整的打包、部署、配置指南 |
| QUICKSTART.md | 快速开始指南 |
| README.md | 项目概述和双模式说明 |
| build/README_ICON.md | 图标准备说明 |
| ELECTRON_REFACTOR.md | 本文档，改造说明 |

## 技术选型说明

### 为什么选择Electron？

1. **跨平台兼容性**: 同一套代码可以运行在Linux、Windows、macOS
2. **Web技术栈**: 复用现有Vue3项目，无需重写
3. **成熟生态**: electron-builder提供完善的打包工具
4. **离线运行**: 不依赖Web服务器，适合嵌入式设备

### 架构设计原则

1. **向后兼容**: 保持对原有Web版本和Android WebView的支持
2. **环境自适应**: 自动检测运行环境，使用对应的API
3. **配置灵活性**: 支持运行时配置，无需重新打包
4. **代码复用**: 最大化复用现有代码，最小化改动

## 关键技术实现

### 1. Electron安全通信

使用contextBridge实现安全的进程间通信：

```javascript
// electron/preload.js
contextBridge.exposeInMainWorld('electronAPI', {
  getDeviceId: () => ipcRenderer.invoke('get-device-id'),
  // 其他API...
});

// electron/main.js
ipcMain.handle('get-device-id', async () => {
  const deviceId = machineId.machineIdSync();
  return deviceId;
});
```

### 2. 环境检测机制

```javascript
// 检测是否为Electron环境
const isElectron = window.electronAPI && window.electronAPI.isElectron;

// 根据环境使用不同实现
if (isElectron) {
  // Electron专用逻辑
} else {
  // 浏览器逻辑
}
```

### 3. 资源路径处理

```javascript
// vite.config.js
export default defineConfig({
  base: isElectron ? './' : '/',  // 相对路径 vs 绝对路径
  build: {
    rollupOptions: {
      output: {
        assetFileNames: 'assets/[name]-[hash][extname]',  // 确保相对路径
      }
    }
  }
});
```

## 性能优化

1. **代码分割**: Vite自动进行代码分割和懒加载
2. **资源压缩**: 生产构建自动压缩JS、CSS
3. **树摇优化**: 移除未使用的代码
4. **Console移除**: 生产环境移除所有console输出

## 测试建议

### 开发测试
```bash
# 1. 启动Web开发服务器
npm run dev

# 2. 在另一个终端启动Electron
npm run dev:electron
```

### 打包测试
```bash
# 快速打包（仅目录，不生成安装包）
npm run build:electron:dir

# 运行打包后的应用
./dist-electron/linux-unpacked/zkxh-digitalhuman
```

### 服务测试
```bash
# 安装deb包
sudo dpkg -i dist-electron/zkxh-digitalhuman_*.deb

# 测试systemd服务
sudo systemctl start zkxh-digitalhuman
sudo systemctl status zkxh-digitalhuman
```

## 已知限制

1. **图标依赖**: 需要手动准备应用图标文件
2. **后端配置**: 首次运行需要配置后端服务器地址
3. **显示环境**: systemd服务需要正确配置DISPLAY环境变量
4. **沙箱模式**: 某些环境可能需要 `--no-sandbox` 参数

## 未来优化方向

1. **自动更新**: 集成electron-updater实现自动更新
2. **崩溃报告**: 添加Sentry等错误监控
3. **性能监控**: 集成性能监控工具
4. **配置界面**: 提供GUI配置后端服务器地址
5. **多语言支持**: i18n国际化支持
6. **主题定制**: 支持自定义主题和样式

## 升级路径

### 从Web版本迁移到Electron版本

1. **数据迁移**: localStorage数据自动迁移
2. **配置迁移**: 需要重新配置后端地址
3. **功能兼容**: 所有原有功能保持不变

### 版本更新流程

1. 停止旧版本服务
2. 备份配置文件
3. 安装新版本deb包
4. 恢复配置
5. 重启服务

## 总结

通过本次改造，项目实现了：

✅ **多平台支持**: Web浏览器 + Electron桌面应用 + Android WebView  
✅ **代码质量提升**: 重构优化，遵循面向对象原则  
✅ **Bug修复**: 修复已知问题  
✅ **文档完善**: 提供详尽的部署和使用文档  
✅ **生产就绪**: 支持systemd服务和开机自启  

项目现在可以灵活地在不同环境下部署，满足各种使用场景的需求。

---

**改造完成时间**: 2024-11-04  
**改造版本**: 3.0.2  
**技术栈**: Vue3 + Vite + Electron + systemd
