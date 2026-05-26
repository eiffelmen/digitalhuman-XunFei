<script setup>
import { RouterView } from "vue-router";

import { onMounted, onUnmounted } from "vue";

const initStorage = () => {
  localStorage.setItem("inited", "true");
  localStorage.setItem("wakeUpMode", "true");
  localStorage.setItem("wakeUpWords", "管家\n小助\n");
  localStorage.setItem("sleepWords", "退下吧\n再见\n");
};


onMounted(() => {
  if (localStorage.getItem("inited") !== "true") {
    initStorage();
    console.log("init");
  } else {
    console.log("no init");
  }
});

onUnmounted(() => {});
</script>

<template>
  <RouterView />
</template>

<style scoped></style>
