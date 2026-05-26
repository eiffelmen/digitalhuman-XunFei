# python -m tests.test_ratubrain_llm

import json
import unittest
from unittest.mock import ANY, AsyncMock, MagicMock, patch, call

from loguru import logger

from llm.api.ratubrain_stream import chat_request_streaming


TEST_BASE_URL = "https://test.ratubrain.com/api/ai/chat/stream/start_chat/get"
TEST_API_KEY = "test-ratubrain-token"


class AsyncLineIterator:
    def __init__(self, lines):
        self.lines = [line.encode("utf-8") for line in lines]

    def __aiter__(self):
        self._iter = iter(self.lines)
        return self

    async def __anext__(self):
        try:
            return next(self._iter)
        except StopIteration:
            raise StopAsyncIteration


class MockResponse:
    def __init__(self, lines):
        self.content = AsyncLineIterator(lines)

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False


class MockSession:
    def __init__(self, response=None):
        self.get = MagicMock(return_value=response)

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False


class TestChatRequestStreaming(unittest.IsolatedAsyncioTestCase):

    def setUp(self):
        logger.remove()
        logger.add(lambda msg: None, level="DEBUG")

    @patch('llm.api.ratubrain_stream._ratubrain_config')
    @patch('llm.api.ratubrain_stream.aiohttp.ClientSession')
    async def test_chat_request_streaming_success(self, mock_client_session, mock_config):
        mock_config.return_value = (TEST_BASE_URL, TEST_API_KEY)
        response = MockResponse([
            f"data: {json.dumps({'token': 'Hello'})}",
            f"data: {json.dumps({'token': ' world'})}",
            f"data: {json.dumps({'token': ' this is a test.'})}",
            f"data: {json.dumps({'file_name': 'done'})}",
        ])
        session = MockSession(response)
        mock_client_session.return_value = session

        queue = AsyncMock()

        goal = "test message"
        await chat_request_streaming(goal, queue, temperature=0.7, sessionid="12345")

        session.get.assert_called_once_with(
            TEST_BASE_URL,
            params={
                "goal": goal,
                "token": TEST_API_KEY,
                "chat_id": ANY,
                "token_sleep": 0,
            },
        )

        expected_calls = [
            call('Hello world this is a test.'),
            call(None)
        ]
        queue.put.assert_has_calls(expected_calls, any_order=False)
        self.assertEqual(queue.put.await_count, 2)

    @patch('llm.api.ratubrain_stream._ratubrain_config')
    @patch('llm.api.ratubrain_stream.aiohttp.ClientSession')
    async def test_chat_request_streaming_with_punctuation(self, mock_client_session, mock_config):
        mock_config.return_value = (TEST_BASE_URL, TEST_API_KEY)
        response = MockResponse([
            f"data: {json.dumps({'token': '你好，'})}",
            f"data: {json.dumps({'token': '世界。这是'})}",
            f"data: {json.dumps({'token': '一个测试'})}",
            f"data: {json.dumps({'file_name': 'done'})}",
        ])
        mock_client_session.return_value = MockSession(response)

        queue = AsyncMock()
        await chat_request_streaming("test", queue, sessionid="12345")

        expected_calls = [
            call('你好，世界。这是一个测试'),
            call(None)
        ]
        queue.put.assert_has_calls(expected_calls, any_order=False)
        self.assertEqual(queue.put.await_count, 2)

    @patch('llm.api.ratubrain_stream._ratubrain_config')
    @patch('llm.api.ratubrain_stream.aiohttp.ClientSession')
    async def test_chat_request_streaming_error(self, mock_client_session, mock_config):
        mock_config.return_value = (TEST_BASE_URL, TEST_API_KEY)
        session = MockSession()
        session.get.side_effect = Exception("Network error")
        mock_client_session.return_value = session
        queue = AsyncMock()

        with self.assertRaises(Exception) as context:
            await chat_request_streaming("test", queue, sessionid="12345")
        self.assertEqual(str(context.exception), "Network error")
        queue.put.assert_called_once_with(None)


if __name__ == '__main__':
    unittest.main()
