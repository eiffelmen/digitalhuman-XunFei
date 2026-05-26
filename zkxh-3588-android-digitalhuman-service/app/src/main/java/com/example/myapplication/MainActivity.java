package com.example.myapplication;

import static android.view.View.SYSTEM_UI_FLAG_HIDE_NAVIGATION;
import static android.view.View.SYSTEM_UI_FLAG_IMMERSIVE_STICKY;

import android.app.Activity;
import android.app.AlertDialog;
import android.content.Intent;
import android.os.Bundle;
import android.util.Log;
import com.example.myapplication.network.BackendApi;
import com.example.myapplication.view.ZkxhView;
import android.os.Handler;
import android.os.Looper;
import android.view.View;
import android.view.ViewGroup;
import android.widget.FrameLayout;
import android.widget.TextView;

//import androidx.appcompat.app.AppCompatActivity;

public class MainActivity extends Activity {

    ZkxhView zkxhView = null;
    private FrameLayout zkxhContainer;
    private BackendApi backendApi;
    private View startupOverlay;
    private TextView deviceStatusView;
    private TextView realtimeStatusView;
    private TextView webViewStatusView;
    private Handler checkHandler = new Handler(Looper.getMainLooper());
    private static final int CHECK_INTERVAL = 2000; // 2 seconds
    private boolean businessStarted = false;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);

        // 全屏模式，沉浸式，隐藏状态栏和导航栏
        getWindow().getDecorView().setSystemUiVisibility(
                View.SYSTEM_UI_FLAG_FULLSCREEN
                        | View.SYSTEM_UI_FLAG_HIDE_NAVIGATION
                        | View.SYSTEM_UI_FLAG_IMMERSIVE_STICKY
        );

        setContentView(R.layout.activity_main);

        zkxhContainer = findViewById(R.id.zkxh_container);
        startupOverlay = findViewById(R.id.startup_overlay);
        deviceStatusView = findViewById(R.id.status_device_service);
        realtimeStatusView = findViewById(R.id.status_realtime_service);
        webViewStatusView = findViewById(R.id.status_webview_service);
        backendApi = new BackendApi(this);

        instance = this;

        // 开始轮询检查服务状态
        startReadyCheck();
    }

    private void startReadyCheck() {
        checkHandler.post(new Runnable() {
            @Override
            public void run() {
                new Thread(() -> {
                    String deviceUrl = "http://" + AppConstants.SERVER_IP + ":8000/ready";
                    String realtimeUrl = "http://" + AppConstants.SERVER_IP + ":8010/ready";
                    String webViewUrl = "http://" + AppConstants.SERVER_IP + "/";

                    boolean deviceReady = backendApi.isServiceReady(deviceUrl);
                    boolean realtimeReady = backendApi.isServiceReady(realtimeUrl);
                    boolean webViewReady = backendApi.isUrlAccessible(webViewUrl);

                    Log.d("MAIN_ACTIVITY", "Checking services: device=" + deviceReady + 
                        ", realtime=" + realtimeReady + ", webView=" + webViewReady);

                    runOnUiThread(() -> {
                        updateServiceStatus(deviceReady, realtimeReady, webViewReady);
                        if (deviceReady && realtimeReady && webViewReady) {
                            startBusinessLogic();
                        } else {
                            checkHandler.postDelayed(this, CHECK_INTERVAL);
                        }
                    });
                }).start();
            }
        });
    }

    private void updateServiceStatus(boolean deviceReady, boolean realtimeReady, boolean webViewReady) {
        if (deviceStatusView != null) {
            deviceStatusView.setText("设备服务：" + (deviceReady ? "就绪" : "检查中"));
        }
        if (realtimeStatusView != null) {
            realtimeStatusView.setText("实时服务：" + (realtimeReady ? "就绪" : "检查中"));
        }
        if (webViewStatusView != null) {
            webViewStatusView.setText("网页服务：" + (webViewReady ? "就绪" : "检查中"));
        }
    }

    private void startBusinessLogic() {
        if (businessStarted) {
            return;
        }
        businessStarted = true;
        Log.i("MAIN_ACTIVITY", "All services ready, starting business logic...");

        // 隐藏启动页
        if (startupOverlay != null) {
            startupOverlay.setVisibility(View.GONE);
        }

        // 延后初始化并添加 ZkxhView，确保服务就绪后再创建
        if (zkxhView == null) {
            zkxhView = new ZkxhView(this);
            if (zkxhContainer != null) {
                zkxhContainer.addView(
                        zkxhView,
                        new FrameLayout.LayoutParams(
                                ViewGroup.LayoutParams.MATCH_PARENT,
                                ViewGroup.LayoutParams.MATCH_PARENT
                        )
                );
            }
        }

        // 启动后台服务
        startService(new Intent(this, MyBackgroundService.class));
        startService(new Intent(this, ImageSocketService.class));
        startService(new Intent(this, AudioSocketService.class));

        // 加载网页
        if (zkxhView != null) {
            zkxhView.loadWebView();
        }
    }

    private static MainActivity instance;

    public static void showAlertFromService(String title, String message) {
        if (instance != null) {
            instance.runOnUiThread(() -> {
                new AlertDialog.Builder(instance)
                        .setTitle(title)
                        .setMessage(message)
                        .setPositiveButton("确定", null)
                        .show();
            });
        }
    }
}
