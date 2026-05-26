import os
import time
import uuid
from datetime import datetime

from loguru import logger
from openai import AsyncOpenAI
from dotenv import load_dotenv
from basereal import BaseReal
import json

# 编辑.env文件中的对应内容
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


client = AsyncOpenAI(
    api_key=API_KEY,
    base_url=BASE_URL,
)


async def check_model_health():
    try:
        test_response = await client.chat.completions.create(messages=[{
            "role":
            "system",
            "content":
            "You are a helpful assistant."
        }, {
            "role":
            "user",
            "content":
            "Say 'hello'"
        }],
                                                             model=MODEL_NAME,
                                                             max_tokens=5)
        return test_response.choices[0].message.content.strip().lower(
        ) == "hello"
    except Exception as e:
        logger.error(f"模型健康检查失败: {str(e)}")
        return False


async def chat_request(text, temperature=0, sessionid="0"):
    history = get_history(sessionid)
    history.append({
        "role": "user",
        "content": text,
    })

    # 使用await等待异步响应
    response = await client.chat.completions.create(
        messages=[history[0]] + history[1:][-9:],
        model=MODEL_NAME,
        temperature=temperature,
        stream_options={"include_usage": True})
    reponse_text = response.choices[
        0].message.content if response.choices else ""
    history.append({
        "role": "assistant",
        "content": reponse_text,
    })
    return reponse_text


async def chat_request_streaming(text, queue, temperature=0, sessionid="0"):
    history = get_history(sessionid)
    history.append({
        "role": "user",
        "content": text,
    })

    response = await client.chat.completions.create(
        messages=[history[0]] + history[1:][-9:],  # system和除system的最近9条对话
        model=MODEL_NAME,
        temperature=temperature,
        stream=True,
        # 通过以下设置，在流式输出的最后一行展示token使用信息
        stream_options={"include_usage": True})

    start = time.perf_counter()
    buffer = []
    complete_response = []
    first = True
    try:
        async for chunk_response in response:
            if not chunk_response.choices:
                continue
            if first:
                logger.info(f"LLM首次响应耗时: {time.perf_counter() - start:.2f}s")
                first = False
            msg = chunk_response.choices[0].delta.content.translate(
                str.maketrans("", "", "*#-"))
            if not msg:
                continue
            complete_response.append(msg)
            buffer.append(msg)
            if len(buffer) >= 10:
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
                    await queue.put(output_text)
                    buffer = [text[last_punct + 1:]]
        if buffer:
            final_text = ''.join(buffer)
            if final_text.strip():
                logger.debug(f"输出最终文本片段: {final_text}")
                await queue.put(final_text)

        logger.info(f"LLM总响应耗时: {time.perf_counter() - start:.2f}s")
        history.append({
            "role": "assistant",
            "content": ''.join(complete_response),
        })

    except Exception as e:
        logger.error(f"流式输出处理错误: {str(e)}")
        raise
    finally:
        await queue.put(None)

import requests
def llm_response(message, nerfreal: BaseReal, ws):
    start_time = time.perf_counter()
    first_token_received = False
    buffer = []
    msg_id = str(uuid.uuid4())  # 生成消息ID

    try:
        # 使用 requests 进行同步流式请求
        with requests.post(
            "http://localhost:8002/query",
            json={"user_input": message},
            headers={"Content-Type": "application/json"},
            stream=True,
            timeout=30
        ) as response:
            if response.status_code != 200:
                logger.error(
                    f"请求失败: {response.status_code} {response.text}")
                return

            logger.info("开始接收流式响应")

            # 处理流式响应
            for chunk in response.iter_content(chunk_size=1024, decode_unicode=True):
                if chunk:
                    decoded = chunk.strip()
                    if not decoded:
                        continue

                    if not first_token_received:
                        first_token_received = True
                        logger.info(
                            f"首次响应耗时: {time.perf_counter() - start_time:.2f}s"
                        )

                    buffer.append(decoded)

                    if len(''.join(buffer)) >= 30:
                        text = ''.join(buffer)
                        last_punct = max(
                            (text.rfind(p) for p in ',.!;:，。！？：；'),
                            default=-1)

                        if last_punct != -1:
                            output_text = text[:last_punct + 1]
                            logger.debug(f"输出文本片段: {output_text}")
                            nerfreal.put_msg_txt(output_text)
                            # 修复WebSocket消息格式，添加id字段
                            ws.send(json.dumps({
                                'data': output_text,
                                'id': msg_id,
                                'finish': False
                            }))
                            buffer = [text[last_punct + 1:]]

    except Exception as e:
        logger.error(f"流式传输异常: {str(e)}")
        raise
    finally:
        if buffer:
            final_text = ''.join(buffer)
            if final_text.strip():
                logger.debug(f"输出最终文本片段: {final_text}")
                nerfreal.put_msg_txt(final_text)
                # 修复：发送最终文本时使用finish: False
                ws.send(json.dumps({
                    'data': final_text,
                    'id': msg_id,
                    'finish': False
                }))

        # 发送完成消息
        ws.send(json.dumps({
            'data': "",
            'id': msg_id,
            'finish': True
        }))

        logger.info(f"总响应耗时: {time.perf_counter() - start_time:.2f}s")
