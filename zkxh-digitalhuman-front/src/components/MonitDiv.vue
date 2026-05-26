<script setup>
import { ref } from 'vue'
const imgSrc = ref('/renlian.jpg')
</script>
<template>
  <div id="monitdiv">
    <v-img :src="imgSrc" cover aspect-ratio="1/1" />
  </div>
</template>
<style scoped>
#monitdiv {
  height: 100%;
  width: 100%;
  background-color: black;
}
</style>
