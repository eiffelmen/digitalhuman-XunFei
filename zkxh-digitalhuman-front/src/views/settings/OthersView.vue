<script setup>
import { store } from '@/store/store.js'
import { onMounted, ref, watch } from 'vue'

const wakeUpMode = ref(true)

const wakeUpWords = ref('管家\n小助\n')
const sleepWords = ref('退下吧\n再见\n')

watch(wakeUpMode, (now, pre) => {
  console.log('now: ', now)
  setStorageValue()
})

const initStorage = () => {
  localStorage.setItem('inited', 'true')
  localStorage.setItem('wakeUpMode', 'true')
  localStorage.setItem('wakeUpWords', '管家\n小助\n')
  localStorage.setItem('sleepWords', '退下吧\n再见\n')
}

const setStorageValue = () => {
  console.log('setting storage: wakeupmode: ', wakeUpMode.value)
  localStorage.setItem('wakeUpMode', wakeUpMode.value)
}

const getStorageValue = () => {
  if (localStorage.getItem('wakeUpMode') === 'true') {
    wakeUpMode.value = true
  } else {
    wakeUpMode.value = false
  }
  console.log('setting ui: ', wakeUpMode.value)
}

onMounted(() => {
  if (!localStorage.getItem('wakeUpMode')) {
    console.log('init no ')
    // initStorage()
  } else {
    console.log('init yes ')
    getStorageValue()
  }
})
</script>

<template>
  <v-col cols="12">
    <div>
      <v-card class="pa-5" elevation="20">
        <v-card-text
          >后端服务状态:
          <v-chip prepend-icon="$vuetify" color="success" variant="outlined">
            ASR: {{ store.asrStatus ? '在线' : '离线' }}
          </v-chip>
          <v-chip prepend-icon="$vuetify" color="success" variant="outlined">
            LLM: {{ store.llmStatus ? '在线' : '离线' }}
          </v-chip>
        </v-card-text>
      </v-card>
    </div>
  </v-col>
  <v-col cols="12">
    <v-row>
      <v-switch label="唤醒词模式" v-model="wakeUpMode" color="primary"></v-switch>
    </v-row>
    <v-row>
      <v-col cols="3">
        <v-textarea label="唤醒词" v-model="wakeUpWords"></v-textarea>
      </v-col>
      <v-col cols="3">
        <v-textarea label="睡眠词" v-model="sleepWords"></v-textarea>
      </v-col>
      <v-col cols="3">
        <v-textarea label="唤醒提示语"></v-textarea>
      </v-col>
      <v-col cols="3">
        <v-textarea label="睡眠提示语"></v-textarea>
      </v-col>
    </v-row>
  </v-col>
</template>

<style scoped></style>
