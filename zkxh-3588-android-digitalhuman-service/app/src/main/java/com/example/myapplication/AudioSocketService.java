package com.example.myapplication;

import android.app.Service;
import android.content.Intent;
import android.os.IBinder;
import android.util.Log;

import androidx.annotation.Nullable;

import java.io.DataInputStream;
import java.io.IOException;
import java.net.Socket;
import java.nio.ByteBuffer;
import java.nio.ByteOrder;

import com.example.myapplication.network.BackendApi;

/**
 * 音频转流服务（Android 前台服务）：
 * - 建立到设备（RK3588 多模态盒子）的 TCP 连接（端口 9080）。
 * - 按你提供的 8.2/8.4/8.5 协议解析音频帧（消息类型 0x0a）。
 * - 提取 VAD 状态、帧号、以及 16k 16bit 单通道小端 PCM 音频数据。
 * - 根据 VAD：开始/持续/结束，说话周期内将音频分片转发到 ASR WebSocket 服务。
 *
 * 协议回顾：
 * 头部（9 字节 + 校验位）
 *  [0] 同步头 0xA5
 *  [1] 用户ID 0x01
 *  [2] 消息类型 0x0a（音频帧）
 *  [3~6] 消息数据长度（4 字节，小端 LE）
 *  [7~8] 消息ID（2 字节，小端 LE）
 *  [9~n] 消息数据 payload
 *  [n+1] 校验位（固定 0x00）
 *
 * 音频帧 payload：
 *  [0]  vad 状态（0 静音，1 开始，2 持续，3 结束）
 *  [1]  通道号（多人版本标识说话人）
 *  [2-3] 保留（0x00）
 *  [4-7] 帧号（4 字节，小端 LE）
 *  [8..] 16k 16bit 单通道 PCM（LE）
 */
public class AudioSocketService extends Service {
    private static final String TAG = "AudioSocketService";

    private volatile boolean running = false;
    private Thread socketThread;
    private Socket socket;
    private DataInputStream input;

    // ASR 客户端
    private AsrWebSocketClient asrClient;

    // PCM 缓存区（样本级 short[]），用于按 chunk 分片发送
    private short[] pcmBuffer = new short[0];
    private BackendApi backendApi;

    // 采样率与每片样本数（16kHz）
    private static final int SAMPLE_RATE = 16000;
    private static final int CHUNK_MS = AppConstants.ASR_CHUNK_MS; // 默认 10ms
    private static final int CHUNK_SAMPLES = SAMPLE_RATE * CHUNK_MS / 1000; // 160 样本

    @Nullable
    @Override
    public IBinder onBind(Intent intent) { return null; }

    @Override
    public int onStartCommand(Intent intent, int flags, int startId) {
        start();
        return START_STICKY;
    }

    @Override
    public void onDestroy() {
        stop();
        super.onDestroy();
    }

