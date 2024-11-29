import numpy as np
import os
import pprint
import time
import folder_paths
import torch
import subprocess
import json

from PIL import Image, ImageOps
from typing import Optional
import json

class GigapixelUpscaleSettings:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            'required': {
                'enabled': (['true', 'false'], {'default': 'true'}),
                'model': ([
                    'Standard', 
                    'Low Resolution', 
                    'High Fidelity', 
                    'Very Compressed', 
                    'Art & CG', 
                    'Lines'
                ], {'default': 'Standard'}),
                'scale': ('FLOAT', {'default': 2.0, 'min': 1, 'max': 16, 'round': False}),
                'sharpen': ('FLOAT', {'default': 1, 'min': 1, 'max': 100, 'round': False, 'display': 'Sharpen Strength'}),
                'denoise': ('FLOAT', {'default': 1, 'min': 1, 'max': 100, 'round': False, 'display': 'Denoise Strength'}),
                'compression': ('FLOAT', {'default': 67, 'min': 1, 'max': 100, 'round': False, 'display': 'Compression'}),
            },
            'optional': {},
        }

    RETURN_TYPES = ('GigapixelUpscaleSettings',)
    RETURN_NAMES = ('upscale_settings',)
    FUNCTION = 'init'
    CATEGORY = 'image'
    OUTPUT_NODE = False
    OUTPUT_IS_LIST = (False,)
    
    def init(self, enabled, model, scale, sharpen, denoise, compression):
        self.enabled = str(True).lower() == enabled.lower()
        self.model = model
        self.scale = scale
        self.sharpen = sharpen
        self.denoise = denoise
        self.compression = compression
        return (self,)


class GigapixelAI:
    def __init__(self):
        self.this_dir = os.path.dirname(os.path.abspath(__file__))
        self.comfy_dir = os.path.abspath(os.path.join(self.this_dir, '..', '..'))
        self.subfolder = 'upscaled'
        self.output_dir = os.path.join(self.comfy_dir, 'temp')
        self.prefix = 'gigapixel'

    @classmethod
    def INPUT_TYPES(cls):
        return {
            'required': {
                'images': ('IMAGE',),
            },
            'optional': {
                'gigapixel_exe': ('STRING', {
                    'default': '',                    
                }),
                'upscale': ('GigapixelUpscaleSettings',),
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

    def load_image(self, image):
        image_path = folder_paths.get_annotated_filepath(image)
        i = Image.open(image_path)
        i = ImageOps.exif_transpose(i)
        image = i.convert('RGB')
        image = np.array(image).astype(np.float32) / 255.0
        image = torch.from_numpy(image)[None,]
        return image

    def upscale_image(self, images, gigapixel_exe=None, 
                    upscale: Optional[GigapixelUpscaleSettings]=None):
        now_millis = int(time.time() * 1000)
        prefix = '%s-%d' % (self.prefix, now_millis)
        
        batch_output_dir = os.path.join(self.output_dir, self.subfolder, f'batch_{now_millis}')
        os.makedirs(batch_output_dir, exist_ok=True)
        
        upscaled_images = []
        upscale_settings = []
        upscale_image_paths = []
        
        count = 0
        for image in images:
            count += 1
            i = 255.0 * image.cpu().numpy()
            img = Image.fromarray(np.clip(i, 0, 255).astype(np.uint8))
            img_file = self.save_image(
                img, self.output_dir, '%s-%d.png' % (prefix, count)
            )
            
            self.output_dir = batch_output_dir
            
            (settings, output_image_paths) = self.gigapixel_upscale(img_file, gigapixel_exe, upscale)
            
            for output_path in output_image_paths:
                upscaled_image = self.load_image(output_path)
                upscaled_images.append(upscaled_image)
                upscale_settings.append(settings)
                upscale_image_paths.append(output_path)

        return (upscale_settings, upscale_image_paths, upscaled_images)

    def gigapixel_upscale(self, img_file, gigapixel_exe=None, 
                        upscale: Optional[GigapixelUpscaleSettings]=None):
        if not os.path.exists(gigapixel_exe):
            raise ValueError(f'Gigapixel AI not found: {gigapixel_exe}')
        
        model_mapping = {
            'Art & CG': 'art',
            'Lines': 'lines',
            'Very Compressed': 'very compressed',
            'High Fidelity': 'hf',
            'Low Resolution': 'lowres',
            'Standard': 'std',
            'Text & Shapes': 'text'
        }
        
        target_dir = self.output_dir
        os.makedirs(target_dir, exist_ok=True)
        
        gigapixel_args = [gigapixel_exe]
        
        if upscale and upscale.enabled:
            gigapixel_args.extend(['--scale', str(upscale.scale)])
            
            if upscale.model in model_mapping:
                gigapixel_args.extend(['--model', model_mapping[upscale.model]])
            
            gigapixel_args.extend(['-i', img_file])
            
            gigapixel_args.extend(['-o', target_dir])
            
            if upscale.denoise > 1:
                gigapixel_args.extend(['--dn', str(upscale.denoise)])
            
            if upscale.sharpen > 1:
                gigapixel_args.extend(['--sh', str(upscale.sharpen)])
            
            if upscale.compression < 100:
                gigapixel_args.extend(['--cm', str(upscale.compression)])
        else:
            gigapixel_args.extend([
                '--scale', '2',
                '-i', img_file,
                '-o', target_dir
            ])
        
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
                'scale': upscale.scale if upscale else 2,
                'model': upscale.model if upscale else 'Standard',
                'denoise': upscale.denoise if upscale else 1,
                'sharpen': upscale.sharpen if upscale else 1,
                'compression': upscale.compression if upscale else 67
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
            print(f"error while propcessing: {e}")
            raise
    
NODE_CLASS_MAPPINGS = {
    'GigapixelAI': GigapixelAI,
    'GigapixelUpscaleSettings': GigapixelUpscaleSettings,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    'GigapixelAI': 'Gigapixel AI',
    'GigapixelUpscaleSettings': 'Gigapixel Upscale Settings',
}
