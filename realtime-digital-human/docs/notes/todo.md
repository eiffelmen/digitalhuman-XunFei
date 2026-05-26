运行一段时间后，
generate_session正常



某次报错


2025-09-08 11:27:30.781 | WARNING  | __main__:ws_connect:645 - WebSocket连接关闭 sessionid=c866d338-6c49-4dad-9df9-b1fc86298035                                                     
2025-09-08 11:28:50.039 | INFO     | __main__:human:499 - 会话ID: c866d338-6c49-4dad-9df9-b1fc86298035                                                                              
2025-09-08 11:28:50.039 | WARNING  | __main__:human:503 - 收到中断请求 sessionid=c866d338-6c49-4dad-9df9-b1fc86298035                                                               
2025-09-08 11:28:50.048 | INFO     | rag_llm:llm_response:127 - 开始接收流式响应                                                                                                    
2025-09-08 11:28:50.098 | INFO     | rag_llm:llm_response:132 - Received chunk: I am Offic
2025-09-08 11:28:50.098 | ERROR    | rag_llm:llm_response:164 - 流式传输异常: Socket is dead                                                                                        
2025-09-08 11:28:50.099 | WARNING  | rag_llm:llm_response:167 - 这是啥                                                                                                              
2025-09-08 11:28:50.099 | INFO     | rag_llm:llm_response:180 - 总响应耗时: 0.06s
ERROR:asyncio:Future exception was never retrieved                                                                                                                                  
future: <Future finished exception=WebSocketError('Socket is dead')>
Traceback (most recent call last):                                                                                                                                                  
  File "/data/realtime-digitalhuman/.venv/lib/python3.9/site-packages/geventwebsocket/websocket.py", line 344, in send
    self.send_frame(message, opcode)
  File "/data/realtime-digitalhuman/.venv/lib/python3.9/site-packages/geventwebsocket/websocket.py", line 318, in send_frame
    raise WebSocketError(MSG_ALREADY_CLOSED)
geventwebsocket.exceptions.WebSocketError: Connection is already closed

During handling of the above exception, another exception occurred:

Traceback (most recent call last):
  File "/root/.local/share/uv/python/cpython-3.9.23-linux-x86_64-gnu/lib/python3.9/concurrent/futures/thread.py", line 58, in run
    result = self.fn(*self.args, **self.kwargs)
  File "/data/yunzetest/zkxh-digitalhuman-backend/realtime-digitalhuman/custom_llm.py", line 94, in llm_response_with_frontend_sync
    implementation(text, nerfreal_instance, ws)
  File "/data/yunzetest/zkxh-digitalhuman-backend/realtime-digitalhuman/rag_llm.py", line 135, in llm_response
    ws.send(json.dumps({'data': chunk,"id":msg_id, "finish": False}))
  File "/data/realtime-digitalhuman/.venv/lib/python3.9/site-packages/geventwebsocket/websocket.py", line 347, in send
    raise WebSocketError(MSG_SOCKET_DEAD)
geventwebsocket.exceptions.WebSocketError: Socket is dead






realtime-digitalhuman/
├── app/                          # 核心应用代码
│   ├── __init__.py
│   ├── main.py                   # 启动入口（极简）
│   ├── state.py                  # AppState 类
│   ├── config.py                 # ConfigManager + 配置加载
│   ├── handlers/                 # 所有 route handler
│   │   ├── __init__.py
│   │   ├── webrtc.py             # offer、setup_webrtc_tracks 等
│   │   ├── chat.py               # human、interrupt、echo、chat
│   │   ├── session.py            # generate_session、list_sessions、is_speaking
│   │   ├── config_handler.py     # update_config、set_audiotype
│   │   └── health.py
│   ├── services/                 # 业务服务层
│   │   ├── __init__.py
│   │   ├── nerfreal_factory.py   # 创建 LipReal 的统一工厂
│   │   ├── llm_bridge.py         # LLM 调用 + queue 管理
│   │   └── webrtc_manager.py     # PeerConnection 创建、codec、清理逻辑
│   ├── models/                   # 如果以后有 pydantic 模型
│   └── utils/
│       ├── __init__.py
│       ├── logger.py             # 如果要封装
│       └── exceptions.py
│
├── core/                         # 核心依赖（以后可能独立成包）
│   └── lipreal_wrapper.py        # 对 LipReal/BaseReal 的轻量封装
│
├── config/
│   ├── config.toml               # 你的配置文件
│   └── settings.py               # 可选：用 pydantic-settings 加载
│
├── data/                         # 数据目录（不提交 git）
│   ├── avatars/
│   ├── ref_audios/
│   └── customimage/
│
├── web/                          # 前端静态文件（你现在的 web 文件夹）
│   ├── webrtcapi.html
│   ├── dashboard.html
│   └── ...
│
├── logs/                         # 日志目录（.gitignore）
├── tests/                        # 以后慢慢加
├── requirements.txt
├── .gitignore
├── README.md
└── run.py                        # 生产启动脚本（可选）





