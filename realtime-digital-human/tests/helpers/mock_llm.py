import json
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from basereal import BaseReal


def llm_response(message, nerfreal: BaseReal, ws):
    test_text = "这是测试文本"
    nerfreal.put_msg_txt(test_text)
    ws.send(json.dumps({"data": test_text, "finish": False}))
    ws.send(json.dumps({"data": "", "finish": True}))
