"""
测试修复后的Ratubrain LLM实现
"""

import json
import asyncio
from pathlib import Path
import sys
from loguru import logger

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# 配置日志
logger.remove()
logger.add(sys.stderr, level="INFO")


def test_llm_response():
    """测试llm_response函数"""
    from llm.providers.ratubrain import llm_response

    # 模拟nerfreal_instance
    class MockNerfreal:
        def put_msg_txt(self, text):
            logger.info(f"数字人收到文本: {text}")

    nerfreal = MockNerfreal()
    result_queue = asyncio.Queue()

    # 测试调用
    logger.info("开始测试Ratubrain LLM...")
    result = llm_response("你好，这是一个测试", nerfreal, "manual-test", result_queue)

    if result:
        logger.info(f"测试成功! 响应内容: {result}")
        while not result_queue.empty():
            data = result_queue.get_nowait()
            logger.info(f"结果队列消息: {json.dumps(data, ensure_ascii=False)}")
    else:
        logger.error("测试失败!")


if __name__ == "__main__":
    test_llm_response()
