import time
import os
import asyncio
from basereal import BaseReal
from logger import logger
import json


def llm_response(message, nerfreal: BaseReal, sessionid: str, result_queue: asyncio.Queue):

    start = time.perf_counter()
    from openai import OpenAI

    client = OpenAI(
        # 如果您没有配置环境变量，请在此处用您的API Key进行替换
        api_key=os.getenv("DASHSCOPE_API_KEY", "gpt"),
        # 填写DashScope SDK的base_url
        base_url="http://localhost:11434/v1",
    )
    end = time.perf_counter()
    logger.info(f"llm Time init: {end-start}s")
    completion = client.chat.completions.create(
        model="gpt-oss:20b",
        messages=[
            {
                "role": "system",
                "content": """你是一个公安业务助手 你的职责是解答与中国法律相关的问题
                      请遵循以下要求

                      1 回复语言必须是中文
                      2 你可以回答与法律相关的问题 尤其是刑法 宪法 公安执法相关的法律条文与解释
                      3 如果用户的问题超出了法律范畴 比如娱乐 编程 日常闲聊 生活建议等 请礼貌拒绝回答 可以回复
                      抱歉 我只能解答与法律相关的问题 尤其是刑法和宪法内容
                      4 在回答时 尽量引用法律条文或相关规定 保持严谨 专业 简明
                      5 不要编造不存在的法律条文 如果不能确定答案 可以建议用户查阅权威法律文件或咨询专业律师
                      6 回答内容要适合语音播报 避免复杂的符号和表格 避免中英文夹杂 尽量用简短自然的中文句子来表达
                      7 不要使用括号 引号 或者代码格式 也不要输出项目符号列表 回答应像一段播报稿 """,
            },
            {"role": "user", "content": message},
        ],
        stream=True,
        # 通过以下设置，在流式输出的最后一行展示token使用信息
        stream_options={"include_usage": True},
    )
    result = ""
    first = True
    for chunk in completion:
        if len(chunk.choices) > 0:
            # print(chunk.choices[0].delta.content)
            if first:
                end = time.perf_counter()
                logger.info(f"llm Time to first chunk: {end-start}s")
                first = False
            msg = chunk.choices[0].delta.content
            # if msg: yield msg
            lastpos = 0
            # msglist = re.split('[,.!;:，。！?]',msg)
            for i, char in enumerate(msg):
                if char in ",.!;:，。！？：；":
                    result = result + msg[lastpos : i + 1]
                    lastpos = i + 1
                    if len(result) > 10:
                        logger.info(result)
                        nerfreal.put_msg_txt(result)
                        result_queue.put_nowait({'data': result, "finish": False})
                        result = ""
            result = result + msg[lastpos:]
    end = time.perf_counter()
    logger.info(f"llm Time to last chunk: {end-start}s")
    logger.info(result)
    nerfreal.put_msg_txt(result)
    result_queue.put_nowait({'data': result, "finish": False})
    result_queue.put_nowait({'data': '', "finish": True})
