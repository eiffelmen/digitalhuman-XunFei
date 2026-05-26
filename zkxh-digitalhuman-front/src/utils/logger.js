/**
 * 日志管理工具
 * 在Electron环境下可以将日志发送到主进程
 */

const isElectron = window.electronAPI && window.electronAPI.isElectron;

// 日志级别
export const LOG_LEVELS = {
  DEBUG: 'debug',
  INFO: 'info',
  WARN: 'warn',
  ERROR: 'error',
  NONE: 'none', // 关闭所有日志
};

// 日志级别优先级
const LEVEL_PRIORITY = {
  debug: 0,
  info: 1,
  warn: 2,
  error: 3,
  none: 999,
};

/**
 * 统一日志方法
 */
class Logger {
  constructor(prefix = '') {
    this.prefix = prefix;
    // 从 localStorage 读取日志级别配置，默认为 info
    this.currentLevel = localStorage.getItem('logLevel') || 'info';
  }

  /**
   * 设置日志级别
   */
  setLevel(level) {
    if (LEVEL_PRIORITY[level] !== undefined) {
      this.currentLevel = level;
      localStorage.setItem('logLevel', level);
    }
  }

  /**
   * 获取当前日志级别
   */
  getLevel() {
    return this.currentLevel;
  }

  /**
   * 检查是否应该输出日志
   */
  shouldLog(level) {
    return LEVEL_PRIORITY[level] >= LEVEL_PRIORITY[this.currentLevel];
  }

  /**
   * 格式化日志消息
   */
  formatMessage(level, message, ...args) {
    const timestamp = new Date().toISOString();
    const prefix = this.prefix ? `[${this.prefix}]` : '';
    return {
      timestamp,
      level,
      prefix,
      message,
      args,
    };
  }

  /**
   * 发送日志到Electron主进程
   */
  sendToElectron(level, message) {
    if (isElectron && window.electronAPI.logMessage) {
      window.electronAPI.logMessage(level, message);
    }
  }

  /**
   * 调试日志
   */
  debug(message, ...args) {
    if (!this.shouldLog(LOG_LEVELS.DEBUG)) return;
    const formatted = this.formatMessage(LOG_LEVELS.DEBUG, message, ...args);
    console.debug(`${formatted.prefix}`, message, ...args);
    this.sendToElectron(LOG_LEVELS.DEBUG, `${formatted.prefix} ${message}`);
  }

  /**
   * 信息日志
   */
  info(message, ...args) {
    if (!this.shouldLog(LOG_LEVELS.INFO)) return;
    const formatted = this.formatMessage(LOG_LEVELS.INFO, message, ...args);
    console.info(`${formatted.prefix}`, message, ...args);
    this.sendToElectron(LOG_LEVELS.INFO, `${formatted.prefix} ${message}`);
  }

  /**
   * 警告日志
   */
  warn(message, ...args) {
    if (!this.shouldLog(LOG_LEVELS.WARN)) return;
    const formatted = this.formatMessage(LOG_LEVELS.WARN, message, ...args);
    console.warn(`${formatted.prefix}`, message, ...args);
    this.sendToElectron(LOG_LEVELS.WARN, `${formatted.prefix} ${message}`);
  }

  /**
   * 错误日志
   */
  error(message, ...args) {
    if (!this.shouldLog(LOG_LEVELS.ERROR)) return;
    const formatted = this.formatMessage(LOG_LEVELS.ERROR, message, ...args);
    console.error(`${formatted.prefix}`, message, ...args);
    this.sendToElectron(LOG_LEVELS.ERROR, `${formatted.prefix} ${message}`);
  }

  /**
   * 创建子logger
   */
  createChild(childPrefix) {
    const newPrefix = this.prefix ? `${this.prefix}:${childPrefix}` : childPrefix;
    return new Logger(newPrefix);
  }
}

// 创建默认logger实例
export const logger = new Logger('DigitalHuman');

// 导出Logger类供创建自定义logger
export { Logger };

// 在开发环境下，将 logger 暴露到 window 对象，方便控制台调试
if (typeof window !== 'undefined') {
  window.logger = logger;
  window.LOG_LEVELS = LOG_LEVELS;
  console.log('[Logger] logger 已暴露到 window 对象，可在控制台使用 logger.setLevel() 控制日志级别');
  console.log('[Logger] 可用级别:', Object.values(LOG_LEVELS));
  console.log('[Logger] 当前级别:', logger.getLevel());
}

export default logger;
