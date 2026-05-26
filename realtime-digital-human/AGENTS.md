# AGENTS.md

本文件为在本仓库协作的智能体提供统一工作指南。

## 项目概述

实时数字人后端系统，支持多种数字人模型（wav2lip、synctalk、ernerf）、语音克隆、语音打断、全身视频拼接，以及 RTMP 和 WebRTC 推流。

## 开发环境

### 环境要求
- Ubuntu 20.04
- Python 3.10+
- PyTorch 2.0+
- CUDA 11.7+
- GPU（模型推理必需）

### 依赖安装
```bash
# 使用 uv（推荐）
uv sync

# 或使用 pip
pip install -r requirements.txt
```

### 环境变量
- `CUDA_VISIBLE_DEVICES`：GPU 设备选择
- `TTS_SERVICE`：TTS 服务地址
- `HF_ENDPOINT`：HuggingFace 镜像（如需要）
- `LLM_PROVIDER`：LLM 提供商（`gongan`、`rag`、`chatgpt_oss`、`ratubrain`、`aliyun`、`iflytek`，默认 `gongan`）

## 常用命令

### 运行服务
```bash
# 默认启动（wav2lip + WebRTC）
sh run_digitalman_server.sh

# 使用 .venv 环境运行
.venv/bin/python app_v2.py --max_session 10 --tts sparktts --TTS_SERVER http://localhost:8779 --wav2lip_size 256 --transport webrtc

# 自定义视频配置模式
make dev

# 快速运行（默认配置）
make noconfig
```

### 测试
```bash
# 运行所有测试
pytest tests -q

# 运行特定测试
pytest tests/test_digitalman_api.py -k smoke
```

### 关键启动参数
| 参数 | 说明 | 默认值 |
|------|------|--------|
| `--max_session` | 最大并发会话数 | 10 |
| `--tts` | TTS 提供商（sparktts、gpt-sovits-v2、edge-tts） | - |
| `--TTS_SERVER` | TTS 服务地址 | - |
| `--wav2lip_size` | 模型输出尺寸（256、512） | 256 |
| `--transport` | 推流协议（webrtc、rtmp） | webrtc |

## 架构概览

### 核心组件

```text
app_v2.py          # 主入口（aiohttp WebSocket + aiohttp HTTP）
├── lipreal.py     # 数字人模型调度
├── session_manager.py  # 会话生命周期管理
├── webrtc.py      # WebRTC 流媒体管理
├── basereal.py    # 模型基类
├── ttsreal.py     # TTS 适配层
└── lipasr.py      # ASR 适配层
```

### LLM 实现
- `llm_gongan.py`：公安 LLM（默认）
- `rag_llm.py`：RAG LLM
- `chatgpt_oss_client.py`：ChatGPT OSS
- `llm_ratubrain.py`：Ratubrain
- `llm_aliyun.py`：阿里云 LLM
- `llm/providers/iflytek.py`：讯飞 LLM

通过 `LLM_PROVIDER` 环境变量切换。

### WebSocket 会话管理
- `sessionid_ws`：存储 WebSocket 连接，key 为 sessionid
- LLM 模块通过 `run_coroutine_threadsafe()` 跨线程发送消息到 WebSocket
- LLM 函数签名：`llm_response(message, nerfreal, sessionid_ws, sessionid, main_loop)`

### 数据流
```text
客户端 → WebRTC/RTMP → lipreal → TTS → 数字人视频合成 → 推送
                ↑                              ↓
              ASR ←──────────────────────────┘
```

## 端口配置

| 服务 | 端口 | 说明 |
|------|------|------|
| API + WebSocket | 8010 | 主服务端口（统一） |
| SRS/WebRTC | 8000/1985 | 流媒体 |

需要开放：TCP 8000、8010、1985；UDP 8000

## 代码规范

### 风格
- 遵循 PEP 8，4 空格缩进
- 日志统一使用 `loguru`（已在 `mylogger.py` 配置每周轮转、保留 14 天）
- 禁止硬编码配置，统一使用环境变量

### 提交格式
```text
type(scope): 简短描述

示例：
feat(tts): 添加 FlashTTS 支持
fix: 修复日志轮转问题
refactor(session): 提取会话清理逻辑
```

## 配置管理

- `config.toml`：运行时配置（由 ConfigManager 管理）
- 自定义视频配置 JSON 文件
- LLM 提供商通过 `LLM_PROVIDER` 环境变量配置

## 性能参考

- 帧率：A800 上约 25 FPS（去掉编码约 30 FPS）
- 延迟：2-3 秒（不含 ASR）
  - TTS 延迟：1.2-1.7 秒
  - 模型推理：约 0.4 秒

## 目录结构

```text
.
├── app_v2.py          # 主服务入口
├── app.py             # 旧版 Flask 实现
├── session_manager.py # 会话管理
├── lipreal.py         # 数字人模型
├── basereal.py        # 模型基类
├── webrtc.py          # WebRTC 处理
├── llm*.py            # LLM 相关实现（gongan, rag_llm, chatgpt_oss, ratubrain, aliyun）
├── llm/providers/     # Provider 实现（含 iflytek）
├── ttsreal.py         # TTS 适配
├── lipasr.py          # ASR 适配
├── mylogger.py        # 日志配置
├── wav2lip256/        # wav2lip 模型
├── tests/             # 测试用例
├── data/              # 静态资源
├── web/               # 前端资源
└── logs/              # 日志目录
```

## 协作约定

- 每次对代码进行重要改动后，需同步更新项目内相应文档。
- 优先采用最佳实践，并避免过度设计。
