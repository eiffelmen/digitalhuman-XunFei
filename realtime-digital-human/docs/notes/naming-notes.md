Python 项目的文件命名规范通常遵循 **PEP 8**（Python 官方代码风格指南）和一些社区共识。下面我会分几个层级讲清楚：项目 → 模块 → 类/函数 → 测试 → 特殊文件。

---

## 🧱 一、项目整体结构命名

推荐全部使用**小写字母 + 下划线**（snake_case），避免大小写混合或空格。

**示例结构：**

```
my_project/
├── README.md
├── pyproject.toml
├── requirements.txt
├── setup.py
├── my_project/
│   ├── __init__.py
│   ├── config.py
│   ├── utils/
│   │   ├── __init__.py
│   │   ├── file_utils.py
│   │   └── network_utils.py
│   ├── core/
│   │   ├── __init__.py
│   │   ├── service_manager.py
│   │   └── device_controller.py
│   └── main.py
└── tests/
    ├── __init__.py
    ├── test_service_manager.py
    └── test_device_controller.py
```

**命名规范说明：**

| 类型         | 命名风格                       | 示例                                               |
| ---------- | -------------------------- | ------------------------------------------------ |
| 包名（文件夹）    | 全小写，必要时用下划线                | `my_project`, `core`, `utils`                    |
| 模块（.py 文件） | 全小写，必要时用下划线                | `config.py`, `file_utils.py`                     |
| 配置文件       | 约定俗成名称                     | `setup.py`, `requirements.txt`, `pyproject.toml` |
| 主入口文件      | 一般命名为 `main.py` 或 `app.py` | ✅                                                |
| 测试文件       | `test_` 开头                 | `test_device_controller.py`                      |

---

## 🧩 二、代码内部命名规范（PEP 8）

| 类型   | 命名风格            | 示例                                   | 说明          |
| ---- | --------------- | ------------------------------------ | ----------- |
| 变量名  | 小写 + 下划线        | `user_name`, `max_retry`             | 避免缩写        |
| 函数名  | 小写 + 下划线        | `get_user_info()`                    | 动词开头        |
| 类名   | 大驼峰（PascalCase） | `UserManager`, `HttpClient`          | 每个单词首字母大写   |
| 常量   | 全大写 + 下划线       | `DEFAULT_TIMEOUT`, `MAX_CONNECTIONS` | 放在模块顶部      |
| 私有成员 | 前导下划线 `_`       | `_connect()`, `_cache`               | 表示内部使用      |
| 特殊方法 | 双下划线开头结尾        | `__init__`, `__repr__`               | Python 保留命名 |
| 异常类  | 大驼峰 + “Error”结尾 | `FileNotFoundError`, `ConfigError`   | 统一风格        |

---

## 🧪 三、测试文件命名

建议使用 **pytest** 风格，文件与被测模块对应：

| 模块文件                 | 测试文件                      | 测试类                  | 测试函数                   |
| -------------------- | ------------------------- | -------------------- | ---------------------- |
| `service_manager.py` | `test_service_manager.py` | `TestServiceManager` | `test_start_service()` |

---

## 🧰 四、命名避免的错误

❌ 不推荐：

```
FileUtil.py      # 大写首字母不符合PEP8
myProject/       # 驼峰目录名不推荐
utils2.py        # 没有语义意义的数字
a.py             # 无意义的名字
```

✅ 推荐：

```
file_utils.py
my_project/
```

---

## 🧠 五、可选进阶建议

* 若项目较大，可使用分层命名：

  ```
  domain_user_service.py
  domain_user_repository.py
  infra_http_client.py
  ```
* 若包含异步功能，可加后缀 `_async`：

  ```
  fetch_data_async.py
  ```
* 若区分平台：

  ```
  config_linux.py
  config_windows.py
  ```

---

是否希望我帮你生成一个**符合规范的项目模板结构（含文件命名）**？我可以按你项目类型（如 Web 服务 / SDK / 工具脚本）来定制。
