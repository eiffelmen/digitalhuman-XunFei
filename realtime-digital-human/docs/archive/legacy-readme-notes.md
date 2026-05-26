# README 历史内容归档

以下内容从根目录 `README.md` 中迁出，原因是它们更偏向历史背景、旧方案记录或长期参考资料，不再适合作为当前项目入口文档的主体。

## 历史依赖安装记录

测试环境如下：

- Ubuntu 20.04
- Python 3.10
- Pytorch 2.0.1
- CUDA 11.7

```bash
conda create -n nerfstream python=3.10 -y
conda activate nerfstream
conda install pytorch==2.0.1 torchvision==0.15.2 torchaudio==2.0.2 pytorch-cuda=11.7 -c pytorch -c nvidia
sudo apt install portaudio19-dev
pip install -r requirements.txt

# 如果只用wav2lip模型，不需要安装下面的库
# pip install "git+https://github.com/facebookresearch/pytorch3d.git"
pip install tensorflow-gpu==2.8.0
pip install --upgrade "protobuf<=3.20.1"

# 运行funasr需要安装
pip install -U funasr
pip install -U modelscope
```

## 历史 WebSocket 兼容问题记录

曾经项目依赖 `flask-sockets`，需要手动修改第三方库：

- 文件：`flask_sockets.py`
- 函数：`add_url_rule`
- 修改前：`self.url_map.add(Rule(rule, endpoint=f))`
- 修改后：`self.url_map.add(Rule(rule, endpoint=f, websocket=True))`

参考：

- <http://blog.mangolovecarrot.net/2022/03/13/368>
- <https://github.com/heroku-python/flask-sockets/issues/81>
- <https://github.com/slipperstree/flask-sockets/commit/cb06c69db3af2cb52fbc050f3595ffa4100bbee3>

## 历史前端与附属服务说明

- 旧前端地址示例：`https://10.100.10.31`
- 历史说明里引用过 `digitalhuman-web/README.md`

启动 ASR 识别服务：

```bash
cd funasr
sh run_funasr_server.sh
```

GPT-SoVITS-TTS 服务搭建：

```bash
conda activate GPT-SoVits
cd GPT-SoVITS
sh run_sovits_server.sh
```

## 历史大模型启动示例

ollama 启动配置：

```bash
curl -fsSL https://ollama.com/install.sh | sh
ollama serve
ollama run qwen2.5:1.5b
```

vllm 服务启动：

```bash
pip install vllm

python -m vllm.entrypoints.openai.api_server --trust-remote-code --served-model-name Qwen2-1.5B --model Qwen/Qwen2-1.5B-Instruct
```

或：

```bash
export VLLM_USE_V1=1
export VLLM_RPC_TIMEOUT=50000
export VLLM_LOGITS_PROCESSOR_THREADS=16
export VLLM_ENABLE_V1_MULTIPROCESSING=0

CUDA_VISIBLE_DEVICES=4 \
vllm serve /Data3/liwenjie/AI-ModelScope/qwen/Qwen2.5-1.5B-Instruct \
  --served-model-name qwen2.5_1_5b_20241102 \
  --api-key token-abc123 \
  --gpu-memory-utilization=0.5 \
  --enforce-eager \
  --max-model-len 32768 \
  --port 8019 \
  --enable-prefix-caching \
  --tensor-parallel-size 1 \
  --pipeline-parallel-size 1 \
  --max-num-seqs 10 \
  --enable-chunked-prefill \
  --max-num-batched-tokens 8192 \
  --block-size 32
```

旧说明中曾提到需要修改 `llm.py`，该文件已不再是当前主路径。

## 历史自定义视频说明

提取自定义视频图片：

```bash
ffmpeg -i silence.mp4 -vf fps=25 -qmin 1 -q:v 1 -start_number 0 data/customvideo/img/%d.png
```

旧版数字人启动方式：

```bash
python app.py --customvideo --customvideo_img data/customvideo/img --customvideo_imgnum 100
```

替换自己的数字人：

```bash
cd wav2lip256
sh create_avatar.sh
```

运行后将 `results/avatars` 下文件拷到本项目的 `data/avatars` 下。

## SyncTalk 训练素材参考

可以替换成自己训练的模型：

<https://github.com/ZiqiaoPeng/SyncTalk>

样例目录：

```text
data/
  XinHe/
    transforms_train.json
    bc.jpg
    ngp_kf.pth
    template.npy
    ori_imgs/
    parsing/
    torso_imgs/
    fullbody_imgs/
    bs.npy
```

## 历史性能记录

- A800 显卡整体 fps 约 25
- 去掉音视频编码推流，fps 约 30
- 整体延时约 2 到 3 秒，不包含 ASR 服务
- edge-tts 延时约 1.7 秒
- GPT_SoVITS-tts 延时约 1.2 秒
- wav2vec 延时约 0.4 秒，需要缓存 18 帧音频

## 致谢与参考论文

项目大量参考了以下开源项目：

- <https://github.com/aiortc/aiortc>
- <https://github.com/ZiqiaoPeng/SyncTalk>
- <https://github.com/Rudrabha/Wav2Lip>

```text
@InProceedings{peng2023synctalk,
  title     = {SyncTalk: The Devil is in the Synchronization for Talking Head Synthesis},
  author    = {Ziqiao Peng and Wentao Hu and Yue Shi and Xiangyu Zhu and Xiaomei Zhang and Jun He and Hongyan Liu and Zhaoxin Fan},
  booktitle = {Proceedings of the IEEE/CVF Conference on Computer Vision and Pattern Recognition (CVPR)},
  month     = {June},
  year      = {2024},
}

@inproceedings{10.1145/3394171.3413532,
  author = {Prajwal, K R and Mukhopadhyay, Rudrabha and Namboodiri, Vinay P. and Jawahar, C.V.},
  title = {A Lip Sync Expert Is All You Need for Speech to Lip Generation In the Wild},
  year = {2020},
  isbn = {9781450379885},
  publisher = {Association for Computing Machinery},
  address = {New York, NY, USA},
  url = {https://doi.org/10.1145/3394171.3413532},
  doi = {10.1145/3394171.3413532},
  booktitle = {Proceedings of the 28th ACM International Conference on Multimedia},
  pages = {484–492},
  numpages = {9},
  keywords = {lip sync, talking face generation, video generation},
  location = {Seattle, WA, USA},
  series = {MM '20}
}
```
