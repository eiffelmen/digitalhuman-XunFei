#!/bin/bash
export VLLM_USE_V1=1
export VLLM_RPC_TIMEOUT=50000
export VLLM_LOGITS_PROCESSOR_THREADS=16
export VLLM_ENABLE_V1_MULTIPROCESSING=0
export VLLM_USE_MODELSCOPE=True

# CUDA_VISIBLE_DEVICES=3 \
#     vllm serve Qwen/Qwen2.5-1.5B-Instruct \
#     --served-model-name qwen2.5_1_5b_20241102 \
#     --api-key token-abc123 \
#     --gpu-memory-utilization=0.5 \
#     --enforce-eager \
#     --max-model-len 32768 \
#     --port 8019 \
#     --enable-prefix-caching \
#     --tensor-parallel-size 1 \
#     --pipeline-parallel-size 1 \
#     --max-num-seqs 10 \
#     --enable-chunked-prefill \
#     --max-num-batched-tokens 8192 \
#     --block-size 32

CUDA_VISIBLE_DEVICES=0 \
    vllm serve ../ms-swift/output/v4-20250707-114158/checkpoint-291-merged \
    --served-model-name qwen2.5_1_5b_20250707 \
    --api-key token-abc123 \
    --gpu-memory-utilization=0.9 \
    --enforce-eager \
    --max-model-len 2048 \
    --port 8019 \
    --enable-prefix-caching \
    --tensor-parallel-size 1 \
    --pipeline-parallel-size 1 \
    --max-num-seqs 10 \
    --enable-chunked-prefill \
    --max-num-batched-tokens 2048 \
    --block-size 32
