const { app, BrowserWindow, ipcMain, screen } = require('electron');
const path = require('path');
const fs = require('fs');
const { FaceDataBridge } = require('./face-server.cjs');

let mainWindow = null;
let faceBridgeServer = null;
// 判断是否为开发模式：
// 1. 未打包时（源码运行）：始终是开发模式
// 2. 已打包时：仅当明确设置 DEV_MODE=1 时才作为开发模式（连接开发服务器）
const isSourceDev = !app.isPackaged; // 源码开发模式
const isPackagedDev = app.isPackaged && process.env.DEV_MODE === '1'; // 打包后的开发模式
const shouldLoadDevServer = isSourceDev || isPackagedDev; // 是否加载开发服务器
const isDev = process.env.NODE_ENV === 'development' || isSourceDev; // 是否开发环境（影响日志等配置）

console.log('='.repeat(60));
console.log('Electron 应用启动');
console.log('='.repeat(60));
console.log('运行模式:', shouldLoadDevServer ? '开发服务器模式' : '本地文件模式');
console.log('开发环境:', isDev ? '是' : '否');
console.log('NODE_ENV:', process.env.NODE_ENV);
console.log('isPackaged:', app.isPackaged);
console.log('DEV_MODE:', process.env.DEV_MODE);
console.log('__dirname:', __dirname);
console.log('process.cwd():', process.cwd());
console.log('='.repeat(60));

// 默认启用详细日志输出
const enableLogging = process.env.ELECTRON_ENABLE_LOGGING !== '0'; // 默认开启，设置为'0'才关闭
const logLevel = process.env.LOG_LEVEL || '2'; // 默认级别2

if (enableLogging) {
  app.commandLine.appendSwitch('enable-logging');
  app.commandLine.appendSwitch('v', logLevel);
  console.log('详细日志已启用，日志级别:', logLevel);
} else {
  console.log('详细日志已禁用');
}

// 开发环境下忽略证书错误
if (shouldLoadDevServer) {
  console.log('[开发服务器模式] 忽略证书错误配置已启用');
  app.commandLine.appendSwitch('ignore-certificate-errors');
  app.commandLine.appendSwitch('allow-insecure-localhost', 'true');
}

