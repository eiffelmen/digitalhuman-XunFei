<script setup>
import Recorder from 'recorder-core'
import 'recorder-core/src/engine/wav'
const recordBtnText = ref('开始录音')
const videocover_text = ref('你好,我想咨询XXX')

const audiosrc = ref('')
let rec = null
let isRec = true
let asr_streaming_client = null

function init_llm_streaming_client() {
  asr_streaming_client = new WebSocket(asr_streaming_server_url)
  asr_streaming_client.onmessage = (jsonMsg) => {
    // asr 2pass 模型，先流式显示，一段处理完成后再返回完整的文本

    const msg = JSON.parse(jsonMsg.data)
    // console.log('message: ' + JSON.parse(jsonMsg.data)['text'])
    // console.log('is final: ' + JSON.parse(jsonMsg.data)['is_final'])
    console.log(JSON.parse(jsonMsg.data))
    if (msg['mode'] === '2pass-online') {
      videocover_text.value = videocover_text.value + msg['text']
    } else if (msg['mode'] === '2pass-offline') {
      // 第一个字符可能是上一句的最后的标点，目前2pass模型没有解决这个问题
      // https://github.com/modelscope/FunASR/issues/1095
      // 直接去掉第一个标点
      if (
        msg['text'][0] === '。' ||
        msg['text'][0] === '！' ||
        msg['text'][0] === '，' ||
        msg['text'][0] === '？' ||
        msg['text'][0] === '、'
      ) {
        msg['text'] = msg['text'].slice(1)
      }
      videocover_text.value = msg['text']

      // 将asr结果发送给llm
      llm_client_humanchat.send(msg['text'])
    }
  }
  asr_streaming_client.onopen = () => {
    // var chunk_size = new Array(5, 10, 5)
    // var request = {
    //   chunk_size: chunk_size,
    //   wav_name: 'h5',
    //   is_speaking: true,
    //   chunk_interval: 10,
    //   itn: 'false',
    //   mode: '2pass'
    // }

    // llm_streaming_client.send(JSON.stringify(request))
    console.log('llm streaming service connected')
  }
  asr_streaming_client.onclose = () => {
    console.log('llm streaming service disconnected')
  }
  asr_streaming_client.onerror = () => {
    console.log('llm streaming service error')
  }
}
function init_recorder() {
  rec = Recorder({
    type: 'pcm',
    bitRate: 16,
    sampleRate: 16000,
    onProcess: recProcess
    // onProgress: function (buffers, powerLevel, bufferDuration, bufferSampleRate) {
    //   RealTimeSendTry(buffers, bufferSampleRate, false)
    // }
  })
}

function start_record() {
  isRec = true
  rec.open(() => {
    rec.start()

    // RealTimeSendTryReset()
    console.log('开始录音')
  })
}

function start_one_asr() {
  var chunk_size2 = new Array(5, 10, 5)
  var request = {
    chunk_size: chunk_size2,
    wav_name: 'h5',
    is_speaking: true,
    wav_format: 'pcm',
    chunk_interval: 10,
    itn: 'true',
    mode: '2pass'
  }

  asr_streaming_client.send(JSON.stringify(request))
}
var sampleBuf = new Int16Array()

// 缓存一秒历史录音
const cache_buffers = []

const cache_count = 5

let record_start_time = 0

let speaking_flag = false

// 2秒内没有再说话，判断为一整句
const after_speak_blank_time = 2000

var testSampleRate = 16000
var testBitRate = 16

var SendFrameSize = 960

var realTimeSendTryNumber
var transferUploadNumberMax
var realTimeSendTryChunk
var realTimeSendTryChunks

var realTimeChunkSize = 960

