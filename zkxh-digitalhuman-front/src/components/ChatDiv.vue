<script setup>
import Recorder from 'recorder-core'
import 'recorder-core/src/engine/wav'
import 'recorder-core/src/extensions/waveview'
import { nextTick, onMounted, onUnmounted, ref, watch } from 'vue'

import { asrSocket } from '@/api/asr.js'
import { llmSocket, initLLMSocket as startInitLLMSocket } from '@/api/llm.js'
import { buildApiUrl } from '@/config'
import { store } from '@/store/store'
import { getPublicUrl } from '@/utils/getAssets'
import { getStore } from '@/utils/store'
import { isChinese } from '@/utils/string'
import useMessage from '@/utils/useMessage'
import MessageBox from './chat/MessageBox.vue'
import { v4 as uuidv4 } from "uuid";
import { eventBus } from '@/api/session'

// 高通滤波器实现
Recorder.IIRFilter_DigitalAudio = function (useLowPass, sampleRate, freq) {
  var Q = 1
  var ov = (2 * Math.PI * freq) / sampleRate
  var sn = Math.sin(ov)
  var cs = Math.cos(ov)
  var alpha = sn / (2 * Q)

  var a0 = 1 + alpha
  var a1 = (-2 * cs) / a0
  var a2 = (1 - alpha) / a0
  if (useLowPass) {
    var b0 = (1 - cs) / 2 / a0
    var b1 = (1 - cs) / a0
    var b2 = (1 - cs) / 2 / a0
  } else {
    // eslint-disable-next-line no-redeclare
    var b0 = (1 + cs) / 2 / a0
    // eslint-disable-next-line no-redeclare
    var b1 = -(1 + cs) / a0
    // eslint-disable-next-line no-redeclare
    var b2 = (1 + cs) / 2 / a0
  }

  var x1 = 0,
    x2 = 0,
    y = 0,
    y1 = 0,
    y2 = 0
  return function (x) {
    y = b0 * x + b1 * x1 + b2 * x2 - a1 * y1 - a2 * y2
    x2 = x1
    x1 = x
    y2 = y1
    y1 = y
    return y
  }
}

// chat show buffers
const chatBuffers = ref([])

const props = defineProps({
  // show: {
  //   type: Boolean,
  //   default: true
  // },
  welcomeMsg: {
    // type: String,
    // default: '您好，有什么可以帮助您的？'
    default: { role: 'bot', msg: '您好，有什么可以帮助您的？' }
  },
  question: {
    type: String,
    default: '你好，我想咨询XXX'
    // default: ''
  },
  answer: {
    type: String,
    default: '好的，正在查询XXX'
  },
})

const emits = defineEmits(['recordChange']);
let asrSendCache = new Int16Array(0)
let rec = null

const initRecorder = () => {
  rec = Recorder({
    type: 'pcm',
    // type: 'unknown'  ,
    bitRate: 16,
    sampleRate: 16000,
    onProcess: (buffers, powerLevel, bufferDuration, bufferSampleRate) => {
      processRealtimeAudio(buffers, powerLevel, bufferSampleRate)
    }
  })
  rec.CLog = () => {}
  const chunk_size = 960
  const filter = Recorder.IIRFilter_DigitalAudio(false, 16000, 3000)
  const processRealtimeAudio = (buffers, powerLevel, bufferSampleRate) => {
    // handle waveview
    wave.input(buffers[buffers.length - 1], powerLevel, bufferSampleRate)

    const oneBuffer = new Array(buffers[buffers.length - 1])
    let pcmData = Recorder.SampleData(oneBuffer, bufferSampleRate, 16000).data
    const useFilter = false
    if(useFilter){
      // 高通滤波
      const newPcmData = []
      for (let i = 0; i < pcmData.length; i++) {
        newPcmData[i] = filter(pcmData[i])
      }
      pcmData = newPcmData
    }
    asrSendCache = Int16Array.from([...asrSendCache, ...pcmData])
    while (asrSendCache.length > chunk_size) {
      const chunk = asrSendCache.slice(0, chunk_size)
      asrSendCache = asrSendCache.slice(chunk_size, asrSendCache.length)
      asrSocket.send(chunk)
    }
  }

  rec.open(
    () => {
      wave = Recorder.WaveView({ elem: '#waveview', keep: false })
      // asr服务准备好后，再开始录音
      showWaveView.value = true
    },
    (msg, isUserNotAllow) => {
      console.log((isUserNotAllow ? '用户拒绝' : '') + '无法录音' + msg)
    }
  )
}

