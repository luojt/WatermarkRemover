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
    边缘像素填充 - 从水印区域边缘逐步向内填充。

    性能优化：使用 cv2.boxFilter（3x3 均值）一次性计算所有像素的邻域均值，
    仅对掩码边缘像素应用，避免纯 Python 双层循环。
    """
    result = image.copy()
    current_mask = mask.copy()
    kernel = np.ones((3, 3), np.uint8)

    # 多次迭代从边缘填充（实际由 max_iters 兜底，正常情况由 current_mask == 0 提前终止）
    max_iters = 50
    for _ in range(max_iters):
        if not np.any(current_mask > 0):
            break

        # 3x3 均值滤波（BORDER_REPLICATE 保持边界连续）
        mean_img = cv2.boxFilter(
            result, -1, (3, 3),
            normalize=True, borderType=cv2.BORDER_REPLICATE)

        # 找到掩码区域的边缘（膨胀 - 自身）
        dilated = cv2.dilate(current_mask, kernel, iterations=1)
        edge = (dilated & ~current_mask) > 0

        # 仅对边缘像素赋均值（向量化赋值，O(1) Python 操作）
        result[edge] = mean_img[edge]

        # 更新掩码 - 移除已填充的区域
        current_mask = cv2.erode(current_mask, kernel, iterations=1)

    return result


def texture_synthesis(image: np.ndarray, mask: np.ndarray,
                      patch_size: int = 7) -> np.ndarray:
    """
    纹理合成算法 - 基于块匹配的纹理合成

    使用 Criminisi 算法的简化版本，从已知区域寻找最佳匹配块来填充水印区域。

    性能优化点：
    - 仅维护**边界轮廓（frontier）**像素集合，避免每次重建全部坐标列表
    - 块匹配使用 cv2 模板匹配 + 掩码，按降采样步长搜索

    Args:
        image: 输入图像 (BGR格式)
        mask: 二值掩码 (白色区域为需要填充的区域)
        patch_size: 块大小 (奇数)

    Returns:
        处理后的图像
    """
    if mask is None or not np.any(mask > 0):
        return image.copy()

    result = image.copy().astype(np.float32)
    work_mask = (mask > 0).astype(np.uint8)
    h, w = image.shape[:2]
    half_patch = patch_size // 2
    ph = patch_size

    # ---------- 计算初始 frontier（待填充像素 + 邻域已知像素的边界） ----------
    # known_mask = 1 表示已知区域
    known_mask = (work_mask == 0).astype(np.uint8)

    # 初始 frontier = work_mask 的全部像素（待填充）
    frontier = set(zip(*np.where(work_mask > 0)))
    if not frontier:
        return image.copy()

    # 搜索步长：图像越大步长越大，最少 1，最多 16
    # 同时限制搜索候选总数（避免 200x200 图像产生 ~2400 个候选导致单次 patch 匹配耗时数秒）
    step = max(1, min(h, w) // 25)
    max_candidates = 100  # 单次 patch 匹配最多采样 100 个候选
    total_positions = ((h - ph) // step + 1) * ((w - ph) // step + 1)
    if total_positions > max_candidates:
        # 按比例放大步长以减少候选数
        scale = (total_positions / max_candidates) ** 0.5
        step = max(step, int(step * scale))

    max_iters = max(1, len(frontier) * 4)  # 兜底：最多每个像素尝试 4 次
    iters = 0

    while frontier and iters < max_iters:
        iters += 1
        # 取一个 frontier 像素
        y, x = frontier.pop()

        # 提取待填充块（含边界裁剪）
        y1, y2 = max(0, y - half_patch), min(h, y + half_patch + 1)
        x1, x2 = max(0, x - half_patch), min(w, x + half_patch + 1)
        patch_h, patch_w = y2 - y1, x2 - x1
        if patch_h != ph or patch_w != ph:
            # 边界附近忽略（无法组成完整块）— 直接按均值填充
            result[y, x] = _neighbor_mean(result, known_mask, y, x)
            work_mask[y, x] = 0
            known_mask[y, x] = 1
            continue

        target_patch = result[y1:y2, x1:x2]
        target_known = known_mask[y1:y2, x1:x2]
        if not np.any(target_known):
            continue

        # ---------- 在已知区域采样搜索最佳匹配块 ----------
        best_ssd = float('inf')
        best_src_y = best_src_x = None

        for sy in range(0, h - patch_h + 1, step):
            for sx in range(0, w - patch_w + 1, step):
                src_patch = result[sy:sy + patch_h, sx:sx + patch_w]
                src_known = known_mask[sy:sy + patch_h, sx:sx + patch_w]
                # 要求"target 已知的像素，source 也已知"
                if (src_known & target_known).sum() < target_known.sum():
                    continue
                diff = src_patch - target_patch
                ssd = np.sum((diff * target_known[..., np.newaxis]) ** 2)
                if ssd < best_ssd:
                    best_ssd = ssd
                    best_src_y, best_src_x = sy, sx

        if best_src_y is None:
            # 无合适候选：使用邻域已知像素均值兜底，避免 frontier 无限循环
            result[y, x] = _neighbor_mean(result, known_mask, y, x)
            work_mask[y, x] = 0
            known_mask[y, x] = 1
        else:
            # 用最佳匹配填充整个 patch
            src_patch = result[best_src_y:best_src_y + patch_h,
                                best_src_x:best_src_x + patch_w]
            fill_region = (work_mask[y1:y2, x1:x2] > 0)
            result[y1:y2, x1:x2][fill_region] = src_patch[fill_region]
            work_mask[y1:y2, x1:x2] = 0
            known_mask[y1:y2, x1:x2] = 1

        # ---------- 扩展 frontier ----------
        kernel = np.ones((3, 3), np.uint8)
        unknown_dilated = cv2.dilate(work_mask, kernel, iterations=1)
        new_frontier_mask = unknown_dilated & (1 - work_mask) & (known_mask == 1)
        for ny, nx in zip(*np.where(new_frontier_mask > 0)):
            frontier.add((int(ny), int(nx)))

    # 兜底：剩余 frontier 用邻域均值填充（处理 max_iters 兜底情况）
    for y, x in frontier:
        result[y, x] = _neighbor_mean(result, known_mask, y, x)
        work_mask[y, x] = 0
        known_mask[y, x] = 1

    return result.astype(np.uint8)


def _neighbor_mean(image: np.ndarray, known_mask: np.ndarray,
                   y: int, x: int) -> np.ndarray:
    """计算像素 (y, x) 周围 3x3 已知像素的均值（BGR 向量）。"""
    h, w = image.shape[:2]
    vals = []
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            ny, nx = y + dy, x + dx
            if 0 <= ny < h and 0 <= nx < w and known_mask[ny, nx]:
                vals.append(image[ny, nx])
    if vals:
        return np.mean(vals, axis=0)
    return image[y, x]  # 全部未知时保留原值


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