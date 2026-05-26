import { store } from '@/store/store'

let asrSocket = null
const asrUrl = '/asr/'
const getHotWords = () => {
  let hotWords = { 管家: 20 }
  localStorage
    .getItem('wakeUpWords')
    .split('\n')
    .forEach((item) => {
      hotWords[item] = 20
    })
  localStorage
    .getItem('sleepWords')
    .split('\n')
    .forEach((item) => {
      hotWords[item] = 20
    })
  // console.log(hotWords)
  return JSON.stringify(hotWords)
}

let HEARTBEAT_INTERVAL = 5000
let heartbeatInternal

function startHeartbeat() {
  heartbeatInternal = setInterval(() => {
    asrSocket.send('ping')
  }, HEARTBEAT_INTERVAL)
}

const initASRSocket = () => {
  asrSocket = new WebSocket(asrUrl,'binary')
  asrSocket.addEventListener('open', () => {
    // const firstMsg = {
    //   mode: 'offline',
    //   wav_name: 'h5',
    //   wav_format: 'pcm',
    //   audio_fs: 16000,
    //   is_speaking: true,
    //   chunk_size: [5, 10, 5],
    //   hotwords: getHotWords(),
    //   itn: true
    // }
    // asrSocket.send(JSON.stringify(firstMsg))
    // // todo: start, end? should send {is_final:true}?
    // console.log('asr service connected')
    store.changeAsrStatus(true)

    startHeartbeat()
  })
  asrSocket.addEventListener('close', () => {
    console.log('asr service closed')
    store.changeAsrStatus(false)

    clearInterval(heartbeatInternal)
    heartbeatInternal = null
  })
  asrSocket.addEventListener('error', () => {
    console.log('asr service error')
    store.changeAsrStatus(false)

    clearInterval(heartbeatInternal)
    heartbeatInternal = null
  })
}
// initASRSocket()

export { asrSocket }
