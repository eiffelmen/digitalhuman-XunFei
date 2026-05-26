import json
import time
import uuid
import asyncio
from datetime import datetime

from loguru import logger
from openai import OpenAI
from dotenv import load_dotenv
from basereal import BaseReal
import os

# 加载环境变量
load_dotenv()

BASE_URL = os.environ.get("BASE_URL")
API_KEY = os.environ.get("API_KEY")
MODEL_NAME = os.environ.get("MODEL_NAME")

SYSTEM_PROMPT = f"""你是一位名为"晓云警官"的专业AI助手，由连云港市公安局开发，今天是{datetime.now().strftime('%Y年%-m月%-d日')}。
You are a professional AI assistant named "Officer Xiaoyun", developed by the Lianyungang Public Security Bureau. Today is {datetime.now().strftime('%B %-d, %Y')}.

**核心能力**:
- 知识覆盖至2025年7月7日
- 提供准确、权威且实用的信息
- 响应速度快，处理效率高

**Core Competencies**:
- Knowledge coverage up to July 7, 2025
- Provide accurate, authoritative, and practical information
- Fast response and high processing efficiency

**交互规范**:
1. **语言模式**：
   - 默认使用标准中文普通话
   - 根据用户提问语言自动切换(中/英)

2. **回答要求**：
   - 内容必须专业、完整且直接解决问题
   - 避免简单确认语句("好的"、"是的"等)
   - 禁用非正式表达和表情符号
   - 禁止添加"请注意"、"需要说明的是"等解释性语句

3. **输出控制**：
   - 简明扼要，单次回答不超过 80 字
   - 复杂问题可分点说明
   - 确保信息准确性和时效性
   - 对输出内容进行总结，需突出重点

**Interaction Guidelines**:
1. **Language Mode**:
   - Default to standard Mandarin Chinese
   - Automatically switch based on user's question language (Chinese/English)

2. **Response Requirements**:
   - Content must be professional, comprehensive, and directly address the issue
   - Avoid simple confirmation statements ("OK", "Yes", etc.)
   - Prohibit informal expressions and emojis
   - Do not add explanatory phrases like "Please note", "It should be noted" etc.

3. **Output Control**:
   - Be concise, with single responses not exceeding 80 words
   - Present complex issues in points
   - Ensure information accuracy and timeliness
   - Summarize output content, highlighting key points

**注意事项**：
- 对任何问题都需提供实质性帮助
- 不确定的内容明确说明
- 涉及隐私或敏感话题时礼貌拒绝
- 不需要总结内容

**Notes**:
- Provide substantial assistance for all questions
- Clearly state uncertain information
- Politely decline when privacy or sensitive topics are involved
- Summaries must be faithful to the original response without adding new information

请严格遵循上述规范，为用户提供高质量的专业服务。
Please strictly follow the above guidelines to provide high - quality professional services to users."""

conversation_histories = {}


def get_history(sessionid):
    """获取或创建指定会话的历史记录"""
    if sessionid not in conversation_histories:
        conversation_histories[sessionid] = [{
            "role": "system",
            "content": SYSTEM_PROMPT,
        }]
    return conversation_histories[sessionid]


# 创建同步OpenAI客户端
client = OpenAI(
    api_key=API_KEY,
    base_url=BASE_URL,
)


def llm_response(message: str, nerfreal: BaseReal, sessionid: str, result_queue: asyncio.Queue) -> str:
    """
    公安LLM响应方法 - 基于OpenAI客户端重新实现

    Args:
        message: 用户输入消息
        nerfreal: 数字人实例
        sessionid: WebSocket会话ID
        result_queue: 异步队列，用于主线程发送WebSocket消息

    Returns:
        str: 完整的响应文本
    """

    start_time = time.perf_counter()
    first_token_received = False
    msg_id = str(uuid.uuid4())  # 生成消息ID

    try:
        # 获取会话历史
        history_sessionid = "0"  # 默认会话ID
        history = get_history(history_sessionid)
        history.append({
            "role": "user",
            "content": message,
        })

        # 使用OpenAI客户端进行流式请求
        response = client.chat.completions.create(
            messages=[history[0]] + history[1:][-9:],  # system和除system的最近9条对话
            model=MODEL_NAME,
            temperature=0,
            stream=True,
            # 通过以下设置，在流式输出的最后一行展示token使用信息
            stream_options={"include_usage": True}
        )

        buffer = []
        complete_response = []

        logger.info("开始接收公安LLM流式响应")

        # 处理流式响应
        for chunk_response in response:
            if not chunk_response.choices:
                continue

            if not first_token_received:
                first_token_received = True
                logger.info(f"LLM首次响应耗时: {time.perf_counter() - start_time:.2f}s")

            # 获取消息内容
            msg = chunk_response.choices[0].delta.content
            if not msg:
                continue

            # 清理特殊字符
            msg = msg.translate(str.maketrans("", "", "*#-"))

            # 通过队列发送到WebSocket
            result_queue.put_nowait({'data': msg, 'id': msg_id, 'finish': False})

            complete_response.append(msg)
            buffer.append(msg)

            # 增加分段长度阈值,确保每段文本更完整
            if len(''.join(buffer)) >= 20:
                text = ''.join(buffer)
                # 优化标点符号查找逻辑
                last_punct = -1
                for p in ',.!;:，。！？：；':
                    pos = text.rfind(p)
                    if pos > last_punct:
                        last_punct = pos

                if last_punct != -1:
                    output_text = text[:last_punct + 1]
                    logger.debug(f"输出文本片段: {output_text}")
                    nerfreal.put_msg_txt(output_text)
                    buffer = [text[last_punct + 1:]]

        # 处理剩余的buffer
        if buffer:
            final_text = ''.join(buffer)
            if final_text.strip():
                logger.debug(f"输出最终文本片段: {final_text}")
                nerfreal.put_msg_txt(final_text)

        # 更新会话历史
        history.append({
            "role": "assistant",
            "content": ''.join(complete_response),
        })

        # 发送完成消息
        result_queue.put_nowait({'data': "", 'id': msg_id, 'finish': True})

        logger.info(f"LLM总响应耗时: {time.perf_counter() - start_time:.2f}s")

        return ''.join(complete_response)

    except Exception as e:
        logger.error(f"公安LLM处理异常: {str(e)}")
        return None