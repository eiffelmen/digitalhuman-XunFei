import request from '@/utils/request';
import { eventBus } from '@/api/session';

/* 视频file文件换取url */
export const uploadVideo = data =>
	request(api_8086 + '/v1/upload', {
		method: 'POST',
		body: data,
	});

/* 通过视频链接获取数字人ID */
export const getDigitalHumanIdByVideoUrl = data =>
	request(api_8085 + '/v1/process_video_url', {
		method: 'POST',
		body: JSON.stringify(data),
		headers: {
			'Content-Type': 'application/json',
		},
	});

/* 上传视频链接给后端处理 */
export const processVideo = data =>
	request(api_8085 + '/v1/process_video', {
		method: 'POST',
		body: data,
	});

/* 数字人ID切换 */
export const switchDigitalHumanId = data =>
	request('/backend/change_avatar', {
		method: 'POST',
		body: JSON.stringify(data),
	});

/* 上传用户音色模板 */
export const uploadUserVoice = data =>
	request(`${api_8088}/v1/upload_audio`, {
		method: 'POST',
		body: data,
	});

/* 删除用户音色模板 */
export const deleteUserVoice = avatar_audio_id =>
	request(`${api_8088}/v1/delete_audio/${avatar_audio_id}`, {
		method: 'DELETE',
		headers: {
			'Content-Type': 'application/json',
		},
	});

/* 上传用户自定义背景图模板 */
export const uploadUserBackground = data =>
	request(`${api_8088}/v1/upload_image`, {
		method: 'POST',
		body: data,
	});

/* 删除用户自定义背景图模板 */
export const deleteUserBackground = avatar_bg_id =>
	request(`${api_8088}/v1/delete_image/${avatar_bg_id}`, {
		method: 'DELETE',
		headers: {
			'Content-Type': 'application/json',
		},
	});

/* 数字人素材模板切换 */
export const switchDigitalHumanTemplate = data =>
	request(`${api_8011}/update_config`, {
		method: 'POST',
		body: JSON.stringify(data),
		headers: {
			'Content-Type': 'application/json',
		},
	});

/* 删除数字人形象 */
export const deleteDigitalHuman = avatar_id =>
	request(`${api_8085}/v1/delete_avatar/${avatar_id}`, {
		method: 'DELETE',
		headers: {
			'Content-Type': 'application/json',
		},
	});

/* 更新加载配置 */
export const updateLoadConfig = (data = {}) =>
	request(`${api_8011}/reload_config`, {
		method: 'POST',
		body: JSON.stringify(data),
		headers: {
			'Content-Type': 'application/json',
		},
	});

// 初始化形象
export const getInitConfig = data =>
	request(`${api_8011}/init_config`, {
		method: 'POST',
		body: JSON.stringify(data),
		headers: {
			'Content-Type': 'application/json',
		},
	});

// 轮询接口获取处理后的人物形象
export const getCheckDigital = task_id =>
	request(`${api_8085}/v1/check_status/${task_id}`, {
		method: 'GET',
		headers: {
			'Content-Type': 'application/json',
		},
	});

// 获取sessionID
export const getSessionId = () =>
	request(`/backend/generate_session`, {
		method: 'POST',
		headers: {
			'Content-Type': 'application/json',
		},
	});

// 查询数字人形象是否开始说话
export const queryAvatarSpeaking = data =>
	request(`/backend/is_speaking`, {
		method: 'POST',
		body: JSON.stringify(data),
		headers: {
			'Content-Type': 'application/json',
		},
	});

// 数字人说话接口
export const digitalHumanSay = (text, deviceId) => {
  // 确保有 deviceId，如果没有则尝试从 localStorage 获取
  const sessionId = deviceId || eventBus.sessionId || localStorage.getItem('deviceid');
  
  return request(`/backend/human`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      text,
      type: 'echo',
      interrupt: true,
      sessionid: sessionId
    }),
  });
};
