package com.example.myapplication.network;

import android.content.Context;
import android.provider.Settings;
import android.util.Log;

import com.alibaba.fastjson.JSONObject;
import com.example.myapplication.AppConstants;

import java.io.IOException;
import java.security.cert.CertificateException;
import java.util.UUID;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.ExecutorService;

import javax.net.ssl.SSLContext;
import javax.net.ssl.SSLSocketFactory;
import javax.net.ssl.TrustManager;
import javax.net.ssl.X509TrustManager;

import okhttp3.MediaType;
import okhttp3.OkHttpClient;
import okhttp3.Request;
import okhttp3.RequestBody;
import okhttp3.Response;

public class BackendApi {

    // 替换为您的后端服务器地址和端口
//    private static final String BACKEND_URL = "http://your-backend-server.com:8080/upload_data";
//    private static final String BACKEND_URL = "http://10.100.10.31:8010/human";
    private static final String BASE_URL = "http://"+ AppConstants.SERVER_IP+ ":8000";
    private static final String BACKEND_URL = BASE_URL + "/asr_result2";
    private static final String DEVICE_REGISTER_URL = BASE_URL + "/device_register";
    private static final String INTERRUPT_DIGITALMAN_URL = BASE_URL + "/interrupt_digitalman";
    private static final String UPDATE_HAS_FACE_URL = BASE_URL + "/updateHasFace";
    private static final MediaType JSON = MediaType.get("application/json; charset=utf-8");

    private OkHttpClient client;
    private String deviceId ;

    public BackendApi(Context context) {
        deviceId = Settings.Secure.getString(context.getContentResolver(), Settings.Secure.ANDROID_ID);
        if (deviceId == null) {
            deviceId = UUID.randomUUID().toString();
        }
        client = new OkHttpClient();
    }

    private OkHttpClient getUnsafeOkHttpClient() {
        try {
            // Create a trust manager that does not validate certificate chains
            final TrustManager[] trustAllCerts = new TrustManager[]{
                    new X509TrustManager() {
                        @Override
                        public void checkClientTrusted(java.security.cert.X509Certificate[] chain, String authType) throws CertificateException {
                        }

                        @Override
                        public void checkServerTrusted(java.security.cert.X509Certificate[] chain, String authType) throws CertificateException {
                        }

                        @Override
                        public java.security.cert.X509Certificate[] getAcceptedIssuers() {
                            return new java.security.cert.X509Certificate[]{};
                        }
                    }
            };

            // Install the all-trusting trust manager
            final SSLContext sslContext = SSLContext.getInstance("SSL");
            sslContext.init(null, trustAllCerts, new java.security.SecureRandom());
            // Create an ssl socket factory with our all-trusting manager
            final SSLSocketFactory sslSocketFactory = sslContext.getSocketFactory();

            OkHttpClient.Builder builder = new OkHttpClient.Builder();
            builder.sslSocketFactory(sslSocketFactory, (X509TrustManager) trustAllCerts[0]);
            builder.hostnameVerifier((hostname, session) -> true);

            return builder.build();
        } catch (Exception e) {
            throw new RuntimeException(e);
        }
    }

    public String getDeviceId() {
        return deviceId;
    }

    public boolean isServiceReady(String url) {
        // 使用短超时时间的客户端进行就绪检查
        OkHttpClient shortTimeoutClient = client.newBuilder()
                .connectTimeout(500, TimeUnit.MILLISECONDS)
                .readTimeout(500, TimeUnit.MILLISECONDS)
                .build();

        Request request = new Request.Builder()
                .url(url)
                .get()
                .build();

        try (Response response = shortTimeoutClient.newCall(request).execute()) {
            if (response.isSuccessful() && response.body() != null) {
                String bodyStr = response.body().string();
                JSONObject json = JSONObject.parseObject(bodyStr);
                return json.getInteger("status") != null && json.getInteger("status") == 1;
            }
        } catch (Exception e) {
            // 记录超时或连接失败，但在轮询期间这是预期的
            Log.d("BackendApi", "Service not ready at " + url + " (Error: " + e.getMessage() + ")");
        }
        return false;
    }

    /**
     * 检查普通 URL 是否可访问 (用于 WebView 网页检查)
     */
    public boolean isUrlAccessible(String url) {
        OkHttpClient shortTimeoutClient = client.newBuilder()
                .connectTimeout(1000, TimeUnit.MILLISECONDS)
                .readTimeout(1000, TimeUnit.MILLISECONDS)
                .build();

        // 默认网页检测使用 GET 请求，以确保网页内容能正常拉取且避开 HEAD 方法支持不佳的问题
        Request request = new Request.Builder()
                .url(url)
                .get()
                .build();

        try (Response response = shortTimeoutClient.newCall(request).execute()) {
            // 2xx 或 3xx 通常都认为网页是可访问的（例如重定向到登录页）
            return response.isSuccessful() || (response.code() >= 300 && response.code() < 400);
        } catch (Exception e) {
            Log.d("BackendApi", "URL not accessible: " + url + " (Error: " + e.getMessage() + ")");
            return false;
        }
    }

