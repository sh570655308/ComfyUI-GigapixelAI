import numpy as np
import os
import pprint
import time
import folder_paths
import torch
import subprocess
import json
import shutil

from PIL import Image, ImageOps
from typing import Optional

class GigapixelUpscaleSettings:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            'required': {
                'enabled': (['true', 'false'], {'default': 'true'}),
                'sharpen': ('FLOAT', {'default': 1, 'min': 0, 'max': 100, 'round': False, 'display': 'Sharpen Strength'}),
                'denoise': ('FLOAT', {'default': 1, 'min': 0, 'max': 100, 'round': False, 'display': 'Denoise Strength'}),
                'compression': ('FLOAT', {'default': 67, 'min': 0, 'max': 100, 'round': False, 'display': 'Compression'}),
                'fr': ('FLOAT', {'default': 50, 'min': 0, 'max': 100, 'round': False, 'display': 'Fine Detail Retention'}),
            },
            'optional': {},
        }

    RETURN_TYPES = ('GigapixelUpscaleSettings',)
    RETURN_NAMES = ('upscale_settings',)
    FUNCTION = 'init'
    CATEGORY = 'image'
    OUTPUT_NODE = False
    OUTPUT_IS_LIST = (False,)

    def init(self, enabled, sharpen, denoise, compression, fr):
        self.enabled = str(True).lower() == enabled.lower()
        self.sharpen = sharpen
        self.denoise = denoise
        self.compression = compression
        self.fr = fr
        return (self,)

class GigapixelModelSettings:
    MODEL_MAPPING = {
        'Art & CG': 'art',
        'Lines': 'lines',
        'Very Compressed': 'vc',
        'High Fidelity': 'fidelity',
        'Low Resolution': 'lowres',
        'Standard': 'std',
        'Text & Shapes': 'text'
    }

    # 需要添加 mv 2 参数的模型列表
    MV2_MODELS = {'std', 'fidelity', 'lowres'}

    @classmethod
    def INPUT_TYPES(cls):
        return {
            'required': {
                'model': (list(cls.MODEL_MAPPING.keys()), {'default': 'Standard'}),
            },
        }

    RETURN_TYPES = ('GigapixelModelSettings',)
    RETURN_NAMES = ('model_settings',)
    FUNCTION = 'init'
    CATEGORY = 'image'
    OUTPUT_NODE = False
    OUTPUT_IS_LIST = (False,)

    def init(self, model):
        self.model = self.MODEL_MAPPING[model]
        self.needs_mv2 = self.model in self.MV2_MODELS
        return (self,)

