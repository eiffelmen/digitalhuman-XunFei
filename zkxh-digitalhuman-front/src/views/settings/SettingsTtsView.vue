<script setup></script>

<template>
  <v-col cols="12" class="pa-2">
    <div class="text-h2">
      TTS配置
      <v-card class="pa-5" elevation="20">
        <v-select
          class="w-50"
          label="模型选择"
          variant="outlined"
          :items="['EdgeTTS', 'GPT-Sovits', 'CosyVoice']"
        ></v-select>
      </v-card>
    </div>
  </v-col>
</template>

<style scoped></style>
