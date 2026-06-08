import { queryAvatarSpeaking } from '@/api';
import { eventBus } from '@/api/session';

const sleep = (ms) => new Promise(resolve => setTimeout(resolve, ms));

export function useAvatarSpeechSync() {
  async function isAvatarSpeaking() {
    const sessionid = eventBus.sessionId;

    if (!sessionid) {
      return false;
    }

    try {
      const res = await queryAvatarSpeaking({ sessionid });
      return !!(res && res.data);
    } catch (error) {
      console.warn('数字人说话查询接口查询失败~', error);
      return false;
    }
  }

  async function waitUntilSpeaking(signal, interval = 500) {
    while (!signal?.aborted) {
      if (await isAvatarSpeaking()) {
        return true;
      }
      await sleep(interval);
    }

    return false;
  }

  async function waitUntilSilent(signal, interval = 500) {
    while (!signal?.aborted) {
      if (!await isAvatarSpeaking()) {
        return true;
      }
      await sleep(interval);
    }

    return false;
  }

  return {
    isAvatarSpeaking,
    waitUntilSpeaking,
    waitUntilSilent,
  };
}

export default useAvatarSpeechSync;
