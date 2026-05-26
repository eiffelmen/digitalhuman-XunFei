import os
import asyncio
from pathlib import Path
import subprocess
import sys

import torch

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from wav2lip256.models import Wav2Lip

gpu_count = torch.cuda.device_count()
print(f"检测到 {gpu_count} 个可用GPU")

gpu_num = 0
os.environ['CUDA_VISIBLE_DEVICES'] = str(gpu_num)
device = f"cuda:{gpu_num}"
print(f"使用GPU: {gpu_num}")


def _load(checkpoint_path, device='cuda'):
    if device == 'cuda':
        checkpoint = torch.load(checkpoint_path).to(device)
    else:
        checkpoint = torch.load(checkpoint_path,
                                map_location=lambda storage, loc: storage)
    return checkpoint


def load_model(path, device='cuda'):
    model = Wav2Lip()
    checkpoint = _load(path, device=device)
    s = checkpoint["state_dict"]
    new_s = {}
    for k, v in s.items():
        new_s[k.replace('module.', '')] = v
    model.load_state_dict(new_s)
    model = model.to(device=device)
    return model.eval()


def get_gpu_memory_usage():
    try:
        result = subprocess.run([
            'nvidia-smi', '--query-gpu=memory.used',
            '--format=csv,nounits,noheader'
        ],
                                stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE)
        output = result.stdout.decode('utf-8').strip()
        if not output:
            print("警告: nvidia-smi未返回有效数据")
            return 0

        gpu_memories = [int(x) for x in output.split('\n')]
        return gpu_memories[0]
    except Exception as e:
        print(f"获取显存占用失败: {str(e)}")
        return 0


async def run_inference(model, device, semaphore):
    async with semaphore:
        try:
            mem_before = get_gpu_memory_usage()
            img_batch = torch.randn(1, 6, 256, 256).to(device)
            mel_batch = torch.randn(1, 1, 80, 16).to(device)
            with torch.no_grad():
                model(mel_batch, img_batch)
            mem_after = get_gpu_memory_usage()
            return mem_before, mem_after
        except Exception as e:
            print(f"推理任务出错: {str(e)}")
            return get_gpu_memory_usage(), get_gpu_memory_usage()


async def run_concurrent_test(concurrency=4, device="cuda", max_concurrent=10):
    initial_mem = get_gpu_memory_usage()
    print(f"初始显存占用: {initial_mem}MB")

    model_path = PROJECT_ROOT / "wav2lip256" / "wav2lip.pth"
    model = load_model(str(model_path), device=device)
    # warm up the model
    img_batch = torch.randn(1, 6, 256, 256).to(device)
    mel_batch = torch.randn(1, 1, 80, 16).to(device)

    with torch.no_grad():
        model(mel_batch, img_batch)

    after_load_mem = get_gpu_memory_usage()
    print(f"模型加载后显存占用: {after_load_mem}MB (Δ{after_load_mem-initial_mem}MB)")

    semaphore = asyncio.Semaphore(max_concurrent)
    tasks = [
        run_inference(model, device, semaphore) for _ in range(concurrency)
    ]
    results = await asyncio.gather(*tasks)

    max_mem_usage = max(r[1] for r in results)
    for i, (mem_before, mem_after) in enumerate(results):
        print(
            f"任务{i+1}: 显存占用: {mem_before}MB -> {mem_after}MB (Δ{mem_after-mem_before}MB)"
        )

    print(f"\n并发数: {concurrency} | 最大显存占用: {max_mem_usage}MB")


if __name__ == "__main__":
    asyncio.run(
        run_concurrent_test(concurrency=100, device=device, max_concurrent=10))
