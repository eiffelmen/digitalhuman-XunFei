import os
import cv2
from tqdm import tqdm
import numpy as np
from PIL import Image

import torch
from torchvision import transforms
from transformers import AutoModelForImageSegmentation

import warnings

warnings.filterwarnings('ignore', category=FutureWarning)


class RMBGImageSegmentation:
    def __init__(self, model_name='ZhengPeng7/BiRefNet', device='cuda'):
        self.device = torch.device(
            device if torch.cuda.is_available() else 'cpu')
        self.model = AutoModelForImageSegmentation.from_pretrained(
            model_name, trust_remote_code=True).to(self.device)
        torch.set_float32_matmul_precision('high')
        self.model.eval()
        self.model.half()

        self.image_size = (1024, 1024)
        self.transform_image = transforms.Compose([
            transforms.Resize(self.image_size),
            transforms.ToTensor(),
            transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225])
        ])

    @torch.inference_mode()
    def __call__(self, input_image_matrix):
        image_cv2 = cv2.cvtColor(input_image_matrix.astype(
            'uint8'), cv2.COLOR_BGR2RGB)
        image = Image.fromarray(image_cv2)
        input_tensor = self.transform_image(
            image).unsqueeze(0).to(self.device).half()
        preds = self.model(input_tensor)[-1].sigmoid().cpu()
        pred = preds[0].squeeze()
        mask = (pred.numpy() * 255).astype('uint8')
        mask = cv2.resize(
            mask, image_cv2.shape[1::-1], interpolation=cv2.INTER_LINEAR)

        # 新增边缘滤波处理
        mask = cv2.GaussianBlur(mask, (5, 5), 0)  # 高斯模糊柔化边缘
        mask = np.clip(mask, 0, 255).astype('uint8')  # 确保数值范围在0-255之间

        return mask


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(
        description='Image Segmentation with BiRefNet')
    parser.add_argument('--input_dir', type=str, required=True,
                        help='Input image directory path')
    parser.add_argument('--output_dir', type=str, required=True,
                        help='Output directory path for masks')
    args = parser.parse_args()

    segmenter = RMBGImageSegmentation()

    if not os.path.exists(args.output_dir):
        os.makedirs(args.output_dir)

    for filename in tqdm((os.listdir(args.input_dir))):
        if filename.endswith(('.png')):
            input_path = os.path.join(args.input_dir, filename)
            output_path = os.path.join(args.output_dir, filename)
            input_image = cv2.imread(input_path)
            mask = segmenter(input_image)
            cv2.imwrite(output_path, mask)
