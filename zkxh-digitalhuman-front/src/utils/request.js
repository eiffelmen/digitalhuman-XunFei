import { buildApiUrl } from '@/config';

// 检测是否为Electron环境
const isElectron = window.electronAPI && window.electronAPI.isElectron;

// API路径映射到服务器键名
const pathToServerMap = {
  '/api/': 'main',
  '/backend/': 'backend',
  '/asr/': 'asr',
  '/v1/rag': 'rag',
  '/v1/upload_file': 'rag',
};

/**
 * 自动转换URL（Electron环境下）
 */
function resolveUrl(url) {
  // 非Electron环境，直接返回相对路径（由Vite代理处理）
  if (!isElectron) {
    return url;
  }
  
  // 如果已经是完整URL，直接返回
  if (url.startsWith('http://') || url.startsWith('https://')) {
    return url;
  }
  
  // 查找匹配的服务器配置
  for (const [prefix, serverKey] of Object.entries(pathToServerMap)) {
    if (url.startsWith(prefix)) {
      // 将 prefix 替换成 /
      const path = url.replace(prefix, '/');
      return buildApiUrl(serverKey, path);
    }
  }
  
  // 默认使用main服务器
  console.warn(`未找到URL映射: ${url}, 使用默认服务器`);
  return buildApiUrl('main', url);
}

const request = async (url, options = {}) => {
  try {
    // Electron环境下转换URL
    const resolvedUrl = resolveUrl(url);
    
    console.log(`[Request] ${url} => ${resolvedUrl}`);
    
    const response = await fetch(resolvedUrl, options);
    if (!response.ok) {
      //throw new Error(`HTTP error! status: ${response.status}`);
      const error = await response.json();
      return Promise.reject(error.detail || error.error || '服务器错误');
    }
    // 解析 JSON 响应或返回其他类型的数据
    const data = await response.json();
    return data;
  } catch (error) {
    console.log(error, '===error')
  }
}
export default request;