import uuid
import os
from io import BytesIO
from fastapi import FastAPI, UploadFile, File, HTTPException
from minio import Minio  # pip install minio==7.1.0


def _get_required_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"缺少环境变量: {name}")
    return value


def _get_minio_client() -> Minio:
    return Minio(
        _get_required_env("MINIO_ENDPOINT"),
        access_key=_get_required_env("MINIO_ACCESS_KEY"),
        secret_key=_get_required_env("MINIO_SECRET_KEY"),
        secure=os.getenv("MINIO_SECURE", "false").lower() == "true",
    )


bucket_name = os.getenv("MINIO_BUCKET", "laboratory")

app = FastAPI()


def upload_file_to_minio_sync(file_data: BytesIO, file_name: str, file_type: str, file_size: int):
    try:
        file_name = 'file/' + file_name
        minio_client = _get_minio_client()
        minio_client.put_object(bucket_name, file_name,
                                file_data, file_size, content_type=file_type)
        public_base_url = os.getenv("MINIO_PUBLIC_BASE_URL", "").rstrip("/")
        if public_base_url:
            return f"{public_base_url}/{bucket_name}/{file_name}"
        return f"{bucket_name}/{file_name}"
    except Exception as err:
        print(f"上传文件失败: {err}")
        raise HTTPException(
            status_code=500, detail=f"文件上传到MinIO失败: {str(err)}")


@app.post("/v1/upload")
async def upload_video(file: UploadFile = File(...)):
    try:
        file_data = BytesIO(await file.read())
        file_name = f'{uuid.uuid4()}.{file.filename.split(".")[-1]}'
        file_size = file_data.getbuffer().nbytes
        file_type = file.content_type if file.content_type else "application/octet-stream"
        url = upload_file_to_minio_sync(
            file_data, file_name, file_type, file_size)
        return {"message": "文件上传成功", "url": url}
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"文件上传失败: {str(e)}")


def upload_image_file(file_path: str) -> dict:
    try:
        with open(file_path, 'rb') as f:
            file_data = BytesIO(f.read())

        import mimetypes
        file_type = mimetypes.guess_type(
            file_path)[0] or 'application/octet-stream'

        if not file_type.startswith('image/'):
            raise ValueError("只允许上传图片文件")

        file_name = f'{uuid.uuid4()}.{file_path.split(".")[-1]}'
        file_size = file_data.getbuffer().nbytes

        url = upload_file_to_minio_sync(
            file_data, file_name, file_type, file_size)
        return {"message": "图片上传成功", "url": url}

    except Exception as e:
        raise Exception(f"图片上传失败: {str(e)}")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8086)
