package com.example.myapplication.view

import android.annotation.SuppressLint
import android.content.Context
import android.net.ConnectivityManager
import android.net.Network
import android.net.NetworkCapabilities
import android.net.NetworkRequest
import android.net.http.SslError
import android.provider.Settings
import android.util.AttributeSet
import android.view.LayoutInflater
import android.view.View
import android.webkit.JavascriptInterface
import android.webkit.SslErrorHandler
import android.webkit.WebChromeClient
import android.webkit.WebResourceRequest
import android.webkit.WebSettings
import android.webkit.WebView
import android.webkit.WebViewClient
import androidx.constraintlayout.widget.ConstraintLayout
import com.example.myapplication.AppConstants
import com.example.myapplication.R
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import java.util.UUID


/**
 * @author Hubowen
 * @date 2025/8/13.
 * description：
 */
class ZkxhView @JvmOverloads constructor(
    context: Context,
    attrs: AttributeSet? = null,
    defStyleAttr: Int = 0
) : ConstraintLayout(context, attrs, defStyleAttr) {

    var zkxhWebView: WebView? = null
    var cameraView: CameraView? = null
    private var connectivityManager: ConnectivityManager? = null
    private var networkCallback: ConnectivityManager.NetworkCallback? = null
    private var isNetworkAvailable = false
    private var isWebViewLoaded = false
    private var pendingFaceStatus: String? = null

    init {
        LayoutInflater.from(context).inflate(R.layout.view_zkxh, this, true)
        zkxhWebView = findViewById(R.id.id_view_zkxh_wb)
        cameraView = findViewById(R.id.id_view_zkxh_cv)
        //初始化网页
        initWebView()
        // 初始化网络监控
        initNetworkMonitoring(context)
        // 假设 FrameDataBus 是全局数据总线
        FrameDataBus.listener = { data ->
            post {  // 这个就是切回主线程执行
                cameraView?.onFrameData(data)
            }
        }
        FrameDataBus.faceListener = { data ->
            post {
                cameraView?.onFaceData(data)
            }
        }
        FrameDataBus.cameraViewVisible = { data ->
            post {
                isShowCameraView(data)
            }
        }

        FrameDataBus.faceStatusListener = { status ->
            post {
                notifyWebFaceStatus(status)
            }
        }

        FrameDataBus.readyToRecvListener = {
            post {
                sendCurrentFaceStatus()
            }
        }

        FrameDataBus.asrIntermediateListener = { text ->
            post {
                android.util.Log.d("ZkxhView", "asrIntermediateListener called, isWebViewLoaded=$isWebViewLoaded, text=$text")
                if (isWebViewLoaded) {
                    zkxhWebView?.evaluateJavascript("window.handleAsrIntermediate?.('$text');", null)
                }
            }
        }
    }

    fun loadWebView() {
        // 检查网络状态，如果网络可用则立即加载，否则等待网络连接
        zkxhWebView?.apply {
            if (isNetworkAvailable) {
                this.loadUrl("http://" + AppConstants.SERVER_IP + "/")
//                this.loadUrl("http://your-server-host:3001/")
            } else {
                // 网络不可用，等待网络连接后再加载
                waitForNetworkAndLoad()
            }
        }
    }

    fun initWebView() {
        zkxhWebView?.apply {
            settings.javaScriptEnabled = true
            settings.domStorageEnabled = true
            settings.loadsImagesAutomatically = true
            settings.mediaPlaybackRequiresUserGesture = false
            settings.useWideViewPort = true
            settings.loadWithOverviewMode = true
            settings.setSupportZoom(true)
            settings.builtInZoomControls = true
            settings.displayZoomControls = false
            settings.cacheMode = WebSettings.LOAD_NO_CACHE

            // 在配置 WebView 时就注入 JS 接口，确保页面加载前接口已可用
            addJavascriptInterface(DeviceBridge(context), "DeviceBridge")

            webViewClient = object : WebViewClient() {
                override fun shouldOverrideUrlLoading(
                    view: WebView?,
                    request: WebResourceRequest?
                ): Boolean {
                    return false // 直接在 WebView 内加载
                }

                @SuppressLint("WebViewClientOnReceivedSslError")
                override fun onReceivedSslError(
                    view: WebView?,
                    handler: SslErrorHandler?,
                    error: SslError?
                ) {
                    // 忽略证书错误（仅用于测试，生产环境要替换成合法证书）
                    handler?.proceed()
                }

                override fun onPageFinished(view: WebView?, url: String?) {
                    super.onPageFinished(view, url)
                    isWebViewLoaded = true
                    // WebView加载完成后，发送积压的状态
                    pendingFaceStatus?.let { status ->
                        notifyWebFaceStatus(status)
                        pendingFaceStatus = null
                    }
                }
            }

            webChromeClient = WebChromeClient()
        }
    }

    /**
     * 是否显示CameraView
     */
    fun isShowCameraView(isShow: Boolean) {
        cameraView?.post {
            cameraView?.let { view ->
                val targetVisibility = if (isShow) View.VISIBLE else View.GONE
                if (view.visibility != targetVisibility) {
                    view.visibility = targetVisibility
                }
            }
        }
    }

    override fun onDetachedFromWindow() {
        super.onDetachedFromWindow()
        cameraView?.release()
        FrameDataBus.listener = null
        zkxhWebView?.apply {
            stopLoading()
            clearHistory()
            destroy()
        }
        // 取消网络监控
        unregisterNetworkCallback()
    }

    /**
     * 初始化网络监控
     */
    private fun initNetworkMonitoring(context: Context) {
        connectivityManager = context.getSystemService(Context.CONNECTIVITY_SERVICE) as ConnectivityManager

        // 检查当前网络状态
        checkCurrentNetworkStatus()

        // 注册网络状态监听
        val networkRequest = NetworkRequest.Builder()
            .addCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET)
            .build()

        networkCallback = object : ConnectivityManager.NetworkCallback() {
            override fun onAvailable(network: Network) {
                super.onAvailable(network)
                isNetworkAvailable = true
                // 网络可用时，如果网页还未加载，则加载网页
                post {
                    zkxhWebView?.let { webView ->
                        if (webView.url.isNullOrEmpty()) {
                            webView.loadUrl("http://" + AppConstants.SERVER_IP + "/")
//                            webView.loadUrl("http://your-server-host:3001/")
                        }
                    }
                }
            }

            override fun onLost(network: Network) {
                super.onLost(network)
                isNetworkAvailable = false
            }
        }

        connectivityManager?.registerNetworkCallback(networkRequest, networkCallback!!)
    }

    /**
     * 检查当前网络状态
     */
    private fun checkCurrentNetworkStatus() {
        val network = connectivityManager?.activeNetwork
        val capabilities = connectivityManager?.getNetworkCapabilities(network)
        isNetworkAvailable = capabilities?.hasCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET) == true
    }

    /**
     * 等待网络连接并加载网页
     */
    private fun waitForNetworkAndLoad() {
        // 如果网络不可用，设置一个超时重试机制
        postDelayed({
            if (isNetworkAvailable) {
                zkxhWebView?.loadUrl("http://" + AppConstants.SERVER_IP + "/")
//                zkxhWebView?.loadUrl("http://your-server-host:3001/")

            } else {
                // 如果30秒后网络仍然不可用，尝试重试加载
                waitForNetworkAndLoad()
            }
        }, 30000) // 30秒后重试
    }

    /**
     * 取消网络监控
     */
    private fun unregisterNetworkCallback() {
        networkCallback?.let { callback ->
            connectivityManager?.unregisterNetworkCallback(callback)
            networkCallback = null
        }
    }

    /**
     * 通知前端人脸状态
     */
    private fun notifyWebFaceStatus(status: String) {
        // 更新状态缓存
        FrameDataBus.currentFaceStatus = status

        if (isWebViewLoaded) {
            // WebView已加载完成，直接发送状态
            zkxhWebView?.evaluateJavascript("window.handleFaceStatus?.('$status');", null)
        } else {
            // WebView未加载完成，暂存状态
            pendingFaceStatus = status
        }
    }

    /**
     * 发送当前缓存的人脸状态
     */
    private fun sendCurrentFaceStatus() {
        if (isWebViewLoaded) {
            FrameDataBus.currentFaceStatus?.let { status ->
                // WebView已加载完成，发送缓存的状态
                zkxhWebView?.evaluateJavascript("window.handleFaceStatus?.('$status');", null)
            }
        }
    }
}

class DeviceBridge(private val context: Context) {

    @SuppressLint("HardwareIds")
    @JavascriptInterface
    fun getDeviceId(): String {
        // 示例：使用 ANDROID_ID
        return Settings.Secure.getString(context.contentResolver, Settings.Secure.ANDROID_ID)
            ?: UUID.randomUUID().toString()
    }

    @JavascriptInterface
    fun notifyStatus(status: String) {
        // 前端可以通过此方法接收状态通知
        // 状态值："work" 表示工作状态，"sleep" 表示睡眠状态
    }

    @JavascriptInterface
    fun readyToRecv() {
        // 前端准备好接收状态，触发readyToRecv事件
        FrameDataBus.readyToRecvListener?.invoke()
    }
}
