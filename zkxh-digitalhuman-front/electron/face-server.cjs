const http = require('http');
const { EventEmitter } = require('events');
const { WebSocketServer } = require('ws');

class FaceDataBridge extends EventEmitter {
  constructor(options = {}) {
    super();
    this.httpPort = Number(options.httpPort ?? process.env.FACE_HTTP_PORT ?? 3100);
    this.httpPath = options.httpPath ?? process.env.FACE_HTTP_PATH ?? '/face';
    this.wsPort = Number(options.wsPort ?? process.env.FACE_WS_PORT ?? 3200);
    this.logger = options.logger || console;
    this.httpServer = null;
    this.wsServer = null;
  }

  start() {
    this.startHttpServer();
    this.startWsServer();
  }

  stop() {
    if (this.httpServer) {
      this.httpServer.close(() => this.logger.log('[FaceBridge] HTTP 服务已关闭'));
      this.httpServer = null;
    }
    if (this.wsServer) {
      this.wsServer.close(() => this.logger.log('[FaceBridge] WebSocket 服务已关闭'));
      this.wsServer = null;
    }
  }

  startHttpServer() {
    if (this.httpServer) {
      return;
    }
    this.httpServer = http.createServer((req, res) => {
      // 处理 CORS 预检请求
      res.setHeader('Access-Control-Allow-Origin', '*');
      res.setHeader('Access-Control-Allow-Methods', 'POST, OPTIONS');
      res.setHeader('Access-Control-Allow-Headers', 'Content-Type');

      if (req.method === 'OPTIONS') {
        res.writeHead(204);
        res.end();
        return;
      }

      if (req.method !== 'POST' || req.url !== this.httpPath) {
        res.writeHead(404, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify({ message: 'Not Found' }));
        return;
      }

      let body = '';
      req.on('data', chunk => {
        body += chunk;
      });
      req.on('end', () => {
        this.handleIncomingPayload(body, 'http');
        res.writeHead(200, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify({ status: 'ok' }));
      });
    });

    this.httpServer.listen(this.httpPort, '0.0.0.0', () => {
      this.logger.log(
        `[FaceBridge] HTTP 服务已启动: http://127.0.0.1:${this.httpPort}${this.httpPath}`
      );
    });
  }

  startWsServer() {
    if (this.wsServer) {
      return;
    }
    this.wsServer = new WebSocketServer({ port: this.wsPort });
    this.wsServer.on('connection', socket => {
      this.logger.log('[FaceBridge] WebSocket 客户端已连接');
      socket.on('message', message => {
        this.handleIncomingPayload(message, 'ws');
      });
      socket.on('close', () => {
        this.logger.log('[FaceBridge] WebSocket 客户端断开');
      });
    });
    this.wsServer.on('listening', () => {
      this.logger.log(`[FaceBridge] WebSocket 服务监听端口: ws://127.0.0.1:${this.wsPort}`);
    });
    this.wsServer.on('error', error => {
      this.logger.error('[FaceBridge] WebSocket 服务异常:', error);
    });
  }

  handleIncomingPayload(buffer, source = 'unknown') {
    if (!buffer || buffer.length === 0) {
      return;
    }
    let payload = null;
    try {
      const text = buffer.toString();
      payload = JSON.parse(text);
    } catch (error) {
      this.logger.error(`[FaceBridge] ${source} 数据解析失败:`, error);
      return;
    }

    this.logger.log(`[FaceBridge] 收到 ${source} 人脸数据:`, payload);
    this.emit('face-data', payload);
  }
}

module.exports = { FaceDataBridge };
