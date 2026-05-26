package com.example.myapplication;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.Service;
import android.content.Intent;
import android.content.pm.ServiceInfo;
import android.os.Build;
import android.os.IBinder;
import android.util.Log;

import com.alibaba.fastjson.JSONArray;
import com.alibaba.fastjson.JSONObject;
import com.alibaba.fastjson.JSONPath;
import com.example.myapplication.network.BackendApi;
import com.example.myapplication.tcp.CommonUtil;
import com.example.myapplication.view.FrameDataBus;
import com.example.myapplication.tcp.Message;

import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.Socket;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.stream.Collectors;

import okhttp3.OkHttpClient;
import okhttp3.Request;
import okhttp3.Response;
import okhttp3.WebSocket;
import okhttp3.WebSocketListener;

public class MyBackgroundService extends Service {

    private static final String TAG = "MyBackgroundService";
    private static final String NOTIFICATION_CHANNEL_ID = "TcpServiceChannel";
    private static final int NOTIFICATION_ID = 1;
    private static final String ASR_WEBSOCKET_URL = "ws://" + AppConstants.SERVER_IP + ":8000/ws/asr_ifly?deviceid=%s";

    // 鲁班猫设备IP，需要根据设备网络环境修改
    private static final String DEVICE_IP = "localhost"; // 替换为你的设备IP
    // 固定端口
    private static final int DEVICE_PORT = 19199;

    private ExecutorService executorService; // 用于管理后台线程
    private Socket tcpSocket;
    private BackendApi backendApi;
    private OkHttpClient asrWsClient;
    private WebSocket asrWebSocket;
    private final Object wsLock = new Object();

    private boolean interrupted = false;

    // iat结果缓存，用于缓存指定sid的所有识别结果帧结果，用于动态修正
    private final Map<String, List<String>> aiuiIatResultCache = new HashMap<>();

    /**
     * 计算校验码
     * 逻辑来源于MMPSocketDemo.java
     *
     * @param data 消息数据，包含消息描述和消息内容
     * @return
     */
    private static int calCode(byte[] data) { // 保持 static 与 MMPSocketDemo 一致
        int sum = 0;
        for (int i = 0; i < data.length; i++) {
            sum += data[i];
        }
        int calCode = (~sum + 1) & 0xFF;
        return calCode;
    }

    /**
     * 构造指定消息id的确认消息
     * 逻辑来源于MMPSocketDemo.java
     *
     * @param msgId 接收到的消息id
     * @return 确认消息数据
     */
    public static byte[] makeConfirmMsg(int msgId) { // 保持 static 与 MMPSocketDemo 一致
        try (ByteArrayOutputStream data = new ByteArrayOutputStream()) {
            // 确认消息内容固定
            byte[] messageContent = new byte[]{(byte) 0xA5, 0, 0, 0};
            data.write(0xA5); // Header
            data.write(0x01); // UserId
            data.write(0xFF); // MsgType (Confirm)
            data.write(toLittleEndianHex(messageContent.length)); // MsgLen
            data.write(toLittleEndianHex(msgId)); // MsgId
            data.write(messageContent); // Content
            data.write(calCode(data.toByteArray())); // Checksum (调用本类中的 static calCode)
            return data.toByteArray();
        } catch (IOException e) {
            Log.e(TAG, "Error making confirm message: " + e.getMessage());
        }
        return null;
    }

    /**
     * 将16进制数据转换成数字 (小端序)
     * 逻辑来源于MMPSocketDemo.java
     */
    private static int fromLittleEndianHex(byte[] data) {
        return (data[1] << 8) | (data[0] & 0xFF);
    }

    /**
     * 将数字转换成16进制数据 (小端序)
     * 逻辑来源于MMPSocketDemo.java
     */
    private static byte[] toLittleEndianHex(int value) {
        return new byte[]{(byte) (value & 0xFF), (byte) ((value >> 8) & 0xFF)};
    }

    @Override
    public void onCreate() {
        super.onCreate();
        executorService = Executors.newCachedThreadPool();
        backendApi = new BackendApi(getApplicationContext());
        asrWsClient = new OkHttpClient.Builder()
                .pingInterval(30, java.util.concurrent.TimeUnit.SECONDS)
                .build();

//        executorService.submit(() -> {
//            boolean success = backendApi.registerDevice();
//            if (success) {
//                Log.d(TAG, "device register success");
//            } else {
//                Log.e(TAG, "Failed to register device.");
//            }
//        });

    }

