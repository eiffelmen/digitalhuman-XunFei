<script setup>
import Recorder from 'recorder-core'
import 'recorder-core/src/engine/mp3'
import 'recorder-core/src/engine/mp3-engine'
import 'recorder-core/src/engine/pcm'
import 'recorder-core/src/engine/wav'
import { onMounted, onUnmounted, ref } from 'vue'

const recordBtnText = ref('开始录音')
let rec = null
let isRec = true
let wave = null
function start_record() {
  isRec = true
  rec.open(() => {
    rec.start()

    // RealTimeSendTryReset()
    console.log('开始录音')

    // wave = Recorder.WaveView({ elem: '.waveview' })
  })
}
function toggleRecordingState() {
  if (recordBtnText.value === '开始录音') {
    console.log('开始录音')
    // start_record()
    rec.start()
  } else if (recordBtnText.value === '停止录音') {
    console.log('停止录音')
    rec.stop((blob, duration) => {
      var localUrl = (window.URL || webkitURL).createObjectURL(blob)
      console.log(blob, localUrl, '时长:' + duration + 'ms')
      rec.close()

      ASRSocket.send(JSON.stringify({ is_speaking: false }))

      // var audio = document.createElement('audio')
      // document.body.prepend(audio)
      // audio.controls = true
      // audio.src = localUrl
      // audio.play()
    })
  }
  recordBtnText.value = recordBtnText.value === '开始录音' ? '停止录音' : '开始录音'
}
Recorder.PCMMerge = function (fileBytesList, bitRate, sampleRate, True, False) {
  //计算所有文件总长度
  var size = 0
  for (var i = 0; i < fileBytesList.length; i++) {
    size += fileBytesList[i].byteLength
  }

  //全部直接拼接到一起
  var fileBytes = new Uint8Array(size)
  var pos = 0
  for (var i = 0; i < fileBytesList.length; i++) {
    var bytes = fileBytesList[i]
    fileBytes.set(bytes, pos)
    pos += bytes.byteLength
  }

  //计算合并后的总时长
  var duration = Math.round(((size * 8) / bitRate / sampleRate) * 1000)

  True(fileBytes, duration, { bitRate: bitRate, sampleRate: sampleRate })
}
function init_recorder() {
  rec = Recorder({
    type: 'pcm',
    bitRate: 16,
    sampleRate: 16000,
    // onProcess: recProcess
    onProcess: (buffers, powerLevel, bufferDuration, bufferSampleRate) => {
      testProcess(buffers, bufferSampleRate)
    }
  })
}

let ASRSendQueue = []
const chunk_size = 960 // 600ms model input

const testProcess = (buffers, bufferSampleRate) => {
  const oneBuffer = buffers[buffers.length - 1]
  // 将1440个buffer拼接成一个buffer
  const dataArray = new Array(oneBuffer)
  const pcmData = Recorder.SampleData(dataArray, bufferSampleRate, 16000).data
  // console.log(pcmData)
  ASRSendQueue = Int16Array.from([...ASRSendQueue, ...pcmData])
  while (ASRSendQueue.length > chunk_size) {
    const chunk = ASRSendQueue.slice(0, chunk_size)
    ASRSendQueue = ASRSendQueue.slice(chunk_size, ASRSendQueue.length)
    // console.log(chunk)
    ASRSocket.send(chunk)
  }
}

const cache_buffers = []
const test_buffers = []

