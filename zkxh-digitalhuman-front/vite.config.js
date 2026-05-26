import { fileURLToPath, URL } from 'node:url';
import { loadEnv } from 'vite';

import viteBasicSslPlugin from '@vitejs/plugin-basic-ssl';
import vue from '@vitejs/plugin-vue';
import postCssPxToRem from 'postcss-pxtorem';
import { defineConfig } from 'vite';

// Electron环境检测
const isElectron = process.env.ELECTRON === 'true' || process.argv.includes('--electron');
// 构建模式检测：如果是构建Electron应用，应使用相对路径
const isBuildingElectron = process.env.npm_lifecycle_event?.includes('electron') || process.env.BUILD_ELECTRON === 'true';

// 加载环境变量
const env = loadEnv('development', process.cwd(), '');

// 后端服务地址配置
const BACKEND_HOST = env.VITE_BACKEND_HOST || 'localhost';
const BACKEND_PORT = env.VITE_BACKEND_PORT || '8010';
const MAIN_API_PORT = env.VITE_MAIN_API_PORT || '8000';
const ASR_WS_PORT = env.VITE_ASR_WS_PORT || '10099';
const RAG_PORT = env.VITE_RAG_PORT || '8888';
const LLM_WS_PORT = env.VITE_LLM_WS_PORT || '8011';

console.log('[Vite Config] BACKEND_PORT:', BACKEND_PORT);

// https://vitejs.dev/config/
export default defineConfig({
	// 根据环境配置base路径
	// Electron 应用必须使用相对路径，因为使用 file:// 协议
	base: isBuildingElectron || isElectron ? './' : '/',
	server: {
		// 开发环境使用 HTTP，不使用 HTTPS
		https: false,
		proxy: {
			'/v1/upload_file': `http://${BACKEND_HOST}:${RAG_PORT}`,

			'/v1/rag': `http://${BACKEND_HOST}:${RAG_PORT}`,
			'/asr': `ws://${BACKEND_HOST}:${ASR_WS_PORT}`,
			'/backend': {
				target: `http://${BACKEND_HOST}:${BACKEND_PORT}`,
				changeOrigin: true,
				ws: true,
				rewrite: path => path.replace(/^\/backend/, ''),
			},
			'/api': {
				target: `http://${BACKEND_HOST}:${MAIN_API_PORT}`,
				changeOrigin: true,
				rewrite: path => path.replace(/^\/api/, ''),
			},
			'/api/ws': {
				target: `http://${BACKEND_HOST}:${MAIN_API_PORT}`,
				ws: true,
				changeOrigin: true,
				rewrite: path => path.replace(/^\/api/, ''),
			},
			'/ws': {
				target: `http://${BACKEND_HOST}:${MAIN_API_PORT}`,
				ws: true,
				changeOrigin: true,
				rewrite: path => path, // 不需要重写
			},
		},
	},
	plugins: [
		vue(),
		// vueDevTools(),
		// viteBasicSslPlugin(),  // 开发环境不使用 HTTPS，禁用 SSL 插件
	],
	resolve: {
		alias: {
			'@': fileURLToPath(new URL('./src', import.meta.url)),
		},
	},
	// Electron构建优化
	build: {
		outDir: 'dist',
		assetsDir: 'assets',
		// Electron 应用必须使用相对路径（file:// 协议下绝对路径无效）
		// 此配置会被上面的 base 配置覆盖，但保留以确保兼容性
		// base: './',  // 已移除，使用顶层 base 配置
		rollupOptions: {
			output: {
				// 确保资源文件使用相对路径
				assetFileNames: 'assets/[name]-[hash][extname]',
				chunkFileNames: 'assets/[name]-[hash].js',
				entryFileNames: 'assets/[name]-[hash].js',
			},
		},
	},
	esbuild: {
		// 开发模式和打包调试时保留console，纯生产环境才移除
		drop: process.env.NODE_ENV === 'production' && !process.env.DEBUG ? ['debugger'] : [],
	},
	css: {
		postcss: {
			plugins: [
				postCssPxToRem({
					rootValue: 14,
					propList: ['*'],
					selectorBlackList: ['html', 'mdi', 'v-'],
					replace: true,
					mediaQuery: false,
					minPixelValue: 0,
				}),
			],
		},
	},
});
