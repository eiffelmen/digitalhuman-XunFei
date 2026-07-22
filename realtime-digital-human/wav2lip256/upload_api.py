import uuid
import os
from io import BytesIO
from fastapi import FastAPI, UploadFile, File, HTTPException
from minio import Minio  # pip install minio==7.1.0

bucket_name = os.environ.get("MINIO_BUCKET", "laboratory")

app = FastAPI()


def _get_minio_client():
    minio_server = os.environ.get("MINIO_ENDPOINT")
    minio_access_key = os.environ.get("MINIO_ACCESS_KEY")
    minio_secret_key = os.environ.get("MINIO_SECRET_KEY")
    minio_secure = os.environ.get("MINIO_SECURE", "0").lower() in {
        "1",
        "true",
        "yes",
    }
    if not minio_server or not minio_access_key or not minio_secret_key:
        raise HTTPException(
            status_code=500,
            detail=(
                "MinIO is not configured. Set MINIO_ENDPOINT, "
                "MINIO_ACCESS_KEY and MINIO_SECRET_KEY."
            ),
        )
    return Minio(
        minio_server,
        access_key=minio_access_key,
        secret_key=minio_secret_key,
        secure=minio_secure,
    )


def upload_file_to_minio_sync(file_data: BytesIO, file_name: str, file_type: str, file_size: int):
    try:
        file_name = 'file/' + file_name
        minio_client = _get_minio_client()
        minio_client.put_object(bucket_name, file_name,
                                file_data, file_size, content_type=file_type)
        public_base = os.environ.get("MINIO_PUBLIC_BASE_URL")
        if public_base:
            return f"{public_base.rstrip('/')}/{bucket_name}/{file_name}"
        return f"minio://{bucket_name}/{file_name}"
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
