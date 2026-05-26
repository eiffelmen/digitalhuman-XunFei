# URL 统一管理文档

本文档详细说明了项目中 `buildApiUrl`、`buildWsUrl` 和 `getPublicUrl` 三个函数的使用方法，以及新增域名时需要进行的配置修改。

---

## 一、核心函数说明

### 1. buildApiUrl - HTTP/HTTPS 接口地址构建

**位置**: `/src/config/index.js`

**用途**: 构建 HTTP/HTTPS 请求的 API 地址，自动适配浏览器开发环境和 Electron 打包环境

**函数签名**:
```javascript
buildApiUrl(serverKey, path)
```

**参数说明**:
- `serverKey`: 服务器键名（对应 `apiServers` 配置中的 key）
- `path`: API 路径（必须以 `/` 开头）

**使用示例**:
```javascript
import { buildApiUrl } from '@/config';

// 调用主服务器接口
const url = buildApiUrl('main', '/api/user/info');
// 浏览器环境: /api/api/user/info (通过 Vite 代理转发)
// Electron环境: http://your-server-host:8000/api/user/info

// 调用后端服务器接口
const url = buildApiUrl('backend', '/human');
// 浏览器环境: /backend/human
// Electron环境: http://your-server-host:8010/human

// 调用 RAG 服务器接口
const url = buildApiUrl('rag', '/v1/rag');
// 浏览器环境: /v1/rag
// Electron环境: http://your-server-host:8888/v1/rag
```

**实际应用场景**:
```javascript
// 在 fetch 请求中使用
const response = await fetch(buildApiUrl('backend', '/offer'), {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(data)
});

// 在 img 标签中使用（动态资源）
const adVideoSrc = buildApiUrl('main', '/static/反诈视频.mp4');
<video :src="adVideoSrc" />
```

---

### 2. buildWsUrl - WebSocket 地址构建

**位置**: `/src/config/index.js`

**用途**: 构建 WebSocket 连接地址，自动适配浏览器开发环境和 Electron 打包环境

**函数签名**:
```javascript
buildWsUrl(serverKey, path)
```

**参数说明**:
- `serverKey`: 服务器键名（对应 `apiServers` 配置中的 key）
- `path`: WebSocket 路径（必须以 `/` 开头）

**使用示例**:
```javascript
import { buildWsUrl } from '@/config';

// 连接主服务器 WebSocket
const wsUrl = buildWsUrl('main', '/ws/asr');
// 浏览器环境: ws://localhost:3000/ws/asr
// Electron环境: ws://your-server-host:8000/ws/asr

// 连接 LLM WebSocket
const llmUrl = buildWsUrl('llm', `/ws/${sessionId}`);
// 浏览器环境: ws://localhost:3000/llm/ws/xxx
// Electron环境: ws://your-server-host:8011/ws/xxx
```

**实际应用场景**:
```javascript
// 初始化 WebSocket 连接
function initAsrWebSocket() {
  const wsUrl = buildWsUrl('main', '/ws/asr');
  const socket = new WebSocket(wsUrl);
  
  socket.addEventListener('open', () => {
    console.log('WebSocket 连接成功');
  });
  
  socket.addEventListener('message', (event) => {
    console.log('收到消息:', event.data);
  });
}

// 在 LLM 接口中使用
const llmSocket = new WebSocket(buildWsUrl('llm', `/ws/${sessionId}`));
```

---

### 3. getPublicUrl - 静态资源路径获取

**位置**: `/src/utils/getAssets.js`

**用途**: 获取 `public` 目录下的静态资源路径，兼容浏览器和 Electron 环境

**函数签名**:
```javascript
getPublicUrl(url)
```

**参数说明**:
- `url`: 资源路径（通常以 `/` 开头，相对于 public 目录）

**使用示例**:
```javascript
import { getPublicUrl } from '@/utils/getAssets';

// 获取图片路径
const iconPath = getPublicUrl('/icon.webp');
// 浏览器环境: ./icon.webp
// Electron环境: ./icon.webp

// 获取背景图路径
const bgPath = getPublicUrl('/chat_bg_model.png');
```

**实际应用场景**:
```vue
<template>
  <!-- 在 img 标签中使用 -->
  <img :src="getPublicUrl('/name.png')" alt="名称" />
  
  <!-- 在背景图样式中使用 -->
  <div 
    :style="`background-image: url('${getPublicUrl('/chat_bg_model.png')}');`"
  />
  
  <!-- 在 video 标签中使用 -->
  <video 
    :poster="getPublicUrl('/video_bg2.png')"
    src="/videos/demo.mp4"
  />
</template>

<script setup>
import { getPublicUrl } from '@/utils/getAssets';
</script>
```

**注意事项**:
- `getPublicUrl` 仅用于 `public` 目录下的资源
- 对于 `src/assets` 目录下的资源，使用 `getAssetImgUrl` 函数
- 资源路径必须以 `/` 开头

