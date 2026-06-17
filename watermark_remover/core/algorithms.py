"""
图像去水印算法模块
提供多种去水印算法实现
"""

import cv2
import numpy as np
from enum import Enum


class AlgorithmType(Enum):
    """算法类型枚举"""
    INPAINT_TELEA = "OpenCV 修复 (Telea)"
    INPAINT_NS = "OpenCV 修复 (NS)"
    AREA_COVER = "区域覆盖"
    TEXTURE_SYNTHESIS = "纹理合成"
    AI_REPAIR = "AI 智能修复"


def get_algorithms():
    """获取所有可用算法列表"""
    return [algo.value for algo in AlgorithmType]


def inpaint_telea(image: np.ndarray, mask: np.ndarray) -> np.ndarray:
    """
    使用 Telea 算法进行图像修复

    Args:
        image: 输入图像 (BGR格式)
        mask: 二值掩码 (白色区域为需要修复的区域)

    Returns:
        修复后的图像
    """
    if mask is None or not np.any(mask > 0):
        return image.copy()

    result = cv2.inpaint(image, mask, inpaintRadius=3, flags=cv2.INPAINT_TELEA)
    return result


def inpaint_ns(image: np.ndarray, mask: np.ndarray) -> np.ndarray:
    """
    使用 Navier-Stokes 算法进行图像修复

    Args:
        image: 输入图像 (BGR格式)
        mask: 二值掩码 (白色区域为需要修复的区域)

    Returns:
        修复后的图像
    """
    if mask is None or not np.any(mask > 0):
        return image.copy()

    result = cv2.inpaint(image, mask, inpaintRadius=3, flags=cv2.INPAINT_NS)
    return result


def area_cover(image: np.ndarray, mask: np.ndarray,
               method: str = 'average') -> np.ndarray:
    """
    区域覆盖算法 - 用周围像素覆盖水印区域

    Args:
        image: 输入图像 (BGR格式)
        mask: 二值掩码 (白色区域为需要覆盖的区域)
        method: 覆盖方法 ('average', 'median', 'edge')

    Returns:
        处理后的图像
    """
    result = image.copy()

    if mask is None or not np.any(mask > 0):
        return result

    # 膨胀掩码以获得更好的边缘覆盖
    kernel = np.ones((3, 3), np.uint8)
    mask_dilated = cv2.dilate(mask, kernel, iterations=1)

    if method == 'average':
        # 使用周围像素的平均值
        mean_color = cv2.mean(image, cv2.bitwise_not(mask))[:3]
        result[mask_dilated > 0] = mean_color

    elif method == 'median':
        # 使用周围像素的中位数
        surrounding = image[cv2.bitwise_not(mask) > 0]
        if len(surrounding) > 0:
            median_color = np.median(surrounding, axis=0)
            result[mask_dilated > 0] = median_color

    elif method == 'edge':
        # 从边缘向内部扩散填充
        result = _edge_pixel_fill(result, mask_dilated)

    return result


def _edge_pixel_fill(image: np.ndarray, mask: np.ndarray) -> np.ndarray:
    """
    边缘像素填充 - 从水印区域边缘逐步向内填充
    """
    result = image.copy()
    current_mask = mask.copy()

    # 多次迭代从边缘填充
    for _ in range(50):
        if not np.any(current_mask > 0):
            break

        # 找到掩码区域的边缘
        kernel = np.ones((3, 3), np.uint8)
        dilated = cv2.dilate(current_mask, kernel, iterations=1)
        edge = dilated & ~current_mask

        # 对于每个边缘像素，取周围非掩码像素的平均值
        edge_ys, edge_xs = np.where(edge > 0)
        for y, x in zip(edge_ys, edge_xs):
            neighbors = []
            for dy in range(-1, 2):
                for dx in range(-1, 2):
                    ny, nx = y + dy, x + dx
                    if 0 <= ny < image.shape[0] and 0 <= nx < image.shape[1]:
                        if current_mask[ny, nx] == 0:
                            neighbors.append(image[ny, nx])
            if neighbors:
                result[y, x] = np.mean(neighbors, axis=0).astype(np.uint8)

        # 更新掩码 - 移除已填充的区域
        current_mask = cv2.erode(current_mask, kernel, iterations=1)

    return result


