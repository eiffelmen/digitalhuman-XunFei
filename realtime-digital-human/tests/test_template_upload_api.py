import httpx
import asyncio
import argparse


async def test_upload_audio(file_path: str):
    url = "http://10.100.10.31:8088/v1/upload_audio"

    try:
        with open(file_path, "rb") as f:
            files = {"file": (file_path, f, "audio/wav")}
            async with httpx.AsyncClient() as client:
                response = await client.post(url, files=files)
                print(response.json())
    except FileNotFoundError:
        print("File not found. Please provide a valid audio file path.")


async def test_upload_image(file_path: str):
    url = "http://10.100.10.31:8088/v1/upload_image"

    try:
        with open(file_path, "rb") as f:
            files = {"file": (file_path, f, "image/jpeg")}
            async with httpx.AsyncClient() as client:
                response = await client.post(url, files=files)
                print(response.json())
    except FileNotFoundError:
        print("文件未找到。请提供有效的图片文件路径。")


async def test_delete_audio(avatar_audio: int):
    url = f"http://10.100.10.31:8088/v1/delete_audio/{avatar_audio}"

    async with httpx.AsyncClient() as client:
        response = await client.delete(url)
        print(response.json())


async def test_delete_image(avatar_bg: int):
    url = f"http://10.100.10.31:8088/v1/delete_image/{avatar_bg}"

    async with httpx.AsyncClient() as client:
        response = await client.delete(url)
        print(response.json())


async def main():
    parser = argparse.ArgumentParser(
        description="Upload audio or image files.")
    parser.add_argument(
        "--audio", type=str, default="ref_audios/1.wav", help="Path to the audio file.")
    parser.add_argument(
        "--image", type=str, default="images/lishuang.png", help="Path to the image file.")
    args = parser.parse_args()

    if args.audio:
        await test_upload_audio(args.audio)
    if args.image:
        await test_upload_image(args.image)

    await test_delete_audio(1)
    await test_delete_image(1)


if __name__ == "__main__":
    asyncio.run(main())


# curl -X POST http://10.100.10.31:8088/v1/upload_audio -F "file=@ref_audios/1.wav"
# curl -X POST http://10.100.10.31:8088/v1/upload_image -F "file=@customimage/1.jpg;type=image/jpeg" \
# curl -X DELETE http://10.100.10.31:8088/v1/delete_audio/{avatar_audio}
# curl -X DELETE http://10.100.10.31:8088/v1/delete_image/{avatar_bg}