watch(
  () => store.startRecord,
  () => {
    // 用户点击后，开始录音
    // 注释了 点击按钮再开始录音
    if (store.startRecord) {
      rec.open(() => {
        rec.start()
      })
    }
  }
)

// asr服务准备好后，再开始录音
watch(
  () => store.asrStatus,
  () => {
    console.log('store.asrStatus状态', store.asrStatus)
    if (store.asrStatus) {
      console.log('asr ready! start rec! asr status changed to ', store.asrStatus)
      // rec.start()
      // showWaveView.value = true
    } else {
      rec.stop()
    }
  }
)

let wave = null

const asrRealtime = ref('')

const initASRSocket = () => {
  asrSocket.addEventListener('message', (event) => {
    console.log('收到的消息asr', event)
    console.log('asr service recv << ', event.data)
    const msg = JSON.parse(event.data)
    console.log(msg)
    // streaming
    if (msg['mode'] === '2pass-online') {
      asrRealtime.value += msg.text
      // 偶发停止说话后，funasr还会发一个online的结果
    } else if (msg['mode'] === '2pass-offline') {
      asrRealtime.value += msg.text
    } else if (msg['mode'] === 'offline') {
      console.log('receiving offline text: '+ msg.text +' : from asr done')
      store.changeAsrStatus(false)
      store.changeStartRecord(false)
      asrRealtime.value = ''
      asrRealtime.value += msg.text
      if (asrRealtime.value) {
        handleUserText(asrRealtime.value)
      } else {
        useMessage({
          message: '时间太短，识别内容无效',
          type: 'warning',
        })
      }
    }
    scrollScreen()
  })
}

const initLLMSocket = () => {
  startInitLLMSocket().then(res => {
    if (res === 'open') {
      let llmReceiving = false
  let oneMsgQueue = []
  const addBlankBox = () => {
    chatBuffers.value.push({ role: 'bot', msg: '' })
  }
  async function handleLLMMessage(msg) {
    // 处理消息
    if (!msg.finish) {
      // 分块接收，入队
      handleChunkedMessage(msg)
    } else {
      // 接收完毕，开始显示
      handleFinishMessage()
    }
  }
  async function handleChunkedMessage(msg) {
    // 逐块接收
    if (chatBuffers.value.length > 0) {
      oneMsgQueue.push(msg.data)
    } else {
      console.error('chatBuffers is empty, cannot update last buffer')
    }
  }
  async function handleFinishMessage() {
    // 接收完毕
    console.info('receiving one llm msg done.')
    llmReceiving = false

    // 开始显示
    const completeMsg = oneMsgQueue.join('')
    oneMsgQueue.length = 0
    await updateLastBuffer(completeMsg)
  }

  const updateLastBuffer = async (msg) => {
    // 中文每120ms显示一个字，英文每50ms显示一个字
    const getCharDelay = (character) =>
      isChinese(character)
        ? new Promise((resolve) => setTimeout(resolve, 120))
        : new Promise((resolve) => setTimeout(resolve, 50))

    const lastBox = chatBuffers.value[chatBuffers.value.length - 1]

    // 1. 伪流式显示
    if (lastBox.role === 'bot') {
      for (let i = 0; i < msg.length; i++) {
        lastBox.msg += msg[i]

        // 输出后等待一段时间，伪流式
        await getCharDelay(msg[i])
        await scrollScreen()
      }
    }

    // 2. 直接显示
    // lastBox.msg += msg
  }

  llmSocket.addEventListener('message', async (event) => {
    try {
      const msg = JSON.parse(event.data)
      console.info("需要输出的文本内容:", msg)

      if (typeof msg !== 'object' || msg === null) {
        console.error('Invalid message format.')
        return
      }

      if (!llmReceiving) {
        // 开始接收消息
        llmReceiving = true
        oneMsgQueue = []
        addBlankBox()
      }

      await handleLLMMessage(msg)
      await scrollScreen()
    } catch (error) {
      console.error('Error parsing message: ', error)
      llmReceiving = false
    }
  })
    }
  })
}