const RealTimeSendTryReset = () => {
  realTimeSendTryChunks = null
}
const RealTimeSendTry = (buffers, bufferSampleRate, isClose) => {
  if (realTimeSendTryChunks == null) {
    realTimeSendTryNumber = 0
    transferUploadNumberMax = 0
    realTimeSendTryChunk = null
    realTimeSendTryChunks = []
  }

  var pcm = []
  var pcmSampleRate = 0
  if (buffers.length > 0) {
    var chunk = Recorder.SampleData(buffers, bufferSampleRate, testSampleRate, realTimeSendTryChunk)
    for (var i = realTimeSendTryChunk ? realTimeSendTryChunk.index : 0; i < chunk.index; i++) {
      buffers[i] = null
    }
    realTimeSendTryChunk = chunk
    pcm = chunk.data
    pcmSampleRate = chunk.sampleRate
    if (pcmSampleRate != testSampleRate)
      //除非是onProcess给的bufferSampleRate低于testSampleRate
      throw new Error(
        '不应该出现pcm采样率' + pcmSampleRate + '和需要的采样率' + testSampleRate + '不一致'
      )
  }
  if (pcm.length > 0) {
    realTimeSendTryChunks.push({ pcm: pcm, pcmSampleRate: pcmSampleRate })
  }
  pcm = new Int16Array(realTimeChunkSize)
  pcmSampleRate = 0
  var pcmOK = false
  var pcmLen = 0
  for1: for (var i1 = 0; i1 < realTimeSendTryChunks.length; i1++) {
    var chunk = realTimeSendTryChunks[i1]
    pcmSampleRate = chunk.pcmSampleRate

    for (var i2 = chunk.offset || 0; i2 < chunk.pcm.length; i2++) {
      pcm[pcmLen] = chunk.pcm[i2]
      pcmLen++

      //满一帧了，清除已消费掉的缓冲
      if (pcmLen == chunkSize) {
        pcmOK = true
        chunk.offset = i2 + 1
        for (var i3 = 0; i3 < i1; i3++) {
          realTimeSendTryChunks.splice(0, 1)
        }
        break for1
      }
    }
  }
  //缓冲的数据不够一帧时，不发送 或者 是结束了
  if (!pcmOK) {
    if (isClose) {
      var number = ++realTimeSendTryNumber
      TransferUpload(number, null, 0, null, isClose)
    }
    return
  }
}
let lastSpeakingTime = 0
let lastMuteTime = 0

const startTime = 20
const releaseTime = 750

const testlisten = []

