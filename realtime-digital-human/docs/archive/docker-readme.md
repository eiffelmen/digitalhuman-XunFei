docker build -t digitalman . -f Dockerfile.digitalman

docker run -p 8010:8010 -p 8011:8011 digitalman

# docker run --net=host  -p 8010:8010 -p 8011:8011 digitalman


docker save realtime-digitalhuman-funasr-service | gzip > funasr-service.tar.gz

docker save realtime-digitalhuman-sparktts-service | gzip > sparktts-service.tar.gz

docker save realtime-digitalhuman-main-service | gzip > main-service.tar.gz

docker save realtime-digitalhuman-nginx-service | gzip > digitalhuman-nginx-service.tar.gz


docker compose up --build

## 获取主板序列号

sudo dmidecode -s baseboard-serial-number

echo "123" |md5sum

修改docker compose 文件，和app_v2.py内的验证硬件指纹功能的字符串
