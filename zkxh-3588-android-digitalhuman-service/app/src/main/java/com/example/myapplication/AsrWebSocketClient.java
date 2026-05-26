package com.example.myapplication;

import android.util.Log;

import com.alibaba.fastjson.JSONObject;

import java.nio.ByteBuffer;
import java.nio.ByteOrder;
import java.util.concurrent.ConcurrentLinkedQueue;
import java.util.concurrent.atomic.AtomicBoolean;

import javax.net.ssl.X509TrustManager;
import javax.net.ssl.SSLSocketFactory;

import okhttp3.OkHttpClient;
import okhttp3.Request;
import okhttp3.WebSocket;
import okhttp3.WebSocketListener;
import okio.ByteString;

/**
 * ASR WebSocket 客户端：
 * - 负责连接 AppConstants.ASR_WS_URL。
 * - 按协议发送控制消息（首包、结束包）与二进制 PCM 音频分片。
 * - 简单解析服务端返回的识别结果（中间/最终）。
 *
 * 注意：
 * - 当前使用了“信任所有证书”的 OkHttpClient，以适配 IP + wss 的测试场景。
 *   生产环境务必替换为合法证书或正确的 CA 配置。
 */
public class AsrWebSocketClient {
    private static final String TAG = "AsrWebSocketClient";
    private static final int[] DEFAULT_CHUNK_SIZE = new int[]{5, 10, 5};

    private OkHttpClient client;
    private WebSocket webSocket;
    private final AtomicBoolean connected = new AtomicBoolean(false);
    private final AtomicBoolean speaking = new AtomicBoolean(false);
    private volatile JSONObject pendingStartPayload;
    private volatile Integer pendingFinalChunkSamples = null;
    private final ConcurrentLinkedQueue<byte[]> pendingAudioChunks = new ConcurrentLinkedQueue<>();

    /**
     * 识别回调接口，供上层服务记录日志或展示结果。
     */
    public interface AsrListener {
        void onOpen();
        void onPartialResult(String text);
        void onFinalResult(String text);
        void onError(String error);
        void onClosed(String reason);
    }

    private final AsrListener listener;

    public AsrWebSocketClient(AsrListener listener) {
        this.listener = listener;
        this.client = buildUnsafeOkHttpClient();
    }

    public boolean isConnected() { return connected.get(); }
    public boolean isSpeaking() { return speaking.get(); }

    /**
     * 连接 ASR WebSocket。
     */
    public void connect() {
        if (webSocket != null && connected.get()) return;
        Request request = new Request.Builder()
                .url(AppConstants.ASR_WS_URL)
                .addHeader("Sec-WebSocket-Protocol", "binary")
                .build();
        webSocket = client.newWebSocket(request, new WebSocketListener() {
            @Override
            public void onOpen(WebSocket ws, okhttp3.Response response) {
                connected.set(true);
                if (listener != null) listener.onOpen();
                Log.d(TAG, "ASR WebSocket connected");
                if (pendingStartPayload != null) {
                    JSONObject payload = pendingStartPayload;
                    pendingStartPayload = null;
                    sendStartInternal(payload);
                }
            }

            @Override
            public void onMessage(WebSocket webSocket, String text) {
                // 简单区分中间/最终结果：具体字段以 ASR 服务返回为准。
                try {
                    JSONObject obj = JSONObject.parseObject(text);
                    String mode = obj.getString("mode");
                    Boolean isFinal = obj.getBoolean("is_final");
                    if (isFinal == null) {
                        isFinal = obj.getBoolean("final");
                    }
                    String result = obj.getString("text");
                    if (result == null) {
                        result = obj.getString("result");
                    }
                    boolean treatAsFinal = (isFinal != null && isFinal)
                            || (mode != null && mode.toLowerCase().contains("offline"));
                    Log.d("yunzetest", "ASR message:" + result);
                    if (treatAsFinal) {
                        if (listener != null) listener.onFinalResult(result);
                    } else {
                        if (listener != null) listener.onPartialResult(result);
                    }
                } catch (Exception e) {
                    Log.w(TAG, "ASR message parse warn:" + e.getMessage());
                }
            }

            @Override
            public void onClosed(WebSocket webSocket, int code, String reason) {
                connected.set(false);
                speaking.set(false);
                pendingStartPayload = null;
                pendingFinalChunkSamples = null;
                pendingAudioChunks.clear();
                if (listener != null) listener.onClosed(reason);
                Log.d(TAG, "ASR WebSocket closed:" + reason);
            }

            @Override
            public void onFailure(WebSocket webSocket, Throwable t, okhttp3.Response response) {
                connected.set(false);
                speaking.set(false);
                pendingStartPayload = null;
                pendingFinalChunkSamples = null;
                pendingAudioChunks.clear();
                if (listener != null) listener.onError(t.getMessage());
                Log.e(TAG, "ASR WebSocket failure:" + t.getMessage(), t);
            }
        });
    }

    /**
     * 发送首包控制消息：
     * {"chunk_size":[5,10,5],"wav_name":"h5","wav_format":"pcm","is_speaking":true,"mode":"offline","itn":true,"final":false}
     * 其中 chunk_size 数组用于表征推荐的分片毫秒范围（示例值）。
     */
    public synchronized void sendStart() {
        JSONObject startPayload = buildStartPayload();
        if (!connected.get()) {
            pendingStartPayload = startPayload;
            connect();
            return;
        }
        sendStartInternal(startPayload);
    }

