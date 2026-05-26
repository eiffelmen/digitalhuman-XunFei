package com.example.myapplication;

import android.app.Service;
import android.content.Intent;
import android.os.IBinder;
import android.provider.Settings;
import android.util.Log;

import androidx.annotation.Nullable;

import com.example.myapplication.view.FrameDataBus;

import org.json.JSONArray;
import org.json.JSONException;
import org.json.JSONObject;

import java.io.ByteArrayOutputStream;
import java.io.DataInputStream;
import java.io.DataOutputStream;
import java.io.IOException;
import java.net.Socket;
import java.nio.ByteBuffer;
import java.nio.ByteOrder;
import java.util.UUID;

import okhttp3.OkHttpClient;
import okhttp3.Request;
import okhttp3.WebSocket;
import okhttp3.WebSocketListener;

/**
 * @author Hubowen
 * @date 2025/7/29.
 * description：
 */
public class ImageSocketService extends Service {

    private static final String TAG = "ImageSocketService";

    private Socket socket;
    private DataInputStream input;
    private DataOutputStream output;
    private Thread socketThread;

    private boolean isRunning = false;
    //指定端口
    private static final int PORT = 9090;
    //可通过发送串口指令来获取
    private static final String IP = "0.0.0.0";

    //websocket
    private WebSocket webSocket;
    private OkHttpClient client;
    //WebSocket地址
    private static final String BASE_WS_URL = "ws://"+ AppConstants.SERVER_IP +":8000/ws?type=app&id=";
    private static String WS_URL = "";


    @Nullable
    @Override
    public IBinder onBind(Intent intent) {
        return null; // 如果需要绑定服务，可以返回 Binder
    }

    @Override
    public int onStartCommand(Intent intent, int flags, int startId) {
        Log.d(TAG, "ImageSocketService is starting.");
        WS_URL = BASE_WS_URL + Settings.Secure.getString(getContentResolver(), Settings.Secure.ANDROID_ID);
        startSocket();
        initWebSocket();
        return START_STICKY;
    }

    @Override
    public void onDestroy() {
        Log.d(TAG, "ImageSocketService is being destroyed.");
        stopSocket();
        closeWebSocket();
        super.onDestroy();
    }

    private void closeWebSocket() {
        if (webSocket != null) {
            webSocket.close(1000, "Service destroyed");
            webSocket = null;
        }

        if (client != null) {
            client.dispatcher().executorService().shutdown();
            client = null;
        }
    }

    private void startSocket() {
        if (isRunning) {
            Log.d(TAG, "startSocket called, but it is already running.");
            return;
        }
        isRunning = true;

        socketThread = new Thread(() -> {
            // 使用循环来实现失败后自动重试
            while (isRunning) {
                try {
                    Log.d(TAG, "Attempting to connect to Socket at " + IP + ":" + PORT + "...");
                    socket = new Socket(IP, PORT);
                    Log.d(TAG, "Socket connection successful!");

                    // 连接成功后，跳出重试循环，开始处理数据
                    break;

                } catch (IOException e) {
                    Log.e(TAG, "Socket connection failed, will retry in 3 seconds. Reason: " + e.getMessage());

                    // 如果服务已被停止，则不再重试
                    if (!isRunning) {
                        return;
                    }

                    // 等待3秒再进行下一次尝试
                    try {
                        Thread.sleep(3000);
                    } catch (InterruptedException interruptedException) {
                        Log.d(TAG, "Socket retry thread was interrupted, exiting.");
                        return; // 退出线程
                    }
                }
            }

            // --- 连接成功后，执行下面的数据读取逻辑 ---
            if (!isRunning) {
                Log.d(TAG, "Socket connection was successful, but service is no longer running. Exiting data loop.");
                return;
            }

            Log.d(TAG, "Socket connection stable, entering data reading loop.");
            try {
                input = new DataInputStream(socket.getInputStream());
                output = new DataOutputStream(socket.getOutputStream());

                while (isRunning) {
                    if (input.available() < 9) {
                        Thread.sleep(10);
                        continue;
                    }

                    byte sync = input.readByte();     // 0xA5
                    byte userId = input.readByte();   // 0x01
                    byte msgType = input.readByte();  // 0x07, 0x08, 0x09, 0x0B, 0xFF

                    byte[] lenBytes = new byte[4];
                    input.readFully(lenBytes);
                    int msgLen = ByteBuffer.wrap(lenBytes).order(ByteOrder.LITTLE_ENDIAN).getInt();

                    byte[] msgIdBytes = new byte[2];
                    input.readFully(msgIdBytes);
                    int msgId = ByteBuffer.wrap(msgIdBytes).order(ByteOrder.LITTLE_ENDIAN).getShort() & 0xFFFF;

                    byte[] payload = new byte[msgLen];
                    input.readFully(payload);

                    byte checksum = input.readByte();

                    handleMessage(msgType, payload, msgId);
                    sendAck(msgId);
                }
            } catch (Exception e) {
                if (isRunning) {
                    Log.e(TAG, "An error occurred during Socket data processing: ", e);
                }
            } finally {
                Log.d(TAG, "Exiting Socket data reading loop.");
                stopSocket(); // 清理资源
            }
        });

        socketThread.start();
    }

