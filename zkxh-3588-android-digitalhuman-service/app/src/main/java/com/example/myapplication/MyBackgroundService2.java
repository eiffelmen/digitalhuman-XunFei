package com.example.myapplication;


import android.app.Service;
import android.content.Intent;
import android.os.IBinder;
import android.util.Log;

public class MyBackgroundService2 extends Service {
    private static final String TAG = "MyBackgroundService";
    @Override
    public void onCreate() {
        super.onCreate();
        Log.e(TAG, "Service onCreate begin");
    }
    @Override
    public int onStartCommand(Intent intent, int flags, int startId) {
        Log.e(TAG, "Service onStartCommand");
        return START_STICKY;
    }
    @Override
    public IBinder onBind(Intent intent) { return null; }
}