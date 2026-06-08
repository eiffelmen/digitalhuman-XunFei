import tensorrt as trt
import argparse
import sys
import os

def build_engine(onnx_file_path, engine_file_path, fp16_mode=False):
    logger = trt.Logger(trt.Logger.WARNING)
    builder = trt.Builder(logger)
    network = builder.create_network()
    parser = trt.OnnxParser(network, logger)

    if not os.path.exists(onnx_file_path):
        print(f"Error: ONNX file {onnx_file_path} not found.")
        sys.exit(1)

    print(f"Parsing ONNX file: {onnx_file_path}")
    with open(onnx_file_path, "rb") as model:
        if not parser.parse(model.read()):
            print("Failed to parse the ONNX file.")
            for error in range(parser.num_errors):
                print(parser.get_error(error))
            sys.exit(1)

    config = builder.create_builder_config()
    config.set_memory_pool_limit(trt.MemoryPoolType.WORKSPACE, 2048 * (1 << 20)) # 2048 MiB

    if fp16_mode and builder.platform_has_fast_fp16:
        print("Enabling FP16 mode")
        config.set_flag(trt.BuilderFlag.FP16)
    else:
        print("Using FP32 mode")

    profile = builder.create_optimization_profile()
    # Shapes: min=1, opt=16, max=16, size=256
    profile.set_shape("mel", (1, 1, 80, 16), (16, 1, 80, 16), (16, 1, 80, 16))
    profile.set_shape("face", (1, 6, 256, 256), (16, 6, 256, 256), (16, 6, 256, 256))
    config.add_optimization_profile(profile)

    print("Building TensorRT engine. This may take a while...")
    engine_bytes = builder.build_serialized_network(network, config)
    
    if engine_bytes is None:
        print("Failed to create engine")
        sys.exit(1)

    with open(engine_file_path, "wb") as f:
        f.write(engine_bytes)
    print(f"Successfully saved engine to {engine_file_path}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--onnx", default="./wav2lip256/wav2lip_256.onnx")
    parser.add_argument("--output", default="./wav2lip256/wav2lip_windows_fp32.engine")
    parser.add_argument("--fp16", action="store_true")
    args = parser.parse_args()
    build_engine(args.onnx, args.output, args.fp16)