function createWindow() {
  console.log('\n' + '='.repeat(60));
  console.log('开始创建窗口');
  console.log('='.repeat(60));
  
  // 获取主显示器信息
  const primaryDisplay = screen.getPrimaryDisplay();
  const { width, height } = primaryDisplay.workAreaSize;
  console.log('屏幕尺寸:', { width, height });

  const preloadPath = path.join(__dirname, 'preload.cjs');
  console.log('Preload 脚本路径:', preloadPath);
  console.log('Preload 脚本是否存在:', require('fs').existsSync(preloadPath));
  
  const windowOptions = {
    width: width,
    height: height,
    fullscreen: true, // 默认非全屏，可通过快捷键切换
    autoHideMenuBar: true, // 隐藏菜单栏
    fullscreenable: true,
    titleBarStyle: 'hidden',
    webPreferences: {
      preload: preloadPath,
      contextIsolation: true,
      nodeIntegration: false,
      webSecurity: shouldLoadDevServer ? false : true, // 开发服务器模式禁用webSecurity以支持自签名证书
      // 启用WebRTC和媒体设备访问
      webviewTag: false,
    },
  };
  
  console.log('窗口配置:', JSON.stringify(windowOptions, null, 2));
  
  try {
    mainWindow = new BrowserWindow(windowOptions);
    console.log('BrowserWindow 创建成功');
  } catch (error) {
    console.error('创建 BrowserWindow 失败:', error);
    throw error;
  }

  // 监听窗口事件
  mainWindow.webContents.on('did-start-loading', () => {
    console.log('[页面加载] 开始加载页面...');
  });
  
  mainWindow.webContents.on('did-finish-load', () => {
    console.log('[页面加载] 页面加载完成 ✓');
  });
  
  mainWindow.webContents.on('did-fail-load', (event, errorCode, errorDescription, validatedURL) => {
    console.error('[页面加载] 页面加载失败 ✗');
    console.error('错误代码:', errorCode);
    console.error('错误描述:', errorDescription);
    console.error('URL:', validatedURL);
    
    // 写入日志文件
    writeLogToFile('error', `页面加载失败 - 错误代码: ${errorCode}, 描述: ${errorDescription}, URL: ${validatedURL}`);
  });
  
  mainWindow.webContents.on('dom-ready', () => {
    console.log('[页面加载] DOM 已就绪');
  });
  
  mainWindow.webContents.on('console-message', (event, level, message, line, sourceId) => {
    const levelMap = ['DEBUG', 'INFO', 'WARNING', 'ERROR'];
    const timestamp = new Date().toISOString();
    console.log(`[${timestamp}] [CONSOLE] [L${level}] ${message}`);
    if (sourceId) {
      console.log(`[${timestamp}] [CONSOLE]   源文件: ${sourceId}:${line}`);
    }
    
    // 将警告和错误级别的控制台消息写入日志文件
    if (level >= 2) { // 2=WARNING, 3=ERROR
      const levelName = levelMap[level] || 'UNKNOWN';
      const logMessage = sourceId ? `${message} (${sourceId}:${line})` : message;
      writeLogToFile(levelName.toLowerCase(), logMessage);
    }
  });
  
  // 捕获渲染进程的JavaScript错误
  mainWindow.webContents.on('render-process-gone', (event, details) => {
    const timestamp = new Date().toISOString();
    console.error(`[${timestamp}] [严重] 渲染进程终止!`);
    console.error(`[${timestamp}] [严重] 原因: ${details.reason}`);
    console.error(`[${timestamp}] [严重] 退出码: ${details.exitCode}`);
    
    // 写入日志文件
    writeLogToFile('error', `渲染进程终止! 原因: ${details.reason}, 退出码: ${details.exitCode}`);
  });
  
  mainWindow.webContents.on('crashed', (event, killed) => {
    console.error('[严重错误] 渲染进程崩溃!');
    console.error('是否被杀死:', killed);
  });
  
  mainWindow.on('unresponsive', () => {
    console.warn('[警告] 窗口无响应');
  });
  
  mainWindow.on('responsive', () => {
    console.log('[恢复] 窗口已恢复响应');
  });
  
  // 根据模式加载不同的内容
  if (shouldLoadDevServer) {
    // 开发模式：加载 Vite 开发服务器
    const devUrl = 'http://localhost:3000';
    console.log('\n[开发服务器] 加载 URL:', devUrl);
    console.log('[开发服务器] 请确保 Vite 开发服务器已启动: npm run dev');
    
    mainWindow.loadURL(devUrl).then(() => {
      console.log('[开发服务器] loadURL 调用成功');
    }).catch((error) => {
      console.error('[开发服务器] loadURL 调用失败:', error);
      console.error('[开发服务器] 请检查 Vite 开发服务器是否运行在 http://localhost:3000');
    });
    
    console.log('[开发服务器] 打开开发者工具...');
    mainWindow.webContents.openDevTools();
  } else {
    // 生产模式：加载本地打包文件
    const indexPath = path.join(__dirname, '../dist/index.html');
    console.log('\n[本地文件] 加载路径:', indexPath);
    console.log('[本地文件] 文件是否存在:', require('fs').existsSync(indexPath));
    
    if (require('fs').existsSync(indexPath)) {
      mainWindow.loadFile(indexPath).then(() => {
        console.log('[本地文件] loadFile 调用成功');
        
        // 开发环境下打开开发者工具（用于调试打包后的应用）
        if (isDev) {
          console.log('[本地文件] 开发环境，打开开发者工具...');
          mainWindow.webContents.openDevTools();
        }
      }).catch((error) => {
        console.error('[本地文件] loadFile 调用失败:', error);
      });
    } else {
      console.error('[本地文件] 错误: index.html 文件不存在!');
      console.error('[本地文件] 请确保已执行构建: npm run build');
      console.error('[本地文件] 当前查找路径:', indexPath);
    }
  }

  // 处理窗口关闭
  mainWindow.on('closed', () => {
    console.log('[窗口事件] 窗口已关闭');
    mainWindow = null;
  });

  // 启用全屏快捷键 F11
  mainWindow.webContents.on('before-input-event', (event, input) => {
    if (input.key === 'F11' && input.type === 'keyDown') {
      mainWindow.setFullScreen(!mainWindow.isFullScreen());
    }
  });
}

// 确保单例运行
const gotTheLock = app.requestSingleInstanceLock();

if (!gotTheLock) {
  app.quit();
} else {
  app.on('second-instance', () => {
    // 当运行第二个实例时，聚焦到已存在的窗口
    if (mainWindow) {
      if (mainWindow.isMinimized()) mainWindow.restore();
      mainWindow.focus();
    }
  });

  app.whenReady().then(() => {
    console.log('\n' + '='.repeat(60));
    console.log('App whenReady 事件触发');
    console.log('='.repeat(60));
    
    // 开发服务器模式下忽略证书错误（自签名证书）
    if (shouldLoadDevServer) {
      app.commandLine.appendSwitch('ignore-certificate-errors');
      console.log('[开发服务器模式] 证书错误忽略已配置');
    }
    
    try {
      createWindow();
    } catch (error) {
      console.error('创建窗口时发生错误:', error);
      console.error('错误堆栈:', error.stack);
    }

    // 启动本地人脸数据桥，接收 C++ 端推送
    faceBridgeServer = new FaceDataBridge();
    faceBridgeServer.on('face-data', payload => {
      if (mainWindow && payload) {
        mainWindow.webContents.send('face-data', payload);
      }
    });
    faceBridgeServer.start();

    app.on('activate', () => {
      console.log('[App 事件] activate 事件触发');
      if (BrowserWindow.getAllWindows().length === 0) {
        console.log('[App 事件] 没有窗口，创建新窗口...');
        createWindow();
      }
    });
  });
}

