"""
图标资源管理模块

职责：
- 集中管理 watermark_remover/icons/ 目录下的 SVG 图标
- 根据当前主题动态着色（避免为每个主题维护两套资源）
- 提供缓存机制，避免重复渲染
- 监听主题变更，自动清空缓存以便重新着色
- 不包含 logo（logo 由 utils.helpers.resource_path 直接管理）

API:
    from watermark_remover.gui.icons import get_icon, IconName

    btn.setIcon(get_icon(IconName.SAVE))
    pm = get_icon_pixmap(IconName.FOLDER, size=64)
"""

import os
from typing import Dict, Tuple, Optional

from PyQt5.QtCore import QSize, Qt
from PyQt5.QtGui import QIcon, QPixmap, QPainter, QColor
from PyQt5.QtSvg import QSvgRenderer
from PyQt5.QtWidgets import QApplication

from ..utils.helpers import resource_path
from .theme import get_manager, ThemePalette


# ----------------------------- 图标名称常量 -----------------------------

class IconName:
    """所有可用图标名称（集中维护，避免字符串散落）"""
    # 通用操作
    FOLDER = "folder"
    OPEN = "open"
    IMAGE = "image"
    SAVE = "save"
    COMPARE = "compare"
    INFO = "info"
    EXPAND = "expand"

    # 缩放与视图
    ZOOM_IN = "zoom-in"
    ZOOM_OUT = "zoom-out"
    ZOOM_FIT = "zoom-fit"

    # 编辑
    SELECT = "select"
    TRASH = "trash"
    UNDO = "undo"
    REDO = "redo"
    RESET = "reset"
    PLAY = "play"
    SYNC = "sync"

    # 批量
    BATCH = "batch"

    # 状态
    CHECK = "check"
    CLOSE = "close"
    CIRCLE_CHECK = "circle-check"

    # 主题
    SUN = "sun"              # 亮色（轮廓版）
    SUN_FILLED = "sun-filled"  # 亮色（选中版，实心）
    MOON = "moon"              # 暗色（轮廓版）
    MOON_FILLED = "moon-filled"  # 暗色（选中版，实心）
    MONITOR = "monitor"        # 跟随系统（轮廓版）
    MONITOR_FILLED = "monitor-filled"  # 跟随系统（选中版，实心）

    # 主题图标映射（方便代码使用）
    THEME_OUTLINE = {
        "sun": SUN,
        "moon": MOON,
        "monitor": MONITOR,
    }
    THEME_FILLED = {
        "sun": SUN_FILLED,
        "moon": MOON_FILLED,
        "monitor": MONITOR_FILLED,
    }


# 图标目录（应用图标，不含 logo）
ICONS_DIR_NAME = "watermark_remover/icons"


# ----------------------------- 主题颜色映射 -----------------------------

# 不同主题下图标使用的颜色（与各主题对比度匹配）
ICON_COLOR_LIGHT = "#5f6368"   # 中灰 - 在亮色背景上清晰
ICON_COLOR_DARK = "#e8eaed"    # 浅灰 - 在暗色背景上清晰


def _icon_color(palette: ThemePalette) -> str:
    """根据主题返回图标颜色"""
    return ICON_COLOR_DARK if palette.is_dark else ICON_COLOR_LIGHT


# ----------------------------- IconManager -----------------------------

