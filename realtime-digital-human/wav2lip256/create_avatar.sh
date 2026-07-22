CUDA_VISIBLE_DEVICES=0 python genavatar.py \
    --video_path /data/realtime-digitalhuman/videos/gongan_0806.mp4 \
    --avatar_id wav2lip_avatar4 \
    --pads 0 10 0 0 \
    --face_det_batch_size 4 \
    --bg ../data/customimage/1.jpg