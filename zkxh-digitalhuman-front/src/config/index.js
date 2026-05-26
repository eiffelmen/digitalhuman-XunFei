/**
 * 应用配置文件
 * 用于管理后端服务器地址等配置
 */

// 检测是否为Electron环境
const isElectron = window.electronAPI && window.electronAPI.isElectron;

const BACKEND_HOST = import.meta.env.VITE_BACKEND_HOST || 'localhost';
const BACKEND_PORT = import.meta.env.VITE_BACKEND_PORT || '8010';
const MAIN_API_PORT = import.meta.env.VITE_MAIN_API_PORT || '8000';
const ASR_WS_PORT = import.meta.env.VITE_ASR_WS_PORT || '10099';
const RAG_PORT = import.meta.env.VITE_RAG_PORT || '8888';

// 默认后端配置
const DEFAULT_BACKEND_CONFIG = {
  // 主后端服务器
  mainServer: `${BACKEND_HOST}:${BACKEND_PORT}`,

  // API服务器映射
  apiServers: {
    main: `${BACKEND_HOST}:${MAIN_API_PORT}`,      // /api
    backend: `${BACKEND_HOST}:${BACKEND_PORT}`,   // /backend
    asr: `${BACKEND_HOST}:${ASR_WS_PORT}`,      // /asr
    rag: `${BACKEND_HOST}:${RAG_PORT}`,       // /v1/rag, /v1/upload_file
  },
  
  // WebSocket配置
  websocket: {
    useSSL: false,
  },
};

/**
 * 获取后端配置
 */
export function getBackendConfig() {
  // 从localStorage尝试读取用户配置
  const savedConfig = localStorage.getItem('backendConfig');
  
  if (savedConfig) {
    try {
      return { ...DEFAULT_BACKEND_CONFIG, ...JSON.parse(savedConfig) };
    } catch (e) {
      console.error('解析后端配置失败:', e);
    }
  }
  
  return DEFAULT_BACKEND_CONFIG;
}

/**
 * 保存后端配置
 */
export function saveBackendConfig(config) {
  localStorage.setItem('backendConfig', JSON.stringify(config));
}

/**
 * 构建API URL
 * @param {string} serverKey - 服务器键名
 * @param {string} path - API路径
 */
export function buildApiUrl(serverKey, path) {
  const config = getBackendConfig();
  const server = config.apiServers[serverKey];
  
  if (!server) {
    console.error(`未找到服务器配置: ${serverKey}`);
    return path;
  }
  
  // Electron环境下返回完整URL
  if (isElectron) {
    const protocol = config.websocket.useSSL ? 'https' : 'http';
    return `${protocol}://${server}${path}`;
  }
  
  // 浏览器环境下，根据 serverKey 添加代理前缀
  const proxyPrefixMap = {
    main: '/api',
    backend: '/backend',
    asr: '/asr',
    rag: '', // rag 直接使用 /v1/rag 路径
  };
  
  const prefix = proxyPrefixMap[serverKey];
  if (prefix === undefined) {
    console.warn(`未知的 serverKey: ${serverKey}，直接返回 path`);
    return path;
  }
  
  // 如果path已经包含了prefix，直接返回
  if (prefix && path.startsWith(prefix)) {
    return path;
  }
  
  // 添加代理前缀
  return prefix ? `${prefix}${path}` : path;
}

/**
 * 构建WebSocket URL
 * @param {string} serverKey - 服务器键名
 * @param {string} path - WebSocket路径
 */
export function buildWsUrl(serverKey, path) {
  const config = getBackendConfig();
  const server = config.apiServers[serverKey];

  if (!server) {
    console.error(`未找到服务器配置: ${serverKey}`);
    return path;
  }
  // Electron环境下返回完整WebSocket URL
  if (isElectron) {
    const protocol = config.websocket.useSSL ? 'wss' : 'ws';
    return `${protocol}://${server}${path}`;
  }

  // 浏览器环境下，根据 serverKey 添加代理前缀
  const wsProxyPrefixMap = {
    main: '/ws',
    asr: '/asr',
    // 其他服务使用默认代理前缀
    backend: '/backend',
    rag: '/v1/rag',
  };

  const prefix = wsProxyPrefixMap[serverKey];
  if (prefix === undefined) {
    console.warn(`未知的 serverKey: ${serverKey}，直接返回 path`);
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const host = window.location.host;
    return `${protocol}//${host}${path}`;
  }

  // 如果path已经包含了prefix，直接返回
  if (prefix && path.startsWith(prefix)) {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const host = window.location.host;
    return `${protocol}//${host}${path}`;
  }

  // 添加代理前缀
  const fullPath = prefix ? `${prefix}${path}` : path;
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  const host = window.location.host;
  return `${protocol}//${host}${fullPath}`;
}

export default {
  getBackendConfig,
  saveBackendConfig,
  buildApiUrl,
  buildWsUrl,
  isElectron,
};