// eslint-disable-next-line no-unused-vars
const testChat = () => {
  // test add msg
  let testflag = true
  setInterval(() => {
    if (testflag) {
      chatBuffers.value.push({
        role: 'user',
        msg: 'hello from user'
      })
    } else {
      chatBuffers.value.push({
        role: 'bot',
        msg: 'hello from bot'
      })
    }
    scrollScreen()
    testflag = !testflag
  }, 1000)
}

// eslint-disable-next-line no-unused-vars
const testLongText = () => {
  chatBuffers.value.push({
    role: 'bot',
    msg: '长长文本长文本长文本长文本长文本长文本长文本长文本长文本长文本长文本长文本长文本长文本长文本长文本长文本长文本长文本长文本长文本长文本长文本长文本长文本长文本文本'
  })
}

const chatBox = ref(null)
const scrollScreen = async () => {
  if (!chatBox.value || !(chatBox.value instanceof HTMLElement)) {
    return
  }
  // 使用 nextTick 来确保在 Vue 完成 DOM 更新后再执行滚动操作。
  await nextTick()
  chatBox.value.scrollTop = chatBox.value.scrollHeight
}

const handleUserText = (msg) => {
  chatBuffers.value.push({ role: 'user', msg: msg })
  // 将asr结果发送给llm
  sendToLLm(msg)

  asrRealtime.value = ''
}