    public boolean registerDevice() {
        // 设备注册
        JSONObject json = new JSONObject();
        json.put("deviceid",deviceId);
        RequestBody body = RequestBody.create(json.toJSONString(), JSON);
        Request request = new Request.Builder()
                .url(DEVICE_REGISTER_URL)
                .post(body)
                .build();

        try (Response response = client.newCall(request).execute()) {
            if (response.isSuccessful()) {
                // 请求成功
                return true;
            } else {
                // 请求失败，打印错误信息
                System.err.println("Failed to upload data: " + response.code() + " " + response.message() + " " + response.body().string());
                return false;
            }
        } catch (IOException e) {
            e.printStackTrace();
            return false;
        }

    }

    public boolean interruptDigitalman() {
        JSONObject json = new JSONObject();
        json.put("deviceid", deviceId);

        RequestBody body = RequestBody.create(json.toJSONString(), JSON);
        Request request = new Request.Builder()
                .url(INTERRUPT_DIGITALMAN_URL)
                .post(body)
                .build();

        try (Response response = client.newCall(request).execute()) {
            if (response.isSuccessful()) {
                // 请求成功
                return true;
            } else {
                // 请求失败，打印错误信息
                System.err.println("Failed to interrupt: " + response.code() + " " + response.message() + " " + response.body().string());
                return false;
            }
        } catch (IOException e) {
            e.printStackTrace();
            return false;
        }

    }

    /**
     * 从后端获取sessionid，前端再从这里获取（？？？？怎么实现），后续调整sessionid逻辑
     *
     * @return
     */
    private String getSessionId() {

        return "";
    }

    /**
     * 将 AIUI 识别结果发送到后端服务器
     *
     * @param aiuiResult 最终识别结果字符串
     * @return true 如果成功，false 如果失败
     */
    public boolean uploadAiuiResult(String aiuiResult) {
        JSONObject json = new JSONObject();
        json.put("result", aiuiResult);
        json.put("deviceid", deviceId);

        RequestBody body = RequestBody.create(json.toJSONString(), JSON);
        Request request = new Request.Builder()
                .url(BACKEND_URL)
                .post(body)
                .build();

        try (Response response = client.newCall(request).execute()) {
            if (response.isSuccessful()) {
                // 请求成功
                return true;
            } else {
                // 请求失败，打印错误信息
                System.err.println("Failed to upload data: " + response.code() + " " + response.message() + " " + response.body().string());
                return false;
            }
        } catch (IOException e) {
            e.printStackTrace();
            return false;
        }
    }

    /**
     * 更新后端 hasFace 状态
     * @param hasFace 是否有面部检测
     * @return true 如果成功，false 如果失败
     */
    public boolean updateHasFace(boolean hasFace) {
        JSONObject json = new JSONObject();
        json.put("face_status", hasFace);

        RequestBody body = RequestBody.create(json.toJSONString(), JSON);
        Request request = new Request.Builder()
                .url(UPDATE_HAS_FACE_URL)
                .post(body)
                .build();

        try (Response response = client.newCall(request).execute()) {
            if (response.isSuccessful()) {
                // 请求成功
                return true;
            } else {
                // 请求失败，打印错误信息
                System.err.println("Failed to update hasFace: " + response.code() + " " + response.message() + " " + response.body().string());
                return false;
            }
        } catch (IOException e) {
            e.printStackTrace();
            return false;
        }
    }

    /**
     * 将 AIUI 识别结果发送到后端服务器
     * @param aiuiResult 最终识别结果字符串
     * @return true 如果成功，false 如果失败
     */
//    public boolean uploadAiuiResult(String aiuiResult) {
//        JSONObject json = new JSONObject();
////        json.put("recognitionResult", aiuiResult);
////        json.put("timestamp", System.currentTimeMillis());
//        // 可以添加更多你需要发送的数据
//        json.put("text", aiuiResult);
//        json.put("type", "chat");
//        json.put("interrupt", true);
//        json.put("sessionid", "3ab7ee93-2e8c-4a55-8bfd-eeae4f2361f6");
//
//        RequestBody body = RequestBody.create(json.toJSONString(), JSON);
//        Request request = new Request.Builder()
//                .url(BACKEND_URL)
//                .post(body)
//                .build();
//
//        try (Response response = client.newCall(request).execute()) {
//            if (response.isSuccessful()) {
//                // 请求成功
//                return true;
//            } else {
//                // 请求失败，打印错误信息
//                System.err.println("Failed to upload data: " + response.code() + " " + response.message() + " " + response.body().string());
//                return false;
//            }
//        } catch (IOException e) {
//            e.printStackTrace();
//            return false;
//        }
//    }
}
