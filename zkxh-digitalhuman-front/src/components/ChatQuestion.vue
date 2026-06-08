<script setup>
import 'recorder-core/src/engine/wav';
import 'recorder-core/src/extensions/waveview';
import { nextTick, onUnmounted, ref, watch } from 'vue';
import { getPublicUrl } from '@/utils/getAssets';
import { buildWsUrl } from '@/config';

const messagebox = ref('');
const chatBox = ref(null);

// WebSocket 实例
let asrWebSocket = null;
let asrFirstTextLogged = false;
let asrEndLogged = false;

function formatTraceTime() {
  const now = new Date();
  const pad = value => String(value).padStart(2, '0');
  const ms = String(now.getMilliseconds()).padStart(3, '0');
  return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())} ${pad(now.getHours())}:${pad(now.getMinutes())}:${pad(now.getSeconds())}.${ms}`;
}

function logFrontendTimepoint(module, event, fields = {}) {
  const detail = Object.entries(fields)
    .filter(([, value]) => value !== undefined && value !== null && value !== '')
    .map(([key, value]) => `${key}=${String(value).replace(/\s+/g, '_')}`)
    .join(' ');
  console.log(`[时间点] 模块=${module} 事件=${event} 时间=${formatTraceTime()}${detail ? ` ${detail}` : ''}`);
}

function resetAsrTraceFlags() {
  asrFirstTextLogged = false;
  asrEndLogged = false;
}

function markAsrFirstText(text, source = 'websocket') {
  if (!text || asrFirstTextLogged) {
    return;
  }
  asrFirstTextLogged = true;
  asrEndLogged = false;
  logFrontendTimepoint('ASR', '收到第一个字', {
    first_char: text.slice(0, 1),
    text_len: text.length,
    source,
  });
}

function markAsrEnd(reason = 'final') {
  if (!asrFirstTextLogged || asrEndLogged) {
    return;
  }
  asrEndLogged = true;
  logFrontendTimepoint('ASR', '结束', { reason });
}

function isFinalAsrMessage(data) {
  return Boolean(
    data?.finish ||
    data?.final ||
    data?.is_final ||
    data?.isFinal ||
    data?.mode === 'offline' ||
    data?.mode === '2pass-offline' ||
    data?.type === 'final'
  );
}

// Android WebView ASR intermediate result handler - 使用事件机制
window.handleAsrIntermediate = (text) => {
  markAsrFirstText(text, 'android');
  window.dispatchEvent(new CustomEvent('asr-intermediate', { detail: text }));
};

// 监听 ASR 中间结果事件
window.addEventListener('asr-intermediate', (e) => {
  messagebox.value = e.detail;
  resetClearMessageTimer();
});

// 倒计时定时器
let clearMessageTimer = null;

/**
 * 重置清空消息的倒计时
 */
function resetClearMessageTimer() {
  // 清除之前的定时器
  if (clearMessageTimer) {
    clearTimeout(clearMessageTimer);
    clearMessageTimer = null;
  }
  
  // 设置新的5秒倒计时
  clearMessageTimer = setTimeout(() => {
    console.log('[倒计时] 5秒内无新消息，清空messagebox');
    markAsrEnd('5秒无新消息');
    messagebox.value = '';
    resetAsrTraceFlags();
    clearMessageTimer = null;
  }, 5000); // 5秒
  
  console.log('[倒计时] 已重置，5秒后清空消息');
}

/**
 * 清除倒计时
 */
function clearTimer() {
  if (clearMessageTimer) {
    clearTimeout(clearMessageTimer);
    clearMessageTimer = null;
    console.log('[倒计时] 已清除');
  }
}

/**
 * 初始化 ASR WebSocket 连接
 */
function initAsrWebSocket() {
  // 每次初始化前先关闭已有连接，防止重复创建
  closeAsrWebSocket();

  const deviceid = localStorage.getItem('deviceid');
  if (!deviceid) {
    console.warn('[ASR WebSocket] deviceid 未初始化，跳过连接');
    return;
  }

  const wsUrl = buildWsUrl('main', '/ws/web?id=' + deviceid);
  
  console.log('[ASR WebSocket] 连接地址:', wsUrl);
  
  try {
    asrWebSocket = new WebSocket(wsUrl);
    
    // 连接成功
    asrWebSocket.addEventListener('open', () => {
      console.log('[ASR WebSocket] 连接成功');
      resetAsrTraceFlags();
    });
    
    // 接收消息
    asrWebSocket.addEventListener('message', (event) => {
      try {
        const data = JSON.parse(event.data);
        console.log('[ASR WebSocket] 收到消息:', data);
        
        // 将 ASR 识别结果放入 messagebox
        if (data.text || data.result) {
          const asrText = data.text || data.result;
          markAsrFirstText(asrText, 'websocket');
          messagebox.value = asrText;
          // 收到消息后重置倒计时
          resetClearMessageTimer();
          if (isFinalAsrMessage(data)) {
            markAsrEnd(data.mode || data.type || 'final');
          }
        }
      } catch (error) {
        console.error('[ASR WebSocket] 解析消息失败:', error);
        // 如果不是 JSON，直接显示
        markAsrFirstText(event.data, 'raw');
        messagebox.value = event.data;
        // 收到消息后重置倒计时
        resetClearMessageTimer();
      }
    });
    
    // 连接关闭
    asrWebSocket.addEventListener('close', () => {
      console.log('[ASR WebSocket] 连接关闭');
      markAsrEnd('websocket关闭');
    });
    
    // 连接错误
    asrWebSocket.addEventListener('error', (error) => {
      console.error('[ASR WebSocket] 连接错误:', error);
    });
  } catch (error) {
    console.error('[ASR WebSocket] 创建失败:', error);
  }
}

let scrollAF = null;
watch(messagebox, () => {
  if (scrollAF) cancelAnimationFrame(scrollAF);
  scrollAF = requestAnimationFrame(() => {
    if (chatBox.value) {
      chatBox.value.scrollTop = chatBox.value.scrollHeight;
    }
  });
});

/**
 * 关闭 WebSocket 连接
 */
function closeAsrWebSocket() {
  // 清除倒计时
  clearTimer();
  
  if (asrWebSocket) {
    asrWebSocket.close();
    asrWebSocket = null;
    console.log('[ASR WebSocket] 已关闭');
  }
}

// 组件卸载时关闭 WebSocket
onUnmounted(() => {
  closeAsrWebSocket();
});

// 暴露方法供父组件调用
defineExpose({
  initAsrWebSocket,
  closeAsrWebSocket,
});

</script>
<template>
	<div class="chat-wrap w-100 h-100 position-relative overflow-hidden" v-show="messagebox.length > 0"
		:style="`background-image: url('${getPublicUrl('/chat_question_bg.png')}');background-repeat: no-repeat; background-position: top center;`">

		<img class="chat-icon" :src="getPublicUrl('/icon.webp')" alt="">
		<div class="chatview">
			<div ref="chatBox" class="message">
				{{ messagebox }}
			</div>
		</div>
	</div>
</template>

<style scoped>
.chat-wrap {
	background-size: 100%;
	display: flex;
	align-items: center;
	padding: 0 50px;
}

.chat-icon {
	width: 164px;
	height: 164px;
}

.chatview {
	-ms-overflow-style: none;
	/* IE and Edge */
	scrollbar-width: none;
	/* Firefox */
	height: 100% !important;
	width: 100%;
	flex: 1;
	align-items: center;
    display: flex;
}

.message {
	width: 100%;
	font-size: 5.25rem;
	color: white;
	padding-left: 50px;
	line-height: 120px;
	white-space: pre-wrap;
	word-break: break-word;
	padding-right: 20px;
	max-height: 240px;
	overflow-y: auto;
}
</style>
