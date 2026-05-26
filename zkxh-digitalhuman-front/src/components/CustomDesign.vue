<script setup>
import {
	getDigitalHumanIdByVideoUrl,
	switchDigitalHumanTemplate,
	uploadUserVoice,
	uploadVideo,
	getCheckDigital,
} from '@/api';
import { store } from '@/store/store';
import { getAssetImgUrl, getPublicUrl } from '@/utils/getAssets';
import { getStore } from '@/utils/store';
import useMessage from '@/utils/useMessage';
import Recorder from 'recorder-core';
import { computed, nextTick, onMounted, onUnmounted, ref } from 'vue';

const mediaRecorder = ref(null);
const chunks = ref([]);
const isRecording = ref('start');
const isVoicing = ref('start');
const videoRef = ref(null);
const videoBoxRef = ref(null);
const recordTimer = ref(null);
const widthNumer = ref(0);
const videoUrl = ref(null);
const timerResult = ref(null);
const taskFinish = ref(false);
let recorder = null;
const curentObj = ref({
	...store.digitalDefault,
});
const isLoading = ref(false);
const isVoiceLoading = ref(false);
const voiceTimer = ref(null);
const voiceWidthNumer = ref(0);
const btnText = computed(() => {
	if (['start', 'cancel', 'fail'].includes(isRecording.value))
		return '开始制作';
	if (isRecording.value === 'stop') return '取消制作';
	if (isRecording.value === 'recordFinish') return '形象制作中,请稍后...';
	if (isRecording.value === 'confirm') return '制作完成';
});
const voiceBtnText = computed(() => {
	if (['start', 'cancel', 'fail'].includes(isVoicing.value)) return '开始制作';
	if (isVoicing.value === 'stop') return '取消制作';
	if (isVoicing.value === 'recordFinish') return '音色制作中,请稍后...';
	if (isVoicing.value === 'confirm') return '制作完成';
});
const overloayLoading = ref(false);
const emits = defineEmits(['back', 'success']);
function resetData(type) {
	if (type === 'record') {
		isVoiceLoading.value = false;
		voiceWidthNumer.value = 0;
		curentObj.value = {
			...curentObj.value,
			voice_type: store.digitalDefault.voice_type,
		};
		if (voiceTimer.value) {
			clearInterval(voiceTimer.value);
			voiceTimer.value = null;
		}
	} else {
		chunks.value = [];
		isLoading.value = false;
		videoUrl.value = null;
		curentObj.value = {
			...curentObj.value,
			digital_human_id: store.digitalDefault.digital_human_id,
		};
		if (recordTimer.value) {
			clearInterval(recordTimer.value);
			recordTimer.value = null;
		}
		widthNumer.value = 0;
	}
}
async function initMedia() {
	try {
		const constraints = {
			video: {
				// width: 607.5,
				width: (1080 * 9) / 16,
				height: 1080,
				facingMode: 'user',
			},
			voice: true,
		};
		const stream = await navigator.mediaDevices.getUserMedia(constraints);
		videoRef.value.srcObject = stream;
		mediaRecorder.value = new MediaRecorder(stream, { mimeType: 'video/mp4' });
		mediaRecorder.value.ondataavailable = event => {
			if (event.data && event.data.size > 0) {
				chunks.value.push(event.data);
			}
		};
		mediaRecorder.value.onstop = () => {
			if (isRecording.value === 'recordFinish') {
				downloadVideo();
			}
		};
	} catch (error) {
		console.error('获取媒体设备失败:', error);
		// useMessage({
		//   type: 'error',
		//   message: '无法访问您的摄像头和麦克风，请检查权限设置'
		// })
	}
}

