package com.example.myapplication.view

import android.content.Context
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.graphics.Color
import android.graphics.Paint
import android.graphics.Rect
import android.graphics.RectF
import android.util.AttributeSet
import android.view.SurfaceHolder
import android.view.SurfaceView
import androidx.constraintlayout.widget.ConstraintLayout
import com.example.myapplication.R
import org.json.JSONObject
import java.util.concurrent.ArrayBlockingQueue
import java.util.concurrent.Executors

/**
 * @author Hubowen
 * @date 2025/8/13.
 * description：
 */
class CameraView @JvmOverloads constructor(context: Context, attrs: AttributeSet? = null, defStyleAttr: Int = 0) : ConstraintLayout(context, attrs, defStyleAttr) {
    private val surfaceView: SurfaceView
    private val paint = Paint(Paint.ANTI_ALIAS_FLAG)
    private val facePaint = Paint(Paint.ANTI_ALIAS_FLAG)
    private var bitmap: Bitmap? = null

    // 队列 + 线程池
    private val frameQueue = ArrayBlockingQueue<ByteArray>(2)
    private val decodeExecutor = Executors.newSingleThreadExecutor()

    // 保存人脸矩形框
    // 人脸框结构体
    data class FaceRect(val rect: Rect, val color: Int)

    private val faceRects = mutableListOf<FaceRect>()

    init {
        inflate(context, R.layout.view_camera, this)
        surfaceView = findViewById(R.id.id_view_camera_surfaceView)

        // SurfaceView 回调
        surfaceView.holder.addCallback(object : SurfaceHolder.Callback {
            override fun surfaceCreated(holder: SurfaceHolder) {}
            override fun surfaceChanged(holder: SurfaceHolder, format: Int, width: Int, height: Int) {}
            override fun surfaceDestroyed(holder: SurfaceHolder) {}
        })

        // 启动解码线程
        decodeExecutor.execute {
            while (!Thread.currentThread().isInterrupted) {
                try {
                    val data = frameQueue.take()
                    val bmp = decodeBitmap(data)
                    if (bmp != null) {
                        bitmap = bmp
                        drawFrame()
                    }
                } catch (e: InterruptedException) {
                    break
                }
            }
        }
    }

    /**
     * 外部调用传入帧数据
     */
    fun onFrameData(data: ByteArray) {
        frameQueue.clear()
        frameQueue.offer(data)
    }

    private fun decodeBitmap(data: ByteArray): Bitmap? {
        return try {
            val options = BitmapFactory.Options().apply {
                inPreferredConfig = Bitmap.Config.RGB_565
                inMutable = true
                inBitmap = bitmap
            }
            BitmapFactory.decodeByteArray(data, 0, data.size, options)
        } catch (_: Exception) {
            null
        }
    }

    private fun drawFrame() {
        val canvas = surfaceView.holder.lockCanvas() ?: return
        canvas.drawColor(Color.BLACK)
        bitmap?.let {
            val src = Rect(0, 0, it.width, it.height)
            val dst = Rect(0, 0, surfaceView.width, surfaceView.height)
            canvas.drawBitmap(it, src, dst, paint)

            // 按比例映射人脸框
            val scaleX = surfaceView.width.toFloat() / it.width
            val scaleY = surfaceView.height.toFloat() / it.height

            facePaint.style = Paint.Style.STROKE // 只画边框
            facePaint.strokeWidth = 4f           // 边框宽度

            for (rect in faceRects) {
                val mapped = RectF(
                    rect.rect.left * scaleX,
                    rect.rect.top * scaleY,
                    rect.rect.right * scaleX,
                    rect.rect.bottom * scaleY
                )
                facePaint.color = rect.color
                canvas.drawRect(mapped, facePaint)
            }
        }
        surfaceView.holder.unlockCanvasAndPost(canvas)
    }

    fun onFaceData(jsonStr: String) {
        try {
            faceRects.clear()
            val obj = JSONObject(jsonStr)

            // 单人脸
            if (obj.has("hasFace")) {
                val hasFace = obj.optBoolean("hasFace")
                val wakeup = obj.optBoolean("wakeup")
                if (hasFace) {
                    val face = obj.optJSONObject("faceInfo")
                    if (face != null) {
                        val rect = Rect(
                            face.optInt("x"),
                            face.optInt("y"),
                            face.optInt("x") + face.optInt("w"),
                            face.optInt("y") + face.optInt("h")
                        )
                        val color = if (wakeup) Color.GREEN else Color.RED
                        faceRects.add(FaceRect(rect, color))
                    }
                }
            }

            // 多人脸
            if (obj.has("list")) {
                val list = obj.getJSONArray("list")
                for (i in 0 until list.length()) {
                    val item = list.getJSONObject(i)
                    val hasFace = item.optBoolean("hasFace")
                    val wakeup = item.optBoolean("wakeup")
                    if (hasFace) {
                        val face = item.optJSONObject("faceInfo")
                        if (face != null) {
                            val rect = Rect(
                                face.optInt("x"),
                                face.optInt("y"),
                                face.optInt("x") + face.optInt("w"),
                                face.optInt("y") + face.optInt("h")
                            )
                            val color = if (wakeup) Color.GREEN else Color.RED
                            faceRects.add(FaceRect(rect, color))
                        }
                    }
                }
            }
            drawFrame()
        } catch (_: Exception) {
        }
    }

    fun release() {
        decodeExecutor.shutdownNow()
        bitmap?.recycle()
        bitmap = null
    }
}

object FrameDataBus {
    @JvmStatic
    var listener: ((ByteArray) -> Unit)? = null

    @JvmStatic
    var faceListener: ((String) -> Unit)? = null

    @JvmStatic
    var cameraViewVisible: ((Boolean) -> Unit)? = null

    @JvmStatic
    var faceStatusListener: ((String) -> Unit)? = null

    @JvmStatic
    var readyToRecvListener: (() -> Unit)? = null

    @JvmStatic
    var asrIntermediateListener: ((String) -> Unit)? = null

    @JvmStatic
    var currentFaceStatus: String? = null
}