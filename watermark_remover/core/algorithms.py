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

    参数:
        image: 输入图像 (BGR格式, uint8)
        mask: 二值掩码 (白色区域为需要填充的区域, uint8)
        patch_size: 块大小 (奇数)

    安全性:
        - 大尺寸图像自动降采样（最大 500px）
        - 绝对迭代上限 2000 次
        - 内置 try/except 异常捕获
        - 任何失败时回退为邻域均值填充

    Returns:
        处理后的图像 (uint8)
    """
    # ---------- 输入验证 ----------
    if image is None or image.size == 0:
        return np.zeros((1, 1, 3), dtype=np.uint8)
    if mask is None or not np.any(mask > 0):
        return image.copy()

    h, w = image.shape[:2]

    # ---------- 大尺寸图像保护 ----------
    # 纹理合成是 O(N*M) 算法，超大图像会耗尽内存或冻结 UI
    max_dim = 500
    downscaled = False
    scale = 1.0
    work_img = image
    work_mask = (mask > 0).astype(np.uint8)
    if h > max_dim or w > max_dim:
        scale = min(max_dim / h, max_dim / w)
        new_w = int(w * scale)
        new_h = int(h * scale)
        work_img = cv2.resize(image, (new_w, new_h),
                              interpolation=cv2.INTER_AREA)
        work_mask = cv2.resize((mask > 0).astype(np.uint8) * 255,
                               (new_w, new_h),
                               interpolation=cv2.INTER_NEAREST)
        work_mask = (work_mask > 0).astype(np.uint8)
        h, w = new_h, new_w
        downscaled = True

    try:
        result = work_img.astype(np.float32)
        known_mask = (work_mask == 0).astype(np.uint8)

        # 前置检查：如果 mask 面积过大，直接回退到均值填充
        mask_pixels = int(np.sum(work_mask))
        max_pixels = int(h * w * 0.8)  # mask 超过 80% 图像面积则弃用块匹配
        if mask_pixels > max_pixels or mask_pixels < 1:
            # 用邻域填充直接兜底
            _fill_remaining(result, known_mask, work_mask)
            small_out = result.astype(np.uint8)
            return _composite_output(small_out, image, mask, downscaled, h, w)

        half_patch = patch_size // 2
        ph = patch_size

        # ---------- 构建 frontier ----------
        frontier = set(zip(*np.where(work_mask > 0)))

        # 搜索步长：控制候选总数 ≤ 100
        step = max(1, min(h, w) // 25)
        total_positions = ((h - ph) // step + 1) * ((w - ph) // step + 1)
        max_candidates = 100
        if total_positions > max_candidates:
            scale_step = (total_positions / max_candidates) ** 0.5
            step = max(step, int(step * scale_step))

        # 绝对迭代上限（而不是 len(frontier) * 4，后者可能达数百万）
        max_iters = min(2000, mask_pixels * 2)
        max_iters = max(10, max_iters)
        iters = 0
        frontier_update_counter = 0

        while frontier and iters < max_iters:
            iters += 1
            try:
                y, x = frontier.pop()

                # 跳过已处理的像素
                if work_mask[y, x] == 0:
                    continue

                # 提取待填充块
                y1, y2 = max(0, y - half_patch), min(h, y + half_patch + 1)
                x1, x2 = max(0, x - half_patch), min(w, x + half_patch + 1)
                patch_h, patch_w = y2 - y1, x2 - x1

                if patch_h != ph or patch_w != ph:
                    # 边界处无法构成完整块 → 邻域均值填充
                    _neighbor_fill(result, known_mask, y, x)
                    work_mask[y, x] = 0
                    known_mask[y, x] = 1
                    continue

                target_patch = result[y1:y2, x1:x2]
                target_known = known_mask[y1:y2, x1:x2]
                if not np.any(target_known):
                    continue

                # ---------- 块匹配搜索 ----------
                best_ssd = float('inf')
                best_src_y = best_src_x = None

                for sy in range(0, h - patch_h + 1, step):
                    for sx in range(0, w - patch_w + 1, step):
                        src_known = known_mask[sy:sy + patch_h,
                                                sx:sx + patch_w]
                        # 要求"target 已知的像素，source 也已知"
                        if (src_known & target_known).sum() < target_known.sum():
                            continue
                        src_patch = result[sy:sy + patch_h, sx:sx + patch_w]
                        diff = src_patch - target_patch
                        ssd = np.sum(
                            (diff * target_known[..., np.newaxis]) ** 2)
                        if ssd < best_ssd:
                            best_ssd = ssd
                            best_src_y, best_src_x = sy, sx

                if best_src_y is None:
                    # 无合适候选 → 邻域均值填充单像素
                    _neighbor_fill(result, known_mask, y, x)
                    work_mask[y, x] = 0
                    known_mask[y, x] = 1
                else:
                    # 用最佳匹配填充整个 patch
                    src_patch = result[
                        best_src_y:best_src_y + patch_h,
                        best_src_x:best_src_x + patch_w]
                    fill_region = (work_mask[y1:y2, x1:x2] > 0)
                    if np.any(fill_region):
                        work_mask_slice = work_mask[y1:y2, x1:x2]
                        known_slice = known_mask[y1:y2, x1:x2]
                        result[y1:y2, x1:x2][fill_region] = \
                            src_patch[fill_region]
                        work_mask_slice[fill_region] = 0
                        known_slice[fill_region] = 1

                # ---------- 每 5 次迭代更新一次 frontier ----------
                frontier_update_counter += 1
                if frontier_update_counter >= 5:
                    frontier_update_counter = 0
                    kernel = np.ones((3, 3), np.uint8)
                    unknown_dilated = cv2.dilate(work_mask, kernel,
                                                 iterations=1)
                    new_frontier_mask = unknown_dilated & (1 - work_mask)
                    for ny, nx in zip(*np.where(new_frontier_mask > 0)):
                        frontier.add((int(ny), int(nx)))

            except Exception as e:
                # 单次迭代出错：跳过该像素，继续处理剩余
                if y is not None and x is not None and 0 <= y < h and 0 <= x < w:
                    _neighbor_fill(result, known_mask, y, x)
                    work_mask[y, x] = 0
                    known_mask[y, x] = 1
                continue

        # ----------兜底：处理剩余未填充像素 ----------
        _fill_remaining(result, known_mask, work_mask)

        small_out = result.astype(np.uint8)
        return _composite_output(small_out, image, mask, downscaled, h, w)

    except Exception as e:
        # ---------- 全局异常捕获：任何失败时回退到纯均值填充 ----------
        import logging
        logging.warning("纹理合成发生异常(%s)，回退到邻域均值填充", str(e))
        fallback_img = image.copy()
        fallback_mask = (mask > 0).astype(np.uint8)
        result_fb = fallback_img.astype(np.float32)
        known_fb = (fallback_mask == 0).astype(np.uint8)
        _fill_remaining(result_fb, known_fb, fallback_mask)
        return result_fb.astype(np.uint8)


def _neighbor_fill(image: np.ndarray, known_mask: np.ndarray,
                   y: int, x: int):
    """将像素(y,x)填充为周围3x3已知像素的均值"""
    h, w = image.shape[:2]
    vals = []
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            ny, nx = y + dy, x + dx
            if 0 <= ny < h and 0 <= nx < w and known_mask[ny, nx]:
                vals.append(image[ny, nx])
    if vals:
        image[y, x] = np.mean(vals, axis=0)
    # 无已知邻域时保持原值


def _fill_remaining(result: np.ndarray, known_mask: np.ndarray,
                    work_mask: np.ndarray):
    """用邻域均值填充 work_mask 中剩余的未处理像素

    Args:
        result: 当前结果图像 (float32, 会被就地修改)
        known_mask: 已知区域掩码 (uint8, 会被就地修改)
        work_mask: 待填充掩码 (uint8, 会被就地修改)
    """
    h, w = result.shape[:2]
    frontier = set(zip(*np.where(work_mask > 0)))
    max_iters = min(10000, len(frontier) * 2)
    iters = 0
    while frontier and iters < max_iters:
        iters += 1
        y, x = frontier.pop()
        if work_mask[y, x] == 0:
            continue
        _neighbor_fill(result, known_mask, y, x)
        work_mask[y, x] = 0
        known_mask[y, x] = 1
        # 加入新暴露的边界像素
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                ny, nx = y + dy, x + dx
                if 0 <= ny < h and 0 <= nx < w and work_mask[ny, nx] > 0:
                    frontier.add((ny, nx))
    # 仍然剩余？逐个处理
    for y, x in frontier:
        if work_mask[y, x] > 0:
            _neighbor_fill(result, known_mask, y, x)
            work_mask[y, x] = 0


def _composite_output(small_result: np.ndarray,
                      original_image: np.ndarray,
                      original_mask: np.ndarray,
                      downscaled: bool,
                      small_h: int, small_w: int) -> np.ndarray:
    """将处理结果（可能在小尺寸上运行）合成回原始图像

    防止核心问题：降采样处理后对整个图像升采样，导致非 mask 区也被模糊。

    策略：
    - 非降采样路径：直接返回 small_result（已在原始分辨率上处理）
    - 降采样路径：将 small_result 升采样到原始尺寸后，**仅把 mask 区域**
      从升采样结果中拷贝到原始图像副本上，非 mask 区域保持原始像素
    """
    if not downscaled:
        # 图像未降采样，直接返回（已在原始分辨率上处理完毕）
        return small_result

    h_orig, w_orig = original_image.shape[:2]

    # 1. 将小尺寸处理结果升采样到原始尺寸
    upsampled = cv2.resize(small_result, (w_orig, h_orig),
                           interpolation=cv2.INTER_LINEAR)

    # 2. 从原始图像复制一份，作为底图
    final = original_image.copy()

    # 3. 仅替换 mask 区域像素（mask > 0 的位置）
    #    原始 mask 坐标直接对应到升采样后的结果
    final[original_mask > 0] = upsampled[original_mask > 0]

    return final


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