// 添加一个函数来停止录制并释放资源
function stopMedia() {
	if (mediaRecorder.value) {
		mediaRecorder.value.stop();
		mediaRecorder.value = null;
	}
}
function startFn() {
	resetData();
	if (!mediaRecorder.value) {
		useMessage({
			type: 'error',
			message: '无法访问您的摄像头和麦克风，请检查权限设置',
		});
		return;
	}
	isRecording.value = 'stop';
	mediaRecorder.value.start();
	recordTimer.value = setInterval(() => {
		widthNumer.value += 5;
		if (widthNumer.value >= 100) {
			clearInterval(recordTimer.value);
			isRecording.value = 'recordFinish';
			mediaRecorder.value.stop();
		}
	}, 1000);
}
function cancelFn() {
	isRecording.value = 'cancel';
	resetData();
	mediaRecorder.value.stop();
}
async function confirmDesign() {
	if (isLoading.value) return;
	try {
		isLoading.value = true;
		overloayLoading.value = true;
		await switchDigitalHumanTemplate({
			...curentObj.value,
			sessionid: eventBus.sessionId || 0,
		});
		store.changeDigitalDefault(curentObj.value);
		emits('success', {
			digital_human_id: curentObj.value.digital_human_id,
			voice_type: curentObj.value.voice_type,
		});
		overloayLoading.value = false;
		isLoading.value = false;
	} catch (error) {
		isLoading.value = false;
		overloayLoading.value = false;
	}
}
function downloadVideo() {
	const blob = new Blob(chunks.value, { type: 'video/mp4' });
	const audioFile = new File([blob], 'recording.mp4', {
		type: 'video/mp4',
	});
	chunks.value = [];
	uploadVideoFile(audioFile);
}
function getResultUrl(task_id) {
	taskFinish.value = false;
	getCheckDigital(task_id)
		.then(res => {
			taskFinish.value = true;
			if (res.result) {
				if (timerResult.value) {
					clearInterval(timerResult.value);
					timerResult.value = null;
				}
				const resp = JSON.parse(res.result);
				isLoading.value = false;
				isRecording.value = 'confirm';
				useMessage({
					message: resp.message || '上传成功',
					type: 'success',
				});
				curentObj.value = {
					...curentObj.value,
					digital_human_id: resp.avatar_id.split('wav2lip_avatar')[1] * 1,
				};
				const avatarId = resp.avatar_id.split('wav2lip_avatar')[1] * 1;
				const data = {
					url: resp.templete_image_url,
					id: avatarId,
					name: `自定义形象${avatarId}`,
					isUpload: true,
					sessionid: eventBus.sessionId || 0,
				};
				store.setDefaultSetttingData('image', data);
			}
			if (res.status === 'failed') {
				isRecording.value = 'fail';
			}
		})
		.catch(error => {
			useMessage({
				message: error || '上传失败，请稍后重试',
				type: 'error',
			});
			isRecording.value = 'fail';
			isLoading.value = false;
		});
}
async function uploadVideoFile(file) {
	if (isLoading.value) return;
	try {
		isLoading.value = true;
		const formData = new FormData();
		formData.append('file', file);
		// 通过file获取视频链接
		const res = await uploadVideo(formData);
		const resp = await getDigitalHumanIdByVideoUrl({
			video_url: res.url,
		});
		if (resp.avatar_id) {
			if (timerResult.value) {
				clearInterval(timerResult.value);
				timerResult.value = null;
			}
			isLoading.value = false;
			isRecording.value = 'confirm';
			useMessage({
				message: resp.message || '上传成功',
				type: 'success',
			});
			curentObj.value = {
				...curentObj.value,
				digital_human_id: resp.avatar_id.split('wav2lip_avatar')[1] * 1,
			};
			const avatarId = resp.avatar_id.split('wav2lip_avatar')[1] * 1;
			const data = {
				url: resp.templete_image_url,
				id: avatarId,
				name: `自定义形象${avatarId}`,
				isUpload: true,
				sessionid: eventBus.sessionId || 0,
			};
			store.setDefaultSetttingData('image', data);
		} else {
			taskFinish.value = true;
			timerResult.value = setInterval(() => {
				if (isRecording.value === 'confirm') {
					clearInterval(timerResult.value);
					timerResult.value = null;
					return;
				}
				if (isRecording.value === 'fail') {
					clearInterval(timerResult.value);
					timerResult.value = null;
					return;
				}
				taskFinish.value && getResultUrl(resp.task_id);
			}, 1000 * 10);
		}
	} catch (error) {
		useMessage({
			message: error || '上传失败，请稍后重试',
			type: 'error',
		});
		isRecording.value = 'fail';
		isLoading.value = false;
	}
}
function actionFn() {
	if (isRecording.value === 'recordFinish' || isLoading.value) return;
	if (['start', 'cancel', 'fail'].includes(isRecording.value)) return startFn();
	if (isRecording.value === 'stop') return cancelFn();
	// if (isRecording.value === 'confirm') return confirmDesign();
}
function back() {
	stopMedia();
	resetData();
	resetData('record');
	recorder = null;
	emits('back');
}
function recordActionFn() {
	if (isVoicing.value === 'recordFinish' || isVoiceLoading.value) return;
	if (['start', 'cancel', 'fail'].includes(isVoicing.value))
		return recordStartFn();
	if (isVoicing.value === 'stop') return recordCancelFn();
}
async function uploadRecordFn(blob) {
	if (isVoiceLoading.value) return;
	try {
		isVoiceLoading.value = true;
		const formData = new FormData();
		formData.append('file', blob, 'recording.mp3');
		const res = await uploadUserVoice(formData);
		if (res.voice_id) {
			isVoicing.value = 'confirm';
			curentObj.value = {
				...curentObj.value,
				voice_type: res.voice_id,
			};
			useMessage({
				message: res.message || '音色制作完成',
				type: 'success',
			});
			const data = {
				url: null,
				id: res.voice_id,
				name: `自定义音色${res.voice_id}`,
				isUpload: true,
				sessionid: eventBus.sessionId || 0,
			};
			store.setDefaultSetttingData('timbre', data);
		}
		isVoiceLoading.value = false;
	} catch (error) {
		isVoicing.value = 'fail';
		isVoiceLoading.value = false;
	}
}
function initRecord() {
	if (recorder) {
		startRecord();
	} else {
		recorder = new Recorder({
			sampleBits: 16,
			sampleRate: 44100,
		});
		startRecord();
	}
}
function recordStartFn() {
	resetData('record');
	isVoicing.value = 'stop';
	initRecord();
}
function startRecord() {
	recorder.open(() => {
		recorder.start();
		voiceTimer.value = setInterval(() => {
			voiceWidthNumer.value += 100 / 9; // 由于音色克隆算法限制，需要确保录入音色时长在10s内
			if (voiceWidthNumer.value >= 100) {
				clearInterval(voiceTimer.value);
				isVoicing.value = 'recordFinish';
				stopRecord();
			}
		}, 1000);
	});
}
function stopRecord() {
	recorder.stop(
		blob => {
			if (isVoicing.value === 'recordFinish') {
				uploadRecordFn(blob);
			}
		},
		msg => {
			console.log(msg);
		}
	);
}
function recordCancelFn() {
	isVoicing.value = 'cancel';
	resetData('record');
	stopRecord();
}
onMounted(() => {
	nextTick(() => {
		initMedia();
	});
});
onUnmounted(() => {
	stopMedia();
	if (timerResult.value) {
		clearInterval(timerResult.value);
		timerResult.value = null;
	}
});
</script>
<template>
	<div class="design-page d-flex align-center w-100 h-100 overflow-hidden">
		<div
			class="setting-list h-100 d-flex flex-column"
			:style="{ width: `${(200 / 1920) * 100}%` }"
		>
			<div
				class="back-btn d-flex align-center justify-center cursor-pointer"
				@click="back()"
			>
				<img
					src="@/assets/back_icon.png"
					class="back-btn-icon"
				/>返回
			</div>
			<div
				v-if="isRecording === 'confirm'"
				class="back-btn d-flex align-center justify-center cursor-pointer"
				@click="confirmDesign()"
			>
				确定
			</div>
		</div>
		<div
			class="position-relative h-100 d-flex flex-column"
			:style="{ width: `${(699 / 1920) * 100}%` }"
		>
			<div
				class="tips"
				style="color: #fff; white-space: nowrap"
			>
				<span class="box-title">形象制作</span>
				<span class="box-title_sub"
					>请调整摄像设备位置，让形象位于拾取识别区域</span
				>
			</div>
			<div
				style="flex: 1"
				ref="videoBoxRef"
				class="position-relative overflow-hidden video-info"
			>
				<video
					v-show="!videoUrl"
					ref="videoRef"
					class="video-elem"
					autoplay
					:poster="getPublicUrl('/video_bg2.png')"
				></video>
				<video
					v-show="videoUrl"
					:src="videoUrl"
					class="video-elem"
					autoplay
					loop
					:poster="getPublicUrl('/video_bg2.png')"
				></video>
				<!-- <div class="bg-box">
          <img :src="getPublicUrl('/video_bg.png')" />
        </div> -->
				<div
					class="process-box position-absolute"
					v-if="['stop'].includes(isRecording)"
				>
					<div
						class="process-line"
						:style="{ width: widthNumer + '%' }"
					></div>
					<div class="process-tip position-absolute">
						<span>20</span>s 形象获取完成
					</div>
				</div>
				<v-expand-transition>
					<div v-if="['fail', 'recordFinish'].includes(isRecording)">
						<div
							class="record-tip d-flex flex-column align-center justify-center position-absolute"
						>
							<img
								:src="
									['recordFinish'].includes(isRecording)
										? getAssetImgUrl('tip_success.png')
										: getAssetImgUrl('tip_error.png')
								"
							/>
							<div>
								{{
									['recordFinish'].includes(isRecording)
										? '形象获取已完成'
										: '形象制作失败'
								}}
							</div>
							<span>{{
								['recordFinish'].includes(isRecording)
									? '形象制作中'
									: '请确认摄像头位置并重试'
							}}</span>
						</div>
					</div>
				</v-expand-transition>
			</div>
			<div class="d-flex align-center justify-between">
				<div
					@click="actionFn()"
					class="audio-btn cursor-pointer d-flex align-center justify-center"
				>
					{{ btnText }}
				</div>
				<div
					@click="startFn()"
					v-if="['confirm'].includes(isRecording)"
					class="audio-btn cursor-pointer d-flex align-center justify-center restart-btn"
				>
					重新制作
				</div>
			</div>
		</div>
		<div
			class="position-relative h-100 d-flex flex-column"
			:style="{ width: `${(699 / 1920) * 100}%` }"
		>
			<div
				class="tips"
				style="color: #fff; white-space: nowrap"
			>
				<span class="box-title">音色制作</span>
				<span class="box-title_sub"
					>请通过采音设备，按显示速率，朗读下列文本。</span
				>
			</div>
			<div class="position-relative overflow-hidden video-info video-word">
				<div>
					先帝创业未半<br />
					而中道崩殂<br />
					今天下三分<br />
					益州疲弊<br />
					此城危急存亡之秋也
				</div>
				<div
					class="process-box position-absolute"
					v-if="['stop'].includes(isVoicing)"
				>
					<div
						class="process-line"
						:style="{ width: voiceWidthNumer + '%' }"
					></div>
					<div class="process-tip position-absolute">
						<span>9</span>s 音色获取完成
					</div>
				</div>
			</div>
			<div class="d-flex align-center justify-between">
				<div
					@click="recordActionFn()"
					class="audio-btn cursor-pointer d-flex align-center justify-center"
				>
					{{ voiceBtnText }}
				</div>
				<div
					@click="recordStartFn()"
					v-if="['confirm'].includes(isVoicing)"
					class="audio-btn cursor-pointer d-flex align-center justify-center restart-btn"
				>
					重新制作
				</div>
			</div>
		</div>
		<v-overlay
			v-model="overloayLoading"
			class="align-center justify-center"
			:close-on-content-click="false"
			contained
		>
			<span class="loading-tips">确认中，请稍后...</span>
		</v-overlay>
	</div>
