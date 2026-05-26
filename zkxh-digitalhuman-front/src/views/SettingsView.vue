<script setup>
import SideBar from '@/components/settings/SideBar.vue'
import { store } from '@/store/store.js'
</script>
<template>
  <v-app>
    <v-app-bar>
      <v-app-bar-nav-icon variant="text"
        @click.stop="store.changeSidebarDrawer(!store.sidebarDrawer)"></v-app-bar-nav-icon>
      <v-toolbar-title> 后台管理 </v-toolbar-title>
    </v-app-bar>
    <SideBar />
    <v-main>
      <RouterView />
    </v-main>
  </v-app>
</template>
<style scoped></style>
