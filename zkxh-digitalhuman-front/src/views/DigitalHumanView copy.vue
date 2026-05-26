<script setup>
import {
  getInitConfig,
  switchDigitalHumanTemplate,
  updateLoadConfig,
  getSessionId,
} from '@/api'
import CustomDesign from '@/components/CustomDesign.vue'
import DesignBar from '@/components/DesignBar.vue'
import DetailDiv from '@/components/DetailDiv.vue'
import VideoDiv from '@/components/VideoDiv.vue'
import { store } from '@/store/store'
import { getStore, setStore } from '@/utils/store'
import { v4 as uuidv4 } from 'uuid'
import { watch,onMounted, onUnmounted, ref } from 'vue'
import ChatDiv from '../components/ChatDiv.vue'
import { eventBus } from '@/api/session'

const sessionId = ref("")
const showDetail = ref(false)
const showDiv = ref(false)
const videoDivRef = ref(null)
const loading = ref(false)
const designDivRef = ref(null)
const chatRef = ref(null)
const changeType = ref('形象');
const keyDown = (e) => {
  const keyName = e.key
  if (keyName === 'd') {
    showDetail.value = !showDetail.value
    console.log('change detail view')
  }
}
let hasUserGesture = false
const userInteractionEvents = ['click', 'touchstart', 'mousedown', 'keydown']
function handleFirstUserGesture() {
  if (!hasUserGesture) {
    hasUserGesture = true
    initAudioContext()
  }
}
function initAudioContext() {
  if (hasUserGesture) {
    store.changeStartRecord(true)
    // 进行音频相关的初始化操作
    console.log('AudioContext initialized after first user gesture.')
  }
}
function recordChange(type) {
  if (!hasUserGesture) {
    handleFirstUserGesture()
  } else {
    if (type === 'end') {
      store.changeStartRecord(false)
      store.changeAsrStatus(false)
    } else {
      store.changeAsrStatus(true)
      store.changeStartRecord(true)
    }
  }
}
async function changeAvatar(val, type) {
  /*
    type: template 模板切换
    type: timbre 音色切换
    type: image 形象切换
    type: bg 背景切换
  */
  let curConfig = {
    ...getStore({ name: 'digitalDefault' })
  }
  try {
    loading.value = true;
    if (type === 'bg') {
      changeType.value = '背景';
      curConfig.background_image = val.id;
    } else if (type === 'timbre') {
      curConfig.voice_type = val.id;
      changeType.value = '音色';
    } else if (type === 'image') {
      changeType.value = '形象';
      curConfig.digital_human_id = val.id;
    } else { 
      changeType.value = '默认模板';
      curConfig = {
        digital_human_id: val.id,
        voice_type: [1, 3].includes(val.id) ? 2 : 1,
        background_image: val.id,
      }
      if (val.id === 1) {
        curConfig.background_image = 3;
      } else if (val.id === 2) {
        curConfig.background_image = 2;
      } else {
        curConfig.background_image = 1;
      }
    }
    await switchDigitalHumanTemplate({
      ...curConfig,
      sessionid: eventBus.sessionId || 0,
    });
    store.changeDigitalDefault(curConfig);
    loading.value = false;
    let keyObj = {
      'image': 'digital_human_id',
      'timbre': 'voice_type',
      'bg': 'background_image',
    }
    designDivRef.value.changeCurrent(keyObj[type]);
    designDivRef.value.close();
    // videoDivRef.value.start();
    if (type !== 'bg') {
      chatRef.value.resetChat();
    }
  } catch(error) {
    loading.value = false;
  }
}
function showDesignFn() {
  showDiv.value = true;
}
function resetChat() {
  if (!chatRef.value) return;
  chatRef.value.resetChat();
}
function getConig() {
  /* 前端设置唯一id模仿token用户登录 */
  // debugger
  // const sessionId = getStore({name: 'sessionId'}) || 0;
  const sessionId2 = sessionId.value ||0;
  if (!sessionId2) {
    getSessionId().then(res => {
      // setStore({ name: 'sessionId', content: res.sessionid});
      console.log("request to get sessionId", res.sessionid);
      // sessionId.value = res.sessionid;
      eventBus.sessionId = res.sessionid;

      videoDivRef.value.start();
      chatRef.value.initFn();
    })
  } else {
    videoDivRef.value.start();
    chatRef.value.initFn();
  }
}
function designSuccess() {
  showDiv.value = false;
  // videoDivRef.value.start();
  chatRef.value.resetChat();
}
onMounted(() => {
  window.addEventListener('keydown', keyDown)
  const defualtHuman = getStore({ name: 'digitalDefault' });
  if (!defualtHuman) {
    setStore({ name: 'digitalDefault', content: {
      digital_human_id: 1,
      voice_type: 1,
      background_image: 2,
    }})
  }
  getConig()
})

onUnmounted(() => {
  window.removeEventListener('keydown', keyDown)
  sessionId.value = ""
})
</script>

<template>
  <div id="media" class="w-100 h-100 overflow-hidden position-relative d-flex">
    <audio autoplay></audio>
    <div class="h-100 overflow-hidden position-relative left-box-video">
      <VideoDiv ref="videoDivRef" />
      <div class="position-absolute design-bar-row">
        <DesignBar ref="designDivRef" @toDiv="() => showDesignFn()" @changeAvatar="changeAvatar" @deleteFn="resetChat()" />
      </div>
      <v-overlay class="align-center justify-center" :close-on-content-click="false" v-model="loading" contained>
        <span class="loading-tips">{{changeType}}切换中，请稍后...</span>
      </v-overlay>
    </div>
    <div class="position-relative h-100 overflow-hidden right-box-chat">
      <ChatDiv ref="chatRef" @recordChange="(val) => recordChange(val)" :show="false" />
    </div>
    <div class="position-absolute right-0 top-0 bg-black opacity-70" v-if="showDetail">
      <DetailDiv />
    </div>
    <div v-if="showDiv" class="position-fixed right-0 top-0 w-100 h-100">
      <CustomDesign @back="showDiv = false" @success="designSuccess()" />
    </div>
  </div>
</template>

<style scoped>
.left-box-video {
  width: 739px;
}
.right-box-chat {
  width: 1181px;
}
.loading-div {
  white-space: nowrap;
  align-items: center;
  justify-content: center;
  z-index: 999;
  pointer-events: none;
}
.design-bar-row {
  width: 600px;
  bottom: 33px;
  left: 50%;
  transform: translateX(-50%);
}
.loading-tips {
  font-size: 32px;
  font-weight: bold;
}
</style>
