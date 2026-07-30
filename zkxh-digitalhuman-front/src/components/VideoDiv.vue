<script setup>
import { eventBus } from '@/api/session';
import { store } from '@/store/store';
import { nextTick, onMounted, onUnmounted, ref, defineEmits } from 'vue';
import { buildApiUrl, buildWsUrl } from '@/config';
import { getPublicUrl } from '@/utils/getAssets';

const RECONNECT_BASE_DELAY_MS = 1000;
const RECONNECT_MAX_DELAY_MS = 30000;
const DISCONNECTED_GRACE_MS = 4000;
const ICE_GATHERING_TIMEOUT_MS = 10000;
const CONNECTION_TIMEOUT_MS = 60000;
const FRAME_WATCHDOG_INTERVAL_MS = 3000;
const FRAME_STALL_TIMEOUT_MS = 12000;

let pc = null;
let webFirstFrameLogged = false;
let connectionGeneration = 0;
let connectingGeneration = null;
let reconnectAttempts = 0;
let reconnectTimer = null;
let disconnectedTimer = null;
let connectionTimeoutTimer = null;
let offerAbortController = null;
let frameWatchdogTimer = null;
let videoFrameCallbackId = null;
let monitoredVideoElement = null;
let lastVideoFrameAt = 0;
let lastVideoCurrentTime = -1;
let lifecycleStopped = true;
let networkAvailable = typeof navigator === 'undefined' || navigator.onLine !== false;

defineExpose({
	getPoster,
	start,
	startPlayVideo,
	reconnect: requestReconnect,
	setNetworkAvailable,
});

const emit = defineEmits(['offerSuccess', 'videoReady']);

function startPlayVideo() {
	const videoElem = document.getElementById('video');
	if (!videoElem) {
		return;
	}
	videoElem.play().catch(error => {
		console.error('Error playing video:', error);
	});
	videoElem.muted = false;
}

const loading = ref(true);
const poster = ref('');