    /**
     * 启动服务：
     * - 准备 ASR WebSocket 客户端并连接。
     * - 启动后台线程，连接设备 TCP 并循环读取音频帧数据。
     */
    private void start() {
        if (running) return;
        running = true;

        backendApi = new BackendApi(getApplicationContext());
        asrClient = new AsrWebSocketClient(new AsrWebSocketClient.AsrListener() {
            @Override public void onOpen() { Log.d(TAG, "ASR connected"); }
            @Override public void onPartialResult(String text) { Log.d(TAG, "ASR partial:" + text); }
            @Override public void onFinalResult(String text) {
                Log.d(TAG, "ASR final:" + text);
                uploadAsrResult(text);
            }
            @Override public void onError(String error) { Log.e(TAG, "ASR error:" + error); }
            @Override public void onClosed(String reason) { Log.d(TAG, "ASR closed:" + reason); }
        });
        asrClient.connect();

        socketThread = new Thread(() -> {
            try {
                socket = new Socket(AppConstants.AUDIO_DEVICE_IP, AppConstants.AUDIO_DEVICE_PORT);
                input = new DataInputStream(socket.getInputStream());

                while (running) {
                    // 基础头部长度检查（至少 9 字节：类型3 + 长度4 + 消息ID2）
                    if (input.available() < 9) {
                        try { Thread.sleep(5); } catch (InterruptedException ignored) {}
                        continue;
                    }

                    byte sync = input.readByte();      // 0xA5 同步头
                    byte userId = input.readByte();    // 0x01 用户ID
                    byte msgType = input.readByte();   // 0x0a 音频帧消息类型

                    // 消息数据长度：4 字节小端 LE
                    byte[] lenBytes = new byte[4];
                    input.readFully(lenBytes);
                    int msgLen = ByteBuffer.wrap(lenBytes).order(ByteOrder.LITTLE_ENDIAN).getInt();

                    // 消息ID：2 字节小端 LE
                    byte[] msgIdBytes = new byte[2];
                    input.readFully(msgIdBytes);
                    int msgId = ByteBuffer.wrap(msgIdBytes).order(ByteOrder.LITTLE_ENDIAN).getShort() & 0xFFFF;

                    // 读取消息数据 payload
                    byte[] payload = new byte[msgLen];
                    input.readFully(payload);

                    // 校验位（固定 0x00）。当前单工模式下不用检查。
                    byte checksum = input.readByte();

                    if ((sync & 0xFF) != 0xA5 || (userId & 0xFF) != 0x01) {
                        Log.w(TAG, "invalid header/userId:" + Integer.toHexString(sync & 0xFF) + "," + Integer.toHexString(userId & 0xFF));
                        continue;
                    }

                    if ((msgType & 0xFF) == 0x0a) {
                        handleAudioFrame(payload);
                    } else {
                        // 其他消息忽略
                    }
                }
            } catch (Exception e) {
                Log.e(TAG, "Audio socket error:" + e.getMessage(), e);
            } finally {
                try { if (socket != null) socket.close(); } catch (IOException ignored) {}
            }
        }, "AudioSocketThread");
        socketThread.start();
    }

    private void stop() {
        running = false;
        try { if (socket != null) socket.close(); } catch (IOException ignored) {}
        if (socketThread != null) socketThread.interrupt();
        if (asrClient != null) asrClient.close();
    }

    /**
     * 解析音频帧消息数据并根据 VAD 控制转流：
     * [0]  vad (1 byte)
     * [1]  channel (1 byte)
     * [2-3] 保留(0x00)
     * [4-7] 帧号 (LE 4 bytes)
     * [8..] PCM 音频数据（16k 16bit 单通道 LE）
     */
    private void handleAudioFrame(byte[] payload) {
        if (payload == null || payload.length < 8) return;
        int vad = payload[0] & 0xFF;
        int channel = payload[1] & 0xFF;
        // 保留位 payload[2], payload[3]
        int frameId = ByteBuffer.wrap(payload, 4, 4).order(ByteOrder.LITTLE_ENDIAN).getInt();

        // 调试信息：打印VAD状态和音频数据长度
//        Log.d(TAG, "VAD state: " + vad + ", frameId: " + frameId + ", audio bytes: " + (payload.length - 8));

        // PCM 数据
        int audioOffset = 8;
        int audioLenBytes = payload.length - audioOffset;
        if (audioLenBytes <= 0 || audioLenBytes % 2 != 0) {
            Log.w(TAG, "invalid audio length:" + audioLenBytes);
            return;
        }

        // 将小端字节序的 PCM 数据解码为 short[]（每个样本 2 字节）
        short[] samples = new short[audioLenBytes / 2];
        ByteBuffer bb = ByteBuffer.wrap(payload, audioOffset, audioLenBytes).order(ByteOrder.LITTLE_ENDIAN);
        for (int i = 0; i < samples.length; i++) {
            samples[i] = bb.getShort();
        }

        // 将大的音频帧拆分成10ms的小帧（160样本 = 320字节）
        int chunkSize = CHUNK_SAMPLES; // 160样本
        int chunkBytes = chunkSize * 2; // 320字节

//        Log.d(TAG, "Splitting " + samples.length + " samples into " + chunkSize + " sample chunks");

        for (int i = 0; i < samples.length; i += chunkSize) {
            int remaining = samples.length - i;
            int currentChunkSize = Math.min(chunkSize, remaining);

            short[] chunkSamples = new short[currentChunkSize];
            System.arraycopy(samples, i, chunkSamples, 0, currentChunkSize);

//            Log.d(TAG, "Sending chunk " + (i/chunkSize + 1) + "/" + ((samples.length + chunkSize - 1) / chunkSize) + ", size: " + currentChunkSize + " samples");

            switch (vad) {
                case 0: // 静音片段
                    // 可选择不发送或作为环境噪声
                    break;
                case 1: // 开始说话
                    onVadStart(); // 发送首包（is_speaking=true）
                    appendPcm(chunkSamples);
                    flushChunksIfReady();
                    break;
                case 2: // 持续说话
                    appendPcm(chunkSamples);
                    flushChunksIfReady();
                    break;
                case 3: // 结束说话
                    appendPcm(chunkSamples); // 可能尾部还有音频
                    flushChunksIfReady();
                    onVadEnd(); // 发送结束包（final=true，is_speaking=false）
                    break;
                default:
                    appendPcm(chunkSamples);
                    flushChunksIfReady();
            }
        }
    }

