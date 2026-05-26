# 部署指南

历史部署记录和 Docker 操作说明见 [docs/README.md](docs/README.md)。

## 日常开发工作流

**特性分支开发 → 本地验证 → 合并主分支 → 服务器拉取更新 → 重启服务**

### 第一步：特性分支开发

```bash
git checkout main
git pull origin main
git checkout -b feat/你的功能名

# 写代码...

# 本地跑测试
pytest tests -q

git add .
git commit -m "feat: 描述你做了什么"
git push origin feat/你的功能名
```

提交格式参考：
```
feat(tts): 添加 FlashTTS 支持
fix: 修复日志轮转问题
refactor(session): 提取会话清理逻辑
```

### 第二步：合并主分支

```bash
git checkout main
git merge feat/你的功能名
git push origin main
```

### 第三步：服务器拉取更新

```bash
git pull origin main

# 如果有新依赖
uv sync
```

### 第四步：重启服务

```bash
make stop   # 停止旧进程
make start  # 后台启动
```

前台运行（调试时用）：

```bash
bash run_digitalman_server.sh
```

---

## run_digitalman_server.sh 说明

这是服务的唯一启动入口，修改启动参数在这里改。当前配置：

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `LLM_PROVIDER` | `gongan` | LLM 提供商，可选 `rag`、`chatgpt_oss`、`ratubrain`、`aliyun`、`iflytek` |
| `LISTEN_PORT` | `8010` | 服务监听端口，可通过环境变量覆盖 |
| `CUDA_VISIBLE_DEVICES` | `1` | 使用的 GPU 编号，可通过环境变量覆盖 |
| `--max_session` | `10` | 最大并发会话数 |
| `--tts` | `sparktts` | TTS 提供商 |
| `--TTS_SERVER` | `http://localhost:8779` | TTS 服务地址 |
| `--wav2lip_size` | `256` | 模型输出尺寸 |
| `--transport` | `webrtc` | 推流协议 |

脚本中的变量均支持外部覆盖，生产环境无需修改脚本，在服务器上设置环境变量即可：

```bash
# 生产环境启动
LISTEN_PORT=8010 bash run_digitalman_server.sh

# 或提前 export
export LISTEN_PORT=8010
make start
```

---

## 环境初始化（首次部署）

```bash
# 安装依赖
uv sync

# 复制环境变量配置
cp .env.template .env
# 编辑 .env，填入实际的 API Key 等配置
```

---

## 注意事项

- `.env` 不提交到 git，包含敏感配置
- `make start` 默认把启动日志写到 `logs/server.log`
- GPU 不够用时调小 `--max_session`

---

## 故障排查

```bash
# 查看实时日志
tail -f logs/server.log

# 确认进程在跑
ps aux | grep app_v2.py

# 确认端口在监听
ss -tlnp | grep 8010
```
