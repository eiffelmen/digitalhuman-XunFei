/**
 * WebSocket管理工具类
 * 提供WebSocket连接、心跳、重连等功能
 */

export class WebSocketManager {
  constructor(url, options = {}) {
    this.url = url;
    this.options = {
      heartbeatInterval: options.heartbeatInterval || 5000,
      heartbeatTimeout: options.heartbeatTimeout || 10000,
      reconnectDelay: options.reconnectDelay || 3000,
      maxReconnectAttempts: options.maxReconnectAttempts || 5,
      onOpen: options.onOpen || (() => {}),
      onMessage: options.onMessage || (() => {}),
      onClose: options.onClose || (() => {}),
      onError: options.onError || (() => {}),
      onReconnect: options.onReconnect || (() => {}),
    };

    this.ws = null;
    this.heartbeatTimer = null;
    this.heartbeatTimeoutTimer = null;
    this.reconnectAttempts = 0;
    this.isManualClose = false;
  }

  /**
   * 连接WebSocket
   */
  connect() {
    try {
      this.ws = new WebSocket(this.url);
      this.isManualClose = false;

      this.ws.addEventListener('open', this.handleOpen.bind(this));
      this.ws.addEventListener('message', this.handleMessage.bind(this));
      this.ws.addEventListener('close', this.handleClose.bind(this));
      this.ws.addEventListener('error', this.handleError.bind(this));
    } catch (error) {
      console.error('WebSocket连接失败:', error);
      this.options.onError(error);
      this.reconnect();
    }
  }

  /**
   * 处理连接成功
   */
  handleOpen(event) {
    console.log('WebSocket连接成功');
    this.reconnectAttempts = 0;
    this.startHeartbeat();
    this.options.onOpen(event);
  }

  /**
   * 处理消息
   */
  handleMessage(event) {
    try {
      const data = JSON.parse(event.data);

      // 处理心跳响应
      if (data.type === 'pong') {
        console.log('收到心跳响应');
        if (this.heartbeatTimeoutTimer) {
          clearTimeout(this.heartbeatTimeoutTimer);
        }
        return;
      }

      this.options.onMessage(data, event);
    } catch (error) {
      console.error('解析WebSocket消息失败:', error);
      this.options.onMessage(event.data, event);
    }
  }

  /**
   * 处理连接关闭
   */
  handleClose(event) {
    console.log('WebSocket连接关闭');
    this.stopHeartbeat();
    this.options.onClose(event);

    // 如果不是手动关闭，尝试重连
    if (!this.isManualClose) {
      this.reconnect();
    }
  }

  /**
   * 处理错误
   */
  handleError(event) {
    console.error('WebSocket连接错误:', event);
    this.options.onError(event);
  }

  /**
   * 发送消息
   */
  send(data) {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      const message = typeof data === 'string' ? data : JSON.stringify(data);
      this.ws.send(message);
      return true;
    } else {
      console.warn('WebSocket未连接，无法发送消息');
      return false;
    }
  }

  /**
   * 开始心跳
   */
  startHeartbeat() {
    this.stopHeartbeat();

    // 立即发送第一次心跳
    this.sendHeartbeat();

    // 定时发送心跳
    this.heartbeatTimer = setInterval(() => {
      this.sendHeartbeat();
    }, this.options.heartbeatInterval);
  }

  /**
   * 发送心跳
   */
  sendHeartbeat() {
    if (this.send({ type: 'ping', userId: '1' })) {
      // 设置心跳超时检测
      if (this.heartbeatTimeoutTimer) {
        clearTimeout(this.heartbeatTimeoutTimer);
      }

      this.heartbeatTimeoutTimer = setTimeout(() => {
        console.log('心跳超时，重新连接WebSocket');
        this.reconnect();
      }, this.options.heartbeatTimeout);
    }
  }

  /**
   * 停止心跳
   */
  stopHeartbeat() {
    if (this.heartbeatTimer) {
      clearInterval(this.heartbeatTimer);
      this.heartbeatTimer = null;
    }

    if (this.heartbeatTimeoutTimer) {
      clearTimeout(this.heartbeatTimeoutTimer);
      this.heartbeatTimeoutTimer = null;
    }
  }

  /**
   * 重连
   */
  reconnect() {
    if (this.isManualClose) {
      return;
    }

    if (this.reconnectAttempts >= this.options.maxReconnectAttempts) {
      console.error('WebSocket重连次数超过限制');
      return;
    }

    this.reconnectAttempts++;
    console.log(`尝试重新连接WebSocket... (${this.reconnectAttempts}/${this.options.maxReconnectAttempts})`);

    this.stopHeartbeat();

    setTimeout(() => {
      this.options.onReconnect(this.reconnectAttempts);
      this.connect();
    }, this.options.reconnectDelay);
  }

  /**
   * 关闭连接
   */
  close() {
    this.isManualClose = true;
    this.stopHeartbeat();

    if (this.ws) {
      this.ws.close();
      this.ws = null;
    }
  }

  /**
   * 检查连接状态
   */
  isConnected() {
    return this.ws && this.ws.readyState === WebSocket.OPEN;
  }
}

export default WebSocketManager;
