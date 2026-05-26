import requests

url = "http://localhost:8002/query"
# payload = {"user_input": "你是谁开发的？"}
# payload = {"user_input": "刑法第十六条是什么"}
# payload = {"user_input": "刑法第二十八条是什么"}
payload = {"user_input": "刑法第三十九条是什么"}
# payload = {"user_input": "刑法中第1章节第10条内容是什么"}
# payload = {"user_input": "刑法第49条是什么"}
# payload = {"user_input": "你怎么不去死？"}
headers = {"Content-Type": "application/json"}

response = requests.post(url,
                         json=payload,
                         headers=headers,
                         stream=True,
                         timeout=30)

if response.status_code == 200:
    full_response = []
    try:
        for chunk in response.iter_content(chunk_size=None):
            if chunk:
                decoded = chunk.decode('utf-8')
                if decoded == ' ':
                    continue
                full_response.append(decoded)
                print(decoded, end='', flush=True)
        print()
    except requests.exceptions.ChunkedEncodingError as e:
        print("\n流式传输异常:", str(e))
else:
    print("Failed to get response:", response.status_code, response.text)