function recProcess(buffer, powerLevel, bufferDuration, bufferSampleRate, newBufferIdx, asyncEnd) {
  //录音实时回调，大约1秒调用12次本回调，buffers为开始到现在的所有录音pcm数据块(16位小端LE)
  if (isRec === true) {
    test_buffers.push(buffer[buffer.length - 1])
    // 缓存大概1秒音频数据, 检测到开口说话后加上缓存进行asr
    // cache_buffers.push(buffer[buffer.length - 1])
    // if (cache_buffers.length > cache_count) {
    //   cache_buffers.shift()
    // }
    // // console.log(cache_buffers.length)

    // wave.input(buffer[buffer.length - 1], powerLevel, bufferSampleRate)
    // // 说话检测
    // // 说话检测后，一段一段发
    // // powerlevel阈值预计在80左右？
    // // if (
    // //   powerLevel >= 20 ||
    // //   (powerLevel < 20 && Date.now() - record_start_time < after_speak_blank_time)
    // // ) {
    // // if (speaking_flag === false) {
    // if (powerLevel >= 10) {
    //   lastSpeakingTime = Date.now()

    //   // fixme: 这个括号外的东西，应为else 没处理好
    //   if (speaking_flag === false && Date.now() - lastMuteTime > startTime) {
    //     console.debug('run once per asr??')
    //     start_one_asr()
    //     speaking_flag = true
    //     // record_start_time = Date.now()

    //     // 更新ui
    //     videocover_text.value = ''

    //     // 处理缓存
    //     // const tmp_cache_buffers = cache_buffers
    //     // console.log('tmp_cache buffers length:' + tmp_cache_buffers.length)

    //     // let tmp_data_16k = Recorder.SampleData(tmp_cache_buffers, bufferSampleRate, 16000).data

    //     // var tmp_chunk_size = 960 // for asr tmp_chunk_size [5, 10, 5]
    //     // console.log(tmp_data_16k.length + '对比: ' + tmp_chunk_size)
    //     // while (tmp_data_16k.length >= tmp_chunk_size) {
    //     //   const sendBuf = tmp_data_16k.slice(0, tmp_chunk_size)
    //     //   tmp_data_16k = tmp_data_16k.slice(tmp_chunk_size, tmp_data_16k.length)
    //     //   if (asr_streaming_client.readyState === 1) {
    //     //     console.log('sending cache ...', tmp_data_16k.length)
    //     //     asr_streaming_client.send(sendBuf)
    //     //   }
    //     // }
    //     // console.log('send cache done')

    //     // test listen wav
    //     // let pcm = tmp_data_16k.data
    //     // let blob = new Blob([pcm], { type: 'audio/wav' })
    //     // audiosrc.value = URL.createObjectURL(blob)
    //   } else if (speaking_flag === true) {
    //     var data_48k = buffer[buffer.length - 1]
    //     var array_48k = new Array(data_48k)
    //     var data_16k = Recorder.SampleData(array_48k, bufferSampleRate, 16000).data

    //     // sampleBuf = data_16k
    //     console.debug('before: sampleBuf length: ', sampleBuf.length)
    //     sampleBuf = Int16Array.from([...sampleBuf, ...data_16k])
    //     console.debug('after: will send sampleBuf length: ', sampleBuf.length)
    //     // sampleBuf = Int16Array.from([...sampleBuf, ...data_16k])
    //     var chunk_size = 960 // for asr chunk_size [5, 10, 5]

    //     // 大于80开始入队，小于后停止
    //     console.log(powerLevel)

    //     // // 先发缓存
    //     // 再发实时
    //     // todo: add test wav

    //     // console.log('brfore send ready??', asr_streaming_client.readyState)
    //     console.log('??? before ', chunk_size, ' : ', sampleBuf.length)
    //     while (sampleBuf.length >= chunk_size) {
    //       const sendBuf = sampleBuf.slice(0, chunk_size)
    //       console.log(sampleBuf)
    //       sampleBuf = sampleBuf.slice(chunk_size, sampleBuf.length)
    //       console.log(sampleBuf)
    //       if (asr_streaming_client.readyState === 1) {
    //         console.log('sending ...', sendBuf.length)

    //         testlisten.push(sendBuf)
    //         asr_streaming_client.send(sendBuf)
    //       }
    //     }
    //   }
    //   // console.log(' realtime buffer send done. ')
    //   // console.log('ready??', asr_streaming_client.readyState)
    // } else {
    //   console.log('no power ready??', asr_streaming_client.readyState)
    //   lastMuteTime = Date.now()

    //   if (speaking_flag) {
    //     console.debug('vs: ', Date.now(), ' : ', lastSpeakingTime)
    //     if (Date.now() - lastSpeakingTime > releaseTime) {
    //       console.log('???', sampleBuf.length)

    //       asr_streaming_client.send(JSON.stringify({ is_speaking: false }))
    //       console.log('关闭asr')
    //       speaking_flag = false
    //       sampleBuf = []
    //     } else {
    //       console.log('jm???', sampleBuf.length)
    //       console.log('静默时间')
    //       // let data_16k = new Array()
    //       // data_16k.length = 480
    //       // sampleBuf = Int16Array.from([...sampleBuf, ...data_16k])
    //       // let chunk_size = 960 // for asr chunk_size [5, 10, 5]
    //       // while (sampleBuf.length >= chunk_size) {
    //       //   const sendBuf = sampleBuf.slice(0, chunk_size)
    //       //   sampleBuf = sampleBuf.slice(chunk_size, sampleBuf.length)
    //       //   if (asr_streaming_client.readyState === 1) {
    //       //     console.log('sending ...', sendBuf.length)
    //       //     asr_streaming_client.send(sendBuf)
    //       //   }
    //       // }
    //     }
    //   }
    //   // console.log('没有说话')
    // }
  }
}