const sendToLLm = async (msg) => {
  console.log('Sending to llm: ', msg)

  const requestConfig = {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({
      text: msg,
      type: 'chat',
      interrupt: true,
      // sessionid: getStore({name: 'sessionId'}) || 0
      sessionid: eventBus.sessionId || 0
      // sessionid: instanceId.value || 0
    })
  }

  // llm
  try {
    const response = await fetch(buildApiUrl('backend', '/human'), requestConfig)
    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`)
    }
    const data = await response.json()
    console.log('Response from LLM:', data)
    return data
  } catch (error) {
    console.error('Error communicating with LLM:', error)
    throw error
  }
}

const recordChange = (type) => {
  if (type === 'end') {
    var chunk_size = new Array( 5, 10, 5 );
		var request = {
			"chunk_size": chunk_size,
			"wav_name": "h5",
			"is_speaking": false,
			"chunk_interval":10,
			"mode":'offline',
      "final": true
		};
    if (asrSendCache.length > 0) {
      asrSocket.send(asrSendCache)
      asrSendCache=new Int16Array(0);
    }
    asrSocket.send(JSON.stringify(request));
  } else {
    const firstMsg = {
      // mode: '2pass',
      mode: 'offline',
      wav_name: 'h5',
      wav_format: 'pcm',
      audio_fs: 16000,
      is_speaking: true,
      chunk_size: [5, 10, 5],
      itn: true,
      final: false
    }
    asrSocket.send(JSON.stringify(firstMsg))
  }
  emits('recordChange', type)
}

const showWaveView = ref(false)
const resetChat = () => {
  chatBuffers.value = [{
    ...props.welcomeMsg
  }]
}
const initFn = () => {
  chatBuffers.value.push(props.welcomeMsg)
  initRecorder()
  initASRSocket()
  initLLMSocket()
}
defineExpose({
  resetChat,
  initFn,
})

onUnmounted(() => {
  rec.close()
  rec = null

  asrSocket.close()
  // LLMSocket.close()
  llmSocket.close()
})

// const instanceId = ref("");
onMounted(() => {
  
  // instanceId.value = uuidv4();
  // console.log("instanceId", instanceId.value);

  // test
  // socketTest()
  // testChat()
  // testUpdateLastBuffer()
  // testLongText()
})
</script>
<template>
  <div class="chat-wrap w-100 h-100 position-relative d-flex flex-column overflow-hidden">
    <div
      ref="chatBox"
      class="chatview w-100 overflow-auto"
      style="flex:1;"
    >
      <v-fade-transition class="bg-transparent" group tag="v-list">
        <v-list-item
          v-for="(message, index) in chatBuffers"
          :key="index"
          :class="{
            'justify-end': message.role === 'user',
            'justify-start': message.role === 'bot'
          }"
          class="d-flex"
          transition="fade-transition"
        >
          <div class="d-flex align-start">
            <MessageBox :message="message"></MessageBox>
          </div>
        </v-list-item>
      </v-fade-transition>
    </div>

    <div
      class="w-100"
      style="padding: 30px 0;"
    >
      <div v-if="store.startRecord" class="text-center text-white">正在拾音中...</div>
      <div @click="recordChange('start')" v-if="!store.startRecord" class="audio-btn ma-auto cursor-pointer d-flex align-center justify-center">
        <img :src="getPublicUrl('/audio_icon.webp')" />开始拾音
      </div>
      <div @click="recordChange('end')" v-else class="audio-btn ma-auto cursor-pointer d-flex align-center justify-center">
        <img :src="getPublicUrl('/audio_icon.webp')" />停止拾音
      </div>
      <div
        id="waveview"
        :style="{ visibility: showWaveView ? '' : 'hidden' }"
        style="height: 100%; width: 100%"
      >
        加载中 ...
      </div>
    </div>
    <!-- <div class="position-absolute w-100 bottom-0 pa-5" style="height: 10%">
      <v-card-text class="d-flex justify-center text-white text-h4">{{ asrRealtime }}</v-card-text>
    </div> -->
  </div>
</template>
<style scoped>
/* .chatview {
  background: rgba(0, 0, 0, 0.1);
} */
.chat-wrap {
  /* background: url('/chat_bg.webp') no-repeat top center; */
  background-color: #005cb1;

  background-size: cover;
}

/* 隐藏滚动条 */
.chatview::-webkit-scrollbar {
  display: none;
}

.chatview {
  -ms-overflow-style: none; /* IE and Edge */
  scrollbar-width: none; /* Firefox */
  padding-top: 78px;
}

.list-move, /* 对移动中的元素应用的过渡 */
.list-enter-active,
.list-leave-active {
  transition: all 0.5s ease;
}

.list-enter-from,
.list-leave-to {
  opacity: 0;
  transform: translateX(30px);
}

/* 确保将离开的元素从布局流中删除
  以便能够正确地计算移动的动画。 */
.list-leave-active {
  position: absolute;
}
#waveview {
  opacity: 0;
  z-index: -111;
  position: absolute;
}
.audio-btn {
  width: 420px;
  height: 80px;
  background: linear-gradient(-20deg, #4B93FF 0%, #3279E3 100%);
  box-shadow: 0px 0px 24px 0px rgba(0,16,127,0.51);
  border-radius: 6px;
  font-weight: 500;
  font-size: 36px;
  color: #FFFFFF;
}
.audio-btn img {
  width: 56px;
  height: 56px;
}
.v-list-item {
  padding: 0;
  margin-bottom: 66px;
}
</style>