app.on('window-all-closed', () => {
  console.log('[App 事件] window-all-closed 事件触发');
  console.log('平台:', process.platform);
  // 在 Linux 上，关闭所有窗口后退出应用
  if (process.platform !== 'darwin') {
    console.log('[App 事件] 退出应用...');
    app.quit();
  }
});

app.on('quit', () => {
  if (faceBridgeServer) {
    faceBridgeServer.stop();
    faceBridgeServer = null;
  }
});

// IPC通信处理
console.log('\n' + '='.repeat(60));
console.log('注册 IPC 处理程序');
console.log('='.repeat(60));

ipcMain.handle('get-device-id', async () => {
  console.log('[IPC] get-device-id 被调用');
  // 生成或获取设备唯一ID
  try {
    const { machineIdSync } = require('node-machine-id');
    const deviceId = machineIdSync();
    console.log('[IPC] 获取设备ID成功:', deviceId);
    return deviceId;
  } catch (error) {
    console.error('[IPC] 获取设备ID失败:', error);
    // 返回一个基于时间的唯一ID作为后备方案
    const fallbackId = `device-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
    console.log('[IPC] 使用后备ID:', fallbackId);
    return fallbackId;
  }
});

ipcMain.handle('toggle-fullscreen', () => {
  console.log('[IPC] toggle-fullscreen 被调用');
  if (mainWindow) {
    const isFullScreen = !mainWindow.isFullScreen();
    mainWindow.setFullScreen(isFullScreen);
    console.log('[IPC] 全屏状态:', isFullScreen);
    return mainWindow.isFullScreen();
  }
  console.warn('[IPC] toggle-fullscreen: mainWindow 不存在');
  return false;
});

ipcMain.handle('minimize-window', () => {
  if (mainWindow) {
    mainWindow.minimize();
  }
});

ipcMain.handle('maximize-window', () => {
  if (mainWindow) {
    if (mainWindow.isMaximized()) {
      mainWindow.unmaximize();
    } else {
      mainWindow.maximize();
    }
    return mainWindow.isMaximized();
  }
  return false;
});

ipcMain.handle('close-window', () => {
  if (mainWindow) {
    mainWindow.close();
  }
});

// 获取应用版本号
ipcMain.handle('get-app-version', () => {
  return app.getVersion();
});

// 日志文件路径
const logFilePath = path.join(app.getPath('userData'), 'digitalhuman-error.log');
console.log('[日志系统] 错误日志文件路径:', logFilePath);

/**
 * 写入日志到文件
 */
function writeLogToFile(level, message) {
  try {
    const timestamp = new Date().toISOString();
    const logEntry = `[${timestamp}] [${level.toUpperCase()}] ${message}\n`;
    fs.appendFileSync(logFilePath, logEntry, 'utf8');
  } catch (error) {
    console.error('[日志系统] 写入日志文件失败:', error);
  }
}

// 日志记录
ipcMain.on('log-message', (event, level, message) => {
  const timestamp = new Date().toISOString();
  console.log(`[${timestamp}] [${level.toUpperCase()}]`, message);
  
  // 只将 warn 和 error 级别的日志写入文件
  if (level === 'warn' || level === 'error') {
    writeLogToFile(level, message);
  }
});

// 启用控制台日志输出
process.on('uncaughtException', (error) => {
  console.error('\n' + '!'.repeat(60));
  console.error('[未捕获异常] Uncaught Exception');
  console.error('!'.repeat(60));
  console.error('错误:', error);
  console.error('堆栈:', error.stack);
  console.error('!'.repeat(60));
  
  // 写入日志文件
  writeLogToFile('error', `未捕获异常: ${error.message}\n${error.stack}`);
});

process.on('unhandledRejection', (reason, promise) => {
  console.error('\n' + '!'.repeat(60));
  console.error('[未处理的Promise拒绝] Unhandled Rejection');
  console.error('!'.repeat(60));
  console.error('Promise:', promise);
  console.error('原因:', reason);
  if (reason && reason.stack) {
    console.error('堆栈:', reason.stack);
  }
  console.error('!'.repeat(60));
  
  // 写入日志文件
  const reasonText = reason && reason.stack ? reason.stack : String(reason);
  writeLogToFile('error', `未处理的Promise拒绝: ${reasonText}`);
});

// Chromium 日志
app.on('ready', () => {
  console.log('\n' + '='.repeat(60));
  console.log('App ready 事件触发');
  console.log('='.repeat(60));
  console.log('Electron 版本:', process.versions.electron);
  console.log('Chrome 版本:', process.versions.chrome);
  console.log('Node 版本:', process.versions.node);
  console.log('V8 版本:', process.versions.v8);
  console.log('平台:', process.platform);
  console.log('架构:', process.arch);
  console.log('应用版本:', app.getVersion());
  console.log('应用路径:', app.getAppPath());
  console.log('用户数据路径:', app.getPath('userData'));
  console.log('='.repeat(60));
});
