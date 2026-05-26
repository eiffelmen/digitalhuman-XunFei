<script setup>
import { onMounted, ref } from 'vue'
import { buildWsUrl } from '@/config'
import { getPublicUrl } from '@/utils/getAssets'
const allRoles = ref([])

const currentRole = ref({ name: '', image: '' })

function getAllRoles() {
  fetch(buildWsUrl('llm', '/imagelist'))
    .then((response) => {
      return response.json()
    })
    .then((data) => {
      console.log(data)
      allRoles.value = data
    })
}

function getCurrentRole() {
  fetch(buildWsUrl('llm', '/image'))
    .then((response) => {
      return response.json()
    })
    .then((data) => {
      console.log(data)
      currentRole.value.name = data.name
      currentRole.value.image = data.image
    })
}

function base64View(base64Str) {
  return `data:image/png;base64,${base64Str}`
}

function getRoloPreview(roleName) {
  console.log('getRoloPreview: ', roleName)
  fetch(buildWsUrl('llm', '/imageget?name=' + roleName))
    .then((response) => {
      return response.json()
    })
    .then((data) => {
      console.log(data)
      currentRole.value.name = data.name
      currentRole.value.image = data.image
    })
}

function saveConfigs() {
  fetch(buildWsUrl('llm', '/updatecurrentimage'), {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({
      name: currentRole.value.name
    })
  })
    .then((response) => {
      return response.json()
    })
    .then((data) => {
      console.log(data)
    })
}

onMounted(() => {
  getAllRoles()
  getCurrentRole()
})
</script>

<template>
  <div class="pa-12">
    <v-row>
      <v-col cols="6">
        <!-- <v-img :src="getPublicUrl('/poster.png')"></v-img> -->
        <v-img :src="base64View(currentRole.image)"></v-img>
      </v-col>
      <v-col cols="6">
        <v-select v-model="currentRole.name" label="角色选择" :items="allRoles"
          @update:model-value="getRoloPreview"></v-select>
        <v-spacer class="h-25"></v-spacer>
        <v-img class="w-33" :src="getPublicUrl('/renlian.jpg')"></v-img>
        <v-select label="头像选择" :items="['male', 'female']"></v-select>
        <v-spacer class="h-25"></v-spacer>
        <div>背景</div>
        <div>位置</div>
        <div>挂件</div>
        <v-btn variant="elevated" color="primary" @click="saveConfigs()">保存</v-btn>
      </v-col>
    </v-row>
  </div>
</template>

<style scoped></style>
