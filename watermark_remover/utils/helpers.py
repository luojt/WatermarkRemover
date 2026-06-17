"""
工具函数模块
"""

import os
import sys
import uuid
from datetime import datetime


def resource_path(relative_path: str) -> str:
    """
    获取资源文件的绝对路径（兼容 PyInstaller 打包环境）

    在开发环境中直接使用相对路径；
    在 PyInstaller 打包的 onefile 环境下，
    资源文件被解压到 sys._MEIPASS 临时目录。

    Args:
        relative_path: 相对于项目根目录的路径，如 "watermark_remover/logo.png"

    Returns:
        资源文件的绝对路径
    """
    try:
        # PyInstaller onefile 模式：资源在 _MEIPASS 中
        base_path = sys._MEIPASS
    except AttributeError:
        # 开发模式：基于当前文件位置定位项目根目录
        base_path = os.path.dirname(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return os.path.join(base_path, relative_path)


def generate_output_filename(original_path: str, suffix: str = "_processed",
                             include_date: bool = False) -> str:
    """
    生成输出文件名

    Args:
        original_path: 原始文件路径
        suffix: 文件名后缀
        include_date: 是否包含日期

    Returns:
        生成的文件名
    """
    base_name = os.path.splitext(os.path.basename(original_path))[0]
    ext = os.path.splitext(original_path)[1]

    if include_date:
        date_str = datetime.now().strftime("_%Y%m%d_%H%M%S")
        return f"{base_name}{suffix}{date_str}{ext}"
    else:
        return f"{base_name}{suffix}{ext}"


def generate_output_path(output_dir: str, original_path: str,
                         suffix: str = "_processed",
                         include_date: bool = False) -> str:
    """
    生成输出文件完整路径

    Args:
        output_dir: 输出目录
        original_path: 原始文件路径
        suffix: 文件名后缀
        include_date: 是否包含日期

    Returns:
        生成的完整路径
    """
    filename = generate_output_filename(original_path, suffix, include_date)
    return os.path.join(output_dir, filename)


def ensure_output_dir(output_dir: str) -> bool:
    """
    确保输出目录存在

    Args:
        output_dir: 输出目录路径

    Returns:
        目录是否存在或成功创建
    """
    if not os.path.exists(output_dir):
        try:
            os.makedirs(output_dir)
            return True
        except Exception:
            return False
    return True


def format_file_size(size_bytes: int) -> str:
    """
    格式化文件大小

    Args:
        size_bytes: 文件大小（字节）

    Returns:
        格式化后的字符串
    """
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} TB"


def get_file_info(file_path: str) -> dict:
    """
    获取文件信息

    Args:
        file_path: 文件路径

    Returns:
        文件信息字典
    """
    try:
        stat = os.stat(file_path)
        return {
            'path': file_path,
            'name': os.path.basename(file_path),
            'size': format_file_size(stat.st_size),
            'size_bytes': stat.st_size,
            'modified': datetime.fromtimestamp(stat.st_mtime),
            'created': datetime.fromtimestamp(stat.st_ctime),
        }
    except Exception:
        return {}


def is_image_file(file_path: str) -> bool:
    """
    检查是否为支持的图像文件

    Args:
        file_path: 文件路径

    Returns:
        是否为图像文件
    """
    supported_extensions = {
        '.jpg', '.jpeg', '.png', '.bmp', '.tiff',
        '.tif', '.webp', '.ico', '.ppm', '.pgm'
    }
    ext = os.path.splitext(file_path)[1].lower()
    return ext in supported_extensions


def generate_temp_id() -> str:
    """生成临时ID"""
    return str(uuid.uuid4())[:8]


def limit_image_size(image, max_width: int = 1920, max_height: int = 1080):
    """
    限制图像尺寸，保持宽高比

    Args:
        image: OpenCV图像
        max_width: 最大宽度
        max_height: 最大高度

    Returns:
        调整后的图像
    """
    import cv2
    h, w = image.shape[:2]

    if w <= max_width and h <= max_height:
        return image

    scale = min(max_width / w, max_height / h, 1.0)
    new_w = int(w * scale)
    new_h = int(h * scale)

    return cv2.resize(image, (new_w, new_h), interpolation=cv2.INTER_AREA)