作为单人开发 + 工程师，我给你推荐一个**实用、不过度设计、易维护**的项目结构，专门适合你这种实时数字人项目（aiohttp + WebRTC + LLM + 重模型）。

### 推荐的项目结构（2026 年单人维护友好版）

```bash
realtime-digitalhuman/
├── app/                          # 核心应用代码
│   ├── __init__.py
│   ├── main.py                   # 启动入口（极简）
│   ├── state.py                  # AppState 类
│   ├── config.py                 # ConfigManager + 配置加载
│   ├── handlers/                 # 所有 route handler
│   │   ├── __init__.py
│   │   ├── webrtc.py             # offer、setup_webrtc_tracks 等
│   │   ├── chat.py               # human、interrupt、echo、chat
│   │   ├── session.py            # generate_session、list_sessions、is_speaking
│   │   ├── config_handler.py     # update_config、set_audiotype
│   │   └── health.py
│   ├── services/                 # 业务服务层
│   │   ├── __init__.py
│   │   ├── nerfreal_factory.py   # 创建 LipReal 的统一工厂
│   │   ├── llm_bridge.py         # LLM 调用 + queue 管理
│   │   └── webrtc_manager.py     # PeerConnection 创建、codec、清理逻辑
│   ├── models/                   # 如果以后有 pydantic 模型
│   └── utils/
│       ├── __init__.py
│       ├── logger.py             # 如果要封装
│       └── exceptions.py
│
├── core/                         # 核心依赖（以后可能独立成包）
│   └── lipreal_wrapper.py        # 对 LipReal/BaseReal 的轻量封装
│
├── config/
│   ├── config.toml               # 你的配置文件
│   └── settings.py               # 可选：用 pydantic-settings 加载
│
├── data/                         # 数据目录（不提交 git）
│   ├── avatars/
│   ├── ref_audios/
│   └── customimage/
│
├── web/                          # 前端静态文件（你现在的 web 文件夹）
│   ├── webrtcapi.html
│   ├── dashboard.html
│   └── ...
│
├── logs/                         # 日志目录（.gitignore）
├── tests/                        # 以后慢慢加
├── requirements.txt
├── .gitignore
├── README.md
└── run.py                        # 生产启动脚本（可选）
```

### 为什么这个结构适合你？

- **单人开发友好**：文件夹不多，但逻辑清晰，分层明显。
- **扩展性好**：想加新功能（比如 TTS 服务、监控、鉴权）时，知道该放哪里。
- **可测试性提升**：`services/` 里的类可以单独单元测试。
- **避免文件过大**：目前你的 `main` 文件已经有 400+ 行，拆开后每个文件控制在 100~200 行以内。
- **符合架构师思维**：已经有明显的 **Presentation（handlers） → Service → Core** 分层。

### 拆分建议（按优先级，从易到难）

**第一阶段（推荐你这周做）** — 最有价值：

1. 把 `state.py` 独立出来（包含 `AppState` + `remove_session` 等方法）
2. 创建 `services/webrtc_manager.py`，把 `setup_webrtc_tracks`、`get_h264_preferred_codecs`、`offer` 中的 WebRTC 逻辑放进去
3. 创建 `services/nerfreal_factory.py`，把 `create_nerfreal` 放进去
4. 把所有 handler 按功能拆到 `handlers/` 下（每个文件一个或几个相关路由）

**第二阶段**：
- 把 LLM 消费者逻辑移到 `services/llm_bridge.py`
- 把 `ConfigManager` 移到 `config/` 或 `services/config_service.py`

**第三阶段（等你觉得需要时）**：
- 引入 `pydantic-settings` 管理配置
- 加 `middleware` 处理统一异常和 CORS
- 把启动逻辑拆成 `run.py` + `main.py`

---

### 我可以立刻帮你做的

既然你说“聊聊项目结构”，我直接给你**第一阶段的完整拆分方案**：

