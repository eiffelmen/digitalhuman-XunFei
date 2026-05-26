package com.example.myapplication;

import android.util.Log;

import org.java_websocket.WebSocket;
import org.java_websocket.handshake.ClientHandshake;
import org.java_websocket.server.WebSocketServer;

import java.net.InetSocketAddress;
import java.util.Collections;
import java.util.HashSet;
import java.util.Set;


/**
 * @author Hubowen
 * @date 2025/8/1.
 * description：
 */
class LocalWebSocketServer extends WebSocketServer {

    private static final String TAG = "LocalWebSocketServer";

    private final Set<WebSocket> clients = Collections.synchronizedSet(new HashSet<>());

    public LocalWebSocketServer(int port) {
        super(new InetSocketAddress(port));
    }

    @Override
    public void onOpen(WebSocket conn, ClientHandshake handshake) {
        clients.add(conn);
        Log.d(TAG, "客户端已连接: " + conn.getRemoteSocketAddress());
    }

    @Override
    public void onClose(WebSocket conn, int code, String reason, boolean remote) {
        clients.remove(conn);
        Log.d(TAG, "客户端断开: " + conn.getRemoteSocketAddress());
    }

    @Override
    public void onMessage(WebSocket conn, String message) {
        Log.d(TAG, "收到消息: " + message);
    }

    @Override
    public void onError(WebSocket conn, Exception ex) {
        Log.e(TAG, "WebSocket 错误", ex);
    }

    @Override
    public void onStart() {
        Log.d(TAG, "WebSocket 服务已启动");
    }

    public void broadcastImage(byte[] imageData) {
        synchronized (clients) {
            for (WebSocket client : clients) {
                try {
                    client.send(imageData);
                } catch (Exception e) {
                    Log.e(TAG, "发送图像失败", e);
                }
            }
        }

    }
    public void broadcastJson(String json) {
        synchronized (clients) {
            for (WebSocket client : clients) {
                try {
                    client.send(json);
                } catch (Exception e) {
                    Log.e(TAG, "发送JSON消息失败", e);
                }
            }
        }
    }
}
