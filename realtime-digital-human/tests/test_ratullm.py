import json
import time
import uuid

from sseclient import SSEClient


def message_generator(goal, token, sessionid="0"):
    messages = SSEClient(
        f'https://test.ratubrain.com/api/ai/chat/stream/start_chat/get?goal={goal}&token={token}&chat_id={sessionid}&token_sleep=0')

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


goal = "介绍一下中科智汇工厂"
token = "a52d48b4ffc969cc3d687f5679f8664f"

for token_value in message_generator(goal, token, sessionid=uuid.uuid4()):
    print(token_value, end="", flush=True)
