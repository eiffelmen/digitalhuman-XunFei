<script setup>
import { llmSocket, sendMsg } from '@/api/llm.js'
import { onMounted, ref } from 'vue'

const LLMInput = ref('')
const LLMOutput = ref('')
const sendToLLMService = async () => {
  try {
    // clear output
    LLMOutput.value = ''

    await sendMsg(LLMInput.value)
  } catch (error) {
    console.error('error: ', error)
  }
}

const initLLMSocket = () => {
  llmSocket.addEventListener('message', (event) => {
    try {
      const msg = JSON.parse(event.data)
      console.log('llm service Message: ', msg)
      if (typeof msg !== 'object' || msg === null) {
        console.error('Invalid message format.')
        return
      }
      LLMOutput.value += msg.data
    } catch (error) {
      console.error('Error parsing message: ', error)
    }
  })
}
onMounted(() => {
  initLLMSocket()
})
</script>

<template>
  <v-card class="w-100 pa-5" elevation="20">
    <v-card-title>大模型对话测试</v-card-title>
    <v-form @submit.prevent>
      <v-text-field label="输入内容" v-model="LLMInput"></v-text-field>
      <v-btn @click="sendToLLMService" type="submit">发送</v-btn>
    </v-form>
    <v-textarea label="回复内容" v-model="LLMOutput"></v-textarea>
  </v-card>
</template>

<style scoped></style>