let ASRSocket = null
const initASRSocket = () => {
  ASRSocket = new WebSocket('ws://localhost:10099')
  ASRSocket.addEventListener('open', () => {
    const firstMsg = {
      mode: '2pass',
      wav_name: 'h5',
      wav_format: 'pcm',
      audio_fs: 16000,
      is_speaking: true,
      chunk_size: [5, 10, 5],
      itn: true
    }
    ASRSocket.send(JSON.stringify(firstMsg))
    console.log('test asr server connected')
  })
  ASRSocket.addEventListener('message', (event) => {
    const msg = JSON.parse(event.data)
    console.log(msg.text)
    console.log('Message from server ', msg)
  })
  ASRSocket.addEventListener('close', () => {
    console.log('test asr server disconnected')
  })
  ASRSocket.addEventListener('error', () => {
    console.log('test asr server error')
  })
}
const getPermission = () => {
  rec.open()
}

let llmSocket = null
const initLLMSocket = () => {
  llmSocket = new WebSocket('ws://localhost:8011/ws/0')
  llmSocket.addEventListener('open', () => {
    console.log('llm server connected')
  })
  llmSocket.addEventListener('message', (event) => {
    const msg = JSON.parse(event.data)
    console.log('Message from server ', msg)
  })
  llmSocket.addEventListener('close', () => {
    console.log('llm server disconnected')
  })
  llmSocket.addEventListener('error', () => {
    console.log('llm server error')
  })
}
const testSendToLLM = () => {
  const msg = '你好，我想咨询北京的旅游路线'
  console.log('send to llm', msg)
  llmSocket.send(JSON.stringify({ text: msg }))
}

const testSendToLLMFetch = () => {
  fetch('http://localhost:8010/human', {
    body: JSON.stringify({
      text: '你好，我想咨询北京的旅游路线',
      type: 'chat',
      interrupt: true,
      // sessionid: parseInt(document.getElementById('sessionid').value)
      sessionid: 0
    }),
    headers: {
      'Content-Type': 'application/json'
    },
    method: 'POST'
  })
    .then((response) => {
      if (response.status === 200) {
        return response.json()
      } else {
        throw new Error('Something went wrong on API server!')
      }
    })
    .then((response) => {
      console.log(response)
    })
    .catch((error) => {
      console.error(error)
    })
}

const testWebrtc = async () => {
  const pc = new RTCPeerConnection()
  pc.addTransceiver('video', { direction: 'recvonly' })
  pc.addTransceiver('audio', { direction: 'recvonly' })
  const offer = await pc.createOffer()
  await pc.setLocalDescription(offer)
  const response = await fetch('http://your-server-host:8010/offer', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      sdp: pc.localDescription.sdp,
      type: pc.localDescription.type
    })
  })
  if (!response.ok) {
    console.log('connect to webrtc error', response.status)
  }
  const answer = await response.json()
  console.log(answer)
}

onMounted(() => {
  // init_recorder()
  // initASRSocket()
  // initLLMSocket()
  // auto start record
  // setTimeout(() => {
  //   toggleRecordingState()
  // }, 5000)
})

onUnmounted(() => {
  // llmSocket.close()
  // ASRSocket.close()
  // rec.close()
})
</script>
<template>
  <div>test page</div>
  <v-container>
    <v-row>
      <v-col cols="12">
        <v-btn @click="getPermission">请求录音权限</v-btn>
        <v-btn @click="toggleRecordingState">{{ recordBtnText }} </v-btn>
      </v-col>
      <v-col>
        <v-btn @click="testSendToLLM">测试发送给llm消息</v-btn>
        <v-btn @click="testSendToLLMFetch">测试发送给llm消息fetch</v-btn>
      </v-col>
      <v-col>
        <v-btn @click="testWebrtc">测试webrtc</v-btn>
      </v-col>
    </v-row>
  </v-container>
  <div>
    <video></video>
  </div>
</template>
<style scoped></style>
