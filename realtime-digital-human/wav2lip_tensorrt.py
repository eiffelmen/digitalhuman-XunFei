import os
from pathlib import Path

import torch


def _format_shape(shape):
    return "x".join(str(dim) for dim in shape)


def _to_torch_dtype(dtype):
    text = str(dtype).lower()
    if "float16" in text or "half" in text:
        return torch.float16
    if "int8" in text:
        return torch.int8
    if "int32" in text:
        return torch.int32
    return torch.float32


class TensorRTWav2Lip:
    """Callable TensorRT wrapper that matches the PyTorch Wav2Lip interface."""

    backend_name = "tensorrt"

    def __init__(self, engine_path, device="cuda"):
        if device != "cuda" or not torch.cuda.is_available():
            raise RuntimeError("TensorRT Wav2Lip requires CUDA, but CUDA is not available.")

        try:
            import tensorrt as trt
        except ImportError as exc:
            raise RuntimeError(
                "TensorRT Python package is missing. Install TensorRT on the Ubuntu GPU server "
                "before using WAV2LIP_BACKEND=tensorrt."
            ) from exc

        self.trt = trt
        self.device = torch.device("cuda")
        self.engine_path = str(Path(engine_path))
        if not os.path.exists(self.engine_path):
            raise FileNotFoundError(f"TensorRT engine not found: {self.engine_path}")

        self.logger = trt.Logger(trt.Logger.WARNING)
        with open(self.engine_path, "rb") as f:
            engine_bytes = f.read()

        self.runtime = trt.Runtime(self.logger)
        self.engine = self.runtime.deserialize_cuda_engine(engine_bytes)
        if self.engine is None:
            raise RuntimeError(f"Failed to deserialize TensorRT engine: {self.engine_path}")

        self.context = self.engine.create_execution_context()
        if self.context is None:
            raise RuntimeError("Failed to create TensorRT execution context.")

        self.new_api = hasattr(self.engine, "num_io_tensors")
        self.input_names, self.output_names = self._collect_io_names()
        if len(self.input_names) < 2 or not self.output_names:
            raise RuntimeError(
                "Unexpected TensorRT engine IO layout: "
                f"inputs={self.input_names}, outputs={self.output_names}"
            )

        self.mel_name = "mel" if "mel" in self.input_names else self.input_names[0]
        self.face_name = "face" if "face" in self.input_names else self.input_names[1]
        self.output_name = "pred" if "pred" in self.output_names else self.output_names[0]
        self.mel_dtype = self._get_tensor_dtype(self.mel_name)
        self.face_dtype = self._get_tensor_dtype(self.face_name)
        self.output_dtype = self._get_tensor_dtype(self.output_name)

    def eval(self):
        return self

    def to(self, *_args, **_kwargs):
        return self

    def _collect_io_names(self):
        inputs = []
        outputs = []
        if self.new_api:
            for index in range(self.engine.num_io_tensors):
                name = self.engine.get_tensor_name(index)
                mode = self.engine.get_tensor_mode(name)
                if mode == self.trt.TensorIOMode.INPUT:
                    inputs.append(name)
                else:
                    outputs.append(name)
        else:
            for index in range(self.engine.num_bindings):
                name = self.engine.get_binding_name(index)
                if self.engine.binding_is_input(index):
                    inputs.append(name)
                else:
                    outputs.append(name)
        return inputs, outputs

    def _get_tensor_dtype(self, name):
        if self.new_api:
            return _to_torch_dtype(self.engine.get_tensor_dtype(name))
        return _to_torch_dtype(
            self.engine.get_binding_dtype(self.engine.get_binding_index(name))
        )

    def _set_input_shapes(self, mel_batch, face_batch):
        mel_shape = tuple(int(dim) for dim in mel_batch.shape)
        face_shape = tuple(int(dim) for dim in face_batch.shape)
        if self.new_api:
            mel_ok = self.context.set_input_shape(self.mel_name, mel_shape)
            face_ok = self.context.set_input_shape(self.face_name, face_shape)
            if mel_ok is False:
                raise RuntimeError(f"Failed to set TensorRT mel shape {_format_shape(mel_shape)}")
            if face_ok is False:
                raise RuntimeError(f"Failed to set TensorRT face shape {_format_shape(face_shape)}")
            return

        mel_index = self.engine.get_binding_index(self.mel_name)
        face_index = self.engine.get_binding_index(self.face_name)
        mel_ok = self.context.set_binding_shape(mel_index, mel_shape)
        face_ok = self.context.set_binding_shape(face_index, face_shape)
        if mel_ok is False:
            raise RuntimeError(f"Failed to set TensorRT mel shape {_format_shape(mel_shape)}")
        if face_ok is False:
            raise RuntimeError(f"Failed to set TensorRT face shape {_format_shape(face_shape)}")

    def _output_shape(self, batch_size, model_height, model_width):
        if self.new_api:
            shape = tuple(int(dim) for dim in self.context.get_tensor_shape(self.output_name))
        else:
            output_index = self.engine.get_binding_index(self.output_name)
            shape = tuple(int(dim) for dim in self.context.get_binding_shape(output_index))

        if not shape or any(dim < 0 for dim in shape):
            return (batch_size, 3, model_height, model_width)
        return shape

    def _execute_new_api(self, mel_batch, face_batch, output):
        self.context.set_tensor_address(self.mel_name, int(mel_batch.data_ptr()))
        self.context.set_tensor_address(self.face_name, int(face_batch.data_ptr()))
        self.context.set_tensor_address(self.output_name, int(output.data_ptr()))
        stream = torch.cuda.current_stream(self.device)
        return self.context.execute_async_v3(stream_handle=stream.cuda_stream)

    def _execute_legacy_api(self, mel_batch, face_batch, output):
        bindings = [0] * self.engine.num_bindings
        for name, tensor in (
            (self.mel_name, mel_batch),
            (self.face_name, face_batch),
            (self.output_name, output),
        ):
            bindings[self.engine.get_binding_index(name)] = int(tensor.data_ptr())

        stream = torch.cuda.current_stream(self.device)
        return self.context.execute_async_v2(
            bindings=bindings,
            stream_handle=stream.cuda_stream,
        )

    def __call__(self, mel_batch, face_batch):
        mel_batch = mel_batch.to(
            self.device, dtype=self.mel_dtype, non_blocking=True
        ).contiguous()
        face_batch = face_batch.to(
            self.device, dtype=self.face_dtype, non_blocking=True
        ).contiguous()

        batch_size = int(face_batch.shape[0])
        model_height = int(face_batch.shape[2])
        model_width = int(face_batch.shape[3])

        self._set_input_shapes(mel_batch, face_batch)
        output_shape = self._output_shape(batch_size, model_height, model_width)
        output = torch.empty(
            output_shape,
            dtype=self.output_dtype,
            device=self.device,
        )

        ok = (
            self._execute_new_api(mel_batch, face_batch, output)
            if self.new_api
            else self._execute_legacy_api(mel_batch, face_batch, output)
        )
        if ok is False:
            raise RuntimeError("TensorRT Wav2Lip execution failed.")

        return output
