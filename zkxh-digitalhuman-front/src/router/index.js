import { createRouter, createWebHashHistory } from 'vue-router'
import DigitalHumanView from '@/views/DigitalHumanView.vue'
import TestView from '@/views/TestView.vue'
import SettingsView from '@/views/SettingsView.vue'
import LogsView from '@/views/LogsView.vue'
import RagView from '@/views/settings/RagView.vue'
import HumanView from '@/views/settings/HumanView.vue'
import SettingsBackendView from '@/views/settings/SettingsBackendView.vue'
import SettingsLlmView from '@/views/settings/SettingsLlmView.vue'
import SettingsTtsView from '@/views/settings/SettingsTtsView.vue'
import SettingsAsrView from '@/views/settings/SettingsAsrView.vue'
import OthersView from '@/views/settings/OthersView.vue'

const router = createRouter({
  // 使用 hash 模式以支持 Electron 的 file:// 协议
  history: createWebHashHistory(import.meta.env.BASE_URL),
  routes: [
    {
      path: '/',
      name: 'home',
      // component: HomeView
      component: DigitalHumanView
    },
    {
      path: '/test',
      name: 'test',
      // component: HomeView
      component: TestView
    },
    {
      path: '/settings',
      name: 'settings',
      // component: HomeView
      component: SettingsView,
      children: [
        { path: '/', name: '', component: RagView },
        { path: 'rag', name: 'rag', component: RagView },
        { path: 'human', name: 'human', component: HumanView },
        { path: 'backend', name: 'backend', component: SettingsBackendView },
        { path: 'llm', name: 'llm', component: SettingsLlmView },
        { path: 'tts', name: 'tts', component: SettingsTtsView },
        { path: 'asr', name: 'asr', component: SettingsAsrView },
        { path: 'others', name: 'others', component: OthersView }
      ]
    },
    {
      path: '/logs',
      name: 'logs',
      // component: HomeView
      component: LogsView
    },
  ]
})

export default router
