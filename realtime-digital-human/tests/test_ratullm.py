import json
import os
import time
import uuid

from sseclient import SSEClient


def message_generator(goal, token, sessionid="0"):
    base_url = os.getenv(
        "RATUBRAIN_BASE_URL",
        "https://test.ratubrain.com/api/ai/chat/stream/start_chat/get",
    )
    messages = SSEClient(
        f'{base_url}?goal={goal}&token={token}&chat_id={sessionid}&token_sleep=0')

    start_time = time.time()
    first_token_received = False

    for msg in messages:
        data = msg.data
        if "token" in data:
            data = json.loads(data)
            token_value = data.get("token")
            if token_value:
                if not first_token_received:
                    first_token_received = True
                    elapsed_time = time.time() - start_time
                    print(
                        f"接收第一个令牌所花费的时间: {elapsed_time:.2f} 秒")
                yield token_value
        elif "file_name" in data and "task_name" not in data:
            print()
            break
        elif '"message"' in data:
            data = json.loads(data)
            token_value = data.get("message")
            yield token_value


if __name__ == "__main__":
    goal = "介绍一下中科智汇工厂"
    token = os.getenv("RATUBRAIN_API_KEY", "test-ratubrain-token")

    for token_value in message_generator(goal, token, sessionid=uuid.uuid4()):
        print(token_value, end="", flush=True)
