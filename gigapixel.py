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
                'pre_downscaling': ('FLOAT', {'default': 75, 'min': 50, 'max': 100, 'round': False, 'display': 'Pre-Downscaling (Recovery only)'}),
            },
            'optional': {},
        }

    RETURN_TYPES = ('GigapixelUpscaleSettings',)
    RETURN_NAMES = ('upscale_settings',)
    FUNCTION = 'init'
    CATEGORY = 'image'
    OUTPUT_NODE = False
    OUTPUT_IS_LIST = (False,)

    def init(self, enabled, sharpen, denoise, compression, fr, pre_downscaling):
        self.enabled = str(True).lower() == enabled.lower()
        self.sharpen = sharpen
        self.denoise = denoise
        self.compression = compression
        self.fr = fr
        self.pre_downscaling = pre_downscaling
        return (self,)

class GigapixelModelSettings:
    MODEL_MAPPING = {
        'Art & CG': 'art',
        'Lines': 'lines',
        'Very Compressed': 'vc',
        'High Fidelity': 'fidelity',
        'Low Resolution': 'lowres',
        'Standard': 'std',
        'Text & Shapes': 'text',
        'Redefine': 'redefine',
        'Recover': 'recovery'
    }

    # 需要添加 mv 2 参数的模型列表
    MV2_MODELS = {'std', 'fidelity', 'lowres', 'recovery'}

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
        self.output_dir = os.path.join(self.comfy_dir, 'temp', 'gigapixel')
        self.prefix = 'gpx'

    @classmethod
    def INPUT_TYPES(cls):
        return {
            'required': {
                'images': ('IMAGE',),
                'scale': ('FLOAT', {'default': 2.0, 'min': 1, 'max': 16, 'round': False}),
                'no_temp': (['true', 'false'], {'default': 'true'}),
                'use_system_command': (['true', 'false'], {'default': 'true'}),
            },
            'optional': {
                'gigapixel_exe': ('STRING', {'default': 'C:\Program Files\Topaz Labs LLC\Topaz Gigapixel AI\gigapixel.exe', }),
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

    def upscale_image(self, images, scale, no_temp, use_system_command, gigapixel_exe=None, upscale: Optional[GigapixelUpscaleSettings]=None, model: Optional[GigapixelModelSettings]=None):
        os.makedirs(self.output_dir, exist_ok=True)
        
        now_millis = int(time.time() * 1000)
        batch_dir = os.path.join(self.output_dir, f'b{now_millis}')
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
                
                img_file = os.path.join(batch_dir, f'i{count}.png')
                self.save_image(img, os.path.dirname(img_file), os.path.basename(img_file))
                
                output_dir = os.path.join(batch_dir, f'o{count}')
                os.makedirs(output_dir, exist_ok=True)
                
                (settings, output_image_paths) = self.gigapixel_upscale(img_file, gigapixel_exe, scale, upscale, model, output_dir, use_system_command)
                
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

    def gigapixel_upscale(self, img_file, gigapixel_exe, scale, upscale: Optional[GigapixelUpscaleSettings]=None, model: Optional[GigapixelModelSettings]=None, target_dir=None, use_system_command=True):
        # 根据开关决定使用系统命令还是完整路径
        use_system_cmd = str(True).lower() == str(use_system_command).lower()
        
        if not use_system_cmd and not os.path.exists(gigapixel_exe):
            raise ValueError(f'Gigapixel AI not found: {gigapixel_exe}')
        
        print(f"检查输入文件是否存在: {os.path.exists(img_file)}")
        print(f"输入文件大小: {os.path.getsize(img_file) if os.path.exists(img_file) else 'file not found'}")
        print(f"输出目录权限检查: {os.access(os.path.dirname(target_dir), os.W_OK)}")
        
        if target_dir is None:
            target_dir = os.path.join(self.output_dir, 'default_output')
        os.makedirs(target_dir, exist_ok=True)
        
        if len(img_file) > 250 or len(target_dir) > 250:
            raise ValueError(f"Path too long. Input: {len(img_file)} chars, Output: {len(target_dir)} chars")
        
        # 使用引号包裹带空格的路径
        if use_system_cmd:
            command_exe = 'gigapixel'
        else:
            command_exe = f'"{gigapixel_exe}"'
        
        img_file = f'"{img_file}"'
        target_dir = f'"{target_dir}"'
        
        gigapixel_args = [command_exe]
        
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
            
            # Pre-downscaling参数只对recovery模型生效
            if model and model.model == 'recovery' and upscale.pre_downscaling >= 50:
                gigapixel_args.extend(['--pds', str(upscale.pre_downscaling)])
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
            
            # 根据是否使用系统命令决定是否需要shell=True
            if use_system_cmd:
                # 使用系统命令时，在Windows下需要shell=True
                result = subprocess.run(
                    ' '.join(gigapixel_args), 
                    capture_output=True, 
                    text=True, 
                    timeout=600, 
                    check=False,
                    shell=True  # Windows系统命令需要shell=True
                )
            else:
                # 使用完整路径时，可以直接执行
                result = subprocess.run(
                    ' '.join(gigapixel_args), 
                    capture_output=True, 
                    text=True, 
                    timeout=600, 
                    check=False
                )
            
            print("Gigapixel running:")
            print(result.stdout)
            
            # 检查输出目录中是否有文件
            output_images = [
                os.path.join(target_dir.strip('"'), f) 
                for f in os.listdir(target_dir.strip('"')) 
                if f.endswith(('.png', '.jpg', '.jpeg', '.tif', '.tiff'))
            ]
            
            if not output_images:
                target_dir_clean = target_dir.strip('"')
                print(f"警告: 没有找到输出文件，检查目录: {target_dir_clean}")
                raise ValueError("Gigapixel AI 没有生成输出文件")
            
            settings = {
                'scale': scale,
                'denoise': upscale.denoise if upscale and upscale.denoise > 0 else None,
                'sharpen': upscale.sharpen if upscale and upscale.sharpen > 0 else None,
                'compression': upscale.compression if upscale and upscale.compression > 0 else None,
                'fr': upscale.fr if upscale and upscale.fr > 0 else None,
                'pre_downscaling': upscale.pre_downscaling if upscale and model and model.model == 'recovery' and upscale.pre_downscaling >= 50 else None,
                'model': model.model if model else 'std',
                'mv': 2 if model and model.needs_mv2 else None
            }
            settings_json = json.dumps(settings, indent=2).replace('"', "'")

            return (settings_json, output_images)
        
        except subprocess.TimeoutExpired:
            print("Gigapixel timeout")
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
