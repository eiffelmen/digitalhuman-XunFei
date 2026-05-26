import json
import time
import uuid
import asyncio

import requests
from loguru import logger
# from sseclient import SSEClient
import aiohttp
from typing import Any


API_KEY = "f46aced84191a530e03d09a9456ea5a5"


async def chat_request(goal, temperature=0, sessionid="1"):
    pass


async def chat_request_streaming(goal, queue, temperature=0, sessionid="1"):
    # temperature 用于匹配原生openai开发接口，没有实际意义
    sessionid = uuid.uuid4()
    start_time = time.perf_counter()
    first_token_received = False
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(
                f'https://enterprise-test.ratubrain.com/api/ai/chat/stream/start_chat/get?goal={goal}&token={API_KEY}&chat_id={sessionid}&token_sleep=0'
            ) as response:
                # messages = await SSEClient(
                #     f'https://ratubrain.com/api/ai/chat/stream/start_chat/get?goal={goal}&token={API_KEY}&chat_id={sessionid}&token_sleep=0'
                # )
                buffer = []
                complete_response = []
                async for line in response.content:
                    try:
                        line = line.decode('utf-8')
                        if not line.startswith('data:'):
                            continue
                        data = line[5:].strip()
                        # data = msg.data
                        current_chunk = None
                        if "token" in data:
                            data_json = json.loads(data)
                            current_chunk = data_json.get("token")
                            if not first_token_received:
                                first_token_received = True
                                logger.info(
                                    f"LLM首次响应耗时: {time.perf_counter() - start_time:.2f}s")
                        elif "file_name" in data and "task_name" not in data:
                            logger.info("Streaming completed")
                            break
                        elif '"message"' in data:
                            data_json = json.loads(data)
                            current_chunk = data_json.get("message")

                        if current_chunk:
                            current_chunk = current_chunk.translate(
                                str.maketrans("", "", "*#")
                            )

                            complete_response.append(current_chunk)
                            buffer.append(current_chunk)

                            # 增加分段长度阈值,确保每段文本更完整
                            if len(''.join(buffer)) >= 20:
                                text = ''.join(buffer)
                                last_punct = max((text.rfind(p)
                                                  for p in '。！？；'), default=-1)
                                if last_punct == -1:
                                    # 修改3：在次要标点中增加逗号分割
                                    last_punct = max((text.rfind(p)
                                                      for p in '，、：'), default=-1)

                                if last_punct != -1:
                                    output_text = text[:last_punct + 1]
                                    logger.debug(f"输出文本片段: {output_text}")
                                    await queue.put(output_text)
                                    buffer = [text[last_punct + 1:]]

                    except Exception as chunk_error:
                        logger.error(f"处理消息块错误: {str(chunk_error)}")

                if buffer:
                    final_text = ''.join(buffer)
                    if final_text.strip():
                        logger.debug(f"输出最终文本片段: {final_text}")
                        await queue.put(final_text)

                logger.info(
                    f"LLM总响应耗时: {time.perf_counter() - start_time:.2f}s")
        except Exception as e:
            logger.error(f"流式输出处理错误: {str(e)}")
            raise
        finally:
            await queue.put(None)

def llm_response(text: str, nerfreal_instance: Any, sessionid: str, result_queue: asyncio.Queue) -> str:

    # temperature 用于匹配原生openai开发接口，没有实际意义
    msg_id = str(uuid.uuid4())
    start_time = time.perf_counter()
    first_token_received = False

    try:
        with requests.get(
            f'https://enterprise-test.ratubrain.com/api/ai/chat/stream/start_chat/get?goal={text}&token={API_KEY}&chat_id={msg_id}&token_sleep=0',
            stream=True,
            timeout=30
        ) as response:
            if response.status_code != 200:
                logger.error(
                    f"请求失败: {response.status_code} {response.text}")
                return None

            logger.info("开始接收Ratubrain流式响应")

            buffer = []
            complete_response = []

            # 使用iter_lines正确迭代SSE流
            for line in response.iter_lines(decode_unicode=True):
                if not line:
                    continue

                try:
                    # 根据用户提供的响应格式，需要处理不同的SSE事件
                    if line.startswith('event:'):
                        event_type = line[6:].strip()
                        logger.debug(f"SSE事件类型: {event_type}")
                        continue

                    elif line.startswith('data:'):
                        data_str = line[5:].strip()

                        # 解析JSON数据
                        data_json = json.loads(data_str)
                        current_chunk = None

                        if "token" in data_json:
                            current_chunk = data_json.get("token")
                            if not first_token_received:
                                first_token_received = True
                                logger.info(
                                    f"LLM首次响应耗时: {time.perf_counter() - start_time:.2f}s")

                        # 处理消息内容
                        if current_chunk:
                            # 清理特殊字符
                            current_chunk = current_chunk.translate(
                                str.maketrans("", "", "*#")
                            )

                            # 通过队列发送到WebSocket
                            result_queue.put_nowait({'data': current_chunk, 'id': msg_id, 'finish': False})

                            complete_response.append(current_chunk)
                            buffer.append(current_chunk)

                            # 增加分段长度阈值,确保每段文本更完整
                            if len(''.join(buffer)) >= 20:
                                combined_text = ''.join(buffer)
                                last_punct = max((combined_text.rfind(p)
                                                  for p in '。！？；'), default=-1)
                                if last_punct == -1:
                                    # 在次要标点中增加逗号分割
                                    last_punct = max((combined_text.rfind(p)
                                                      for p in '，、：'), default=-1)

                                if last_punct != -1:
                                    output_text = combined_text[:last_punct + 1]
                                    logger.debug(f"输出文本片段: {output_text}")
                                    nerfreal_instance.put_msg_txt(output_text)
                                    buffer = [combined_text[last_punct + 1:]]

                    # 检查流结束 - 根据用户提供的响应格式
                    elif line.startswith('id:'):
                        # 这是SSE的id字段，可以忽略
                        continue

                except json.JSONDecodeError:
                    # 忽略非JSON数据行
                    continue
                except Exception as chunk_error:
                    logger.error(f"处理消息块错误: {str(chunk_error)}")

            # 循环结束后处理剩余的buffer
            if buffer:
                final_text = ''.join(buffer)
                if final_text.strip():
                    logger.debug(f"输出最终文本片段: {final_text}")
                    nerfreal_instance.put_msg_txt(final_text)

            # 发送完成消息
            result_queue.put_nowait({'data': "", 'id': msg_id, 'finish': True})

            logger.info(
                f"LLM总响应耗时: {time.perf_counter() - start_time:.2f}s")

            return ''.join(complete_response)

    except Exception as e:
        logger.error(f"Ratubrain LLM处理异常: {str(e)}")
        return None