function formatTraceTime() {
	const now = new Date();
	const pad = value => String(value).padStart(2, '0');
	const ms = String(now.getMilliseconds()).padStart(3, '0');
	return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())} ${pad(now.getHours())}:${pad(now.getMinutes())}:${pad(now.getSeconds())}.${ms}`;
}

function logFrontendTimepoint(module, event, fields = {}) {
	const detail = Object.entries(fields)
		.filter(([, value]) => value !== undefined && value !== null && value !== '')
		.map(([key, value]) => `${key}=${String(value).replace(/\s+/g, '_')}`)
		.join(' ');
	console.log(`[时间点] 模块=${module} 事件=${event} 时间=${formatTraceTime()}${detail ? ` ${detail}` : ''}`);
}

function logWebFirstFrame(videoElem) {
	if (!videoElem || webFirstFrameLogged) {
		return;
	}

	webFirstFrameLogged = true;
	logFrontendTimepoint('Web', '显示第一帧', {
		sessionid: eventBus.sessionId,
		video_width: videoElem.videoWidth,
		video_height: videoElem.videoHeight,
		ready_state: videoElem.readyState,
	});
}

function isActiveConnection(targetPc, generation) {
	return (
		!lifecycleStopped &&
		targetPc === pc &&
		generation === connectionGeneration
	);
}

function isPeerConnected(targetPc) {
	return (
		targetPc?.connectionState === 'connected' ||
		targetPc?.iceConnectionState === 'connected' ||
		targetPc?.iceConnectionState === 'completed'
	);
}

function isPeerUnhealthy(targetPc) {
	if (!targetPc) {
		return true;
	}
	return (
		['failed', 'closed', 'disconnected'].includes(targetPc.connectionState) ||
		['failed', 'closed', 'disconnected'].includes(
			targetPc.iceConnectionState,
		)
	);
}

function clearReconnectTimer() {
	if (reconnectTimer !== null) {
		clearTimeout(reconnectTimer);
		reconnectTimer = null;
	}
}

function clearDisconnectedTimer() {
	if (disconnectedTimer !== null) {
		clearTimeout(disconnectedTimer);
		disconnectedTimer = null;
	}
}

function clearConnectionTimeout() {
	if (connectionTimeoutTimer !== null) {
		clearTimeout(connectionTimeoutTimer);
		connectionTimeoutTimer = null;
	}
}

function stopVideoFrameMonitor() {
	if (
		monitoredVideoElement &&
		videoFrameCallbackId !== null &&
		typeof monitoredVideoElement.cancelVideoFrameCallback === 'function'
	) {
		try {
			monitoredVideoElement.cancelVideoFrameCallback(videoFrameCallbackId);
		} catch (error) {
			console.debug('取消视频帧回调失败:', error);
		}
	}
	if (frameWatchdogTimer !== null) {
		clearInterval(frameWatchdogTimer);
		frameWatchdogTimer = null;
	}
	videoFrameCallbackId = null;
	monitoredVideoElement = null;
	lastVideoFrameAt = 0;
	lastVideoCurrentTime = -1;
}

function detachMediaElement(elementId) {
	const mediaElement = document.getElementById(elementId);
	if (!mediaElement) {
		return;
	}
	mediaElement.onloadedmetadata = null;
	mediaElement.onplaying = null;
	const stream = mediaElement.srcObject;
	mediaElement.srcObject = null;
	if (stream && typeof stream.getTracks === 'function') {
		stream.getTracks().forEach(track => {
			try {
				track.stop();
			} catch (error) {
				console.debug(`停止 ${elementId} 轨道失败:`, error);
			}
		});
	}
}

function closeCurrentPeerConnection() {
	stopVideoFrameMonitor();
	clearDisconnectedTimer();
	clearConnectionTimeout();

	if (offerAbortController) {
		offerAbortController.abort();
		offerAbortController = null;
	}

	const currentPc = pc;
	pc = null;
	detachMediaElement('video');
	detachMediaElement('audio');

	if (currentPc) {
		try {
			currentPc.close();
		} catch (error) {
			console.warn('关闭旧 WebRTC 连接失败:', error);
		}
	}
}

function markVideoFrame(videoElem, targetPc, generation) {
	if (!isActiveConnection(targetPc, generation)) {
		return;
	}

	lastVideoFrameAt = Date.now();
	lastVideoCurrentTime = videoElem.currentTime;
	reconnectAttempts = 0;
	loading.value = false;
	store.changeWebrtcStatus(true);

	if (!webFirstFrameLogged) {
		logWebFirstFrame(videoElem);
		emit('videoReady', true);
	}
}

function startVideoFrameMonitor(videoElem, targetPc, generation) {
	stopVideoFrameMonitor();
	monitoredVideoElement = videoElem;
	lastVideoFrameAt = Date.now();
	lastVideoCurrentTime = videoElem.currentTime;

	if (typeof videoElem.requestVideoFrameCallback === 'function') {
		const onVideoFrame = () => {
			if (!isActiveConnection(targetPc, generation)) {
				return;
			}
			markVideoFrame(videoElem, targetPc, generation);
			videoFrameCallbackId = videoElem.requestVideoFrameCallback(onVideoFrame);
		};
		videoFrameCallbackId = videoElem.requestVideoFrameCallback(onVideoFrame);
	}

	frameWatchdogTimer = setInterval(() => {
		if (
			!isActiveConnection(targetPc, generation) ||
			document.hidden ||
			!isPeerConnected(targetPc)
		) {
			return;
		}

		if (
			typeof videoElem.requestVideoFrameCallback !== 'function' &&
			videoElem.currentTime > lastVideoCurrentTime
		) {
			markVideoFrame(videoElem, targetPc, generation);
		}

		const stalledForMs = Date.now() - lastVideoFrameAt;
		if (stalledForMs >= FRAME_STALL_TIMEOUT_MS) {
			console.warn(
				`WebRTC 视频帧连续 ${stalledForMs}ms 未更新，触发自动重连`,
			);
			scheduleReconnect('video-frame-stalled', { immediate: true });
		}
	}, FRAME_WATCHDOG_INTERVAL_MS);
}

function attachRemoteTrack(evt, targetPc, generation) {
	if (!isActiveConnection(targetPc, generation)) {
		return;
	}

	const stream =
		evt.streams && evt.streams[0]
			? evt.streams[0]
			: new MediaStream([evt.track]);

	if (evt.track.kind === 'video') {
		const videoElem = document.getElementById('video');
		if (!videoElem) {
			return;
		}
		videoElem.srcObject = stream;
		videoElem.onloadedmetadata = () => {
			videoElem.play().catch(error => {
				console.warn('WebRTC 视频自动播放失败:', error);
			});
			nextTick(() => {
				loading.value = false;
			});
		};
		videoElem.onplaying = () => {
			if (!isActiveConnection(targetPc, generation)) {
				return;
			}
			console.log('Video is now playing');
			if (typeof videoElem.requestVideoFrameCallback !== 'function') {
				markVideoFrame(videoElem, targetPc, generation);
			}
		};
		evt.track.addEventListener(
			'ended',
			() => {
				if (isActiveConnection(targetPc, generation)) {
					scheduleReconnect('video-track-ended', { immediate: true });
				}
			},
			{ once: true },
		);
		startVideoFrameMonitor(videoElem, targetPc, generation);
		return;
	}

	const audioElem = document.getElementById('audio');
	if (audioElem) {
		audioElem.srcObject = stream;
		audioElem.play().catch(error => {
			console.warn('WebRTC 音频自动播放失败:', error);
		});
	}
}

function waitForIceGatheringComplete(targetPc, signal) {
	return new Promise(resolve => {
		let completed = false;
		let timeoutId = null;
		const checkState = () => {
			if (targetPc.iceGatheringState === 'complete') {
				finish('complete');
			}
		};
		const handleAbort = () => finish('aborted');
		const finish = reason => {
			if (completed) {
				return;
			}
			completed = true;
			if (timeoutId !== null) {
				clearTimeout(timeoutId);
			}
			targetPc.removeEventListener('icegatheringstatechange', checkState);
			signal?.removeEventListener('abort', handleAbort);
			if (reason === 'timeout') {
				console.warn('ICE gathering 等待超时，使用当前候选继续协商');
			}
			resolve();
		};
		timeoutId = setTimeout(
			() => finish('timeout'),
			ICE_GATHERING_TIMEOUT_MS,
		);
		signal?.addEventListener('abort', handleAbort, { once: true });

		if (signal?.aborted) {
			finish('aborted');
		} else if (targetPc.iceGatheringState === 'complete') {
			finish('complete');
		} else {
			targetPc.addEventListener('icegatheringstatechange', checkState);
		}
	});
}

async function negotiate(targetPc, generation, signal) {
	targetPc.addTransceiver('video', { direction: 'recvonly' });
	targetPc.addTransceiver('audio', { direction: 'recvonly' });

	const offer = await targetPc.createOffer();
	if (!isActiveConnection(targetPc, generation)) {
		return;
	}
	await targetPc.setLocalDescription(offer);
	await waitForIceGatheringComplete(targetPc, signal);

	if (!isActiveConnection(targetPc, generation)) {
		return;
	}

	console.log('negotiate eventBus.sessionId:', eventBus.sessionId);
	const response = await fetch(buildApiUrl('backend', '/offer'), {
		body: JSON.stringify({
			sdp: targetPc.localDescription.sdp,
			type: targetPc.localDescription.type,
			sessionid: eventBus.sessionId,
		}),
		headers: {
			'Content-Type': 'application/json',
		},
		method: 'POST',
		signal,
	});

	if (!response.ok) {
		throw new Error(`发送 WebRTC offer 失败: HTTP ${response.status}`);
	}

	const answer = await response.json();
	if (!answer?.sdp || !answer?.type) {
		throw new Error(answer?.error || 'WebRTC answer 缺少 SDP');
	}
	if (!isActiveConnection(targetPc, generation)) {
		return;
	}

	await targetPc.setRemoteDescription(answer);
	if (answer.sessionid) {
		eventBus.sessionId = answer.sessionid;
	}
	emit('offerSuccess', true);
}

function handlePeerStateChange(targetPc, generation, stateSource) {
	if (!isActiveConnection(targetPc, generation)) {
		return;
	}

	const connectionState = targetPc.connectionState;
	const iceState = targetPc.iceConnectionState;
	console.log(
		`WebRTC 状态变化 source=${stateSource} connection=${connectionState} ice=${iceState}`,
	);

	if (isPeerConnected(targetPc)) {
		clearDisconnectedTimer();
		clearConnectionTimeout();
		reconnectAttempts = 0;
		store.changeWebrtcStatus(true);
		return;
	}

	if (connectionState === 'disconnected' || iceState === 'disconnected') {
		if (disconnectedTimer === null) {
			disconnectedTimer = setTimeout(() => {
				disconnectedTimer = null;
				if (
					isActiveConnection(targetPc, generation) &&
					(targetPc.connectionState === 'disconnected' ||
						targetPc.iceConnectionState === 'disconnected')
				) {
					scheduleReconnect('peer-disconnected', { immediate: true });
				}
			}, DISCONNECTED_GRACE_MS);
		}
		return;
	}

	if (
		connectionState === 'failed' ||
		connectionState === 'closed' ||
		iceState === 'failed' ||
		iceState === 'closed'
	) {
		scheduleReconnect(`peer-${connectionState}-${iceState}`, {
			immediate: reconnectAttempts === 0,
		});
	}
}

async function establishConnection(reason) {
	if (lifecycleStopped || !networkAvailable || connectingGeneration !== null) {
		return;
	}

	clearReconnectTimer();
	const generation = ++connectionGeneration;
	connectingGeneration = generation;
	loading.value = true;
	webFirstFrameLogged = false;
	store.changeWebrtcStatus(false);
	emit('videoReady', false);

	const config = {
		sdpSemantics: 'unified-plan',
	};
	const targetPc = new RTCPeerConnection(config);
	const abortController = new AbortController();
	pc = targetPc;
	offerAbortController = abortController;

	targetPc.addEventListener('track', evt => {
		attachRemoteTrack(evt, targetPc, generation);
	});
	targetPc.addEventListener('connectionstatechange', () => {
		handlePeerStateChange(targetPc, generation, 'connection');
	});
	targetPc.addEventListener('iceconnectionstatechange', () => {
		handlePeerStateChange(targetPc, generation, 'ice');
	});

	connectionTimeoutTimer = setTimeout(() => {
		if (isActiveConnection(targetPc, generation)) {
			console.warn(`WebRTC 建连超过 ${CONNECTION_TIMEOUT_MS}ms，触发重连`);
			scheduleReconnect('connection-timeout', { immediate: true });
		}
	}, CONNECTION_TIMEOUT_MS);

	console.log(
		`开始 WebRTC 建连 reason=${reason} generation=${generation} sessionid=${eventBus.sessionId}`,
	);

	try {
		await negotiate(targetPc, generation, abortController.signal);
	} catch (error) {
		if (
			isActiveConnection(targetPc, generation) &&
			error?.name !== 'AbortError'
		) {
			console.error('WebRTC 协商失败:', error);
			scheduleReconnect('negotiate-failed');
		}
	} finally {
		if (connectingGeneration === generation) {
			connectingGeneration = null;
		}
		if (offerAbortController === abortController) {
			offerAbortController = null;
		}
	}
}

function scheduleReconnect(
	reason,
	{ immediate = false, resetAttempts = false, replaceScheduled = false } = {},
) {
	if (lifecycleStopped || !networkAvailable) {
		return;
	}
	if (reconnectTimer !== null && !replaceScheduled) {
		return;
	}

	if (replaceScheduled) {
		clearReconnectTimer();
	}
	if (resetAttempts) {
		reconnectAttempts = 0;
	}

	const attempt = reconnectAttempts + 1;
	const delay = immediate
		? 0
		: Math.min(
				RECONNECT_BASE_DELAY_MS * 2 ** Math.min(reconnectAttempts, 5),
				RECONNECT_MAX_DELAY_MS,
			);
	reconnectAttempts = attempt;

	++connectionGeneration;
	connectingGeneration = null;
	closeCurrentPeerConnection();
	loading.value = true;
	store.changeWebrtcStatus(false);
	emit('videoReady', false);

	console.warn(
		`WebRTC 将自动重连 reason=${reason} attempt=${attempt} delay_ms=${delay}`,
	);
	reconnectTimer = setTimeout(() => {
		reconnectTimer = null;
		establishConnection(`retry:${reason}`);
	}, delay);
}

function requestReconnect(reason = 'external-request') {
	if (lifecycleStopped) {
		return;
	}
	scheduleReconnect(reason, {
		immediate: true,
		resetAttempts: true,
		replaceScheduled: true,
	});
}

function setNetworkAvailable(
	available,
	source = 'external',
	{ forceReconnect = false } = {},
) {
	const nextAvailable = Boolean(available);
	const wasAvailable = networkAvailable;
	networkAvailable = nextAvailable;
	console.log(
		`WebRTC 网络状态 source=${source} available=${nextAvailable} previous=${wasAvailable}`,
	);

	if (!nextAvailable) {
		clearReconnectTimer();
		++connectionGeneration;
		connectingGeneration = null;
		closeCurrentPeerConnection();
		loading.value = true;
		store.changeWebrtcStatus(false);
		emit('videoReady', false);
		return;
	}

	const peerNeedsReconnect =
		isPeerUnhealthy(pc);
	if (forceReconnect || !wasAvailable || peerNeedsReconnect) {
		requestReconnect(`${source}-network-available`);
	}
}

function getPoster() {
	return new Promise((resolve, reject) => {
		fetch(buildWsUrl('llm', '/image'))
			.then(response => {
				return response.json();
			})
			.then(data => {
				console.log(data);
				// return `data:image/png;base64,${base64Str}`

				poster.value = `data:image/png;base64,${data.image}`;
				resolve(poster.value);
			})
			.catch(err => {
				reject(err);
			});
	});
}

function start(reason = 'initial') {
	console.log('start eventBus.sessionId:', eventBus.sessionId);
	lifecycleStopped = false;
	networkAvailable = typeof navigator === 'undefined' || navigator.onLine !== false;
	loading.value = true;
	webFirstFrameLogged = false;
	if (!networkAvailable) {
		console.warn('当前网络不可用，等待网络恢复后建立 WebRTC');
		return;
	}
	if (pc || connectingGeneration !== null) {
		requestReconnect(`${reason}-restart`);
		return;
	}
	establishConnection(reason);
}

function stop() {
	lifecycleStopped = true;
	networkAvailable = false;
	clearReconnectTimer();
	++connectionGeneration;
	connectingGeneration = null;
	closeCurrentPeerConnection();
	loading.value = false;
	console.log('webrtc closed');
	store.changeWebrtcStatus(false);
	emit('videoReady', false);
}

const beforeUnloadHandler = () => {
	console.log('webrtc closeing');
	stop();
};

const onlineHandler = () => setNetworkAvailable(true, 'browser');
const offlineHandler = () => setNetworkAvailable(false, 'browser');
const visibilityHandler = () => {
	if (
		!document.hidden &&
		(isPeerUnhealthy(pc) ||
			(lastVideoFrameAt > 0 &&
				Date.now() - lastVideoFrameAt >= FRAME_STALL_TIMEOUT_MS))
	) {
		requestReconnect('document-visible');
	}
};

onMounted(() => {
	window.addEventListener('beforeunload', beforeUnloadHandler);
	window.addEventListener('online', onlineHandler);
	window.addEventListener('offline', offlineHandler);
	document.addEventListener('visibilitychange', visibilityHandler);
});

onUnmounted(() => {
	window.removeEventListener('beforeunload', beforeUnloadHandler);
	window.removeEventListener('online', onlineHandler);
	window.removeEventListener('offline', offlineHandler);
	document.removeEventListener('visibilitychange', visibilityHandler);
	stop();
});
</script>
<template>
	<div class="w-100 h-100 position-relative d-flex align-center justify-center">
		<video
			id="video"
			autoplay
			playsinline
			webkit-playsinline
			:poster="poster"
		></video>
		<audio id="audio" autoplay></audio>
		<img
			v-if="loading"
			:src="getPublicUrl('/loading.png')"
			alt="alt text"
			class="loading-img position-absolute"
		/>
	</div>
</template>
<style scoped>
#video {
	background-color: gray;
	height: 100%;
	width: 100%;
	background: url(/video_bg2.jpg) no-repeat;
	background-size: 100% 100%;
	object-fit: fill;
}

@keyframes rotate {
	from {
		transform: rotate(0deg);
	}

	to {
		transform: rotate(360deg);
	}
}

.loading-img {
	width: 150px;
	height: 150px;
	animation: rotate 3s linear infinite;
}
</style>
