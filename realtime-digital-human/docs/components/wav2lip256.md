### 数字人开发记录

1. 直接执行

```shell
cd wav2lip256
sh create_avatar.sh
cd ..
```

--video_path 代表需要处理的视频， --avatar_id 生成的人物ID，--bg 背景图像

2. 产品需求：

分为视频上传和推理界面两个

（1）用户拍摄并上传20s左右的视频，分辨率为1080 x 1920，竖屏方式

（2）推理界面参考VUE源码和UI设计


3. API访问:

3.1 视频转链接接口

服务开启：
```python
python upload_api.py
```

测试接口：http://10.100.10.31:8086/v1/upload/

3.2 视频本地数字人处理

服务开启：
```python
python digitalman_api.py --host 0.0.0.0 --port 8085
```
后端得到数字人处理后的文件 ./data/avatars/wav2lip_avatar4 中包含face_imgs、full_imgs和full_masks三个文件夹和coords.pkl，分别代表数字人面部图像、全身图像、全身mask和全身坐标信息。

1. 本地视频处理接口
- URL: `http://10.100.10.31:8085/v1/process_video/`
- 方法: POST
- 用途: 处理上传的视频文件，返回数字人ID

2. 视频链接处理接口
- URL: `http://10.100.10.31:8085/v1/process_video_url/`
- 方法: POST
- 用途: 处理视频链接，返回数字人ID

3.3 设计思路

首先用户上传视频转链接，将视频url上传至后端得到实时数字人演示素材（以数字人ID的方式获取），将需要的数字人ID传给后端进行数字人ID更新。



### 欣禾数字人素材制作


1. 提取全身和面部素材
```
conda activate wav2lip
cd wav2lip256
sh create _avatar.sh   修改对应视频的路径 video_path 和 avatar_id, avatar_id 对应 wav2lip_avatarx
```

2. 提取分割素材
```
conda activate wav2lip
cd wav2lip256
python segmentation_v2.py --input_dir /Data1/home/lishuang/realtime-digitalhuman/data/avatars/wav2lip_avatarx/full_imgs --output_dir realtime-digitalhuman/data/avatars/wav2lip_avatarx/full_masks
```