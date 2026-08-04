<script setup>
import 'recorder-core/src/engine/wav';
import 'recorder-core/src/extensions/waveview';
import { computed, nextTick, onMounted, onUnmounted, ref } from 'vue';
import {
	closeLLMSocket,
	initLLMSocket as startInitLLMSocket,
	subscribeLLMMessages,
} from '@/api/llm.js';
import { isChinese } from '@/utils/string';
import { getPublicUrl } from '@/utils/getAssets';
import useInterruptibleStreamText from '@/utils/useInterruptibleStreamText';
import useAvatarSpeechSync from '@/utils/useAvatarSpeechSync';

const showChatLog = ref(false);
// 是否多模态展示
const isMultiModal = ref(false);
const chatBox = ref(null);

async function scrollScreen() {
	if (!chatBox.value || !(chatBox.value instanceof HTMLElement)) {
		return;
	}
	await nextTick();
	chatBox.value.scrollTop = chatBox.value.scrollHeight;
}

const props = defineProps({
	// show: {
	//   type: Boolean,
	//   default: true
	// },
	welcomeMsg: {
		// type: String,
		// default: '您好，有什么可以帮助您的？'
		default: { role: 'bot', msg: '您好，有什么可以帮助您的？' },
	},
	question: {
		type: String,
		default: '你好，我想咨询XXX',
		// default: ''
	},
	answer: {
		type: String,
		default: '好的，正在查询XXX',
	},
});

const emits = defineEmits(['recordChange', 'close']);

function startStandbyTimer() {
	// 当前待机关闭逻辑由上层控制，这里保留暴露接口以避免影响现有调用方。
}

const STATES={
	IDLE:'idle',   // 空闲状态，等待新消息
	PROCESSING:'processing',  // 正在检查数字人是否开口
	OUTPUTTING: 'outputting',  // 正在输出文本内容
	FINISHED: 'finished',  // 消息处理完成
}
const currentState = ref(STATES.IDLE)
const {
	messagebox,
	activeStreamId,
	activeEpoch,
	abortActiveRender,
	ensureAbortController,
	startNewStream,
	enqueueActiveStreamMessage,
	shouldIgnoreMessage,
	hasPendingMessages,
	isReceiveFinished,
	shiftNextMessage,
	updateMessage,
	resetStream,
} = useInterruptibleStreamText({
	isChinese,
	onChunkRendered: scrollScreen,
})
const { waitUntilSilent } = useAvatarSpeechSync();
const messageTextStyle = computed(() => {
	const length = messagebox.value.length;
	if (length <= 24) {
		return { fontSize: '5.25rem' };
	}
	if (length <= 48) {
		return { fontSize: '4rem' };
	}
	if (length <= 80) {
		return { fontSize: '3rem' };
	}
	return { fontSize: '2.25rem' };
});

// 状态转换函数
function transitionTo(newState, eventData = null) {
  console.log(`State transition: ${currentState.value} -> ${newState}`);
 
  // 退出当前状态的清理逻辑
  cleanupCurrentState();
 
  currentState.value = newState;
  
  // 根据新状态执行相应操作
  switch(newState) {
    case STATES.PROCESSING:
      handleProcessingState(eventData);
      break;
    case STATES.OUTPUTTING:
      handleOutputtingState(eventData);
      break;
    case STATES.FINISHED:
      handleFinishedState(eventData);
      break;
  }
}
let stateMachineAbortController = null

async function handleProcessingState(context) {
    console.log("Entering PROCESSING state with data:", context);
	if (!stateMachineAbortController) {
    stateMachineAbortController = ensureAbortController();
  }

	const { epoch, id } = context;
	if (
		stateMachineAbortController &&
		!stateMachineAbortController.signal.aborted &&
		epoch === activeEpoch.value &&
		id === activeStreamId.value
	) {
		transitionTo(STATES.OUTPUTTING, context)
	}
}