    /**
     * 处理 VAD 开始：
     * - 确保 ASR WS 已连接。
     * - 未处于会话中则发送首包控制消息。
     */
    private void onVadStart() {
        // 首次或新一轮会话开始时发送首包
        if (!asrClient.isConnected()) {
            asrClient.connect();
        }
        if (!asrClient.isSpeaking() && !asrClient.hasPendingStart()) {
            asrClient.sendStart();
        }
    }

    /**
     * 处理 VAD 结束：
     * - 发送结束控制消息。
     * - 清空缓存。
     */
    private void onVadEnd() {
        flushChunksIfReady();
        if (pcmBuffer.length > 0) {
            asrClient.sendAudioChunk(pcmBuffer, 0, pcmBuffer.length);
        }
        pcmBuffer = new short[0];
        // 发送结束控制消息
        asrClient.sendFinal(CHUNK_SAMPLES);
    }

    /**
     * 追加 PCM 样本到内存缓冲区（short[]）。
     * 注意：生产环境可优化为环形缓冲，避免数组频繁复制导致内存抖动。
     */
    private void appendPcm(short[] samples) {
        if (samples == null || samples.length == 0) return;
        short[] merged = new short[pcmBuffer.length + samples.length];
        System.arraycopy(pcmBuffer, 0, merged, 0, pcmBuffer.length);
        System.arraycopy(samples, 0, merged, pcmBuffer.length, samples.length);
        pcmBuffer = merged;
    }

    /**
     * 当缓冲区中样本数达到一个或多个分片时，逐片发送至 ASR。
     * 分片大小：CHUNK_SAMPLES = 16000 * CHUNK_MS / 1000（默认 CHUNK_MS=10ms，对应 160 样本）。
     */
    private void flushChunksIfReady() {
        // 连续发送完整的分片
        int offset = 0;
        while (pcmBuffer.length - offset >= CHUNK_SAMPLES) {
            asrClient.sendAudioChunk(pcmBuffer, offset, CHUNK_SAMPLES);
            offset += CHUNK_SAMPLES;
        }
        // 保留未发送的尾部
        if (offset > 0) {
            short[] remain = new short[pcmBuffer.length - offset];
            System.arraycopy(pcmBuffer, offset, remain, 0, remain.length);
            pcmBuffer = remain;
        }
    }

    private void uploadAsrResult(String text) {
        if (backendApi == null || text == null || text.trim().isEmpty()) {
            return;
        }
        new Thread(() -> {
            boolean success = backendApi.uploadAiuiResult(text);
            Log.d(TAG, "uploadAiuiResult: " + success);
        }, "AsrUploadThread").start();
    }
}
