### 实时数字人项目接口文档

1. 视频转视频链接

   \- URL: `http://backend.example.internal:8086/v1/upload`

   \- 方法: POST

   \- Content-Type: multipart/form-data

    | **参数** | **类型** | **必填** | **描述**         |
    | :------- | -------- | -------- | ---------------- |
    | file     | file     | 是       | 要上传的视频文件 |

   \- 响应

   HTTP 状态码: 200

   ```json
   {
      "message": "文件上传成功",
      "url": "xxx"
   }
   ```

   HTTP 状态码: 400 或 500

   ```json
   {
      "detail": "文件上传失败: 错误详细信息"
   }
   ```

2. 上传视频，返回数字人ID

   2.1 处理视频链接

   \- URL: `http://backend.example.internal:8085/v1/process_video_url`

   \- 方法: POST

   \- Content-Type: application/json

    | **参数**  | **类型** | **必填** | **描述**                               |
    | :-------- | -------- | -------- | -------------------------------------- |
    | video_url | string   | 是       | 视频文件的 URL，需要是有效的 .mp4 链接 |


   \- 命令行调用
   ```shell
   curl -X POST http://backend.example.internal:8085/v1/process_video \
      -F "video=@/Data1/home/luoling/realtime-digitalhuman-v2/data/videos/lishuang.mp4" \
      -H "Content-Type: multipart/form-data"
   ```

   \- 响应

   HTTP 状态码: 200

   ```json
   {
      "message": "视频处理完成",
      "avatar_id": "wav2lip_avatar{新增加的数字人ID}",
      "templete_image_base64": "base64编码的模板图片"
   }
   ```


   HTTP 状态码: 404

   ```json
   {
      "error": "视频处理错误，导致模版图像不存在"
   }
   ```

   HTTP 状态码: 500

   ```json
   {
      "error": "其他错误信息"
   }
   ```


   2.2 处理上传的视频文件

   \- URL: `http://backend.example.internal:8085/v1/process_video`

   \- 方法: POST

   \- Content-Type: multipart/form-data

    | **参数** | **类型** | **必填** | **描述**                       |
    | :------- | -------- | -------- | ------------------------------ |
    | video    | file     | 是       | 用户上传的视频文件，格式为 MP4 |

   \- 响应

   HTTP 状态码: 200

   ```json
   {
      "message": "视频处理完成",
      "avatar_id": "wav2lip_avatar{新增加的数字人ID}",
      "templete_image_base64": "base64编码的模板图片"
   }
   ```

   HTTP 状态码: 400

   ```json
   {
      "error": "必须上传视频文件"
   }
   ```

   HTTP 状态码: 404

   ```json
   {
      "error": "视频处理错误，导致模版图像不存在"
   }
   ```

   HTTP 状态码: 500

   ```json
   {
      "error": "其他错误信息"
   }
   ```

   2.3

3. 删除指定的ID，但禁止删除ID模板1, 2, 3

   \- 接口地址: `http://backend.example.internal:8085/v1/delete_avatar/{avatar_id}`

   \- 方法: DELETE

   \- Content-Type: application/json

    | **参数**  | **类型** | **必填** | **描述**            |
    | :-------- | -------- | -------- | ------------------- |
    | avatar_id | integer  | 需要     | 需要删除的Avatar ID |

   \- 响应

   HTTP 状态码: 200

   ```json
   {
      "message": "Avatar deleted successfully"
   }
   ```

   HTTP 状态码: 403

   ```json
   {
      "error": "Cannot delete avatars 1, 2, or 3" # 用于默认数字人模版
   }
   ```

   HTTP 状态码: 404

   ```json
   {
      "error": "Avatar not found"
   }
   ```

   HTTP 状态码: 500

   ```json
   {
      "error": "Detailed error message"
   }
   ```

4. 获取 webrtc 视频

   \- 接口地址: `http://backend.example.internal:8010/offer`

   \- 方法: POST

   \- 请求参数

   | **参数** | **类型** | **必填** | **描述**       |
   | -------- | -------- | -------- | -------------- |
   | type     | string   | 需要     | 填offer        |
   | sdp      | string   | 需要     | webrtc请求参数 |

   请求示例：

   ```json
   {
       'sdp': 'xxxx',
       'type': 'offer',
   }
   ```

   \- 返回数据

    | **参数**  | **类型** | **必填** | **描述**                         |
    | :-------- | -------- | -------- | -------------------------------- |
    | type      | string   | 是       | 填answer                         |
    | sdp       | string   | 是       | webrtc应答参数                   |
    | sessionid | int      | 是       | 数字人会话ID，用于区分多路数字人 |

   返回示例：

   ```json
   {
        'sdp': 'xxxx',
        'type': 'answer',
        'sessionid': xxxxx,
   }
   ```

