# Android 服务就绪检查逻辑文档

## 概述
为了确保 Android App 在后台服务（实时服务和设备服务）完全启动并就绪后再进行业务逻辑（如加载页面、启动采集服务等），实现了一套基于轮询的就绪检查机制。

## 实现细节

### 1. 后端接口 与 网页检查
系统会同时检查以下三个地址的可访问性：
- **设备服务**: `http://<SERVER_IP>:8000/ready` (GET)
- **实时服务**: `http://<SERVER_IP>:8010/ready` (GET)
- **WebView 网页**: `https://<SERVER_IP>/` (HEAD)
- **响应格式**: 前两个接口需返回 `{"status": 1}`；网页接口需返回状态码 200。

### 2. Android 客户端实现

#### 2.1 网络层 (BackendApi.java)
增加了两个核心检查方法：
- `isServiceReady(String url)`: 专门用于带 JSON 状态检查的后端就绪接口，超时 500ms。
- `isUrlAccessible(String url)`: 用于检查普通 URL（如 WebView 首页）是否可达，超时 1000ms，支持自动忽略 SSL 证书验证。

#### 2.2 UI 与启动层 (MainActivity.java)
- **启动页**: 在 `activity_main.xml` 中增加了一个白色背景的 `startup_overlay` 覆盖层，默认显示。
- **轮询逻辑**: 使用 `Handler` 每隔 2 秒检查一次上述两个接口。
- **业务切换**: 只有当两个服务都返回就绪时，才会隐藏启动页 (`View.GONE`) 并执行 `startBusinessLogic()`，包括启动 `MyBackgroundService` 和加载 WebView。

## 维护记录
- **日期**: 2026-03-16
- **内容**: 增加服务启动就绪检测及 App 启动等待页。
