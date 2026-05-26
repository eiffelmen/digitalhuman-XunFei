# 数字人前端

数字人前端项目 - 支持Web和Electron双模式部署

## 🚀 项目特性

- ✅ **Vue3 + Vite** - 现代化前端技术栈
- ✅ **Electron支持** - 可打包为Ubuntu桌面应用
- ✅ **WebRTC集成** - 实时音视频交互
- ✅ **语音识别** - ASR语音转文字
- ✅ **大模型对话** - LLM智能交互
- ✅ **TTS语音合成** - 文字转语音
- ✅ **开机自启** - systemd服务支持

## 📦 部署方式

本项目支持两种部署方式：

### 1. Electron桌面应用（推荐用于Ubuntu系统）

**适用场景**: 独立部署的Ubuntu桌面系统或服务器

**优势**:
- 无需Web服务器
- 可配置开机自启
- 独立应用，易于管理
- 支持离线运行

**快速开始**:
```bash
# 安装依赖
npm install

# 打包应用
npm run build:electron

# 安装（Ubuntu系统）
sudo dpkg -i dist-electron/zkxh-digitalhuman_*.deb
```

📖 **详细文档**: [Electron部署指南](./ELECTRON_DEPLOYMENT.md) | [快速开始](./QUICKSTART.md)

### 2. Web应用（传统方式）

**适用场景**: 通过浏览器访问的Web服务

**快速开始**:
```bash
# 开发模式
npm run dev

# 生产构建
npm run build
```

📖 **详细文档**: 见下方"Web部署"章节

---

## 🛠️ 开发环境

### 开发环境安装(Nodejs)

```sh
curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.0/install.sh | bash
nvm install 20
```

### 安装项目依赖

进入前端项目根目录执行

```sh
npm install
```

### 预览项目

```sh
npm run dev
```

## 🌐 Web部署

### 安装Nginx服务器

```sh
sudo apt install nginx
```

### 修改配置文件

修改`/etc/nginx/sites-available/default`

将

```sh
location / {
        try_files $uri $uri/ =404;
}
```

修改为

```sh
location / {
    try_files $uri $uri/ /index.html;
}
```

### 构建生产版本

```sh
npm run build
```

### 部署

`npm run build`后，将dist文件夹所有内容复制到`/var/www/html/`

```sh
sudo sh run_deploy_nginx.sh
```

## 启动

### Electron应用启动

```bash
# 方式1: 命令行
zkxh-digitalhuman

# 方式2: 应用程序菜单
# 在Ubuntu应用程序菜单中搜索 "ZKXH DigitalHuman"

# 方式3: systemd服务
sudo systemctl start zkxh-digitalhuman
```

### Web应用启动

打开浏览器访问`http://localhost`


## 配置nginx转发

/etc/nginx/sites-available/digitalhuman

重启：
```sh
sudo systemctl restart nginx
```

## 制作本地证书

```shell
mkcert -cert-file service.pem -key-file service-key.pem 公网IP localhost 127.0.0.1 ::1
```

todo: 制定证书文件名字，这样Dockerfile中和nginx中可以写死证书文件名，到另外的服务器部署不需要调整nginx配置和Dockerfile配置

## Docker方式启动

`docker-compose up -d --build`
