<template>
	<div class="standby-wrapper">
		<div class="camera-video-content">
			<img
				src="../../assets/templete_images/1.png"
				class="camera-image"
			/>
		</div>
		<div class="standby-bg-wrapper">
			<div class="standby-bg-content">
				<img
					src="../../assets/templete_images/1.png"
					class="camera-image"
				/>
			</div>
		</div>
		<div :style="`background-image: url('${getPublicUrl('/version_bg.png')}'); background-size: 100% 100%;`" class="version-content">Version 3.0.2</div>
	</div>
</template>

<script setup>
import { ref } from 'vue';
import { getPublicUrl } from '@/utils/getAssets';
</script>

<style scoped>
.standby-wrapper {
	height: 100%;
	width: 100%;
	position: relative;
	background-repeat: no-repeat;
	background-size: 100% 100%;
	background-image: url(/video_bg2.jpg);
}

.camera-video-content {
	position: absolute;
	width: 364px;
	height: 573px;
	top: 100px;
	right: 132px;
	padding: 8px;
	overflow: hidden;
	background-size: 100% 100%;
	background-image: url(/standby-camera.png);
}

.camera-image {
	width: 100%;
	height: 100%;
	margin: 0;
	padding: 0;
}

.standby-bg-wrapper {
	width: 100%;
	height: 2116px;
	padding: 0 132px;
	position: absolute;
	bottom: 258px;

	.standby-bg-content {
		width: 100%;
		height: 100%;
		padding: 44px;
		background-size: 100% 100%;
		background-image: url(/standby-bg.png);
	}
}

.version-content {
	position: fixed;
	height: 60px;
	right: 60px;
	bottom: 36px;
	font-size: 46px;
	color: #012557;
	padding: 0 24px;
	line-height: 60px;
}
</style>
