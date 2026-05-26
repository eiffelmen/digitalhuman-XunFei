<script setup>
import { store } from '@/store/store.js'

const sidebarMenu = [
  { title: '数字人', to: '/settings/human' },
  { title: 'RAG配置', to: '/settings/rag' },
  { title: '后端配置', to: '/settings/backend' },
  { title: 'LLM配置', to: '/settings/llm' },
  { title: 'TTS配置', to: '/settings/tts' },
  { title: 'ASR配置', to: '/settings/asr' },
  { title: '其他配置', to: '/settings/others' }
]
</script>

<template>
  <v-navigation-drawer v-model="store.sidebarDrawer">
    <v-list>
      <v-list-item nav rounded="xl" :to="item.to" :href="item.to" v-for="(item, i) in sidebarMenu" :key="i">
        {{ item.title }}
      </v-list-item>
    </v-list>
  </v-navigation-drawer>
</template>

<style scoped></style>
