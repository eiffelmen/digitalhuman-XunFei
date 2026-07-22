from abc import ABC, abstractmethod


class BaseASRProvider(ABC):
    @abstractmethod
    async def start_session(self) -> None:
        """建立连接，发送初始化参数"""

    @abstractmethod
    async def send_audio(self, pcm: bytes) -> None:
        """流式发送 PCM 数据（非流式服务在内部缓冲）"""

    @abstractmethod
    async def end_session(self) -> str:
        """发送结束信号，返回最终识别文本"""

    @abstractmethod
    async def close(self) -> None:
        """清理连接资源"""