    private void sendStartInternal(JSONObject payload) {
        speaking.set(true);
        webSocket.send(payload.toJSONString());
        flushPendingAudio();
        if (pendingFinalChunkSamples != null) {
            sendFinalInternal(pendingFinalChunkSamples);
            pendingFinalChunkSamples = null;
        }
    }

    private JSONObject buildStartPayload() {
        JSONObject start = new JSONObject();
        start.put("chunk_size", DEFAULT_CHUNK_SIZE);
        start.put("wav_name", "h5");
        start.put("wav_format", "pcm");
        start.put("is_speaking", true);
        start.put("mode", "offline");
        start.put("itn", true);
        start.put("is_final", false);
        return start;
    }

    /**
     * 发送 PCM 音频分片（二进制，LE）：
     * - 采样率：16kHz
     * - 采样精度：16bit
     * - 通道：单通道
     * @param pcmShorts PCM 样本（short数组）
     * @param offset 起始偏移（样本）
     * @param length 发送长度（样本）
     */
    public void sendAudioChunk(short[] pcmShorts, int offset, int length) {
        if (pcmShorts == null || length <= 0 || offset < 0 || offset + length > pcmShorts.length) {
            return;
        }
        byte[] data = shortsToBytes(pcmShorts, offset, length);
        if (canStreamAudio()) {
            if (!sendBinary(data)) {
                pendingAudioChunks.offer(data);
            }
        } else {
            pendingAudioChunks.offer(data);
        }
        if (canStreamAudio() && !pendingAudioChunks.isEmpty()) {
            flushPendingAudio();
        }
    }

    /**
     * 会话结束控制消息：
     * {"chunk_size":chunkSamples,"wav_name":"h5","is_speaking":false,"chunk_interval":10,"mode":"offline","final":true}
     * 注意：此处 chunk_size 以样本数发送，与已有 H5 示例一致（例如 10ms -> 160 样本）。
     */
    public synchronized void sendFinal(int chunkSamples) {
        pendingFinalChunkSamples = chunkSamples;
        if (!canStreamAudio()) {
            return;
        }
        flushPendingAudio();
        sendFinalInternal(chunkSamples);
        pendingFinalChunkSamples = null;
    }

    public boolean canStreamAudio() {
        return connected.get() && speaking.get();
    }

    public boolean hasPendingStart() {
        return pendingStartPayload != null;
    }

    private byte[] shortsToBytes(short[] pcmShorts, int offset, int length) {
        ByteBuffer byteBuffer = ByteBuffer.allocate(length * 2).order(ByteOrder.LITTLE_ENDIAN);
        for (int i = 0; i < length; i++) {
            byteBuffer.putShort(pcmShorts[offset + i]);
        }
        return byteBuffer.array();
    }

    private boolean sendBinary(byte[] data) {
        if (webSocket == null || data == null || data.length == 0) {
            return false;
        }
        try {
            return webSocket.send(ByteString.of(data));
        } catch (Exception e) {
            Log.e(TAG, "sendBinary error:" + e.getMessage(), e);
            return false;
        }
    }

    private void flushPendingAudio() {
        if (!canStreamAudio()) {
            return;
        }
        byte[] chunk;
        while ((chunk = pendingAudioChunks.poll()) != null) {
            if (!sendBinary(chunk)) {
                pendingAudioChunks.offer(chunk);
                break;
            }
        }
    }

    private void sendFinalInternal(int chunkSamples) {
        JSONObject end = new JSONObject();
        end.put("chunk_size", DEFAULT_CHUNK_SIZE);
        end.put("wav_name", "h5");
        end.put("is_speaking", false);
        end.put("chunk_interval", 10);
        end.put("mode", "offline");
        end.put("is_final", true);
        webSocket.send(end.toJSONString());
        speaking.set(false);
    }

    /**
     * 关闭 WebSocket 连接。
     */
    public void close() {
        if (webSocket != null) {
            try {
                webSocket.close(1000, "normal close");
            } catch (Exception ignored) {}
        }
        connected.set(false);
        speaking.set(false);
        pendingStartPayload = null;
        pendingFinalChunkSamples = null;
        pendingAudioChunks.clear();
    }

    /**
     * 构建“信任所有证书”的 OkHttpClient（用于测试自签场景）。
     * 生产环境请替换为安全配置。
     */
    private OkHttpClient buildUnsafeOkHttpClient() {
        try {
            SSLSocketFactory factory = SSLSocketClient.getSSLSocketFactory();
            X509TrustManager trustManager = SSLSocketClient.getX509TrustManager();
            OkHttpClient.Builder builder = new OkHttpClient.Builder()
                    .sslSocketFactory(factory, trustManager)
                    .hostnameVerifier(SSLSocketClient.getHostnameVerifier());
            return builder.build();
        } catch (Exception e) {
            Log.e(TAG, "buildUnsafeOkHttpClient error:" + e.getMessage());
            return new OkHttpClient();
        }
    }
}
