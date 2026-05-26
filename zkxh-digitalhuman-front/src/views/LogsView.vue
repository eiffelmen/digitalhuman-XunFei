<script setup>
import { ref } from 'vue'

const audioInfos = ref([{ text: 'asr结果', time: '00:01:00' }])
const playAudioNow = ref(false)

const playAudio = (index) => { }
const downloadAudio = (index) => { }
const getAudioLogs = async () => { }
</script>

<template>
  <h1>历史记录</h1>
  <v-row no-gutters class="pa-5">
    <v-col cols="12" class="pa-5">
      <v-btn class="bg-yellow-darken-1" @click="getAudioLogs">刷新</v-btn>
    </v-col>
    <v-col cols="12" class="pa-5">
      <audio controls :autoplay="playAudioNow"></audio>
    </v-col>
    <v-col cols="12">
      <v-list>
        <v-list-item v-for="(item, index) in audioInfos" :key="index">
          <div class="d-flex justify-start align-center">
            <v-icon class="mr-2">mdi-file-music-outline</v-icon>
            <v-list-item-title class="mr-5"> {{ item.text }} </v-list-item-title>
            <span class="ma-5">时长: {{ item.time }}</span>
            <v-list-item-action>
              <v-btn @click="playAudio(index)" class="ma-5">播放</v-btn>
              <v-btn @click="downloadAudio(index)" class="ma-5">下载</v-btn>
            </v-list-item-action>
          </div>
        </v-list-item>
        <v-divider />
      </v-list>
    </v-col>
  </v-row>
</template>

<style scoped></style>
