import OpenAI from 'openai';
import { store } from '@/store/store';
import { buildApiUrl, buildWsUrl } from '@/config';
import { eventBus } from './session';

const llmUrl = '/human';
const HEARTBEAT_INTERVAL = 5000;
const RECONNECT_BASE_DELAY = 1000;
const RECONNECT_MAX_DELAY = 10000;

export const sendMsg = async msg => {
	console.log('sending to llm', msg);
	const options = {
		method: 'POST',
		headers: {
			'Content-Type': 'application/json',
		},
		body: JSON.stringify({
			text: msg,
			type: 'chat',
			interrupt: true,
			sessionid: eventBus.sessionId || 0,
		}),
	};

	try {
		const res = await fetch(buildApiUrl('backend', llmUrl), options);
		console.log(res);
		if (!res.ok) {
			throw new Error(`网络错误: ${res.status} ${res.statusText}`);
		}
		return await res.json();
	} catch (error) {
		console.error('请求失败:', error);
		throw error;
	}
};

let heartbeatInterval = null;
let reconnectTimer = null;
let reconnectAttempts = 0;
let socketGeneration = 0;
let socketSessionId = '';
let desiredSessionId = '';
let manuallyClosed = false;
const messageListeners = new Set();

export let llmSocket = null;

function clearHeartbeat() {
	if (heartbeatInterval !== null) {
		clearInterval(heartbeatInterval);
		heartbeatInterval = null;
	}
}

function clearReconnectTimer() {
	if (reconnectTimer !== null) {
		clearTimeout(reconnectTimer);
		reconnectTimer = null;
	}
}

function isCurrentSocket(socket, generation) {
	return llmSocket === socket && socketGeneration === generation;
}

function startHeartbeat(socket, generation) {
	clearHeartbeat();
	heartbeatInterval = setInterval(() => {
		if (
			isCurrentSocket(socket, generation) &&
			socket.readyState === WebSocket.OPEN
		) {
			socket.send('ping');
		}
	}, HEARTBEAT_INTERVAL);
}

function dispatchMessage(event) {
	for (const listener of messageListeners) {
		try {
			listener(event);
		} catch (error) {
			console.error('处理 LLM WebSocket 消息失败:', error);
		}
	}
}

function scheduleReconnect(reason) {
	if (manuallyClosed || reconnectTimer !== null || !desiredSessionId) {
		return;
	}

	const delay = Math.min(
		RECONNECT_BASE_DELAY * 2 ** Math.min(reconnectAttempts, 4),
		RECONNECT_MAX_DELAY,
	);
	reconnectAttempts += 1;
	console.warn(
		`LLM 文本 WebSocket 将重连 reason=${reason} sessionid=${desiredSessionId} delay_ms=${delay}`,
	);
	reconnectTimer = setTimeout(() => {
		reconnectTimer = null;
		connectLLMSocket(desiredSessionId, { force: true });
	}, delay);
}

function connectLLMSocket(sessionId, { force = false } = {}) {
	const normalizedSessionId = String(sessionId || '').trim();
	if (!normalizedSessionId || normalizedSessionId === '0') {
		console.warn('LLM 文本 WebSocket 缺少有效 sessionid，暂不连接');
		return Promise.resolve('missing-session');
	}

	desiredSessionId = normalizedSessionId;
	manuallyClosed = false;

	if (
		!force &&
		llmSocket &&
		socketSessionId === normalizedSessionId &&
		(llmSocket.readyState === WebSocket.OPEN ||
			llmSocket.readyState === WebSocket.CONNECTING)
	) {
		return Promise.resolve(
			llmSocket.readyState === WebSocket.OPEN ? 'open' : 'connecting',
		);
	}

	clearReconnectTimer();
	clearHeartbeat();
	const generation = ++socketGeneration;
	const previousSocket = llmSocket;
	llmSocket = null;
	socketSessionId = normalizedSessionId;
	if (
		previousSocket &&
		(previousSocket.readyState === WebSocket.OPEN ||
			previousSocket.readyState === WebSocket.CONNECTING)
	) {
		previousSocket.close(1000, 'replace text websocket');
	}

	const llmRecvUrl = buildWsUrl(
		'backend',
		`/ws/${encodeURIComponent(normalizedSessionId)}`,
	);
	console.log('llmRecvUrl:', llmRecvUrl);

	return new Promise(resolve => {
		let settled = false;
		const settle = result => {
			if (!settled) {
				settled = true;
				resolve(result);
			}
		};
		const socket = new WebSocket(llmRecvUrl);
		llmSocket = socket;

		socket.addEventListener('open', () => {
			if (!isCurrentSocket(socket, generation)) {
				socket.close(1000, 'stale text websocket');
				return;
			}
			console.log(`llm service connected sessionid=${normalizedSessionId}`);
			reconnectAttempts = 0;
			store.changLlmStatus(true);
			startHeartbeat(socket, generation);
			settle('open');
		});

		socket.addEventListener('message', event => {
			if (isCurrentSocket(socket, generation)) {
				dispatchMessage(event);
			}
		});

		socket.addEventListener('close', event => {
			if (!isCurrentSocket(socket, generation)) {
				return;
			}
			console.warn(
				`llm service closed sessionid=${normalizedSessionId} code=${event.code}`,
			);
			llmSocket = null;
			clearHeartbeat();
			store.changLlmStatus(false);
			settle('close');
			scheduleReconnect('socket-close');
		});

		socket.addEventListener('error', error => {
			if (!isCurrentSocket(socket, generation)) {
				return;
			}
			console.error('llm service error', error);
			store.changLlmStatus(false);
			settle('error');
		});
	});
}

export function subscribeLLMMessages(listener) {
	if (typeof listener !== 'function') {
		throw new TypeError('LLM WebSocket listener must be a function');
	}
	messageListeners.add(listener);
	return () => messageListeners.delete(listener);
}

export function initLLMSocket(options = {}) {
	return connectLLMSocket(eventBus.sessionId, options);
}

export function closeLLMSocket() {
	manuallyClosed = true;
	desiredSessionId = '';
	clearReconnectTimer();
	clearHeartbeat();
	++socketGeneration;
	const socket = llmSocket;
	llmSocket = null;
	socketSessionId = '';
	store.changLlmStatus(false);
	if (
		socket &&
		(socket.readyState === WebSocket.OPEN ||
			socket.readyState === WebSocket.CONNECTING)
	) {
		socket.close(1000, 'text websocket stopped');
	}
}

export const testOpenAIApi = async () => {
	const openai = new OpenAI({
		baseURL: 'http://localhost:11434/v1',
		apiKey: 'ollama',
		dangerouslyAllowBrowser: true,
	});
	const completion = await openai.chat.completions.create({
		model: 'glm4',
		messages: [{ role: 'user', content: 'Hello!' }],
	});
	console.log(completion.choices[0].message.content);
};
