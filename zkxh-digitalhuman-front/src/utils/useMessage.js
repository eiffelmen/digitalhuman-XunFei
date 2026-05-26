function useMessage(params = {}) {
  // 参数验证
  if (typeof params !== 'object' || params === null) {
    throw new Error('Invalid params, expected an object');
  }

  const { message, type = 'info', duration = 3000 } = params;
  const doc = document;

  // 改进 CSS 类名生成方式
  const timestamp = Date.now().toString(36);
  const cssModule = `_${timestamp}`;
  const className = {
    box: `msg-box${cssModule}`,
    hide: `hide${cssModule}`,
    text: `msg-text${cssModule}`,
    icon: `msg-icon${cssModule}`,
  };

  // 创建消息框元素
  const messageBox = doc.createElement('div');
  messageBox.className = className.box;
  messageBox.style.position = 'fixed';
  messageBox.style.top = '20px';
  messageBox.style.left = '50%';
  messageBox.style.transform = 'translateX(-50%)';
  messageBox.style.borderRadius = '4px';
  messageBox.style.padding = '5px 10px';
  messageBox.style.boxShadow = '0 2px 12px 0 rgba(0, 0, 0, 0.1)';
  messageBox.style.zIndex = '9000';
  messageBox.style.transition = 'opacity 0.3s';

  // 创建消息文本元素
  const messageText = doc.createElement('span');
  messageText.className = className.text;
  messageText.textContent = message;

  // 创建消息图标元素
  const messageIcon = doc.createElement('i');
  messageIcon.className = className.icon;
  messageIcon.style.marginRight = '8px';
  switch (type) {
    case 'success':
      messageBox.style.backgroundColor = 'rgb(225, 243, 216)';
      messageBox.style.color = '#67C23A';
      messageIcon.style.color = '#67C23A';
      messageIcon.textContent = '✓';
      break;
    case 'warning':
      messageIcon.style.color = '#e6a23c';
      messageBox.style.color = '#e6a23c';
      messageBox.style.backgroundColor = 'rgb(250, 236, 216)';
      messageIcon.textContent = '!';
      break;
    case 'error':
      messageIcon.style.color = '#f56c6c';
      messageBox.style.color = '#f56c6c';
      messageBox.style.backgroundColor = 'rgb(253, 226, 226)';
      messageIcon.textContent = '✗';
      break;
    default:
      messageIcon.style.color = '#909399';
      messageBox.style.color = '#909399';
      messageBox.style.backgroundColor = 'rgb(233, 233, 235)';
      messageIcon.textContent = 'i';
  }

  // 将图标和文本添加到消息框
  messageBox.appendChild(messageIcon);
  messageBox.appendChild(messageText);

  // 将消息框添加到文档中
  doc.body.appendChild(messageBox);

  // 设置定时器自动关闭消息框
  setTimeout(() => {
    messageBox.style.opacity = '0';
    setTimeout(() => {
      doc.body.removeChild(messageBox);
    }, 300);
  }, duration);
}
export default useMessage;