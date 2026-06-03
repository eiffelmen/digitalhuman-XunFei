#!/usr/bin/env python3
import argparse
from pathlib import Path

import onnx


def _shape_of(value_info):
    dims = []
    for dim in value_info.type.tensor_type.shape.dim:
        dims.append(dim.dim_param or dim.dim_value or "?")
    return dims


def inspect_onnx(path: Path):
    model = onnx.load(path)
    onnx.checker.check_model(model)

    print(f"ONNX file: {path}")
    print(f"IR version: {model.ir_version}")
    print(f"Opset: {[op.version for op in model.opset_import]}")

    print("\nInputs")
    for item in model.graph.input:
        print(f"- {item.name}: {_shape_of(item)}")

    print("\nOutputs")
    for item in model.graph.output:
        print(f"- {item.name}: {_shape_of(item)}")


def parse_args():
    parser = argparse.ArgumentParser(description="Inspect Wav2Lip ONNX IO.")
    parser.add_argument("onnx_path", type=Path)
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    inspect_onnx(args.onnx_path.expanduser().resolve())
