.PHONY: dev noconfig start stop

# 前台运行（默认配置，无自定义视频）
noconfig:
	. .venv/bin/activate && CUDA_VISIBLE_DEVICES=1 python app_v2.py --max_session 10 --tts sparktts --TTS_SERVER http://localhost:8779 --wav2lip_size 256

# 前台运行（自定义视频配置）
dev:
	. .venv/bin/activate && CUDA_VISIBLE_DEVICES=1 python app_v2.py --max_session 10 --tts sparktts --TTS_SERVER http://localhost:8779 --wav2lip_size 256 --customvideo_config data/custom_config.json

# 后台启动
start:
	nohup bash run_digitalman_server.sh > logs/server.log 2>&1 & echo $$! > server.pid && echo "已启动，PID: $$(cat server.pid)"

# 停止后台服务
stop:
	@if [ -f server.pid ]; then \
		pid=$$(cat server.pid); \
		if kill -0 $$pid 2>/dev/null; then \
			kill $$pid; \
			sleep 2; \
			if kill -0 $$pid 2>/dev/null; then \
				kill -9 $$pid; \
			fi; \
			echo "已停止，PID: $$pid"; \
		else \
			echo "PID $$pid 不存在，清理残留 server.pid"; \
		fi; \
		rm -f server.pid; \
	else \
		echo "server.pid 不存在，服务可能未在运行"; \
	fi