class GigapixelAI:
    def __init__(self):
        self.this_dir = os.path.dirname(os.path.abspath(__file__))
        self.comfy_dir = os.path.abspath(os.path.join(self.this_dir, '..', '..'))
        self.output_dir = os.path.join(self.comfy_dir, 'temp', 'gigapixel_output')
        self.prefix = 'gigapixel'

    @classmethod
    def INPUT_TYPES(cls):
        return {
            'required': {
                'images': ('IMAGE',),
                'scale': ('FLOAT', {'default': 2.0, 'min': 1, 'max': 16, 'round': False}),
                'no_temp': (['true', 'false'], {'default': 'true'}),
            },
            'optional': {
                'gigapixel_exe': ('STRING', {'default': '', }),
                'upscale': ('GigapixelUpscaleSettings',),
                'model': ('GigapixelModelSettings',),
            },
            "hidden": {}
        }

    RETURN_TYPES = ('STRING', 'STRING', 'IMAGE')
    RETURN_NAMES = ('settings', 'image_paths', 'IMAGE')
    FUNCTION = 'upscale_image'
    CATEGORY = 'image'
    OUTPUT_NODE = True
    OUTPUT_IS_LIST = (True, True, True)

    def save_image(self, img, output_dir, filename):
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)
        file_path = os.path.join(output_dir, filename)
        img.save(file_path)
        return file_path

    def load_image(self, image_path):
        i = Image.open(image_path)
        i = ImageOps.exif_transpose(i)
        image = i.convert('RGB')
        image = np.array(image).astype(np.float32) / 255.0
        image = torch.from_numpy(image)[None,]
        return image

    def upscale_image(self, images, scale, no_temp, gigapixel_exe=None, upscale: Optional[GigapixelUpscaleSettings]=None, model: Optional[GigapixelModelSettings]=None):
        os.makedirs(self.output_dir, exist_ok=True)
        
        now_millis = int(time.time() * 1000)
        batch_dir = os.path.join(self.output_dir, f'batch_{now_millis}')
        os.makedirs(batch_dir, exist_ok=True)
        
        upscaled_images = []
        upscale_settings = []
        upscale_image_paths = []
        
        try:
            count = 0
            for image in images:
                count += 1
                i = 255.0 * image.cpu().numpy()
                img = Image.fromarray(np.clip(i, 0, 255).astype(np.uint8))
                
                img_file = os.path.join(batch_dir, f'input_{count}.png')
                self.save_image(img, os.path.dirname(img_file), os.path.basename(img_file))
                
                output_dir = os.path.join(batch_dir, f'output_{count}')
                os.makedirs(output_dir, exist_ok=True)
                
                (settings, output_image_paths) = self.gigapixel_upscale(img_file, gigapixel_exe, scale, upscale, model, output_dir)
                
                for output_path in output_image_paths:
                    upscaled_image = self.load_image(output_path)
                    upscaled_images.append(upscaled_image)
                    upscale_settings.append(settings)
                    upscale_image_paths.append(output_path)
        finally:
            # 如果no_temp为true，清理临时目录
            if str(True).lower() == no_temp.lower():
                try:
                    shutil.rmtree(batch_dir)
                except Exception as e:
                    print(f"Error cleaning up temporary directory: {e}")

        return (upscale_settings, upscale_image_paths, upscaled_images)

    def gigapixel_upscale(self, img_file, gigapixel_exe, scale, upscale: Optional[GigapixelUpscaleSettings]=None, model: Optional[GigapixelModelSettings]=None, target_dir=None):
        if not os.path.exists(gigapixel_exe):
            raise ValueError(f'Gigapixel AI not found: {gigapixel_exe}')
        
        if target_dir is None:
            target_dir = os.path.join(self.output_dir, 'default_output')
        os.makedirs(target_dir, exist_ok=True)
        
        if len(img_file) > 250 or len(target_dir) > 250:
            raise ValueError(f"Path too long. Input: {len(img_file)} chars, Output: {len(target_dir)} chars")
        
        gigapixel_args = [gigapixel_exe]
        
        if upscale and upscale.enabled:
            gigapixel_args.extend(['--scale', str(scale)])
            gigapixel_args.extend(['-i', img_file])
            gigapixel_args.extend(['-o', target_dir])
            
            # 只有当参数大于0时才添加
            if upscale.denoise > 0:
                gigapixel_args.extend(['--dn', str(upscale.denoise)])
            
            if upscale.sharpen > 0:
                gigapixel_args.extend(['--sh', str(upscale.sharpen)])
            
            if upscale.compression > 0:
                gigapixel_args.extend(['--cm', str(upscale.compression)])
            
            if upscale.fr > 0:
                gigapixel_args.extend(['--fr', str(upscale.fr)])
        else:
            gigapixel_args.extend([
                '--scale', str(scale),
                '-i', img_file,
                '-o', target_dir
            ])

        # 添加模型参数
        if model:
            gigapixel_args.extend(['--model', model.model])
            # 对于特定模型添加 mv 2 参数
            if model.needs_mv2:
                gigapixel_args.extend(['--mv', '2'])
        
        try:
            print(f"执行命令: {' '.join(gigapixel_args)}")
            
            result = subprocess.run(
                gigapixel_args, 
                capture_output=True, 
                text=True, 
                timeout=600, 
                check=True
            )
            
            print("Gigapixel running:")
            print(result.stdout)
            
            output_images = [
                os.path.join(target_dir, f) 
                for f in os.listdir(target_dir) 
                if f.endswith(('.png', '.jpg', '.jpeg', '.tif', '.tiff'))
            ]
            
            settings = {
                'scale': scale,
                'denoise': upscale.denoise if upscale and upscale.denoise > 0 else None,
                'sharpen': upscale.sharpen if upscale and upscale.sharpen > 0 else None,
                'compression': upscale.compression if upscale and upscale.compression > 0 else None,
                'fr': upscale.fr if upscale and upscale.fr > 0 else None,
                'model': model.model if model else 'std',
                'mv': 2 if model and model.needs_mv2 else None
            }
            settings_json = json.dumps(settings, indent=2).replace('"', "'")

            return (settings_json, output_images)
        
        except subprocess.TimeoutExpired:
            print("Gigapixel timeout")
            raise
        except subprocess.CalledProcessError as e:
            print(f"Gigapixel CLI error code: {e.returncode}")
            print(f"STDOUT: {e.stdout}")
            print(f"STDERR: {e.stderr}")
            raise
        except Exception as e:
            print(f"error while processing: {e}")
            raise

NODE_CLASS_MAPPINGS = {
    'GigapixelAI': GigapixelAI,
    'GigapixelUpscaleSettings': GigapixelUpscaleSettings,
    'GigapixelModelSettings': GigapixelModelSettings,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    'GigapixelAI': 'Gigapixel AI',
    'GigapixelUpscaleSettings': 'Gigapixel Upscale Settings',
    'GigapixelModelSettings': 'Gigapixel Model Settings',
}
