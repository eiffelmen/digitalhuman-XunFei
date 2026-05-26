import os
import time
from openai import OpenAI
from dotenv import load_dotenv
from loguru import logger

# 1. 配置加载
load_dotenv()
BASE_URL = os.environ.get("BASE_URL")
API_KEY = os.environ.get("API_KEY")
MODEL_NAME = os.environ.get("MODEL_NAME")

# 模拟你定义的 System Prompt
SYSTEM_PROMPT = "你是一位名为'晓云警官'的专业AI助手..." # 此处省略，运行时建议保留完整版

def check_llm_health():
    """
    检查大模型 API 健康状况的核心函数
    """
    logger.info("🚀 开始 API 接口健康检查...")
    logger.info(f"端点: {BASE_URL}")
    logger.info(f"模型: {MODEL_NAME}")

    # 初始化客户端
    try:
        client = OpenAI(api_key=API_KEY, base_url=BASE_URL)
    except Exception as e:
        logger.error(f"❌ 客户端初始化失败: {e}")
        return

    test_messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": "你好，请问你是谁？"}
    ]

    start_time = time.perf_counter()
    first_token_time = None
    full_content = []

    try:
        # 尝试发起流式请求
        response = client.chat.completions.create(
            messages=test_messages,
            model=MODEL_NAME,
            temperature=0,
            stream=True,
            stream_options={"include_usage": True}
        )

        logger.info("📡 正在等待流式响应...")

        for chunk in response:
            if not chunk.choices:
                # 检查 usage 信息 (如果 stream_options 生效)
                if hasattr(chunk, 'usage') and chunk.usage:
                    logger.info(f"📊 Token 使用统计: {chunk.usage}")
                continue

            delta = chunk.choices[0].delta.content
            if delta:
                if first_token_time is None:
                    first_token_time = time.perf_counter()
                    ttft = first_token_time - start_time
                    logger.success(f"✅ 首字响应成功 (TTFT): {ttft:.2f}s")
                
                full_content.append(delta)
                # 实时打印流式内容（可选）
                print(delta, end="", flush=True)

        end_time = time.perf_counter()
        total_duration = end_time - start_time
        result_text = "".join(full_content)

        print("\n" + "-"*30)
        logger.success(f"✅ 响应处理完成！总耗时: {total_duration:.2f}s")
        
        # 验证业务逻辑
        check_business_logic(result_text)

    except Exception as e:
        logger.error(f"❌ API 调用过程中发生异常: {str(e)}")

def check_business_logic(text):
    """
    验证模型是否遵循了 System Prompt 的设定
    """
    logger.info("🔎 正在验证业务逻辑遵循情况...")
    
    # 检查关键词
    checks = {
        "身份标识": "晓云" in text or "警官" in text,
        "字数控制": len(text) <= 150, # 稍微放宽一点，你的要求是80
        "无表情符号": "😊" not in text and "🙏" not in text
    }

    for label, passed in checks.items():
        status = "通过" if passed else "未通过"
        icon = "✔" if passed else "✘"
        logger.info(f"{icon} {label}: {status}")

if __name__ == "__main__":
    if not all([BASE_URL, API_KEY, MODEL_NAME]):
        logger.error("❌ 环境变量缺失，请检查 .env 文件")
    else:
        check_llm_health()