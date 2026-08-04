#!/usr/bin/env python3
import argparse
import sys
from pathlib import Path

import torch


def _repo_dir() -> Path:
    return Path(__file__).resolve().parents[1]


def _load_wav2lip(checkpoint_path: Path):
    sys.path.insert(0, str(_repo_dir()))
    from wav2lip256.models import Wav2Lip

    model = Wav2Lip()
    checkpoint = torch.load(checkpoint_path, map_location="cpu")
    state_dict = checkpoint["state_dict"]
    cleaned_state_dict = {
        key.replace("module.", ""): value for key, value in state_dict.items()
    }
    model.load_state_dict(cleaned_state_dict)
    model.eval()
    return model


def export_onnx(args):
    checkpoint_path = Path(args.checkpoint).expanduser().resolve()
    output_path = Path(args.output).expanduser().resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    model = _load_wav2lip(checkpoint_path)
    mel = torch.randn(args.batch_size, 1, 80, 16, dtype=torch.float32)
    face = torch.randn(
        args.batch_size,
        6,
        args.model_size,
        args.model_size,
        dtype=torch.float32,
    )

    dynamic_axes = None
    if args.dynamic_batch:
        dynamic_axes = {
            "mel": {0: "batch"},
            "face": {0: "batch"},
            "pred": {0: "batch"},
        }

    with torch.no_grad():
        torch.onnx.export(
            model,
            (mel, face),
            output_path,
            input_names=["mel", "face"],
            output_names=["pred"],
            dynamic_axes=dynamic_axes,
            opset_version=args.opset,
            do_constant_folding=True,
        )

    print(f"ONNX exported: {output_path}")

    if args.check:
        import onnx

        onnx_model = onnx.load(output_path)
        onnx.checker.check_model(onnx_model)
        print("ONNX checker: OK")
        for graph_value in list(onnx_model.graph.input) + list(onnx_model.graph.output):
            dims = [
                dim.dim_param or dim.dim_value
                for dim in graph_value.type.tensor_type.shape.dim
            ]
            print(f"{graph_value.name}: {dims}")


def parse_args():
    default_checkpoint = _repo_dir() / "wav2lip256" / "wav2lip.pth"
    default_output = _repo_dir() / "wav2lip256" / "wav2lip_256.onnx"
    parser = argparse.ArgumentParser(description="Export Wav2Lip .pth to ONNX.")
    parser.add_argument("--checkpoint", default=str(default_checkpoint))
    parser.add_argument("--output", default=str(default_output))
    parser.add_argument("--model-size", type=int, default=256)
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--opset", type=int, default=17)
    parser.add_argument(
        "--static-batch",
        action="store_false",
        dest="dynamic_batch",
        help="Export a fixed-batch ONNX model instead of dynamic batch.",
    )
    parser.add_argument("--no-check", action="store_false", dest="check")
    parser.set_defaults(dynamic_batch=True, check=True)
    return parser.parse_args()


if __name__ == "__main__":
    export_onnx(parse_args())
