import { store } from '@/store/store';
import { getStore } from '@/utils/store';
import { buildApiUrl,buildWsUrl } from '@/config';

const llmUrl = '/human'

export const sendMsg = async (msg) => {
  console.log('sending to llm', msg)
  const options = {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({
      text: msg,
      type: 'chat',
      interrupt: true,
      sessionid: eventBus.sessionId || 0,
    })
  }

  try {
    const res = await fetch(buildApiUrl('backend', llmUrl), options)
    console.log(res)
    if (!res.ok) {
      throw new Error(`网络错误: ${res.status} ${res.statusText}`)
    }
    return await res.json()
  } catch (error) {
    console.error('请求失败:', error)
    throw error
  }
}

let heartbeatInternal
const HEARTBEAT_INTERVAL = 5000
function startHeartbeat() {
  heartbeatInternal = setInterval(() => {
    llmSocket.send('ping')
  }, HEARTBEAT_INTERVAL)
}
let llmSocket = null
const initLLMSocket = () => {
  // ! 注意这里必须构建完整的WebSocket URL，否则Android webview 中无法访问相对URL路径
  const llmRecvUrl = buildWsUrl('backend', `/ws/${eventBus.sessionId || 0}`);
  console.log('llmRecvUrl: ', llmRecvUrl)
  return new Promise((resolve, reject) => {
    llmSocket = new WebSocket(llmRecvUrl)
    llmSocket.addEventListener('open', () => {
      console.log('llm service connected')
      store.changLlmStatus(true)
      resolve('open')
      startHeartbeat()
    })
    llmSocket.addEventListener('close', () => {
      console.log('llm service closed')
      store.changLlmStatus(false)
      resolve('close')
      clearInterval(heartbeatInternal)
      heartbeatInternal = null
    })
    llmSocket.addEventListener('error', (error) => {
      console.log('llm service error')
      store.changLlmStatus(false)
      clearInterval(heartbeatInternal)
      heartbeatInternal = null
      reject(error)
    })
  })
}

import OpenAI from 'openai';
import { eventBus } from './session';

export const testOpenAIApi = async () => {
  const openai = new OpenAI({
    baseURL: 'http://localhost:11434/v1',
    apiKey: 'ollama',
    dangerouslyAllowBrowser: true
  })
  const completion = await openai.chat.completions.create({
    model: 'glm4',
    messages: [{ role: 'user', content: 'Hello!' }]
  })
  console.log(completion.choices[0].message.content)
}

// initLLMSocket()

export { llmSocket, initLLMSocket };