</template>
<style scoped>
.design-page {
	padding: 40px;
	justify-content: space-between;
	box-sizing: border-box;
	background: linear-gradient(180deg, #3d5cf2 0%, #80bdff 100%);
}
.setting-list {
	justify-content: space-between;
}
.title-sub {
	font-weight: bold;
	font-size: 36px;
	color: #ffffff;
	line-height: 33px;
}
.config-wrap {
	padding: 0 58px 0 28px;
}
.config-item {
	margin-bottom: 40px;
}
.config-item:last-child {
	margin-bottom: 0;
}
.back-btn {
	width: 150px;
	height: 63px;
	background: linear-gradient(-20deg, #4b93ff 0%, #3279e3 100%);
	box-shadow: 0px 0px 6px 0px rgba(0, 16, 127, 0.5);
	border-radius: 6px;
	font-weight: 500;
	font-size: 24px;
	color: #ffffff;
}
.back-btn-icon {
	width: 42px;
	margin-right: 3px;
}
.audio-btn {
	margin-top: 36px;
	flex: 1;
	height: 80px;
	background: linear-gradient(-20deg, #4b93ff 0%, #3279e3 100%);
	box-shadow: 0px 0px 24px 0px rgba(0, 16, 127, 0.51);
	border-radius: 6px;
	font-weight: 500;
	font-size: 36px;
	color: #ffffff;
}
.video-info {
	background: linear-gradient(0deg, #cbd9f2 0%, #bbd6ff 100%);
	box-shadow: 0px 0px 24px rgba(0, 16, 127, 0.51);
	border-radius: 14px;
}
.process-box {
	background: rgba(0, 0, 0, 0.1);
	height: 44px;
	bottom: 0;
	left: 0;
	width: 100%;
}
.process-line {
	height: 100%;
	background: linear-gradient(90deg, #fffdfb 0%, #fde0bc 96%);
}
.process-tip {
	background: transparent;
	z-index: 1;
	height: 44px;
	bottom: 0;
	left: 0;
	width: 100%;
	display: flex;
	align-items: center;
	justify-content: center;
	font-weight: 400;
	font-size: 18px;
	color: #000000;
}
.process-tip span {
	font-size: 22px;
}
.record-tip {
	width: 58%;
	height: 45.9%;
	/* height: 406px; */
	background: #fff200;
	border-radius: 10px;
	border: 6px solid #ffffff;
	font-weight: 400;
	font-size: 26px;
	color: #000000;
	line-height: 25px;
	left: 50%;
	top: 50%;
	transform: translate(-50%, -50%);
}
.record-tip div {
	font-weight: bold;
	font-size: 36px;
	color: #000000;
	line-height: 35px;
	margin-bottom: 10px;
}
.record-tip img {
	width: 36.94%;
	height: auto;
	margin-bottom: 36px;
}
.video-elem {
	width: 100%;
	height: 100%;
}
.box-title {
	font-size: 26px;
	font-weight: bold;
}
.box-title_sub {
	font-size: 18px;
	font-weight: normal;
	vertical-align: bottom;
}
.video-word {
	flex: 1;
	display: flex;
	align-items: center;
	justify-content: center;
	font-size: 40px;
	color: #000;
	font-weight: bold;
	text-align: center;
}
.restart-btn {
	margin-left: 20px;
}
.loading-tips {
	font-size: 32px;
	font-weight: bold;
}
.bg-box {
	width: 100%;
	height: 100%;
	position: absolute;
	z-index: 9999;
	background: rgba(0, 0, 0, 0.5);
	display: flex;
	justify-content: center;
}
.bg-box img {
	width: 407px;
	height: 394px;
	margin-top: 129px;
}
</style>