async function handleOutputtingState(context) {
  	console.log("Entering OUTPUTTING state with data:", context);
	if (!context) {
		return;
	}
	if (stateMachineAbortController?.signal.aborted) {
		stateMachineAbortController = null;
	}
	if (!stateMachineAbortController) {
		stateMachineAbortController = ensureAbortController();
	}

	const { epoch, id } = context;
  // 在这里处理OUTPUTTING状态的逻辑
    showChatLog.value = true;
	while(
		stateMachineAbortController &&
		!stateMachineAbortController.signal.aborted &&
		epoch === activeEpoch.value &&
		id === activeStreamId.value
	)
	{
			// 队列中无数据，等待
			if(!hasPendingMessages()){
				if (isReceiveFinished()) {
					if (await waitUntilSilent(stateMachineAbortController.signal)){
						console.log("数字人说话完毕，转态到FINISHED")
						transitionTo(STATES.FINISHED, context)
						return
					}
					return
				}
				await new Promise(resolve => setTimeout(resolve, 10));
				continue;
			}
			const currentMsg = shiftNextMessage(id)
			if (!currentMsg) {
				continue
			}
			console.log("开始输出",currentMsg.data)
			await updateMessage(currentMsg.data, stateMachineAbortController.signal);
			// 每次输出完一段，重置超时计时器
			resetFinishedTimeout()
	}
}	

async function handleFinishedState(context) {
  	console.log("Entering FINISHED state with data:", context);
  // 在这里处理FINISHED状态的逻辑
  // 例如，清理资源或准备下一个消息
	stateMachineAbortController = null

	// 重置超时计时器：30秒后隐藏对话框，3分钟后触发close
	resetFinishedTimeout();
}

let closeChatTimeoutId = null;
let sleepTimeoutId = null;

function clearAllTimeouts() {
	console.log("计时清零了，清除所有timeout")
  if (closeChatTimeoutId) {
    clearTimeout(closeChatTimeoutId);
    closeChatTimeoutId = null;
  }
  if (sleepTimeoutId) {
    clearTimeout(sleepTimeoutId);
    sleepTimeoutId = null;
  }
}

function cleanupCurrentState() {
  // 退出当前状态的清理逻辑
	switch (currentState.value) {
	  case STATES.OUTPUTTING:
	  case STATES.PROCESSING:
	      // 中止进行中的操作
	      abortActiveRender();
	      stateMachineAbortController = null;
	      break;
	case STATES.FINISHED:
	      // 清除FINISHED状态的timeout
    //   clearAllTimeouts();
      break;
  }
}

function startInactivityTimeout() {
  console.log("开始5分钟后触发Inacivity事件计时")
  sleepTimeoutId = setTimeout(() => {
    console.log("FINISHED状态超时，触发close事件");
    emits('close');
  }, 5*60*1000); // 5分钟 
//   }, 10*1000); //  10秒
  // }, 180000); // 3分钟 = 180000毫秒
}

function resetFinishedTimeout() {
  clearAllTimeouts();
  
  // 设置新的超时：30秒后隐藏对话框
  closeChatTimeoutId = setTimeout(() => {
    console.log("FINISHED状态超时，隐藏对话框");
    showChatLog.value = false;
    transitionTo(STATES.IDLE);
    startInactivityTimeout();
  }, 30000);
}

function beginMessageStream(msg) {
	// 欢迎语会先本地显示，随后 echo 再从后端返回相同文本。
	// 保留已经显示的内容，避免先清空再逐字重画造成闪烁。
	const preserveVisibleText = Boolean(msg.data) &&
		currentState.value === STATES.FINISHED &&
		messagebox.value === msg.data;
	const context = startNewStream(msg, {
		preserveText: preserveVisibleText,
		enqueueFirst: !preserveVisibleText,
	});

	// startNewStream 已中止上一代内部渲染控制器；同步清掉状态机引用，
	// 避免下一轮继续复用 aborted controller，导致文本框出现但不渲染。
	stateMachineAbortController = null;
	clearAllTimeouts();
	showChatLog.value = true;
	transitionTo(STATES.OUTPUTTING, context);
}

