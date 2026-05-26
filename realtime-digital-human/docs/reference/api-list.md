根据对`app_v2.py`文件的分析，该文件定义了以下API接口：

### FastAPI/aiohttp接口：

1. **POST /generate_session**
   - 功能：生成数字人会话
   - 处理函数：`generate_session`

2. **POST /offer**
   - 功能：处理WebRTC连接的offer请求
   - 处理函数：`offer`
   - 返回WebRTC的answer响应

3. **POST /human**
   - 功能：处理数字人交互请求
   - 处理函数：`human`
   - 支持echo和chat两种类型的请求

4. **POST /interrupt**
   - 功能：中断数字人当前对话
   - 处理函数：`interrupt`

5. **POST /set_audiotype**
   - 功能：切换播放自定义视频
   - 处理函数：`set_audiotype`

6. **POST /is_speaking**
   - 功能：查询数字人是否正在说话
   - 处理函数：`is_speaking`

7. **GET /health**
   - 功能：健康检查接口
   - 处理函数：`health_check`

### WebSocket接口：

8. **WebSocket /ws/<sessionid>**
   - 功能：建立与特定会话的WebSocket连接
   - 处理函数：`ws_connect`
   - 用于实时通信

### Flask接口：

9. **POST /update_config**
   - 功能：更新数字人、背景和音色配置
   - 处理函数：`update_config`

### 注意事项：
- 文件中**没有找到**`/getHasFace`接口的定义
- 服务器同时运行aiohttp服务器（端口`opt.listenport`，默认8010）和Flask WebSocket服务器（端口`opt.listenport + 1`，默认8011）
- 所有HTTP接口都配置了CORS支持，允许跨域请求

需要注意的是，如果您需要`/getHasFace`接口，可能需要在后端代码中添加该接口的实现。
        