**方案 A（最小改动，推荐现在开始）**  
我给你：
- `app/state.py`
- `app/services/webrtc_manager.py`
- `app/handlers/webrtc.py`（改造后的 offer）
- `app/main.py`（新的启动入口）

你只需要把当前文件内容按我给的结构复制粘贴 + 少量 import 修改即可。

**方案 B**  
我直接给你**整个推荐目录结构 + 每个文件应该放什么内容**的模板，你自己慢慢拆。

---

**你选哪种？**

回复以下任意一种即可：

- **A**：给我第一阶段拆分后的 4 个文件完整代码（最快上手）
- **B**：先给我整体结构说明 + 每个文件夹的详细职责，我自己拆
- **C**：我们先讨论一下你最关心的部分（比如想不想把 LLM 部分也拆出来？或者担心拆了之后调试变麻烦？）

另外，我想听听你的想法：
你希望这个项目未来 3~6 个月内发展到什么程度？（支持 10 个并发？做成可部署的 SaaS？还是继续作为个人实验项目？）

告诉我你的选择和长期目标，我给你**最匹配**的结构建议和代码。  

继续保持这个节奏，你已经在架构师的路上了！




一、当前模块的优缺点评价
优点：

使用了流式输出（stream=True），对实时数字人很重要。
把响应分段送给 nerfreal.put_msg_txt()，语音生成更自然。
通过 result_queue 把文本发回主线程，解耦做得对。
有简单的历史记录管理。

主要问题（比较严重）：

全局状态问题conversation_histories = {} 是模块级全局变量，和我们之前努力收拢到 AppState 的方向冲突。
硬编码 + 魔法值太多
history_sessionid = "0"（这很危险，所有人共用同一套历史！）
history[1:][-9:] 这种切片写法可读性差
SYSTEM_PROMPT 里每次启动都重新格式化日期，但其实应该只生成一次

线程安全隐患result_queue.put_nowait() 在线程里调用是安全的，但 conversation_histories 是共享可变对象，没有任何锁。
结构不清晰
这个文件既做了“LLM 调用”又做了“历史管理”还做了“分段输出逻辑”，职责不单一。
配置加载方式不佳
在模块顶部直接 load_dotenv() + 全局变量，不是好习惯。


二、推荐的重构方向（符合你当前项目结构）
按照我们之前讨论的 handlers → services 分层，我建议把这个模块改造成：
app/services/llm_service.py（未来可以支持多 provider）
目标：


## ChatLog.vue 后续优化建议

当前已经完成两步小型整理：

- 抽出 `useInterruptibleStreamText.js`，收拢流式文本控制
- 抽出 `useAvatarSpeechSync.js`，收拢数字人说话状态轮询

目前 `ChatLog.vue` 已经从“UI + 流控制 + 轮询 + 测试代码”收敛到“UI + 状态编排”，可以继续维护。后续如果还要优化，建议按下面顺序推进：

### 优先级 1：先做稳定性回归验证

- 连续提问时新回复能否稳定打断旧回复
- `echo` 和 `chat` 两条链路混用时是否都正常
- 数字人未开口、刚开口、说完这几个临界时刻是否会卡状态
- WebSocket 重连或页面切换后是否有残留计时器和旧流状态

### 优先级 2：继续瘦身 `ChatLog.vue`

- 把 `initLLMSocket` 里的消息分发逻辑提成独立函数
- 减少组件内部直接操作流上下文对象的地方
- 把 “收到消息后决定是开启新流还是续写当前流” 再封装一层

### 优先级 3：继续收敛状态机

- 保留 `IDLE / PROCESSING / OUTPUTTING / FINISHED` 四个状态即可
- 如果后续行为稳定，可以考虑把部分状态切换逻辑内聚到 composable
- 尽量减少状态函数内部直接混入 timeout、socket、轮询三类副作用

### 优先级 4：清理体验层细节

- 统一 `console.log / warn / error` 的输出，减少调试噪音
- 视情况把打字速度抽成可配置参数
- 如有需要，再决定是否把超时隐藏逻辑抽成单独工具

### 当前建议

- 暂时先停在现状，不继续大改
- 先以“功能稳定 + 后续可维护”为目标
- 等前端联调与回归测试跑一轮后，再决定是否做第三步重构

---

让 LLM 服务成为一个可注入、可测试的类
把历史记录管理交给 AppState 或独立的 ConversationManager
让 llm_response 变成异步友好、线程安全的调用


