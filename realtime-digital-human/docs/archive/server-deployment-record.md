# 服务器部署记录

## 前端部署

```shell
npm run build
scp dist/* root@server:/var/www/html
```

## digitalman 部署

- 不使用docker部署

```shell
# 服务器端

# 安装uv

curl -LsSf https://astral.sh/uv/install.sh | sh

# 挂载硬盘

rsync -avzP --exclude='.venv' \
  --exclude='__pycache__' \
  --exclude='.cache' \
  --exclude='*.pyc' \
  --exclude='gguf' \
  --exclude='data' \
  --exclude='Spark-TTS' \
  --exclude='FunASR' \
  --exclude='digitalhuman-web' \
  --exclude='digitalhuman-web-xinhe' \
  --no-specials --no-devices \
  /Data1/home/lishuang/realtime-digitalhuman/ \
  root@your-server-host:/data/realtime-digitalhuman/


```