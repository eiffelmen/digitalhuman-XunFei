const { contextBridge, ipcRenderer } = require('electron');

// 暴露安全的API给渲染进程
contextBridge.exposeInMainWorld('electronAPI', {
  // 获取设备ID
  getDeviceId: () => ipcRenderer.invoke('get-device-id'),
  
  // 窗口控制
  toggleFullscreen: () => ipcRenderer.invoke('toggle-fullscreen'),
  minimizeWindow: () => ipcRenderer.invoke('minimize-window'),
  maximizeWindow: () => ipcRenderer.invoke('maximize-window'),
  closeWindow: () => ipcRenderer.invoke('close-window'),
  
  // 获取应用版本
  getAppVersion: () => ipcRenderer.invoke('get-app-version'),
  
  // 日志记录
  logMessage: (level, message) => ipcRenderer.send('log-message', level, message),

  // 订阅人脸数据
  onFaceData: (callback) => {
    if (typeof callback !== 'function') {
      return () => {};
    }
    const listener = (_event, payload) => {
      callback(payload);
    };
    ipcRenderer.on('face-data', listener);
    return () => ipcRenderer.removeListener('face-data', listener);
  },
  
  // 平台检测
  platform: process.platform,
  isElectron: true,
});

// 捕获渲染进程中的未处理错误
window.addEventListener('error', (event) => {
  const errorMessage = `未捕获错误: ${event.message} at ${event.filename}:${event.lineno}:${event.colno}`;
  ipcRenderer.send('log-message', 'error', errorMessage);
});

// 捕获未处理的Promise拒绝
window.addEventListener('unhandledrejection', (event) => {
  const reason = event.reason && event.reason.stack ? event.reason.stack : String(event.reason);
  const errorMessage = `未处理的Promise拒绝: ${reason}`;
  ipcRenderer.send('log-message', 'error', errorMessage);
});

// 模拟Android桥接对象（用于兼容原有代码）
contextBridge.exposeInMainWorld('DeviceBridge', {
  getDeviceId: async () => {
    try {
      const deviceId = await ipcRenderer.invoke('get-device-id');
      return deviceId;
    } catch (error) {
      console.error('获取设备ID失败:', error);
      return null;
    }
  },
});

console.log('Preload script loaded successfully');