三、我给你两个版本的改进方案
方案A（推荐，轻量级，适合你现在立刻改）
把 llm_gongan.py 改造成一个干净的服务类，放在 app/services/llm_gongan.py
Python# app/services/llm_gongan.py
import time
import uuid
import asyncio
from datetime import datetime
from typing import AsyncIterator

from openai import OpenAI
from loguru import logger

from app.state import AppState   # 我们后续会把 AppState 独立出去


class GonganLLMService:
    def __init__(self, state: AppState):
        self.state = state
        self.client = OpenAI(
            api_key=os.getenv("API_KEY"),
            base_url=os.getenv("BASE_URL"),
        )
        self.model_name = os.getenv("MODEL_NAME")
        
        # 系统提示只生成一次
        self.system_prompt = self._build_system_prompt()

    def _build_system_prompt(self) -> str:
        today = datetime.now().strftime('%Y年%-m月%-d日')
        today_en = datetime.now().strftime('%B %-d, %Y')
        return f"""你是一位名为"晓云警官"的专业AI助手...（把你原来的 SYSTEM_PROMPT 内容放这里，日期用 {today} 和 {today_en} 替换）"""

    def get_or_create_history(self, sessionid: str):
        """每个 session 独立历史记录（关键修复）"""
        if sessionid not in self.state.llm_histories:   # 我们需要在 AppState 加这个字段
            self.state.llm_histories[sessionid] = [
                {"role": "system", "content": self.system_prompt}
            ]
        return self.state.llm_histories[sessionid]

    async def stream_response(self, message: str, nerfreal, sessionid: str, result_queue: asyncio.Queue):
        """供线程中调用的 LLM 流式响应方法"""
        try:
            history = self.get_or_create_history(sessionid)
            history.append({"role": "user", "content": message})

            # 只保留最近 10 轮对话（system + 9轮）
            messages = [history[0]] + history[-9:]

            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=messages,
                temperature=0.0,
                stream=True,
                stream_options={"include_usage": True}
            )

            buffer = []
            full_response = []
            msg_id = str(uuid.uuid4())

            for chunk in response:
                if not chunk.choices or not chunk.choices[0].delta.content:
                    continue

                delta = chunk.choices[0].delta.content
                delta = delta.translate(str.maketrans("", "", "*#-"))  # 清理

                # 发给 WebSocket
                await asyncio.to_thread(result_queue.put_nowait, 
                                      {'data': delta, 'id': msg_id, 'finish': False})

                full_response.append(delta)
                buffer.append(delta)

                # 分段送给数字人说话（每积累约20字符且遇到标点就输出）
                if len(''.join(buffer)) >= 20:
                    text = ''.join(buffer)
                    last_punct = max((text.rfind(p) for p in ',.!;:，。！？：；'), default=-1)
                    if last_punct != -1:
                        output = text[:last_punct + 1]
                        nerfreal.put_msg_txt(output)
                        buffer = [text[last_punct + 1:]]

            # 处理最后剩余部分
            if buffer:
                nerfreal.put_msg_txt(''.join(buffer))

            # 保存助手回复到历史
            history.append({"role": "assistant", "content": ''.join(full_response)})

            # 发送结束信号
            await asyncio.to_thread(result_queue.put_nowait, 
                                  {'data': "", 'id': msg_id, 'finish': True})

        except Exception as e:
            logger.error(f"Gongan LLM 异常: {e}")
            await asyncio.to_thread(result_queue.put_nowait, 
                                  {'data': "抱歉，我暂时无法回答。", 'id': msg_id, 'finish': True})

下一步行动建议
我建议你按以下顺序进行：

先在 AppState 中增加历史记录字段：Pythonself.llm_histories: Dict[str, list] = {}
把上面的 GonganLLMService 类放到 app/services/llm_gongan.py
修改 _handle_chat_request 中调用方式为：Pythonllm_service = GonganLLMService(state)   # 或者做成单例/注入
asyncio.get_event_loop().run_in_executor(
    None,
    lambda: asyncio.run(llm_service.stream_response(...))   # 注意线程里不能直接 await
)


你想现在怎么继续？
回复以下任意选项，我立刻给你对应代码：

A：完整修改后的 AppState + llm_gongan.py 服务类（推荐）
B：只给我改造后的 llm_gongan.py（保持简单，不改 AppState）
C：我们先讨论如何让多 LLM provider（gongan / rag / chatgpt_oss）共存的结构

或者直接告诉我你对这个模块最不满意的地方是什么，我针对性给你方案。
继续往前走吧，这个模块重构完后，你的整个后端就更像一个“架构清晰的项目”了！
