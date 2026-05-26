# 测试数字人生命周期
import requests

URL = "http://localhost:8010/"


# 1. 创建数字人实例
def create_digitalhuman_instance():
    request = {
        "User": {
            "UserId": "123456",
            "UserName": "test_user",
        }
    }
    response = requests.post(URL + "startInstance", json=request)
    # print(response.json())
    print(f"响应状态码: {response.status_code}")
    print(f"响应内容: {response.text}")
    try:
        print(f"JSON解析结果: {response.json()}")
    except Exception as e:
        print(f"JSON解析错误: {e}")


# 2. 获取数字人实例
def query_running_digitalhuman_instance():
    request = {
        "User": {
            "UserId": "123456",
            "UserName": "test_user",
        }
    }
    response = requests.post(URL+"queryRunningInstance",json=request)
    print(f"响应状态码: {response.status_code}")
    print(f"响应内容: {response.text}")
    try:
        print(f"JSON解析结果: {response.json()}")
    except Exception as e:
        print(f"JSON解析错误: {e}")
    


# 3. 停止数字人实例
def stop_digitalhuman_instance(session_id: str):
    request = {
        "SessionId": session_id,
    }
    response = requests.post(URL + "stopInstance", json=request)
    print(f"响应状态码: {response.status_code}")
    print(f"响应内容: {response.text}")
    try:
        print(f"JSON解析结果: {response.json()}")
    except Exception as e:
        print(f"JSON解析错误: {e}")



def main():
    # create_digitalhuman_instance()
    query_running_digitalhuman_instance()
    # stop_digitalhuman_instance("c056ba33-7f65-488e-8c3d-2c7cf38b743e")

if __name__ == "__main__":
    main()
    
    