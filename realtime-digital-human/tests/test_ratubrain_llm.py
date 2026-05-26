# python -m tests.test_ratubrain_llm

import json
import unittest
from unittest.mock import AsyncMock, MagicMock, patch, call

from loguru import logger

from llm.api.ratubrain_stream import chat_request_streaming, API_KEY


class TestChatRequestStreaming(unittest.IsolatedAsyncioTestCase):

    def setUp(self):
        logger.remove()
        logger.add(lambda msg: None, level="DEBUG")

    @patch('llm.api.ratubrain_stream.SSEClient')
    async def test_chat_request_streaming_success(self, mock_sse_client):
        mock_messages = [
            MagicMock(data=json.dumps({"token": "Hello"})),
            MagicMock(data=json.dumps({"token": " world"})),
            MagicMock(data=json.dumps({"token": " this is a test."})),
            MagicMock(data=json.dumps({"file_name": "done"}))
        ]
        mock_sse_client.return_value = iter(mock_messages)

        queue = AsyncMock()

        goal = "test message"
        sessionid = "12345"
        await chat_request_streaming(goal, queue, temperature=0.7, sessionid=sessionid)

        expected_url = (
            f'https://test.ratubrain.com/api/ai/chat/stream/start_chat/get?'
            f'goal={goal}&token={API_KEY}&chat_id={sessionid}&token_sleep=0'
        )
        mock_sse_client.assert_called_once_with(expected_url)

        expected_calls = [
            call('Hello world this is a test.'),
            call(None)
        ]
        queue.put.assert_has_calls(expected_calls, any_order=False)
        self.assertEqual(queue.put.await_count, 2)

    @patch('llm.api.ratubrain_stream.SSEClient')
    async def test_chat_request_streaming_with_punctuation(self, mock_sse_client):
        mock_messages = [
            MagicMock(data=json.dumps({"token": "Hello, "})),
            MagicMock(data=json.dumps({"token": "world"})),
            MagicMock(data=json.dumps({"token": ". This is "})),
            MagicMock(data=json.dumps({"token": "a test"})),
            MagicMock(data=json.dumps({"file_name": "done"}))
        ]
        mock_sse_client.return_value = iter(mock_messages)

        queue = AsyncMock()
        await chat_request_streaming("test", queue, sessionid="12345")

        expected_calls = [
            call('Hello,'),
            call(' world.'),
            call(' This is a test'),
            call(None)
        ]
        queue.put.assert_has_calls(expected_calls, any_order=False)
        self.assertEqual(queue.put.await_count, 4)

    @patch('llm.api.ratubrain_stream.SSEClient')
    async def test_chat_request_streaming_error(self, mock_sse_client):
        mock_sse_client.side_effect = Exception("Network error")
        queue = AsyncMock()

        with self.assertRaises(Exception) as context:
            await chat_request_streaming("test", queue, sessionid="12345")
        self.assertEqual(str(context.exception), "Network error")
        queue.put.assert_called_once_with(None)


if __name__ == '__main__':
    unittest.main()
