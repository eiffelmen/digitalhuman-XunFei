import os
import cv2
from tqdm import tqdm
from PIL import Image

import torch
import numpy as np
from torchvision import transforms
from transformers import AutoModelForImageSegmentation

import warnings

warnings.filterwarnings('ignore', category=FutureWarning)


class RMBGImageSegmentation:
    def __init__(self, model_name='briaai/RMBG-2.0', device='cuda'):
        self.device = torch.device(
            device if torch.cuda.is_available() else 'cpu')
        self.model = AutoModelForImageSegmentation.from_pretrained(
            model_name, trust_remote_code=True).to(self.device)
        torch.set_float32_matmul_precision('high')
        self.model.eval()

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
            image).unsqueeze(0).to(self.device)
        preds = self.model(input_tensor)[-1].sigmoid().cpu()
        pred = preds[0].squeeze()
        mask = (pred.numpy() * 255).astype('uint8')
        mask = cv2.resize(
            mask, image_cv2.shape[1::-1], interpolation=cv2.INTER_LINEAR)

        # 使用更大的核进行形态学闭运算
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (15, 15))
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)

        # 使用漫水填充法填充内部空洞
        mask_flood = mask.copy()
        h, w = mask.shape
        mask_zeros = np.zeros((h+2, w+2), np.uint8)
        cv2.floodFill(mask_flood, mask_zeros, (0, 0), 255)  # 填充外部
        mask_flood_inv = cv2.bitwise_not(mask_flood)
        mask = cv2.bitwise_or(mask, mask_flood_inv)  # 合并结果

        # 找到最大轮廓并填充
        contours, _ = cv2.findContours(
            mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if contours:
            max_contour = max(contours, key=cv2.contourArea)
            mask = cv2.fillPoly(mask, [max_contour], 255)

        # 添加腐蚀操作，使轮廓向内收紧
        erosion_kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (9, 9))
        mask = cv2.erode(mask, erosion_kernel, iterations=3)

        return mask


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(
        description='Image Segmentation with RMBG')
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