5. 向数字人发送聊天内容

   \- 接口地址: `http://backend.example.internal:8010/human`

   \- 方法: POST

   \- 请求参数

   | **参数**  | **类型** | **必填** | **描述**                                     |
   | --------- | -------- | -------- | -------------------------------------------- |
   | sessionid | int      | 是       | 数字人会话ID                                 |
   | interrupt | bool     | 否       | 是否打断数字人当前说话，默认为false          |
   | type      | string   | 需要     | echo：数字人播报输入文字；chat：与数字人对话 |
   | text      | string   | 需要     | 文字内容                                     |


   请求示例：

   ```json
   {
        'text’: 'hello world!',
        'type': 'chat',
        'interrupt': true,
        'sessionid': xxxxxx
   }
   ```

6. ~~数字人ID切换~~

   \- 接口地址: `http://backend.example.internal:8010/change_avatar`

   \- 方法: POST

   \- 请求参数

   | **参数**  | **类型** | **必填** | **描述**     |
   | --------- | -------- | -------- | ------------ |
   | sessionid | int      | 是       | 数字人会话ID |
   | avatar_id | string   | 是       | 数字人ID     |

   请求示例：

   ```json
   {
        'sessionid':0
        'avatar_id': 'wav2lip_avatar{x}'
   }
   ```

   其中x代表添加的数字人ID，例如wav2lip_avatar1，由第二步返回的数字人ID决定。

   简单测试切换效果：
   ```
   curl -X POST -H "Content-Type: application/json" -d '{"sessionid": 0,    "avatar_id": "wav2lip_avatar3"}' http://localhost:8010/change_avatar
   ```


7. **最新** 数字人素材模版切换

   该接口用于设置数字人配置的默认资产，包括ID、音色和背景图片。在确认配置之前，它会检查所需资源是否存在于服务器上。

   \- 接口地址: `http://backend.example.internal:8011/update_config`

   \- 方法: POST

   \- 请求体

      digital_human_id (整数): 代表数字人头像的ID。

      voice_type (整数): 用于数字人的音色类型。

      background_image (整数): 用于选择背景图片的ID。

      sessionid: 从offer接口得到的sessionid

   \- 响应描述

    HTTP 状态码: 200

   ```json
   {
      "message": "设置成功",
      "digital_human_path": <digital_human_path>,
      "ref_voice_path": <ref_voice_path>,
      "background_image_path": <background_image_path>
   }
   ```

   HTTP 状态码: 400

   ```json
   {
      "message": "缺少必要参数"
   }
   ```

   HTTP 状态码: 404

   ```json
   {
      "message": "模板不存在"
   }
   ```

   HTTP 状态码: 500

   ```json
   {
      "message": "服务器内部错误"
   }
   ```

8. 上传用户音色模版

   \- 指定用户读 “先帝创业未半而中道崩殂，今天下三分，益州疲弊，此诚危急存亡之秋也”素材。

   \- 接口地址: `http://backend.example.internal:8088/v1/upload_audio`

   \- 方法: POST

   \- Content-Type: multipart/form-data

   | 参数 | 类型 | 必填 | 描述                                          |
   | :--- | ---- | ---- | --------------------------------------------- |
   | file | file | 是   | 要上传的音频文件，格式为 WAV、MP3、M4A 或 OGG |

   \- 响应描述

   HTTP 状态码: 200

   ```json
   {
      "message": "音频已成功上传，采样率为 16000 Hz！",
      "voice_id": xxx
   }
   ```

   HTTP 状态码: 400

   ```json
   {
      "message": "不支持的音频文件格式。请上传 WAV、MP3、M4A 或 OGG 格式的文件"
   }
   ```

   HTTP 状态码: 500

   ```json
   {
      "message": "其他错误"
   }
   ```

9. 删除用户音频

   \- 接口地址: http://backend.example.internal:8088/v1/delete_audio/{avatar_audio}

   \- 方法: DELETE

   \- Content-Type: application/json

   | 参数         | 类型    | 必填 | 描述                    |
   | ------------ | ------- | ---- | ----------------------- |
   | avatar_audio | integer | 是   | 需要删除的音频文件的 ID |

   \- 响应描述

   HTTP 状态码: 200

   ```json
   {
      "message": "音频 '{avatar_audio}' 已成功删除"
   }
   ```

   HTTP 状态码: 403

   ```json
   {
      "message": "该音频是模板音频，禁止删除！"
   }
   ```

   HTTP 状态码: 404

   ```json
   {
      "message": "文件未找到"
   }
   ```

   HTTP 状态码: 500

   ```json
   {
      "message": "删除音频文件时发生错误: 错误详细信息"
   }
   ```