async function handleLLMMessage(event) {
	try {
		const rawMsg = JSON.parse(event.data);
		const streamId = rawMsg?.trace_id || rawMsg?.id;
		const msg = streamId ? { ...rawMsg, id: streamId } : rawMsg;
		console.info('需要输出的文本内容:', msg);

		if (typeof msg !== 'object' || msg === null) {
			console.error('Invalid message format.');
			return;
		}

		if (!msg.id) {
			console.error('Missing message id.');
			return;
		}

		if (shouldIgnoreMessage(msg)) {
			console.log('忽略已失效流消息', msg.id);
			return;
		}

		if (!activeStreamId.value || currentState.value === STATES.IDLE) {
			beginMessageStream(msg);
			return;
		}

		if (msg.id !== activeStreamId.value) {
			beginMessageStream(msg);
			return;
		}

		enqueueActiveStreamMessage(msg);
		resetFinishedTimeout();
	} catch (error) {
		console.error('Error parsing message: ', error);
	}
}

let unsubscribeLLMMessages = null;
const initLLMSocket = async () => {
	// offer 会替换后端会话，强制让文本 WebSocket 接管新一代会话。
	const result = await startInitLLMSocket({ force: true });
	if (result !== 'open') {
		console.warn(`LLM 文本 WebSocket 首次连接结果: ${result}，等待自动重连`);
	}
};

const resetChat = () => {
	clearAllTimeouts();
	resetStream();
	stateMachineAbortController = null;
	currentState.value = STATES.IDLE;
	showChatLog.value = false;
};
const showText = (text) => {
	if (!text) {
		return;
	}

	clearAllTimeouts();
	resetStream();
	stateMachineAbortController = null;
	messagebox.value = text;
	showChatLog.value = true;
	currentState.value = STATES.FINISHED;
	resetFinishedTimeout();
};
const initFn = () => {
	initLLMSocket();
};

defineExpose({
	resetChat,
	showText,
	initFn,
	startStandbyTimer,
});

onUnmounted(() => {
	abortActiveRender();
	clearAllTimeouts();
	if (unsubscribeLLMMessages) {
		unsubscribeLLMMessages();
		unsubscribeLLMMessages = null;
	}
	closeLLMSocket();
});

onMounted(() => {
	unsubscribeLLMMessages = subscribeLLMMessages(handleLLMMessage);
	transitionTo(STATES.IDLE)
});
</script>
<template>
	<div
		class="chat-wrap w-100 h-100 position-relative overflow-hidden"
		v-show="showChatLog"
		:style="`background-image: url('${isMultiModal ? getPublicUrl('/chat_bg_model.png') : getPublicUrl('/chat_bg_new.png')}');background-repeat: no-repeat; background-position: top center;`"
	>
		<div
			ref="chatBox"
			class="chatview w-100 overflow-auto"
			style="flex: 1"
		>
				<div class="message-content" :style="messageTextStyle">
				{{ messagebox }}
				</div>
		</div>
	</div>
</template>

<style scoped>
.chat-wrap {
	background-size: calc(100% - 464px);

	/* padding: 240px; */
	padding-top: 8rem;
	padding-bottom: 330px;
	padding-left: 400px;
	padding-right: 400px;
}

/* 隐藏滚动条 */
.chatview::-webkit-scrollbar {
	display: none;
}

.chatview {
	-ms-overflow-style: none; /* IE and Edge */
	scrollbar-width: none; /* Firefox */
	/* padding-top: 78px; */
	height: 100% !important;
	width: 100%;
}

.message-content {
	width: 100%;
	min-height: 300px;
	color: white;
	line-height: 1.35;
	letter-spacing: 0;
	white-space: pre-wrap;
	word-break: break-word;
	overflow-wrap: anywhere;
}


</style>
