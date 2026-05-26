from funasr import AutoModel
from funasr.utils.postprocess_utils import rich_transcription_postprocess

model_dir = "/Data3/liwenjie/AI-ModelScope/iic/SenseVoiceSmall"


model = AutoModel(
    model=model_dir,
    trust_remote_code=False,
    vad_model="fsmn-vad",
    vad_kwargs={"max_single_segment_time": 30000},
    device="cuda:0",
    disable_pbar=True,
    disable_log=True,
)

res = model.generate(
    # input="../data/男1.wav",
    # input="../funasr/audios/test2024-11-11 23:12:29.wav",

    # 降噪后
    # input="../funasr/audios/test2024-11-11 23:13:17.wav",
    # 降噪前
    # input="../funasr/audios/test2024-11-11 23:11:25.wav",

    # 杂音
    # test2024-11-11 23:11:54.wav
    # input="../funasr/audios/test2024-11-11 23:11:54.wav",

    # 同时说话
    # test2024-11-11 23:40:46.wav
    # input="../funasr/audios/test2024-11-11 23:40:46.wav",

    # 单独说话
    # test2024-11-11 23:40:22.wav
    # input="../funasr/audios/test2024-11-11 23:40:22.wav",


    # test2024-11-12 11:50:51.wav
    input="../funasr/audios/test2024-11-12 11:50:51.wav",

    cache={},
    language="auto",  # "zn", "en", "yue", "ja", "ko", "nospeech"
    use_itn=True,
    batch_size_s=60,
    merge_vad=True,
    merge_length_s=15,
)

text = rich_transcription_postprocess(res[0]["text"])
print(text)