10. 上传用户自定义背景图模版

    \- 接口地址: `http://backend.example.internal:8088/v1/upload_image`

      \- 方法: POST

      \- Content-Type: multipart/form-data

      | 参数 | 类型 | 必填 | 描述                         |
      | :--- | ---- | ---- | ---------------------------- |
      | file | file | 是   | 要上传的图片文件，格式为 JPG |  |


      \- 响应描述

      HTTP 状态码: 200

      ```json
      {
         "message": "背景图片上传成功！",
         "bg_image_id": xxx,
         "image_base64": "base64编码的模板图片"
      }
      ```

      HTTP 状态码: 400

      ```json
      {
         "message": "上传的文件必须是 PNG、JPG 或 JPEG 格式的图片"
      }
      ```

      HTTP 状态码: 500

      ```json
      {
         "message": "其他错误"
      }
      ```

11. 删除用户自定义背景图模版

      \- 接口地址: http://backend.example.internal:8088/v1/delete_image/{avatar_bg}

      \- 方法: DELETE

      \- Content-Type: application/json

      | 参数      | 类型    | 必填 | 描述                    |
      | --------- | ------- | ---- | ----------------------- |
      | avatar_bg | integer | 是   | 需要删除的图像文件的 ID |

      \- 响应描述

      HTTP 状态码: 200

      ```json
      {
         "message": "图像 '{avatar_bg}' 已成功删除。"
      }
      ```

      HTTP 状态码: 403

      ```json
      {
         "message": "该背景图为模版背景图，禁止删除！"
      }
      ```

      HTTP 状态码: 404

      ```json
      {
         "message": "图像未找到"
      }
      ```

      HTTP 状态码: 500

      ```json
      {
         "message": "删除图像时发生错误: 错误详细信息"
      }
      ```

12. ~~重新加载配置~~

      该接口用于重新加载数字人的配置，包括头像、背景图和其他相关设置。

      \- 接口地址: `http://backend.example.internal:8011/reload_config`

      \- 方法: POST

      \- 请求体


      sessionid: 从offer接口得到的sessionid

      \- 响应描述

      HTTP 状态码: 200

      ```json
      {
         "status": "ok"
      }
      ```

      HTTP 状态码: 500

      ```json
      {
         "status": "error",
         "message": "错误信息"
      }
      ```

13. 处理视频 URL

   该接口用于处理视频 URL，并生成任务 ID 以供轮询查看进度。

   - 接口地址: `http://backend.example.internal:8085/v1/process_video_url`

   - 方法: POST

   - 请求参数:
   - `video_url` (string, 必填): 视频的 URL 地址。

   - 响应描述:

   HTTP 状态码: 200

   ```json
   {
         "task_id": "生成的任务 ID",
         "message": "任务已提交，请轮询查看进度"
   }
   ```

   HTTP 状态码: 400

   ```json
   {
         "message": "错误信息"
   }
   ```

   HTTP 状态码: 500

   ```json
   {
         "message": "错误信息"
   }
   ```

14. 查询任务状态

   该接口用于查询视频处理任务的状态。

   - 接口地址: `http://backend.example.internal:8085/v1/check_status/{task_id}`

   - 方法: GET

   - 请求参数:
   - `task_id` (string, 必填): 任务的唯一标识符。

   - 响应描述:

   HTTP 状态码: 200

   ```json
   {
         "task_id": "任务 ID",
         "status": "任务状态",
         "processing_time": "处理时间（秒）",
         "result": "处理结果（仅在任务完成时返回）",
         "error": "错误信息（仅在任务失败时返回）"
   }
   ```
   HTTP 状态码: 400

   ```json
   {
         "message": "错误信息"
   }
   ```

   HTTP 状态码: 500

   ```json
   {
         "message": "错误信息"
   }
   ```


15. 生成 sessionID

   该接口用于生成用户唯一的 sessionID

   - 接口地址: `http://backend.example.internal:8010/generate_session`
   - 方法: POST
   - Content-Type: application/json

   请求参数：无

   响应示例：

   成功响应 (HTTP 200):
   ```json
   {
      "sessionid": "550e8400-e29b-41d4-a716-446655440000"
   }
   ```

   错误响应 (HTTP 500):
   ```json
   {
      "error": "生成 sessionID 失败"
   }
   ```