def texture_synthesis(image: np.ndarray, mask: np.ndarray,
                      patch_size: int = 7) -> np.ndarray:
    """
    纹理合成算法 - 基于块匹配的纹理合成

    使用 Criminisi 算法的简化版本，从已知区域寻找最佳匹配块来填充水印区域

    Args:
        image: 输入图像 (BGR格式)
        mask: 二值掩码 (白色区域为需要填充的区域)
        patch_size: 块大小 (奇数)

    Returns:
        处理后的图像
    """
    if mask is None or not np.any(mask > 0):
        return image.copy()

    result = image.copy()
    work_mask = mask.copy()
    h, w = image.shape[:2]
    half_patch = patch_size // 2

    # 将水印区域转换为目标区域
    target_pixels = np.where(work_mask > 0)
    target_coords = list(zip(target_pixels[0], target_pixels[1]))

    if not target_coords:
        return result

    # 从外向内逐层填充
    for _ in range(100):
        if not target_coords:
            break

        # 找到最靠近已知区域的像素（简化版：随机顺序）
        np.random.shuffle(target_coords)
        y, x = target_coords[0]

        # 提取待填充块
        y1, y2 = max(0, y - half_patch), min(h, y + half_patch + 1)
        x1, x2 = max(0, x - half_patch), min(w, x + half_patch + 1)

        target_patch = result[y1:y2, x1:x2].copy()
        target_mask = work_mask[y1:y2, x1:x2].copy()

        # 在图像中搜索最佳匹配块（仅从已知区域搜索）
        best_match = None
        best_ssd = float('inf')

        # 采样搜索以提升性能
        step = max(1, min(h, w) // 100)
        for sy in range(0, h - (y2 - y1), step):
            for sx in range(0, w - (x2 - x1), step):
                source_patch = result[sy:sy + y2 - y1, sx:sx + x2 - x1]
                if source_patch.shape != target_patch.shape:
                    continue

                # 只比较已知区域（非掩码部分）
                known_mask = (target_mask == 0)
                if not np.any(known_mask):
                    continue

                diff = (source_patch[known_mask].astype(np.float32) -
                        target_patch[known_mask].astype(np.float32))
                ssd = np.sum(diff ** 2) / np.sum(known_mask)

                if ssd < best_ssd:
                    best_ssd = ssd
                    best_match = source_patch

        # 用最佳匹配填充
        if best_match is not None:
            fill_region = (work_mask[y1:y2, x1:x2] > 0)
            result[y1:y2, x1:x2][fill_region] = best_match[fill_region]
            work_mask[y1:y2, x1:x2][fill_region] = 0

        # 更新目标坐标
        target_pixels = np.where(work_mask > 0)
        target_coords = list(zip(target_pixels[0], target_pixels[1]))

    return result


def ai_repair(image: np.ndarray, mask: np.ndarray,
              strength: float = 0.5) -> np.ndarray:
    """
    AI 智能修复 - 使用 OpenCV 的增强型修复算法

    结合多种修复策略，模拟 AI 修复效果：
    1. 使用更大半径的 Telea 修复作为基础
    2. 使用边缘感知的平滑处理
    3. 自适应颜色匹配

    Args:
        image: 输入图像 (BGR格式)
        mask: 二值掩码 (白色区域为需要修复的区域)
        strength: 修复强度 (0.0~1.0)

    Returns:
        修复后的图像
    """
    if mask is None or not np.any(mask > 0):
        return image.copy()

    radius = max(1, int(strength * 10))

    # 第一步：使用 Telea 修复
    result = cv2.inpaint(image, mask, inpaintRadius=radius,
                         flags=cv2.INPAINT_TELEA)

    # 第二步：使用 NS 修复获得补充结果
    result_ns = cv2.inpaint(image, mask, inpaintRadius=max(1, radius // 2),
                            flags=cv2.INPAINT_NS)

    # 第三步：融合结果
    alpha = 0.6 + 0.3 * strength
    mask_float = (mask > 0).astype(np.float32) * alpha
    mask_float = cv2.GaussianBlur(mask_float, (5, 5), 1.0)

    for c in range(3):
        result[:, :, c] = (result[:, :, c].astype(np.float32) *
                           (1 - mask_float) +
                           result_ns[:, :, c].astype(np.float32) *
                           mask_float).astype(np.uint8)

    # 第四步：在修复区域应用轻微的高斯模糊以平滑过渡
    repair_mask_3ch = cv2.cvtColor(mask, cv2.COLOR_GRAY2BGR)
    repair_area = cv2.GaussianBlur(result, (5, 5), 1.0)
    smooth_alpha = 0.2 * strength
    result = np.where(repair_mask_3ch > 0,
                      (result.astype(np.float32) * (1 - smooth_alpha) +
                       repair_area.astype(np.float32) * smooth_alpha),
                      result.astype(np.float32)).astype(np.uint8)

    return result


# 算法映射表
ALGORITHM_MAP = {
    AlgorithmType.INPAINT_TELEA: inpaint_telea,
    AlgorithmType.INPAINT_NS: inpaint_ns,
    AlgorithmType.AREA_COVER: area_cover,
    AlgorithmType.TEXTURE_SYNTHESIS: texture_synthesis,
    AlgorithmType.AI_REPAIR: ai_repair,
}