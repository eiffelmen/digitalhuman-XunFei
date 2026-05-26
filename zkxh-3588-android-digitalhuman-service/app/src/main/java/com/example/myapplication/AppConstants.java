package com.example.myapplication;

public class AppConstants {
    public final static String SERVER_IP = BuildConfig.SERVER_IP;

    // 音频设备（RK3588多模态盒子）IP与端口（可根据串口查询IP后设置）
    // NOTE: 设备为动态 IP 时，建议通过串口指令获取后写入此处，或在运行时从配置中读取。
    public final static String AUDIO_DEVICE_IP = BuildConfig.AUDIO_DEVICE_IP;
    public final static int AUDIO_DEVICE_PORT = 9080;

    // ASR 服务地址（wss）。如为自签证书，请使用安全证书或在客户端侧明确信任策略。
    public final static String ASR_WS_URL = "ws://" + SERVER_IP + ":10095";
    // ASR 发送分片的目标时长（毫秒）。根据需求，[5,10,5] 可表示范围，这里选用 10ms
    public final static int ASR_CHUNK_MS = 10; // 10ms，对应 16000Hz 下每片 160 样本（320字节）
}
