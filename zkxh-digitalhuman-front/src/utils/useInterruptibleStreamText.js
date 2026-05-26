import { ref } from 'vue';

export function useInterruptibleStreamText({ isChinese, onChunkRendered }) {
  const messagebox = ref('');
  const activeStreamId = ref('');
  const activeEpoch = ref(0);
  const streamReceiveFinished = ref(false);

  let messageQueue = [];
  let renderAbortController = null;
  const staleStreamIds = new Set();

  function abortActiveRender() {
    if (renderAbortController) {
      renderAbortController.abort();
      renderAbortController = null;
    }
  }

  function ensureAbortController() {
    if (!renderAbortController) {
      renderAbortController = new AbortController();
    }
    return renderAbortController;
  }

  function createContext() {
    return {
      id: activeStreamId.value,
      epoch: activeEpoch.value,
    };
  }

  function startNewStream(message) {
    const msgId = message?.id;
    if (!msgId) {
      return null;
    }

    if (activeStreamId.value && activeStreamId.value !== msgId) {
      staleStreamIds.add(activeStreamId.value);
    }

    abortActiveRender();

    activeStreamId.value = msgId;
    activeEpoch.value += 1;
    streamReceiveFinished.value = false;
    messagebox.value = '';
    messageQueue = [];

    if (!message.finish) {
      messageQueue.push(message);
    } else {
      streamReceiveFinished.value = true;
    }

    return createContext();
  }

  function enqueueActiveStreamMessage(message) {
    if (message.finish) {
      streamReceiveFinished.value = true;
      return;
    }

    messageQueue.push(message);
  }

  function shouldIgnoreMessage(message) {
    return staleStreamIds.has(message.id);
  }

  function hasPendingMessages() {
    return messageQueue.length > 0;
  }

  function isReceiveFinished() {
    return streamReceiveFinished.value;
  }

  function shiftNextMessage(expectedId) {
    const currentMsg = messageQueue[0];
    if (!currentMsg) {
      return null;
    }

    messageQueue.shift();
    if (currentMsg.id !== expectedId) {
      return null;
    }

    return currentMsg;
  }

  async function updateMessage(msg, signal) {
    for (const ch of msg) {
      if (signal.aborted) {
        return;
      }

      messagebox.value += ch;

      try {
        await cancellableDelay(isChinese(ch) ? 180 : 70, signal);
      } catch (error) {
        if (error?.name === 'AbortError') {
          return;
        }
        throw error;
      }

      if (signal.aborted) {
        return;
      }

      if (onChunkRendered) {
        await onChunkRendered();
      }
    }
  }

  function resetStream() {
    abortActiveRender();
    activeStreamId.value = '';
    activeEpoch.value = 0;
    streamReceiveFinished.value = false;
    staleStreamIds.clear();
    messageQueue = [];
    messagebox.value = '';
  }

  function cancellableDelay(ms, signal) {
    return new Promise((resolve, reject) => {
      if (signal.aborted) {
        reject(new DOMException('Aborted', 'AbortError'));
        return;
      }

      const timeoutId = setTimeout(() => {
        if (!signal.aborted) {
          resolve();
        }
      }, ms);

      signal.addEventListener('abort', () => {
        clearTimeout(timeoutId);
        reject(new DOMException('Aborted', 'AbortError'));
      }, { once: true });
    });
  }

  return {
    messagebox,
    activeStreamId,
    activeEpoch,
    abortActiveRender,
    ensureAbortController,
    startNewStream,
    enqueueActiveStreamMessage,
    shouldIgnoreMessage,
    hasPendingMessages,
    isReceiveFinished,
    shiftNextMessage,
    updateMessage,
    resetStream,
  };
}

export default useInterruptibleStreamText;