    private void stopSocket() {
        isRunning = false;
        try {
            if (socket != null && !socket.isClosed()) {
                socket.close();
                Log.d(TAG, "Socket has been closed.");
            }
        } catch (IOException ignored) {}
        if (socketThread != null) {
            socketThread.interrupt(); // 中断线程，使其可以从sleep中醒来并退出
            socketThread = null;
        }
    }

    private String lastStatus = ""; // "" 表示未初始化

    private void handleMessage(byte type, byte[] data, int msgId) {
        switch (type) {
            case 0x07: // 图像格式
                break;
            case 0x08: // 图像帧
                if (FrameDataBus.getListener() != null) {
                    FrameDataBus.getListener().invoke(data);
                }
                break;
            case 0x09: // 单人脸
            case 0x0B: // 多人脸
                String faceJsonStr = new String(data);
                JSONObject root;
                try {
                    root = new JSONObject(faceJsonStr);
                    boolean wakeup = root.optBoolean("wakeup", false);

                    if (wakeup) {
                        Log.d(TAG, "Wakeup detected from face data.");
                        if (FrameDataBus.getCameraViewVisible() != null) {
                            FrameDataBus.getCameraViewVisible().invoke(true);
                        }
                        if (FrameDataBus.getFaceListener() != null) {
                            FrameDataBus.getFaceListener().invoke(faceJsonStr);
                        }

                        String newStatus = "work";
                        if (FrameDataBus.getFaceStatusListener() != null) {
                            FrameDataBus.getFaceStatusListener().invoke(newStatus);
                            Log.d(TAG, "Face status sent: " + newStatus);
                        }
                        lastStatus = newStatus;
                    }
                } catch (JSONException e) {
                    Log.e(TAG, "Failed to parse face JSON", e);
                }
                break;
        }
    }

    private void sendAck(int msgId) {
        if (output == null) return;
        try {
            ByteArrayOutputStream baos = new ByteArrayOutputStream();
            baos.write(0xA5); // sync
            baos.write(0x01); // userId
            baos.write(0xFF); // msgType
            baos.write(new byte[]{0x04, 0x00, 0x00, 0x00}); // msgLen = 4
            baos.write(ByteBuffer.allocate(2).order(ByteOrder.LITTLE_ENDIAN).putShort((short) msgId).array()); // msgId
            baos.write(new byte[]{(byte) 0xA5, 0x00, 0x00, 0x00}); // payload
            baos.write(0x00); // checksum

            output.write(baos.toByteArray());
            output.flush();
        } catch (Exception e) {
            Log.e(TAG, "Failed to send ACK", e);
        }
    }

    private void initWebSocket() {
        client = new OkHttpClient.Builder().build();
        Request request = new Request.Builder().url(WS_URL).build();
        webSocket = client.newWebSocket(request, new WebSocketListener() {
            @Override
            public void onOpen(WebSocket ws, okhttp3.Response response) {
                Log.d(TAG, "WebSocket connected.");
            }

            @Override
            public void onMessage(WebSocket webSocket, String text) {
                try {
                    JSONObject json = new JSONObject(text);
                    String type = json.optString("type");
                    String data = json.optString("data");

                    if ("msg2app".equals(type) && "sleep".equalsIgnoreCase(data)) {
                        if (FrameDataBus.getCameraViewVisible() != null) {
                            FrameDataBus.getCameraViewVisible().invoke(false);
                        }
                        if (FrameDataBus.getFaceStatusListener() != null) {
                            FrameDataBus.getFaceStatusListener().invoke("sleep");
                            Log.d(TAG, "Face status sent: sleep");
                        }
                        lastStatus = "sleep";
                    }
                } catch (JSONException e) {
                    Log.e(TAG, "Failed to parse WebSocket message", e);
                }
            }

            @Override
            public void onFailure(WebSocket ws, Throwable t, okhttp3.Response response) {
                Log.e(TAG, "WebSocket connection error", t);
                // 可以考虑在这里也加入重连逻辑
            }

            @Override
            public void onClosed(WebSocket ws, int code, String reason) {
                Log.d(TAG, "WebSocket closed: " + reason);
            }
        });
    }
}