---

## 二、当前服务器配置

### 服务器映射表 (apiServers)

| serverKey | 服务器地址 | 浏览器代理前缀 | 用途说明 |
|-----------|-----------|---------------|---------|
| main | your-server-host:8000 | /api | 主服务器，WebSocket、通用接口 |
| backend | your-server-host:8010 | /backend | 后端服务，数字人控制接口 |
| asr | your-server-host:10099 | /asr | 语音识别服务 |
| rag | your-server-host:8888 | (空字符串) | RAG知识库服务 |

---

## 三、新增域名配置步骤

当需要接入新的后端服务时，需要按以下步骤进行配置：

### 步骤 1: 修改 `src/config/index.js`

在 `DEFAULT_BACKEND_CONFIG.apiServers` 中添加新的服务器配置：

```javascript
const DEFAULT_BACKEND_CONFIG = {
  mainServer: 'your-server-host:8010',
  
  apiServers: {
    main: 'your-server-host:8000',
    backend: 'your-server-host:8010',
    // ... 其他配置 ...
    
    // 新增服务器配置
    newService: 'your-server-host:9000',  // ✅ 添加这一行
  },
  
  websocket: {
    useSSL: false,
  },
};
```

### 步骤 2: 在 `buildApiUrl` 中添加代理前缀映射

```javascript
export function buildApiUrl(serverKey, path) {
  // ... 前面代码省略 ...
  
  const proxyPrefixMap = {
    main: '/api',
    backend: '/backend',
    // ... 其他配置 ...
    
    newService: '/new_service',  // ✅ 添加代理前缀映射
  };
  
  // ... 后续代码省略 ...
}
```

### 步骤 3: 修改 `vite.config.js` 添加开发代理

在 `server.proxy` 中添加新的代理规则：

```javascript
export default defineConfig({
  server: {
    proxy: {
      '/v1/upload_file': 'http://your-server-host:8888',
      '/v1/rag': 'http://your-server-host:8888',
      // ... 其他代理配置 ...
      
      // ✅ 添加新服务的代理配置
      '/new_service': {
        target: 'http://your-server-host:9000',
        changeOrigin: true,
        rewrite: path => path.replace(/^\/new_service/, ''),
      },
    },
  },
  // ... 其他配置 ...
});
```

### 步骤 4: 在代码中使用

```javascript
import { buildApiUrl, buildWsUrl } from '@/config';

// HTTP 请求
const apiUrl = buildApiUrl('newService', '/api/data');
fetch(apiUrl).then(res => res.json());

// WebSocket 连接（如果需要）
const wsUrl = buildWsUrl('newService', '/ws/channel');
const socket = new WebSocket(wsUrl);
```

---

## 四、完整示例：添加 TTS 语音合成服务

假设要添加一个新的 TTS 服务：
- 服务器地址: `your-server-host:7000`
- 代理前缀: `/tts`

### 1. 修改 `src/config/index.js`

```javascript
const DEFAULT_BACKEND_CONFIG = {
  apiServers: {
    main: 'your-server-host:8000',
    backend: 'your-server-host:8010',
    llm: 'your-server-host:8011',
    asr: 'your-server-host:10099',
    tts: 'your-server-host:7000',  // ✅ 新增
    // ... 其他配置
  },
};

export function buildApiUrl(serverKey, path) {
  const proxyPrefixMap = {
    main: '/api',
    backend: '/backend',
    asr: '/asr',
    tts: '/tts',  // ✅ 新增
    // ... 其他配置
  };
  // ... 其余代码
}
```

### 2. 修改 `vite.config.js`

```javascript
export default defineConfig({
  server: {
    proxy: {
      // ... 其他代理配置
      
      '/tts': {
        target: 'http://your-server-host:7000',
        changeOrigin: true,
        rewrite: path => path.replace(/^\/tts/, ''),
      },
    },
  },
});
```

### 3. 使用示例

```javascript
// 在组件中使用
import { buildApiUrl, buildWsUrl } from '@/config';

// HTTP 请求 TTS 接口
async function synthesizeSpeech(text) {
  const response = await fetch(buildApiUrl('tts', '/synthesize'), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ text })
  });
  return await response.json();
}

// WebSocket 连接 TTS 实时合成
function connectTTSStream() {
  const wsUrl = buildWsUrl('tts', '/ws/stream');
  const socket = new WebSocket(wsUrl);
  
  socket.onopen = () => {
    console.log('TTS WebSocket 已连接');
  };
  
  socket.onmessage = (event) => {
    // 处理音频流数据
    const audioData = event.data;
  };
}
```

---

## 五、环境差异对照表

### buildApiUrl 返回值对比