class IconManager:
    """图标管理器 - 单例

    缓存策略：
    - 缓存键 = (图标名, 主题名)
    - 主题切换时清空缓存
    """

    _instance = None

    @classmethod
    def instance(cls) -> "IconManager":
        if cls._instance is None:
            cls._instance = IconManager()
        return cls._instance

    def __init__(self):
        # {(icon_name, theme_name): QPixmap}
        self._cache: Dict[Tuple[str, str], QPixmap] = {}
        # 缓存 QIcon （不区分尺寸，避免重复创建）
        self._icon_cache: Dict[Tuple[str, str], QIcon] = {}
        # 已注册到主题变更信号
        self._connected = False

    # ---- 公共 API ----

    def get_pixmap(self, name: str, size: int = 24,
                   palette: Optional[ThemePalette] = None) -> QPixmap:
        """获取指定尺寸的图标 pixmap

        Args:
            name: 图标名（IconName 常量）
            size: 渲染尺寸（像素）
            palette: 可选，指定调色板；默认使用当前主题
        """
        palette = palette or get_manager().palette
        key = (name, palette.name, size)
        if key in self._cache:
            return self._cache[key]

        svg_path = self._resolve_svg_path(name)
        if not svg_path or not os.path.exists(svg_path):
            pixmap = QPixmap(size, size)
            pixmap.fill(Qt.transparent)
            return pixmap

        renderer = QSvgRenderer(svg_path)
        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.transparent)

        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)

        # 第一遍：用纯黑色渲染 SVG
        renderer.render(painter)

        # 第二遍：用 SourceIn 模式覆盖为目标颜色
        # 这样可以保持原 SVG 的透明度信息，仅改变颜色
        painter.setCompositionMode(QPainter.CompositionMode_SourceIn)
        painter.fillRect(pixmap.rect(), QColor(_icon_color(palette)))

        painter.end()

        self._cache[key] = pixmap
        return pixmap

    def get_icon(self, name: str,
                 palette: Optional[ThemePalette] = None,
                 default_size: int = 24) -> QIcon:
        """获取 QIcon（Qt 控件 setIcon 使用）"""
        palette = palette or get_manager().palette
        key = (name, palette.name)
        if key in self._icon_cache:
            return self._icon_cache[key]

        icon = QIcon(self.get_pixmap(name, default_size, palette))
        self._icon_cache[key] = icon
        return icon

    def get_multi_size_icon(self, name: str,
                            sizes=(16, 20, 24, 32, 48, 64)) -> QIcon:
        """获取多尺寸图标（提升显示效果）"""
        palette = get_manager().palette
        key = (name, palette.name, "multi")
        if key in self._icon_cache:
            return self._icon_cache[key]

        icon = QIcon()
        for s in sizes:
            icon.addPixmap(self.get_pixmap(name, s, palette))
        self._icon_cache[key] = icon
        return icon

    def clear_cache(self):
        """清空缓存（主题变更时调用）"""
        self._cache.clear()
        self._icon_cache.clear()

    def connect_theme_signals(self):
        """连接到主题变更信号（首次调用生效）"""
        if self._connected:
            return
        get_manager().theme_changed.connect(lambda *_: self.clear_cache())
        self._connected = True

    # ---- 内部 ----

    @staticmethod
    def _resolve_svg_path(name: str) -> Optional[str]:
        """解析 SVG 文件路径（兼容 PyInstaller 打包）"""
        return resource_path(os.path.join(ICONS_DIR_NAME, f"{name}.svg"))


# ----------------------------- 便捷函数 -----------------------------

_manager: Optional[IconManager] = None


def _ensure_manager() -> IconManager:
    global _manager
    if _manager is None:
        _manager = IconManager.instance()
        _manager.connect_theme_signals()
    return _manager


def get_icon(name: str, palette: Optional[ThemePalette] = None,
             default_size: int = 24) -> QIcon:
    """便捷函数：获取图标 QIcon"""
    return _ensure_manager().get_icon(name, palette, default_size)


def get_pixmap(name: str, size: int = 24,
               palette: Optional[ThemePalette] = None) -> QPixmap:
    """便捷函数：获取图标 pixmap"""
    return _ensure_manager().get_pixmap(name, size, palette)


def get_multi_size_icon(name: str) -> QIcon:
    """便捷函数：获取多尺寸图标"""
    return _ensure_manager().get_multi_size_icon(name)


def clear_cache():
    """清空缓存（主题切换时由 ThemeManager 调用）"""
    if _manager is not None:
        _manager.clear_cache()