import os

from asr.base import BaseASRProvider
from asr.iflytek import IflyTekASRProvider
from asr.funasr import FunASRProvider
from asr.gongan import GonganASRProvider


def create_asr_provider() -> BaseASRProvider:
    provider = os.environ.get("ASR_PROVIDER", "gongan")
    if provider == "gongan":
        return GonganASRProvider()
    if provider == "iflytek":
        return IflyTekASRProvider(
            app_id=os.environ["IFLYTEK_ASR_APP_ID"],
            api_key=os.environ["IFLYTEK_ASR_API_KEY"],
            api_secret=os.environ["IFLYTEK_ASR_API_SECRET"],
        )
    if provider == "funasr":
        return FunASRProvider(
            host=os.environ.get("FUNASR_HOST", "localhost"),
            port=int(os.environ.get("FUNASR_PORT", "10095")),
        )
    raise ValueError(f"Unknown ASR_PROVIDER: {provider!r}")
