import aiohttp
import asyncio
import time
from loguru import logger
import time
from basereal import BaseReal
import json
import requests
import uuid

MAX_RETRIES = 3
RETRY_DELAY = 2


async def chat_request(goal, temperature=0, sessionid="0"):
    pass

import os
LLM_SERVICE=os.getenv("LLM_SERVICE", "http://localhost:8002")

async def chat_request_streaming(goal, queue, temperature=0, sessionid="0"):
    start_time = time.perf_counter()
    first_token_received = False
    buffer = []

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                    LLM_SERVICE+"/query",
                    json={"user_input": goal},
                    headers={"Content-Type": "application/json"},
                    timeout=30) as response:
                if response.status != 200:
                    logger.error(
                        f"请求失败: {response.status} {await response.text()}")
                    await queue.put(None)
                    return

                logger.info("开始接收流式响应")
                async for chunk in response.content:
                    if chunk:
                        decoded = chunk.decode('utf-8').strip()
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
                                await queue.put(output_text)
                                buffer = [text[last_punct + 1:]]

    except Exception as e:
        logger.error(f"流式传输异常: {str(e)}")
        raise
    finally:
        if buffer:
            final_text = ''.join(buffer)
            if final_text.strip():
                logger.debug(f"输出最终文本片段: {final_text}")
                await queue.put(final_text)

        await queue.put(None)
        logger.info(f"总响应耗时: {time.perf_counter() - start_time:.2f}s")


async def check_model_health():
    retries = 0
    while retries < MAX_RETRIES:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(LLM_SERVICE+"/health",
                                       timeout=10) as response:
                    if response.status == 200:
                        result = await response.json()
                        return result.get("status") == "healthy"
                    else:
                        logger.error(
                            f"RAG 模型健康检查失败，状态码: {response.status}，响应内容: {await response.text()}"
                        )
        except aiohttp.ClientError as e:
            logger.error(f"RAG 模型健康检查网络请求失败: {str(e)}")
        except ValueError as e:
            logger.error(f"RAG 模型健康检查响应解析失败: {str(e)}")
        except Exception as e:
            logger.error(f"RAG 模型健康检查发生未知错误: {str(e)}")

        retries += 1
        if retries < MAX_RETRIES:
            await asyncio.sleep(RETRY_DELAY)

    logger.error("RAG 模型健康检查多次尝试后仍失败")
    return False

def llm_response(message, nerfreal: BaseReal, sessionid: str, result_queue: asyncio.Queue):

    start_time = time.perf_counter()
    first_token_received = False
    buffer = []

    msg_id = str(uuid.uuid4())

    try:
        # 使用 requests 进行同步流式请求
        with requests.post(
            LLM_SERVICE+"/query",
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
                    logger.info(f"Received chunk: {chunk}")

                    # 通过队列发送到WebSocket
                    result_queue.put_nowait({'data': chunk, "id": msg_id, "finish": False})

                    # 这里的chunk已经是正常的带空格的字符串了，直接拼接就可以
                    decoded = chunk
                    if not decoded:
                        continue

                    if not first_token_received:
                        first_token_received = True
                        logger.info(
                            f"首次响应耗时: {time.perf_counter() - start_time:.2f}s"
                        )

                    buffer.append(decoded)

                    # 30个buffer字符就发送一次
                    if len(''.join(buffer)) >= 30:
                        text = ''.join(buffer)
                        # 30个字符中找最后一个标点符号
                        last_punct = max(
                            (text.rfind(p) for p in ',.!;:，。！？：；'),
                            default=-1)

                        if last_punct != -1:
                            output_text = text[:last_punct + 1]
                            logger.info(f"输出文本片段: {output_text}")
                            # todo: 英文的发音也受到了这里不合理分段的影响
                            nerfreal.put_msg_txt(output_text)
                            buffer = [text[last_punct + 1:]]

            logger.warning("这是啥")
            if buffer:
                logger.warning(f"这又是啥, buffer 内容: {buffer}")
                final_text = ''.join(buffer)
                if final_text.strip():
                    logger.debug(f"输出最终文本片段: {final_text}")
                    logger.info(f"输出z最终本片段: {final_text}")
                    nerfreal.put_msg_txt(final_text)

            result_queue.put_nowait({'data': "", "id": msg_id, "finish": True})

    except Exception as e:
        logger.error(f"流式传输异常: {str(e)}")
        raise
    finally:

        logger.info(f"总响应耗时: {time.perf_counter() - start_time:.2f}s")