    @Override
    public int onStartCommand(Intent intent, int flags, int startId) {
        Log.d(TAG, "Service onStartCommand");
        createNotificationChannel();
        Notification notification = createNotification();

        int serviceType = ServiceInfo.FOREGROUND_SERVICE_TYPE_DATA_SYNC | ServiceInfo.FOREGROUND_SERVICE_TYPE_REMOTE_MESSAGING;
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            startForeground(NOTIFICATION_ID, notification, serviceType); // 启动为前台服务
        } else {
            startForeground(NOTIFICATION_ID, notification);
        }


//        ServiceCompat.startForeground(NOTIFICATION_ID, notification); // 启动为前台服务

        // 在新线程中执行 TCP 通信，避免阻塞主线程
        executorService.submit(this::startTcpCommunication);

        // 如果服务被系统杀死后需要重启，请返回 START_STICKY
        return START_STICKY;
    }

    private void createNotificationChannel() {
        NotificationChannel serviceChannel = new NotificationChannel(
                NOTIFICATION_CHANNEL_ID,
                "TCP 通信服务",
                NotificationManager.IMPORTANCE_DEFAULT
        );
        NotificationManager manager = getSystemService(NotificationManager.class);
        if (manager != null) {
            manager.createNotificationChannel(serviceChannel);
        }
    }

    private Notification createNotification() {
        return new Notification.Builder(this, NOTIFICATION_CHANNEL_ID)
                .setContentTitle("AIUI TCP 服务")
                .setContentText("正在连接设备并处理AIUI消息...")
                .setSmallIcon(android.R.drawable.ic_dialog_info) // 设置一个小图标
                .build();
    }

    private void startTcpCommunication() {
        while (!Thread.currentThread().isInterrupted()) { // 持续运行，直到线程中断
            try {
                Log.d(TAG, "Attempting to connect to TCP device: " + DEVICE_IP + ":" + DEVICE_PORT);
                tcpSocket = new Socket(DEVICE_IP, DEVICE_PORT);
                InputStream reader = tcpSocket.getInputStream();
                OutputStream writer = tcpSocket.getOutputStream();
                Log.d(TAG, "Successfully connected to TCP device.");

                while (!Thread.currentThread().isInterrupted() && tcpSocket.isConnected() && !tcpSocket.isClosed()) {
                    Message message = readFrame(reader);
                    // 根据MMPSocketDemo的逻辑，如果msgLen<=0，可能是数据不完整或者错误，直接continue并等待
                    if (message.getMsgLen() <= 0) {
                        Thread.sleep(3000);
                        continue;
                    }

                    // 使用Message中已转换为int的字段进行比较
                    if (0xA5 != message.getHeader() || 0x01 != message.getUserId()) {
                        Log.w(TAG, "unsupport header or userId: " + CommonUtil.byteToHexString((byte) message.getHeader()) + ", " + CommonUtil.byteToHexString((byte) message.getUserId()));
                        continue; // 其他消息不解析
                    }

                    byte[] content = message.getContent();
                    int msgType = message.getMsgType();
                    int msgId = message.getMsgId();

                    switch (msgType) {
                        case 0x01: // 握手请求
                            Log.d(TAG, "连接建立成功！");
                            // 回复确认消息
                            break;
                        case 0x04: // AIUI消息
                            byte[] originalData = CommonUtil.decompress(content);
                            if (originalData == null) {
                                Log.e(TAG, "Failed to decompress AIUI message content.");
                                break;
                            }
                            JSONObject aiuiMessage = JSONObject.parseObject(new String(originalData, StandardCharsets.UTF_8));
                            String type = aiuiMessage.getString("type");
                            if (Objects.equals("aiui_event", type)) {
                                parseAiuiEvent(aiuiMessage);
                            } else if (Objects.equals("speech_device_status", type)) {
                                Log.d(TAG, "多模态设备状态：" + aiuiMessage.toJSONString());
                            } else {
                                Log.d(TAG, "aiui message type:" + type);
                            }
                            break;
                        default:
                            Log.w(TAG, "unsupport msgType: " + msgType);
                            continue;
                    }

                    byte[] confirmMessage = makeConfirmMsg(msgId);
                    if (confirmMessage != null) {
                        writer.write(confirmMessage);
                        writer.flush();
                    }
                }
            } catch (IOException e) {
                Log.e(TAG, "TCP connection error: " + e.getMessage());
                // 连接断开或错误，尝试重连
                try {
                    if (tcpSocket != null && !tcpSocket.isClosed()) {
                        tcpSocket.close();
                    }
                } catch (IOException ex) {
                    Log.e(TAG, "Error closing socket: " + ex.getMessage());
                }
                tcpSocket = null; // 重置socket
                // 等待一段时间后重试
                try {
                    Thread.sleep(5000); // 5秒后重连
                } catch (InterruptedException ie) {
                    Thread.currentThread().interrupt(); // 重新设置中断状态
                    Log.d(TAG, "TCP reconnection wait interrupted.");
                    break; // 退出循环
                }
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt(); // 重新设置中断状态
                Log.d(TAG, "TCP communication interrupted.");
                break; // 退出循环
            } catch (Exception e) {
                Log.e(TAG, "General error in TCP communication loop: " + e.getMessage(), e);
                // 捕获其他异常，避免服务崩溃
                try {
                    Thread.sleep(5000); // 5秒后重试
                } catch (InterruptedException ie) {
                    Thread.currentThread().interrupt(); // 重新设置中断状态
                    Log.d(TAG, "General error wait interrupted.");
                    break; // 退出循环
                }
            }
        }
        Log.d(TAG, "TCP communication loop stopped.");
    }

    /**
     * 解析AIUI结果事件
     * 此方法实现iat结果的解析，并发送给后端服务器
     * 其他AIUI消息类型按MMPSocketDemo的日志记录方式处理
     *
     * @param aiuiMessage AIUI事件
     */
    private void parseAiuiEvent(JSONObject aiuiMessage) {
        JSONObject content = aiuiMessage.getJSONObject("content");
        Integer eType = content.getInteger("eventType");

        if (eType == 2) { // 错误信息
            Log.e(TAG, "AIUI错误信息：" + aiuiMessage.toJSONString());
            return;
        }
        if (eType == 4) { // 唤醒事件
            Log.d(TAG, "唤醒事件触发：" + content.toJSONString());
            return;
        }

        if (eType != 1) { // 只处理 eventType == 1 的 AIUI 结果事件
            return;
        }

        Object so = JSONPath.eval(content, "$.info.data[0].params.sub");
        if (so == null) {
            return;
        }
        String sub = (String) so;
        JSONObject result = content.getJSONObject("result");
        String sid = result.getString("sid");
        if (sid == null || sid.length() == 0) {
            return;
        }

        switch (sub) {
            case "iat": // 识别结果
                List<String> iatRes = aiuiIatResultCache.get(sid);
                if (iatRes == null) {
                    iatRes = new ArrayList<>();
                    // 新的会话开始时，重置打断状态
                    interrupted = false;
                    aiuiIatResultCache.put(sid, iatRes);
                }

                // 当前帧的识别结果
                StringBuilder curIatText = new StringBuilder();
                JSONObject iatResText = result.getJSONObject("text");
                JSONArray wss = iatResText.getJSONArray("ws");
                if (wss != null) {
                    for (int i = 0; i < wss.size(); i++) {
                        JSONObject ws = wss.getJSONObject(i);
                        JSONArray cws = ws.getJSONArray("cw");
                        if (cws != null) {
                            for (int j = 0; j < cws.size(); j++) {
                                JSONObject cs = cws.getJSONObject(j);
                                curIatText.append(cs.getString("w"));
                            }
                        }
                    }
                }

                String pgs = iatResText.getString("pgs");
                if (Objects.equals("rpl", pgs)) {
                    JSONArray rg = iatResText.getJSONArray("rg");
                    if (rg != null && rg.size() >= 2) {
                        int start = rg.getIntValue(0);
                        int end = rg.getIntValue(1);
                        for (int i = start - 1; i < end && i < iatRes.size(); i++) {
                            iatRes.set(i, "");
                        }
                    }
                }
                iatRes.add(curIatText.toString());

                Boolean ls = iatResText.getBoolean("ls");
                if (Objects.equals(true, ls)) {
                    String finalResult = iatRes.stream().collect(Collectors.joining());
                    Log.i(TAG, "最终识别结果: " + finalResult);
                    aiuiIatResultCache.remove(sid);
                    interrupted = false;

                    // 最终结果触发后推送一次空值，通知前端清空中间态
                    sendIntermediateResultOverWebSocket("", true);

                    // ***** 在这里发送最终识别结果到后端服务器 *****
                    // 确保在单独的线程中执行网络请求
                   executorService.submit(() -> {
                       if (finalResult.isEmpty()) {
                           Log.e(TAG, "empty result");
                           return;
                       }
                       boolean success = backendApi.uploadAiuiResult(finalResult);
                       if (success) {
                           Log.d(TAG, "AIUI result uploaded to backend successfully.");
                       } else {
                           Log.e(TAG, "Failed to upload AIUI result to backend.");
                       }
                   });
                    // ********************************************

                } else {
                    String intermediateResult = iatRes.stream().collect(Collectors.joining());
                    Log.d(TAG, "识别中间结果: " + intermediateResult);
                    if (!intermediateResult.isEmpty()) {
                        sendIntermediateResultOverWebSocket(intermediateResult);
                        Log.d(TAG, "send to WebView, listener is " + (FrameDataBus.getAsrIntermediateListener() != null ? "not null" : "null"));
                        if (FrameDataBus.getAsrIntermediateListener() != null) {
                            FrameDataBus.getAsrIntermediateListener().invoke(intermediateResult);
                        }
                    }
                    if (!interrupted && !intermediateResult.isEmpty()) {
                        executorService.submit(() -> {
                            boolean success = backendApi.interruptDigitalman();
                            if (success) {
                                Log.d(TAG, "interrupt successfully.");
                                interrupted = true;
                            } else {
                                Log.e(TAG, "Failed to interrupt");
                            }
                        });
                    }
                }
                break;
            case "cbm_semantic": // MMPSocketDemo.java 中有的其他类型处理
                Log.d(TAG, "技能或自定义问答结果: " + result.toJSONString());
                break;
            case "nlp": // MMPSocketDemo.java 中有的其他类型处理
                Log.d(TAG, "语义结果: " + result.toJSONString());
                break;
            case "cbm_knowledge": // MMPSocketDemo.java 中有的其他类型处理
                Log.d(TAG, "知识图谱结果: " + result.toJSONString());
                break;
            case "tts": // MMPSocketDemo.java 中有的其他类型处理
                Log.d(TAG, "语音合成数据: " + result.toJSONString());
                break;
            case "keywords": // MMPSocketDemo.java 中有的其他类型处理
                Log.d(TAG, "关键词数据: " + result.toJSONString());
                break;
            default:
                Log.d(TAG, "其他语义结果 (" + sub + "): " + result.toJSONString());
                break;
        }
    }

    /**
     * 读取一个消息帧
     * 逻辑基本来源于MMPSocketDemo.java
     *
     * @param inputStream 输入流
     * @return 读取到的数据帧
     */
    private Message readFrame(InputStream inputStream) throws IOException {
        // 数据描述
        byte[] meta = readExpectLengthData(inputStream, 7);

        byte headerByte = meta[0];
        byte userIdByte = meta[1];
        byte msgTypeByte = meta[2];
        // 解析消息长度和消息ID
        int msgLen = fromLittleEndianHex(Arrays.copyOfRange(meta, 3, 5));
        int msgId = fromLittleEndianHex(Arrays.copyOfRange(meta, 5, 7));
        //Log.d(TAG, "同步头: " + CommonUtil.byteToHexString(headerByte) + ", 用户ID: " + CommonUtil.byteToHexString(userIdByte) + ", 消息类型: " + CommonUtil.byteToHexString(msgTypeByte) + ", 消息长度: " + msgLen + ", 消息ID: " + msgId);

        // 根据消息长度读取消息内容
        byte[] msgContent = readExpectLengthData(inputStream, msgLen);
        // 校验码
        int code = inputStream.read();
        if (code == -1) { // 流已结束
            throw new IOException("Stream ended unexpectedly during checksum read.");
        }
        if (!checkCode(meta, msgContent, code)) {
            Log.e(TAG, "校验码不匹配！");
            // MMPSocketDemo 在校验失败时返回 new Message()
            return new Message();
        }

        // 使用Message中带byte参数的构造函数，CommonUtil.byteToUnsignedInt()会在Message内部完成
        return new Message(headerByte, userIdByte, msgTypeByte, msgLen, msgId, msgContent, code);
    }

    /**
     * 从socket读取预取长度的数据
     * 逻辑来源于MMPSocketDemo.java
     *
     * @param inputStream 输入流
     * @param len         预期数据长度
     * @return 读取到的数据
     * @throws IOException
     */
    private byte[] readExpectLengthData(InputStream inputStream, int len) throws IOException {
        byte[] data = new byte[len];
        int read = 0;
        while (read < len) {
            int r = inputStream.read(data, read, len - read);
            if (r == -1) {
                // socket关闭，可能是服务端重启
                throw new IOException("read -1 socket closed or stream ended prematurely");
            }
            read += r;
        }
        if (read != len) {
            throw new RuntimeException("数据不完整，预期长度：" + len + "，实际读取：" + read);
        }
        return data;
    }

    /**
     * 校验code
     * 逻辑来源于MMPSocketDemo.java
     *
     * @param meta       7个字节消息描述
     * @param msgContent 消息内容数据
     * @param code       校验码
     * @return
     */
    private boolean checkCode(byte[] meta, byte[] msgContent, int code) {
        byte[] data = CommonUtil.mergeArray(meta, msgContent);
        int calCode = calCode(data);

        boolean res = calCode == code;
        if (!res) {
            Log.e(TAG, "校验码校验失败：" + code + "|" + calCode);
            Log.e(TAG, "消息数据：" + Arrays.toString(data));
        }
        return res;
    }

    @Override
    public void onDestroy() {
        super.onDestroy();
        Log.d(TAG, "Service onDestroy");
        if (executorService != null) {
            executorService.shutdownNow(); // 尝试关闭所有正在运行的任务
        }
        try {
            if (tcpSocket != null && !tcpSocket.isClosed()) {
                tcpSocket.close();
            }
        } catch (IOException e) {
            Log.e(TAG, "Error closing socket in onDestroy: " + e.getMessage());
        } finally {
            closeAsrWebSocket();
        }
        Log.d(TAG, "TCP socket closed in onDestroy.");
    }

    @Override
    public IBinder onBind(Intent intent) {
        return null; // 此服务不需要绑定
    }

    private void sendIntermediateResultOverWebSocket(String text) {
        sendIntermediateResultOverWebSocket(text, false);
    }

    private void sendIntermediateResultOverWebSocket(String text, boolean allowEmpty) {
        if (text == null) {
            return;
        }
        if (!allowEmpty && text.isEmpty()) {
            return;
        }
        ensureAsrWebSocket();
        WebSocket socket;
        synchronized (wsLock) {
            socket = asrWebSocket;
        }
        if (socket == null) {
            Log.e(TAG, "ASR WebSocket 尚未建立，无法发送中间结果。");
            return;
        }
        JSONObject payload = new JSONObject();
        payload.put("text", text);
        boolean enqueued = socket.send(payload.toJSONString());
        if (!enqueued) {
            Log.e(TAG, "ASR WebSocket 发送失败，重置连接。");
            resetAsrWebSocket();
        }
    }

    private void ensureAsrWebSocket() {
        synchronized (wsLock) {
            if (asrWsClient == null) {
                asrWsClient = new OkHttpClient.Builder()
                        .pingInterval(30, java.util.concurrent.TimeUnit.SECONDS)
                        .build();
            }
            if (asrWebSocket != null) {
                return;
            }
            String deviceId = backendApi != null ? backendApi.getDeviceId() : "";
            if (deviceId == null) {
                deviceId = "";
            }
            Request request = new Request.Builder()
                    .url(String.format(ASR_WEBSOCKET_URL, deviceId))
                    .build();
            asrWebSocket = asrWsClient.newWebSocket(request, new WebSocketListener() {
                @Override
                public void onOpen(WebSocket webSocket, Response response) {
                    Log.d(TAG, "ASR WebSocket 已连接");
                }

                @Override
                public void onFailure(WebSocket webSocket, Throwable t, Response response) {
                    Log.e(TAG, "ASR WebSocket 连接失败: " + t.getMessage(), t);
                    clearWebSocketReference(webSocket);
                }

                @Override
                public void onClosed(WebSocket webSocket, int code, String reason) {
                    Log.d(TAG, "ASR WebSocket 已关闭: " + reason);
                    clearWebSocketReference(webSocket);
                }
            });
        }
    }

    private void resetAsrWebSocket() {
        synchronized (wsLock) {
            if (asrWebSocket != null) {
                asrWebSocket.cancel();
                asrWebSocket = null;
            }
        }
    }

    private void closeAsrWebSocket() {
        synchronized (wsLock) {
            if (asrWebSocket != null) {
                asrWebSocket.close(1000, "service destroy");
                asrWebSocket = null;
            }
        }
    }

    private void clearWebSocketReference(WebSocket webSocket) {
        synchronized (wsLock) {
            if (asrWebSocket == webSocket) {
                asrWebSocket = null;
            }
        }
    }
}
