#!/usr/bin/env python3
import argparse
from pathlib import Path


def parse_args():
    parser = argparse.ArgumentParser(
        description="Build Wav2Lip TensorRT engine from ONNX using TensorRT Python API."
    )
    parser.add_argument("--onnx", default="./wav2lip256/wav2lip_256.onnx")
    parser.add_argument("--engine", default="./wav2lip256/wav2lip_fp16.engine")
    parser.add_argument("--model-size", type=int, default=256)
    parser.add_argument("--min-batch", type=int, default=1)
    parser.add_argument("--opt-batch", type=int, default=16)
    parser.add_argument("--max-batch", type=int, default=16)
    parser.add_argument("--workspace-mib", type=int, default=2048)
    parser.add_argument("--precision", choices=("fp16", "fp32"), default="fp16")
    parser.add_argument("--verbose", action="store_true")
    return parser.parse_args()


def _create_network(builder, trt):
    flags = 0
    explicit_batch = getattr(trt.NetworkDefinitionCreationFlag, "EXPLICIT_BATCH", None)
    if explicit_batch is not None:
        flags |= 1 << int(explicit_batch)
    return builder.create_network(flags)


def _set_workspace(config, trt, workspace_mib):
    workspace_bytes = int(workspace_mib) * 1024 * 1024
    if hasattr(config, "set_memory_pool_limit"):
        config.set_memory_pool_limit(trt.MemoryPoolType.WORKSPACE, workspace_bytes)
    else:
        config.max_workspace_size = workspace_bytes


def _build_serialized_engine(builder, network, config):
    if hasattr(builder, "build_serialized_network"):
        return builder.build_serialized_network(network, config)

    engine = builder.build_engine(network, config)
    if engine is None:
        return None
    return engine.serialize()


def build_engine(args):
    import tensorrt as trt

    onnx_path = Path(args.onnx).expanduser().resolve()
    engine_path = Path(args.engine).expanduser().resolve()
    if not onnx_path.exists():
        raise FileNotFoundError(f"ONNX file not found: {onnx_path}")

    logger_level = trt.Logger.VERBOSE if args.verbose else trt.Logger.INFO
    logger = trt.Logger(logger_level)
    builder = trt.Builder(logger)
    network = _create_network(builder, trt)
    parser = trt.OnnxParser(network, logger)

    print(f">>> Parsing ONNX: {onnx_path}")
    if not parser.parse(onnx_path.read_bytes()):
        errors = "\n".join(str(parser.get_error(i)) for i in range(parser.num_errors))
        raise RuntimeError(f"Failed to parse ONNX:\n{errors}")

    config = builder.create_builder_config()
    _set_workspace(config, trt, args.workspace_mib)

    if args.precision == "fp16":
        has_fast_fp16 = getattr(builder, "platform_has_fast_fp16", True)
        fp16_flag = getattr(trt.BuilderFlag, "FP16", None)
        if fp16_flag is None:
            print(
                ">>> WARNING: This TensorRT Python API has no BuilderFlag.FP16; "
                "building with TensorRT default precision."
            )
        elif has_fast_fp16:
            config.set_flag(fp16_flag)
        else:
            print(">>> WARNING: GPU does not report fast FP16; building without FP16 flag.")

    profile = builder.create_optimization_profile()
    profile.set_shape(
        "mel",
        (args.min_batch, 1, 80, 16),
        (args.opt_batch, 1, 80, 16),
        (args.max_batch, 1, 80, 16),
    )
    profile.set_shape(
        "face",
        (args.min_batch, 6, args.model_size, args.model_size),
        (args.opt_batch, 6, args.model_size, args.model_size),
        (args.max_batch, 6, args.model_size, args.model_size),
    )
    config.add_optimization_profile(profile)

    print(
        ">>> Building TensorRT engine: "
        f"precision={args.precision}, "
        f"batch={args.min_batch}/{args.opt_batch}/{args.max_batch}, "
        f"workspace={args.workspace_mib}MiB"
    )
    serialized_engine = _build_serialized_engine(builder, network, config)
    if serialized_engine is None:
        raise RuntimeError("TensorRT engine build failed.")

    engine_path.parent.mkdir(parents=True, exist_ok=True)
    engine_path.write_bytes(bytes(serialized_engine))
    print(f">>> TensorRT engine created: {engine_path}")


if __name__ == "__main__":
    build_engine(parse_args())