function recProcess(buffer, powerLevel, bufferDuration, bufferSampleRate, newBufferIdx, asyncEnd) {
  //录音实时回调，大约1秒调用12次本回调，buffers为开始到现在的所有录音pcm数据块(16位小端LE)
  if (isRec === true) {
    // 缓存大概1秒音频数据, 检测到开口说话后加上缓存进行asr
    cache_buffers.push(buffer[buffer.length - 1])
    if (cache_buffers.length > cache_count) {
      cache_buffers.shift()
    }
    // console.log(cache_buffers.length)

    // 说话检测
    // 说话检测后，一段一段发
    // powerlevel阈值预计在80左右？
    // if (
    //   powerLevel >= 20 ||
    //   (powerLevel < 20 && Date.now() - record_start_time < after_speak_blank_time)
    // ) {
    // if (speaking_flag === false) {
    if (powerLevel >= 10) {
      lastSpeakingTime = Date.now()

      // fixme: 这个括号外的东西，应为else 没处理好
      if (speaking_flag === false && Date.now() - lastMuteTime > startTime) {
        console.debug('run once per asr??')
        start_one_asr()
        speaking_flag = true
        // record_start_time = Date.now()

        // 更新ui
        videocover_text.value = ''

        // 处理缓存
        // const tmp_cache_buffers = cache_buffers
        // console.log('tmp_cache buffers length:' + tmp_cache_buffers.length)

        // let tmp_data_16k = Recorder.SampleData(tmp_cache_buffers, bufferSampleRate, 16000).data

        // var tmp_chunk_size = 960 // for asr tmp_chunk_size [5, 10, 5]
        // console.log(tmp_data_16k.length + '对比: ' + tmp_chunk_size)
        // while (tmp_data_16k.length >= tmp_chunk_size) {
        //   const sendBuf = tmp_data_16k.slice(0, tmp_chunk_size)
        //   tmp_data_16k = tmp_data_16k.slice(tmp_chunk_size, tmp_data_16k.length)
        //   if (asr_streaming_client.readyState === 1) {
        //     console.log('sending cache ...', tmp_data_16k.length)
        //     asr_streaming_client.send(sendBuf)
        //   }
        // }
        // console.log('send cache done')

        // test listen wav
        // let pcm = tmp_data_16k.data
        // let blob = new Blob([pcm], { type: 'audio/wav' })
        // audiosrc.value = URL.createObjectURL(blob)
      } else if (speaking_flag === true) {
        var data_48k = buffer[buffer.length - 1]
        var array_48k = new Array(data_48k)
        var data_16k = Recorder.SampleData(array_48k, bufferSampleRate, 16000).data

        // sampleBuf = data_16k
        console.debug('before: sampleBuf length: ', sampleBuf.length)
        sampleBuf = Int16Array.from([...sampleBuf, ...data_16k])
        console.debug('after: will send sampleBuf length: ', sampleBuf.length)
        // sampleBuf = Int16Array.from([...sampleBuf, ...data_16k])
        var chunk_size = 960 // for asr chunk_size [5, 10, 5]

        // 大于80开始入队，小于后停止
        console.log(powerLevel)

        // // 先发缓存
        // 再发实时
        // todo: add test wav

        // console.log('brfore send ready??', asr_streaming_client.readyState)
        console.log('??? before ', chunk_size, ' : ', sampleBuf.length)
        while (sampleBuf.length >= chunk_size) {
          const sendBuf = sampleBuf.slice(0, chunk_size)
          console.log(sampleBuf)
          sampleBuf = sampleBuf.slice(chunk_size, sampleBuf.length)
          console.log(sampleBuf)
          if (asr_streaming_client.readyState === 1) {
            console.log('sending ...', sendBuf.length)

            testlisten.push(sendBuf)
            asr_streaming_client.send(sendBuf)
          }
        }
      }
      // console.log(' realtime buffer send done. ')
      // console.log('ready??', asr_streaming_client.readyState)
    } else {
      console.log('no power ready??', asr_streaming_client.readyState)
      lastMuteTime = Date.now()

      if (speaking_flag) {
        console.debug('vs: ', Date.now(), ' : ', lastSpeakingTime)
        if (Date.now() - lastSpeakingTime > releaseTime) {
          console.log('???', sampleBuf.length)

          asr_streaming_client.send(JSON.stringify({ is_speaking: false }))
          console.log('关闭asr')
          speaking_flag = false
          sampleBuf = []
        } else {
          console.log('jm???', sampleBuf.length)
          console.log('静默时间')
          // let data_16k = new Array()
          // data_16k.length = 480
          // sampleBuf = Int16Array.from([...sampleBuf, ...data_16k])
          // let chunk_size = 960 // for asr chunk_size [5, 10, 5]
          // while (sampleBuf.length >= chunk_size) {
          //   const sendBuf = sampleBuf.slice(0, chunk_size)
          //   sampleBuf = sampleBuf.slice(chunk_size, sampleBuf.length)
          //   if (asr_streaming_client.readyState === 1) {
          //     console.log('sending ...', sendBuf.length)
          //     asr_streaming_client.send(sendBuf)
          //   }
          // }
        }
      }
      // console.log('没有说话')
    }
  }
}
function toggleRecordingState() {
  if (recordBtnText.value === '开始录音') {
    console.log('开始录音')
    // asr_client.send({ action: 'start_recording' })

    start_record()
  } else if (recordBtnText.value === '停止录音') {
    console.log('停止录音')
    // asr_client.send({ action: 'stop_recording' })

    isRec = false
    rec.close()
  }
  recordBtnText.value = recordBtnText.value === '开始录音' ? '停止录音' : '开始录音'
}
</script>

<template>
  <v-btn id="toggle_voice" @click="toggleRecordingState">{{ recordBtnText }}</v-btn>

  <form id="echo-form-disable" style="
      margin-right: 10px;
      font-family: Arial, sans-serif;
      font-size: 14px;
      color: #111;
      font-weight: bold;
    ">
    <label for="output" style="margin-right: 10px; white-space: nowrap">语音内容：</label>
    <v-textarea id="output" placeholder="" readonly v-model="output" style="flex-grow: 1; max-width: 100%"></v-textarea>
  </form>

  <form id="echo-form">
    <v-textarea id="message" placeholder="请输入文字内容：" v-model="userInput"></v-textarea>
    <v-btn @click="handleSubmit">发送</v-btn>
  </form>
  <div class="button-container">
    <v-btn id="start" @click="start">推流启动</v-btn>
    <v-btn id="stop" @click="stop">推流停止</v-btn>
  </div>
</template>
