<script setup>
import { testOpenAIApi } from '@/api/llm.js'
</script>

<template>
  <div class="text-h2">后端api测试</div>
  <v-col cols="12" class="d-flex flex-wrap ga-10">
    <v-card>
      <v-btn @click="testOpenAIApi()">测试openai api</v-btn>
    </v-card>
    <v-card>
      <v-btn @click="">历史记录</v-btn>
    </v-card>
  </v-col>
</template>

<style scoped></style>
