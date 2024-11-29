from .gigapixel import NODE_CLASS_MAPPINGS, NODE_DISPLAY_NAME_MAPPINGS
import os
import shutil
import __main__

WEB_DIRECTORY = "./web"
__all__ = ['NODE_CLASS_MAPPINGS', 'NODE_DISPLAY_NAME_MAPPINGS', 'WEB_DIRECTORY']

# 确保扩展路径存在
extensions_path = os.path.join(os.path.dirname(os.path.realpath(__main__.__file__)), "web", "extensions", "gigapixel")
if not os.path.exists(extensions_path):
    os.makedirs(extensions_path)

# 复制所有 *.js 文件到扩展路径
js_path = os.path.join(os.path.dirname(os.path.realpath(__file__)), "web", "js")
for file in os.listdir(js_path):
    if file.endswith(".js"):
        src_file = os.path.join(js_path, file)
        dst_file = os.path.join(extensions_path, file)
        if os.path.exists(dst_file):
            os.remove(dst_file)
        shutil.copy(src_file, dst_file)
        print('installed %s to %s' % (file, extensions_path))
