"""
图像处理器模块 - 负责图像加载、处理和历史管理
"""

import os
import cv2
import numpy as np
from PIL import Image
from typing import Optional, List, Tuple, Callable
from enum import Enum

from .algorithms import ALGORITHM_MAP, AlgorithmType


class ProcessingStep:
    """处理步骤记录 - 用于撤销/重做"""

    def __init__(self, description: str, image: np.ndarray,
                 mask: Optional[np.ndarray] = None):
        self.description = description
        self.image = image.copy()
        self.mask = mask.copy() if mask is not None else None


class ImageState:
    """图像状态"""

    def __init__(self, original: np.ndarray, path: str = ""):
        self.original = original.copy()
        self.current = original.copy()
        self.file_path = path
        self.file_name = os.path.basename(path) if path else "未命名"
        self.mask: Optional[np.ndarray] = None


class ImageProcessor:
    """
    图像处理器 - 管理图像加载、处理和历史操作
    """

    def __init__(self):
        self._current_image: Optional[np.ndarray] = None
        self._original_image: Optional[np.ndarray] = None
        self._mask: Optional[np.ndarray] = None
        self._file_path: str = ""
        self._history: List[ProcessingStep] = []
        self._history_index: int = -1
        self._max_history: int = 50
        self._callback: Optional[Callable] = None

    def set_callback(self, callback: Callable):
        """设置状态变更回调"""
        self._callback = callback

    def _notify(self):
        """通知状态变更"""
        if self._callback:
            self._callback()

    def load_image(self, file_path: str) -> bool:
        """
        加载图像

        Args:
            file_path: 图像文件路径

        Returns:
            是否成功加载
        """
        if not os.path.exists(file_path):
            return False

        # 使用 OpenCV 加载图像
        image = cv2.imread(file_path, cv2.IMREAD_COLOR)
        if image is None:
            # 尝试用 PIL 加载（处理一些特殊格式）
            try:
                pil_image = Image.open(file_path).convert('RGB')
                image = cv2.cvtColor(np.array(pil_image), cv2.COLOR_RGB2BGR)
            except Exception:
                return False

        self._original_image = image.copy()
        self._current_image = image.copy()
        self._file_path = file_path
        self._mask = None

        # 重置历史
        self._history = []
        self._history_index = -1
        self._save_state("加载图像")

        self._notify()
        return True

    @property
    def has_image(self) -> bool:
        return self._current_image is not None

    @property
    def current_image(self) -> Optional[np.ndarray]:
        return self._current_image.copy() if self._current_image is not None else None

    @property
    def original_image(self) -> Optional[np.ndarray]:
        return self._original_image.copy() if self._original_image is not None else None

    @property
    def mask(self) -> Optional[np.ndarray]:
        return self._mask.copy() if self._mask is not None else None

    @property
    def file_path(self) -> str:
        return self._file_path

    @property
    def file_name(self) -> str:
        return os.path.basename(self._file_path) if self._file_path else "未命名"

    def set_mask(self, mask: np.ndarray):
        """设置水印掩码"""
        if mask is not None:
            # 确保掩码是二值图像 (0 或 255)
            self._mask = cv2.threshold(mask, 127, 255, cv2.THRESH_BINARY)[1]
        else:
            self._mask = None

    def clear_mask(self):
        """清除掩码"""
        self._mask = None
        self._notify()

    def reset_to_original(self):
        """重置为原始图像

        重置后丢弃此前所有的处理历史，仅保留"加载图像"和"重置"两条记录，
        这样 undo 不会回退到上一次的算法结果（语义上"重置"不可逆）。
        """
        if self._original_image is not None:
            self._current_image = self._original_image.copy()
            self._mask = None
            # 截断历史：保留最初"加载图像"记录（如有），避免 undo 回到处理中间态
            if self._history:
                self._history = self._history[:1]
            self._history_index = len(self._history) - 1
            self._save_state("重置为原始图像")
            self._notify()

    def apply_algorithm(self, algorithm_type: AlgorithmType, **kwargs) -> bool:
        """
        应用去水印算法

        Args:
            algorithm_type: 算法类型
            **kwargs: 算法参数

        Returns:
            是否成功处理
        """
        if self._current_image is None:
            return False

        if algorithm_type not in ALGORITHM_MAP:
            return False

        algo_func = ALGORITHM_MAP[algorithm_type]

        try:
            if self._mask is not None and np.any(self._mask > 0):
                result = algo_func(self._current_image, self._mask, **kwargs)
            else:
                result = self._current_image.copy()

            self._current_image = result
            self._save_state(f"应用 {algorithm_type.value}")
            self._notify()
            return True

        except Exception as e:
            print(f"处理失败: {e}")
            return False

    def apply_algorithm_to_image(
            self, image: np.ndarray, mask: np.ndarray,
            algorithm_type: AlgorithmType, **kwargs) -> np.ndarray:
        """
        对指定图像应用去水印算法（用于批量处理）

        Args:
            image: 输入图像
            mask: 掩码
            algorithm_type: 算法类型
            **kwargs: 算法参数

        Returns:
            处理后的图像
        """
        if algorithm_type not in ALGORITHM_MAP:
            return image

        algo_func = ALGORITHM_MAP[algorithm_type]
        try:
            if mask is not None and np.any(mask > 0):
                return algo_func(image, mask, **kwargs)
        except Exception:
            pass

        return image.copy()

    def can_undo(self) -> bool:
        """是否可以撤销"""
        return self._history_index > 0

    def can_redo(self) -> bool:
        """是否可以重做"""
        return self._history_index < len(self._history) - 1

    def undo(self) -> bool:
        """撤销"""
        if not self.can_undo():
            return False

        self._history_index -= 1
        step = self._history[self._history_index]
        self._current_image = step.image.copy()
        self._mask = step.mask.copy() if step.mask is not None else None
        self._notify()
        return True

    def redo(self) -> bool:
        """重做"""
        if not self.can_redo():
            return False

        self._history_index += 1
        step = self._history[self._history_index]
        self._current_image = step.image.copy()
        self._mask = step.mask.copy() if step.mask is not None else None
        self._notify()
        return True

    def _save_state(self, description: str):
        """保存当前状态到历史"""
        step = ProcessingStep(description, self._current_image, self._mask)

        # 清除当前位置之后的历史
        if self._history_index < len(self._history) - 1:
            self._history = self._history[:self._history_index + 1]

        self._history.append(step)

        # 限制历史长度
        if len(self._history) > self._max_history:
            self._history = self._history[-self._max_history:]

        self._history_index = len(self._history) - 1

    def get_history_info(self) -> List[str]:
        """获取历史记录信息"""
        return [step.description for step in self._history]

    @staticmethod
    def get_supported_formats() -> List[str]:
        """获取支持的图像格式"""
        return ['*.jpg', '*.jpeg', '*.png', '*.bmp', '*.tiff',
                '*.tif', '*.webp', '*.ico', '*.ppm', '*.pgm']

    @staticmethod
    def save_image(image: np.ndarray, save_path: str,
                   quality: int = 95) -> bool:
        """
        保存图像

        Args:
            image: 要保存的图像 (BGR格式)
            save_path: 保存路径
            quality: 质量参数 (1-100)。
                - JPEG：直接作为质量等级 (IMWRITE_JPEG_QUALITY)
                - PNG：将 100→0 映射为压缩等级 0（无损）→ 9（最大压缩）

        Returns:
            是否成功保存
        """
        try:
            ext = os.path.splitext(save_path)[1].lower()

            if ext in ['.jpg', '.jpeg']:
                cv2.imwrite(save_path, image,
                            [cv2.IMWRITE_JPEG_QUALITY,
                             max(1, min(100, int(quality)))])
            elif ext == '.png':
                # quality 越大 → 压缩等级越小（文件越大、画质越好）
                clamped = max(1, min(100, int(quality)))
                png_compress = max(0, min(9, 9 - (clamped * 9 // 100)))
                cv2.imwrite(save_path, image,
                            [cv2.IMWRITE_PNG_COMPRESSION, png_compress])
            else:
                cv2.imwrite(save_path, image)

            return os.path.exists(save_path)
        except Exception as e:
            print(f"保存失败: {e}")
            return False

    @staticmethod
    def image_to_qimage(image: np.ndarray):
        """
        将OpenCV图像(BGR)转换为QImage

        注意: 必须复制QImage数据，避免numpy数组被回收后内存失效
        """
        from PyQt5.QtGui import QImage

        h, w = image.shape[:2]
        if len(image.shape) == 2:
            # 灰度图
            return QImage(image.data, w, h, w, QImage.Format_Grayscale8).copy()
        else:
            # BGR -> RGB
            rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
            return QImage(rgb.data, w, h, w * 3, QImage.Format_RGB888).copy()

    @staticmethod
    def qimage_to_cvmat(qimage):
        """将QImage转换为OpenCV图像（BGR）"""
        from PyQt5.QtGui import QImage

        if qimage.isNull():
            return None

        width = qimage.width()
        height = qimage.height()

        # 转换为RGBA格式以便处理
        qimage = qimage.convertToFormat(QImage.Format_RGBA8888)
        # PyQt5 在 Python 3 下 qimage.bits() 返回 memoryview，无需 setsize
        ptr = qimage.bits()
        arr = np.frombuffer(ptr, dtype=np.uint8).reshape(
            (height, width, 4)).copy()
        return cv2.cvtColor(arr, cv2.COLOR_RGBA2BGR)