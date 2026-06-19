"""
全局样式表

为保持向后兼容，本模块的 `STYLESHEET` 常量与 `get_style()` 函数
仍然存在；实际样式生成逻辑已迁移到 `theme.py`，
由 `ThemeManager` 统一管理（支持 Light / Dark / Auto）。

新代码应使用：
    from watermark_remover.gui.theme import get_manager
    app.setStyleSheet(get_manager().stylesheet)
"""

from .theme import get_manager


# 向后兼容的默认亮色主题样式（程序首次启动时使用）
def get_style():
    """获取当前主题的样式表（兼容旧 API，推荐使用 theme.get_manager()）"""
    return get_manager().stylesheet


# 兼容旧代码直接引用 STYLESHEET 的场景
STYLESHEET = get_style()