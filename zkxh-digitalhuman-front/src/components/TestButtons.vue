<script setup>
const testLLM = () => {
  fetch('http://localhost:8010/human', {
    body: JSON.stringify({
      text: '你好，我想咨询北京的旅游路线',
      type: 'chat',
      interrupt: true,
      // sessionid: parseInt(document.getElementById('sessionid').value)
      sessionid: getStore({name: 'sessionId'})
    }),
    headers: {
      'Content-Type': 'application/json'
    },
    method: 'POST'
  })
    .then((response) => {
      if (response.status === 200) {
        return response.json()
      } else {
        throw new Error('Something went wrong on API server!')
      }
    })
    .then((response) => {
      console.log(response)
    })
    .catch((error) => {
      console.error(error)
    })
}
</script>
<template>
  <v-btn @click="$router.push('/test')">testPage</v-btn>
  <v-btn @click="testLLM">testllm</v-btn>
  <v-btn @click="$router.push('/settings')">系统设置</v-btn>
</template>
<style scoped></style>
