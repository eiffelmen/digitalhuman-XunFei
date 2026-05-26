<script setup>
import { onMounted, ref } from 'vue'
import { buildWsUrl } from '@/config'

const snackbar = ref(false)
const snackbarText = ref('资料上传成功!')

const uploadFile = ref(null)
const ragFiles = ref([])

const uploadFileBtn = async () => {
  console.log(uploadFile.value)
  if (!uploadFile.value) {
    // snackbar.value = true
    // snackbarText.value = '请先选择文件'
    return
  }
  const formData = new FormData()
  formData.append('file', uploadFile.value)
  console.log(formData)
  const response = await fetch(buildWsUrl('llm', '/rag_upload'), {
    method: 'POST',
    headers: { Accept: 'application/json' },
    body: formData
  })

  console.log(response)

  // showSnackbar('文件上传成功')
  getRagFiles()
}
const getRagFiles = async () => {
  const response = await fetch(buildWsUrl('llm', '/rag_file_list'), {
    method: 'GET'
  })

  if (!response.ok) {
    throw new Error(`Response status: ${response.status}`)
  }
  const files = await response.json()
  console.log(files)
  ragFiles.value = files.files
}
const deleteRagFile = async (item) => {
  const response = await fetch(buildWsUrl('llm', '/rag_delete/' + item), {
    method: 'DELETE'
  })

  if (!response.ok) {
    throw new Error(`Response status: ${response.status}`)
  }
  const json = await response.json()
  console.log(json)

  // showSnackbar('删除成功')
  getRagFiles()
}

// watch(uploadFile, (now, pre) => {
//   console.log('now: ', now)
// })

onMounted(() => {
  getRagFiles()
})
</script>

<template>
  <v-snackbar v-model="snackbar">
    {{ snackbarText }}
    <template v-slot:actions>
      <v-btn color="pink" variant="text" @click="snackbar = false"> 关闭</v-btn>
    </template>
  </v-snackbar>
  <div class="text-h2">RAG配置</div>
  <v-card class="pa-5" elevation="20">
    <v-card-title>资料上传</v-card-title>
    <v-card-subtitle> 上传企业自有知识,生成更符合企业场景和需求的内容。 </v-card-subtitle>
    <v-form>
      <v-row class="align-center">
        <v-col cols="10">
          <v-file-input v-model="uploadFile" accept=".pdf" label="上传pdf" />
          <!-- accept=".pdf,.ppt,.word,.txt"
            label="上传pdf/ppt/word文件" -->
        </v-col>
        <v-col cols="2">
          <v-btn @click="uploadFileBtn" color="primary">上传</v-btn>
        </v-col>
      </v-row>
    </v-form>

    <v-list class="border-thin">
      <v-list-subheader>当前已上传资料</v-list-subheader>
      <v-list-item v-for="(item, index) in ragFiles" :key="index"
        >{{ item }}
        <template v-slot:append>
          <v-btn @click="deleteRagFile(item)" class="bg-red">
            <v-icon icon="mdi-delete" start></v-icon>
            删除
          </v-btn>
        </template>
      </v-list-item>
    </v-list>
  </v-card>
</template>

<style scoped></style>
