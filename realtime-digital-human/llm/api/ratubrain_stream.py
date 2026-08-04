import json
import os
import time
import uuid
import aiohttp

from loguru import logger

API_KEY = os.environ.get("RATUBRAIN_API_KEY", "")


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
                    f'https://ratubrain.com/api/ai/chat/stream/start_chat/get?goal={goal}&token={API_KEY}&chat_id={sessionid}&token_sleep=0'
            ) as response:
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
                                    f"LLM首次响应耗时: {time.perf_counter() - start_time:.2f}s"
                                )
                        elif "file_name" in data and "task_name" not in data:
                            logger.info("Streaming completed")
                            break
                        elif '"message"' in data:
                            data_json = json.loads(data)
                            current_chunk = data_json.get("message")

                        if current_chunk:
                            current_chunk = current_chunk.translate(
                                str.maketrans("", "", "*#"))

                            complete_response.append(current_chunk)
                            buffer.append(current_chunk)

                            # 增加分段长度阈值,确保每段文本更完整
                            if len(''.join(buffer)) >= 20:
                                text = ''.join(buffer)
                                last_punct = max(
                                    (text.rfind(p) for p in '。！？；'),
                                    default=-1)
                                if last_punct == -1:
                                    # 修改3：在次要标点中增加逗号分割
                                    last_punct = max(
                                        (text.rfind(p) for p in '，、：'),
                                        default=-1)

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
