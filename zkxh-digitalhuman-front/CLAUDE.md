# CLAUDE.md

本文件为 Claude Code (claude.ai/code) 在此代码仓库中工作时提供指导。

## 项目概述

数字人交互系统前端 - 基于 Vue 3 + Vite + Vuetify 构建，支持 Web 和 Electron 双模式部署。提供与数字人 AI 服务的 Web 交互界面，包括语音识别(ASR)、大模型对话(LLM)、语音合成(TTS)和实时音视频交互。

## 常用命令

| 命令 | 说明 |
|------|------|
| `npm run dev` | 启动开发服务器（端口 3000） |
| `npm run build` | 构建生产版本（输出到 dist/） |
| `npm run preview` | 预览生产构建（端口 4174） |
| `npm run lint` | 运行 ESLint 并自动修复 |
| `npm run format` | 使用 Prettier 格式化代码 |
| `npm run build:electron` | 构建 Electron 桌面应用 |

## 技术架构

- **前端框架**: Vue 3 (Composition API)
- **UI 组件库**: Vuetify 3 + Material Design Icons
- **构建工具**: Vite
- **路由**: Vue Router（使用 Hash 模式，以支持 Electron file:// 协议）
- **样式**: PostCSS px-to-rem 转换（rootValue: 14）
- **状态管理**: Vue reactive（无外部 store）

## 项目结构

```
src/
├── api/           # API 客户端（asr.js, llm.js, session.js）
├── assets/        # 静态资源（图片、CSS）
├── components/    # Vue 组件（ChatLog, VideoDiv, MediaDiv 等）
├── views/         # 页面视图
│   ├── DigitalHumanView.vue    # 数字人主页面
│   ├── SettingsView.vue        # 设置页面（含子路由）
│   └── settings/               # 设置子页面（RagView, HumanView 等）
├── router/        # Vue Router 配置
└── utils/         # 工具函数
```

## 后端集成

开发服务器通过 Vite 代理将请求转发到后端服务：

| 路径 | 目标地址 | 用途 |
|------|---------|------|
| `/asr` | WebSocket ws://your-server-host:10099 | 语音识别 |
| `/llm` | WebSocket ws://your-server-host:8011 | 大模型对话 |
| `/api` | http://your-server-host:8000 | REST API |
| `/backend` | http://your-server-host:8010 | 后端服务 |
| `/api_five/six/eight/eleven` | 8085/8086/8088/8011 | 其他 API |

## 部署说明

### Web 部署
1. `npm run build` 构建生产版本
2. 将 dist/ 目录部署到 Nginx
3. Nginx 需要配置 `try_files $uri $uri/ /index.html` 以支持 Vue Router

### Electron 部署
1. `npm run build:electron` 构建 Electron 应用
2. 安装生成的 .deb 包或使用 AppImage

## 注意事项

修改代码的时候，注意最佳实践的同时，绝不要过度设计。