| serverKey | path | 浏览器环境（开发） | Electron环境 |
|-----------|------|------------------|-------------|
| main | /user/info | `/api/user/info` | `http://your-server-host:8000/user/info` |
| backend | /human | `/backend/human` | `http://your-server-host:8010/human` |
| rag | /v1/rag | `/v1/rag` | `http://your-server-host:8888/v1/rag` |

### buildWsUrl 返回值对比

| serverKey | path | 浏览器环境（开发） | Electron环境 |
|-----------|------|------------------|-------------|
| main | /ws/asr | `ws://localhost:3000/ws/asr` | `ws://your-server-host:8000/ws/asr` |
| llm | /ws/chat | `ws://localhost:3000/llm/ws/chat` | `ws://your-server-host:8011/ws/chat` |

### getPublicUrl 返回值

| 输入 | 输出（所有环境） |
|------|-----------------|
| `/icon.webp` | `./icon.webp` |
| `/chat_bg_model.png` | `./chat_bg_model.png` |
| `logo.png` | `logo.png` |

---

## 六、常见问题 FAQ

### Q1: 什么时候用 buildApiUrl，什么时候用 buildWsUrl？

**A**: 
- HTTP/HTTPS 请求（fetch、axios 等）→ 使用 `buildApiUrl`
- WebSocket 连接（new WebSocket）→ 使用 `buildWsUrl`

### Q2: 为什么浏览器环境和 Electron 环境返回的 URL 不同？

**A**: 
- **浏览器环境**: 使用 Vite 开发服务器，通过代理转发请求到后端，返回相对路径
- **Electron 环境**: 使用 file:// 协议加载本地文件，必须使用完整的 http:// 或 ws:// 地址

### Q3: getPublicUrl 和 getAssetImgUrl 有什么区别？

**A**:
- `getPublicUrl`: 用于 `public/` 目录下的资源（会被复制到 dist 根目录）
- `getAssetImgUrl`: 用于 `src/assets/` 目录下的资源（会被 Vite 处理和打包）

### Q4: 为什么有些 serverKey 的代理前缀是空字符串？

**A**: 
RAG 服务的接口路径本身就是 `/v1/rag`，不需要额外的代理前缀，所以设置为空字符串。

### Q5: 新增域名后是否需要重启开发服务器？

**A**: 
是的，修改 `vite.config.js` 后必须重启开发服务器才能生效。

### Q6: 如何调试代理是否配置正确？

**A**: 
打开浏览器开发者工具 → Network 标签页，查看请求的实际 URL 和状态码：
- 正确: 请求地址为 `/proxy_prefix/path`，状态码 200
- 错误: 请求地址为完整 URL，状态码 CORS 错误

---

## 七、最佳实践建议

1. **统一导入**: 在文件顶部统一导入这些函数
   ```javascript
   import { buildApiUrl, buildWsUrl } from '@/config';
   import { getPublicUrl } from '@/utils/getAssets';
   ```

2. **避免硬编码**: 永远不要在代码中直接写服务器地址
   ```javascript
   // ❌ 错误示例
   fetch('http://your-server-host:8000/api/user')
   
   // ✅ 正确示例
   fetch(buildApiUrl('main', '/api/user'))
   ```

3. **路径必须以 / 开头**: 传给 buildApiUrl 和 buildWsUrl 的 path 参数必须以 `/` 开头
   ```javascript
   // ❌ 错误
   buildApiUrl('main', 'api/user')
   
   // ✅ 正确
   buildApiUrl('main', '/api/user')
   ```

4. **日志调试**: 开发时可以打印 URL 进行调试
   ```javascript
   const url = buildApiUrl('backend', '/human');
   console.log('请求地址:', url);
   ```

5. **类型提示**: 使用 JSDoc 注释提供类型提示
   ```javascript
   /**
    * @param {'main' | 'backend' | 'llm' | 'asr'} serverKey
    * @param {string} path
    */
   function callAPI(serverKey, path) {
     return fetch(buildApiUrl(serverKey, path));
   }
   ```

---

## 八、配置文件清单

新增域名时需要修改的文件：

- [x] `/src/config/index.js` - 添加服务器地址和代理前缀映射
- [x] `/vite.config.js` - 添加开发环境代理配置
- [x] 业务代码 - 使用 buildApiUrl/buildWsUrl 调用新接口

不需要修改的文件：
- `/src/utils/getAssets.js` - 静态资源处理，无需改动
- `/src/utils/request.js` - 请求封装，自动使用 buildApiUrl



src/config/index.js (lines 10-30) 定义了默认的 DEFAULT_BACKEND_CONFIG，这里的 mainServer 及 apiServers 各项就是前端在没有用户自定义配置时使用的后端地址。要永久改动（需要重新构建/部署），直接把这些值替换成新的 ip:port 后重启即可。





---

**文档版本**: v1.0  
**最后更新**: 2025-11-07  
**维护者**: 数字人项目组
