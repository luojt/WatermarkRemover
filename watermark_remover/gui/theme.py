"""
主题管理模块

负责：
- 定义亮色 / 暗色主题颜色调色板
- 提供 Qt 样式表（QSS）生成
- 监听系统主题变更（Auto 模式）
- 通过 QSettings 持久化用户偏好
- 通过信号通知 UI 刷新
"""

import sys
import platform

from PyQt5.QtCore import QObject, QSettings, pyqtSignal, QEvent
from PyQt5.QtGui import QPalette
from PyQt5.QtWidgets import QApplication


# ----------------------------- 主题枚举 -----------------------------

class ThemeMode:
    """主题模式常量"""
    LIGHT = "light"          # 亮色主题
    DARK = "dark"            # 暗色主题
    AUTO = "auto"            # 跟随系统


class ThemePalette:
    """单个主题的颜色调色板"""

    def __init__(self, *, name, is_dark,
                 window_bg, window_text,
                 base_bg, base_text,             # 输入控件背景 / 文字
                 alternate_bg,
                 panel_bg,                       # GroupBox / Tab 等
                 border, border_light,
                 primary, primary_hover, primary_pressed,
                 selection_bg, selection_text,
                 menu_bg, menu_text,
                 menu_selected_bg, menu_selected_text,
                 disabled_bg, disabled_text,
                 error, success,
                 viewer_bg,                       # 图像查看器背景
                 placeholder_text,
                 info_text,                       # 状态/提示文字
                 muted_text,                      # 弱化文字
                 toolbar_bg,
                 scrollbar_bg, scrollbar_handle,
                 tooltip_bg, tooltip_text):
        self.name = name
        self.is_dark = is_dark
        self.window_bg = window_bg
        self.window_text = window_text
        self.base_bg = base_bg
        self.base_text = base_text
        self.alternate_bg = alternate_bg
        self.panel_bg = panel_bg
        self.border = border
        self.border_light = border_light
        self.primary = primary
        self.primary_hover = primary_hover
        self.primary_pressed = primary_pressed
        self.selection_bg = selection_bg
        self.selection_text = selection_text
        self.menu_bg = menu_bg
        self.menu_text = menu_text
        self.menu_selected_bg = menu_selected_bg
        self.menu_selected_text = menu_selected_text
        self.disabled_bg = disabled_bg
        self.disabled_text = disabled_text
        self.error = error
        self.success = success
        self.viewer_bg = viewer_bg
        self.placeholder_text = placeholder_text
        self.info_text = info_text
        self.muted_text = muted_text
        self.toolbar_bg = toolbar_bg
        self.scrollbar_bg = scrollbar_bg
        self.scrollbar_handle = scrollbar_handle
        self.tooltip_bg = tooltip_bg
        self.tooltip_text = tooltip_text


# ----------------------------- 调色板定义 -----------------------------

LIGHT_PALETTE = ThemePalette(
    name="light",
    is_dark=False,
    window_bg="#f5f5f5",
    window_text="#333333",
    base_bg="#ffffff",
    base_text="#333333",
    alternate_bg="#fafafa",
    panel_bg="#ffffff",
    border="#e0e0e0",
    border_light="#bdbdbd",
    primary="#1976d2",
    primary_hover="#1565c0",
    primary_pressed="#0d47a1",
    selection_bg="#e3f2fd",
    selection_text="#1565c0",
    menu_bg="#ffffff",
    menu_text="#333333",
    menu_selected_bg="#e3f2fd",
    menu_selected_text="#1565c0",
    disabled_bg="#bdbdbd",
    disabled_text="#ffffff",
    error="#d32f2f",
    success="#388e3c",
    viewer_bg="#333333",          # 图像查看器保持深灰，方便凸显图像
    placeholder_text="#666666",
    info_text="#666666",
    muted_text="#999999",
    toolbar_bg="#ffffff",
    scrollbar_bg="#e0e0e0",
    scrollbar_handle="#bdbdbd",
    tooltip_bg="#ffffe1",
    tooltip_text="#333333",
)


DARK_PALETTE = ThemePalette(
    name="dark",
    is_dark=True,
    window_bg="#1e1e1e",
    window_text="#e6e6e6",
    base_bg="#2d2d30",             # 输入框/列表等控件背景（深灰，不是纯黑）
    base_text="#e6e6e6",           # 输入框文字（接近白色但柔和）
    alternate_bg="#252526",
    panel_bg="#252526",
    border="#3f3f46",
    border_light="#555555",
    primary="#4ea3e8",             # 暗色主题使用更亮的蓝色，确保对比度
    primary_hover="#5fb1f0",
    primary_pressed="#3d8bc7",
    selection_bg="#094771",        # VS Code 风格的深蓝选中色
    selection_text="#ffffff",
    menu_bg="#252526",
    menu_text="#e6e6e6",
    menu_selected_bg="#094771",
    menu_selected_text="#ffffff",
    disabled_bg="#3f3f46",
    disabled_text="#888888",
    error="#f48771",
    success="#7ec97e",
    viewer_bg="#1a1a1a",           # 暗色模式下查看器背景更深
    placeholder_text="#9a9a9a",
    info_text="#a0a0a0",
    muted_text="#7a7a7a",
    toolbar_bg="#2d2d30",
    scrollbar_bg="#3f3f46",
    scrollbar_handle="#5a5a5a",
    tooltip_bg="#3f3f46",
    tooltip_text="#e6e6e6",
)


PALETTES = {
    ThemeMode.LIGHT: LIGHT_PALETTE,
    ThemeMode.DARK: DARK_PALETTE,
}


# ----------------------------- 系统主题检测 -----------------------------

def _read_registry_dark_mode() -> bool:
    """通过 Windows 注册表检测系统是否处于深色模式"""
    if platform.system() != "Windows":
        return False
    try:
        import winreg
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize"
        )
        value, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
        return value == 0
    except Exception:
        return False


def _read_macos_dark_mode() -> bool:
    """通过 macOS defaults 命令检测系统深色模式"""
    if platform.system() != "Darwin":
        return False
    try:
        import subprocess
        result = subprocess.run(
            ["defaults", "read", "-g", "AppleInterfaceStyle"],
            capture_output=True, text=True, timeout=2
        )
        return "Dark" in result.stdout
    except Exception:
        return False


def _read_linux_dark_mode() -> bool:
    """通过 GTK / dconf 检测 Linux 桌面环境主题（尽力而为）"""
    if platform.system() != "Linux":
        return False
    # 优先尝试 gsettings（GNOME）
    try:
        import subprocess
        result = subprocess.run(
            ["gsettings", "get", "org.gnome.desktop.interface", "color-scheme"],
            capture_output=True, text=True, timeout=2
        )
        out = result.stdout.strip().lower()
        if "dark" in out:
            return True
        if "light" in out or "default" in out:
            return False
    except Exception:
        pass

    # 备用方案：检查 GTK_THEME 环境变量
    import os
    gtk_theme = os.environ.get("GTK_THEME", "")
    if "dark" in gtk_theme.lower():
        return True
    return False


def detect_system_dark_mode() -> bool:
    """检测当前系统是否使用深色模式"""
    if platform.system() == "Windows":
        return _read_registry_dark_mode()
    elif platform.system() == "Darwin":
        return _read_macos_dark_mode()
    elif platform.system() == "Linux":
        return _read_linux_dark_mode()
    return False


# ----------------------------- QSS 生成 -----------------------------

def build_stylesheet(palette: ThemePalette) -> str:
    """根据调色板生成完整 QSS 样式表"""
    p = palette
    return f"""
/* ============ 全局基础 ============ */
QMainWindow, QDialog {{
    background-color: {p.window_bg};
    color: {p.window_text};
}}

QWidget {{
    font-family: "Microsoft YaHei", "Segoe UI", "PingFang SC", sans-serif;
    color: {p.window_text};
}}

/* ============ 菜单栏 ============ */
QMenuBar {{
    background-color: {p.toolbar_bg};
    color: {p.window_text};
    border-bottom: 1px solid {p.border};
    padding: 2px;
}}

QMenuBar::item {{
    padding: 6px 12px;
    border-radius: 4px;
    background-color: transparent;
    color: {p.window_text};
}}

QMenuBar::item:selected {{
    background-color: {p.selection_bg};
    color: {p.selection_text};
}}

QMenu {{
    background-color: {p.menu_bg};
    color: {p.menu_text};
    border: 1px solid {p.border};
    border-radius: 6px;
    padding: 4px;
}}

QMenu::item {{
    padding: 8px 32px 8px 16px;
    border-radius: 4px;
    color: {p.menu_text};
}}

QMenu::item:selected {{
    background-color: {p.menu_selected_bg};
    color: {p.menu_selected_text};
}}

/* 菜单项选中状态（如主题菜单中的"亮色主题"被选中时） */
QMenu::item:checked {{
    background-color: {p.menu_selected_bg};
    color: {p.menu_selected_text};
    font-weight: bold;
    /* 左侧边框作为选中标记 */
    border-left: 3px solid {p.primary};
    padding-left: 13px;  /* 16 - 3 = 13，保持文字位置不变 */
}}

/* 选中项同时被悬停 - 保持高亮但加深背景 */
QMenu::item:checked:selected {{
    background-color: {p.primary};
    color: white;
}}

QMenu::separator {{
    height: 1px;
    background: {p.border};
    margin: 4px 8px;
}}

/* ============ 按钮 ============ */
QPushButton {{
    background-color: {p.primary};
    color: white;
    border: none;
    border-radius: 4px;
    padding: 8px 16px;
    font-size: 13px;
    min-height: 20px;
}}

QPushButton:hover {{
    background-color: {p.primary_hover};
}}

QPushButton:pressed {{
    background-color: {p.primary_pressed};
}}

QPushButton:disabled {{
    background-color: {p.disabled_bg};
    color: {p.disabled_text};
}}

QPushButton#btnSecondary {{
    background-color: {p.panel_bg};
    color: {p.primary};
    border: 1px solid {p.primary};
}}

QPushButton#btnSecondary:hover {{
    background-color: {p.selection_bg};
}}

QPushButton#btnSecondary:disabled {{
    background-color: {p.disabled_bg};
    color: {p.disabled_text};
    border: 1px solid {p.border};
}}

QPushButton#btnDanger {{
    background-color: {p.error};
    color: white;
}}

QPushButton#btnDanger:hover {{
    background-color: {p.error};
}}

QPushButton#btnDanger:disabled {{
    background-color: {p.disabled_bg};
    color: {p.disabled_text};
}}

QPushButton#btnSuccess {{
    background-color: {p.success};
    color: white;
}}

QPushButton#btnSuccess:hover {{
    background-color: {p.success};
}}

QPushButton#btnSuccess:disabled {{
    background-color: {p.disabled_bg};
    color: {p.disabled_text};
}}

/* ============ 工具按钮 ============ */
QToolButton {{
    background-color: transparent;
    border: 1px solid transparent;
    border-radius: 4px;
    padding: 6px;
    font-size: 13px;
    color: {p.window_text};
}}

QToolButton:hover {{
    background-color: {p.selection_bg};
    border-color: {p.border_light};
    color: {p.selection_text};
}}

QToolButton:checked {{
    background-color: {p.selection_bg};
    border-color: {p.primary};
    color: {p.selection_text};
}}

QToolButton:disabled {{
    color: {p.disabled_text};
    background-color: transparent;
}}

/* ============ 组合框 ============ */
QComboBox {{
    background-color: {p.base_bg};
    color: {p.base_text};
    border: 1px solid {p.border_light};
    border-radius: 4px;
    padding: 6px 12px;
    font-size: 13px;
    min-height: 20px;
}}

QComboBox:hover {{
    border-color: {p.primary};
}}

QComboBox:focus {{
    border-color: {p.primary};
}}

QComboBox:disabled {{
    background-color: {p.disabled_bg};
    color: {p.disabled_text};
}}

QComboBox::drop-down {{
    border: none;
    width: 24px;
}}

QComboBox::down-arrow {{
    image: none;
    border-left: 5px solid transparent;
    border-right: 5px solid transparent;
    border-top: 6px solid {p.muted_text};
    margin-right: 6px;
}}

QComboBox QAbstractItemView {{
    background-color: {p.base_bg};
    color: {p.base_text};
    border: 1px solid {p.border};
    border-radius: 4px;
    selection-background-color: {p.selection_bg};
    selection-color: {p.selection_text};
    padding: 4px;
    outline: none;
}}

/* ============ 滑块 ============ */
QSlider::groove:horizontal {{
    background: {p.border_light};
    height: 6px;
    border-radius: 3px;
}}

QSlider::handle:horizontal {{
    background: {p.primary};
    width: 18px;
    height: 18px;
    margin: -6px 0;
    border-radius: 9px;
}}

QSlider::handle:horizontal:hover {{
    background: {p.primary_hover};
}}

QSlider::handle:horizontal:disabled {{
    background: {p.disabled_bg};
}}

QSlider::sub-page:horizontal {{
    background: {p.primary};
    border-radius: 3px;
}}

QSlider::add-page:horizontal {{
    background: {p.border_light};
    border-radius: 3px;
}}

/* ============ 标签 ============ */
QLabel {{
    font-size: 13px;
    color: {p.window_text};
    background-color: transparent;
}}

QLabel#titleLabel {{
    font-size: 18px;
    font-weight: bold;
    color: {p.primary};
}}

QLabel#statusLabel {{
    font-size: 12px;
    color: {p.info_text};
}}

QLabel#errorLabel {{
    font-size: 12px;
    color: {p.error};
}}

QLabel#successLabel {{
    font-size: 12px;
    color: {p.success};
}}

QLabel#infoLabel {{
    font-size: 12px;
    color: {p.info_text};
}}

QLabel#mutedLabel {{
    font-size: 12px;
    color: {p.muted_text};
}}

QLabel#placeholderLabel {{
    color: {p.placeholder_text};
}}

QLabel#zoomLabel {{
    font-size: 11px;
    color: {p.muted_text};
}}

/* ============ 分组框 ============ */
QGroupBox {{
    background-color: {p.panel_bg};
    border: 1px solid {p.border};
    border-radius: 8px;
    margin-top: 12px;
    padding: 16px 12px 12px 12px;
    font-size: 14px;
    font-weight: bold;
    color: {p.window_text};
}}

QGroupBox::title {{
    subcontrol-origin: margin;
    subcontrol-position: top left;
    padding: 4px 12px;
    background-color: {p.panel_bg};
    border: 1px solid {p.border};
    border-radius: 4px;
    color: {p.primary};
}}

/* ============ 进度条 ============ */
QProgressBar {{
    background-color: {p.border_light};
    border: none;
    border-radius: 4px;
    text-align: center;
    font-size: 12px;
    color: {p.base_text};
    height: 20px;
}}

QProgressBar::chunk {{
    background-color: {p.primary};
    border-radius: 4px;
}}

/* ============ 滚动区域 ============ */
QScrollArea {{
    border: none;
    background-color: transparent;
}}

QScrollBar:vertical {{
    background: {p.scrollbar_bg};
    width: 12px;
    border-radius: 6px;
}}

QScrollBar::handle:vertical {{
    background: {p.scrollbar_handle};
    border-radius: 6px;
    min-height: 24px;
}}

QScrollBar::handle:vertical:hover {{
    background: {p.muted_text};
}}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0;
}}

QScrollBar:horizontal {{
    background: {p.scrollbar_bg};
    height: 12px;
    border-radius: 6px;
}}

QScrollBar::handle:horizontal {{
    background: {p.scrollbar_handle};
    border-radius: 6px;
    min-width: 24px;
}}

QScrollBar::handle:horizontal:hover {{
    background: {p.muted_text};
}}

QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
    width: 0;
}}

/* ============ 分割线 ============ */
QFrame#separator {{
    background-color: {p.border};
    max-height: 1px;
}}

/* ============ 复选框 / 单选 ============ */
QCheckBox, QRadioButton {{
    font-size: 13px;
    color: {p.window_text};
    spacing: 8px;
    background-color: transparent;
}}

QCheckBox:disabled, QRadioButton:disabled {{
    color: {p.disabled_text};
}}

QCheckBox::indicator {{
    width: 18px;
    height: 18px;
    border: 2px solid {p.border_light};
    border-radius: 3px;
    background-color: {p.base_bg};
}}

QCheckBox::indicator:hover {{
    border-color: {p.primary};
}}

QCheckBox::indicator:checked {{
    background-color: {p.primary};
    border-color: {p.primary};
}}

QCheckBox::indicator:disabled {{
    background-color: {p.disabled_bg};
    border-color: {p.disabled_text};
}}

QRadioButton::indicator {{
    width: 18px;
    height: 18px;
    border: 2px solid {p.border_light};
    border-radius: 9px;
    background-color: {p.base_bg};
}}

QRadioButton::indicator:checked {{
    background-color: {p.base_bg};
    border: 6px solid {p.primary};
}}

/* ============ 文本编辑 / 行编辑 ============ */
QTextEdit, QPlainTextEdit, QLineEdit {{
    background-color: {p.base_bg};
    color: {p.base_text};
    border: 1px solid {p.border_light};
    border-radius: 4px;
    padding: 6px;
    font-size: 13px;
    selection-background-color: {p.selection_bg};
    selection-color: {p.selection_text};
}}

QLineEdit {{
    padding: 4px 8px;
    min-height: 20px;
}}

QTextEdit:focus, QPlainTextEdit:focus, QLineEdit:focus {{
    border-color: {p.primary};
}}

QTextEdit:disabled, QPlainTextEdit:disabled, QLineEdit:disabled {{
    background-color: {p.disabled_bg};
    color: {p.disabled_text};
}}

/* ============ 列表 ============ */
QListWidget, QListView, QTreeView, QTableView {{
    background-color: {p.base_bg};
    color: {p.base_text};
    border: 1px solid {p.border};
    border-radius: 4px;
    padding: 4px;
    outline: none;
    selection-background-color: {p.selection_bg};
    selection-color: {p.selection_text};
    alternate-background-color: {p.alternate_bg};
}}

QListWidget::item {{
    padding: 8px;
    border-radius: 4px;
    color: {p.base_text};
}}

QListWidget::item:selected {{
    background-color: {p.selection_bg};
    color: {p.selection_text};
}}

QListWidget::item:hover:!selected {{
    background-color: {p.alternate_bg};
}}

/* ============ 选项卡 ============ */
QTabWidget::pane {{
    background-color: {p.panel_bg};
    border: 1px solid {p.border};
    border-radius: 4px;
    top: -1px;
}}

QTabBar::tab {{
    background-color: {p.alternate_bg};
    color: {p.window_text};
    border: 1px solid {p.border};
    border-bottom: none;
    border-top-left-radius: 4px;
    border-top-right-radius: 4px;
    padding: 8px 20px;
    margin-right: 2px;
    font-size: 13px;
    min-width: 100px;
}}

QTabBar::tab:selected {{
    background-color: {p.panel_bg};
    color: {p.primary};
    font-weight: bold;
}}

QTabBar::tab:hover:!selected {{
    background-color: {p.selection_bg};
    color: {p.selection_text};
}}

/* ============ 微调框 ============ */
QSpinBox, QDoubleSpinBox {{
    background-color: {p.base_bg};
    color: {p.base_text};
    border: 1px solid {p.border_light};
    border-radius: 4px;
    padding: 4px 8px;
    font-size: 13px;
    min-height: 20px;
    selection-background-color: {p.selection_bg};
    selection-color: {p.selection_text};
}}

QSpinBox:focus, QDoubleSpinBox:focus {{
    border-color: {p.primary};
}}

QSpinBox:disabled, QDoubleSpinBox:disabled {{
    background-color: {p.disabled_bg};
    color: {p.disabled_text};
}}

QSpinBox::up-button, QSpinBox::down-button,
QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {{
    background-color: transparent;
    border: none;
    width: 16px;
}}

QSpinBox::up-button:hover, QSpinBox::down-button:hover,
QDoubleSpinBox::up-button:hover, QDoubleSpinBox::down-button:hover {{
    background-color: {p.selection_bg};
}}

/* ============ 状态栏 ============ */
QStatusBar {{
    background-color: {p.toolbar_bg};
    color: {p.window_text};
    border-top: 1px solid {p.border};
}}

QStatusBar::item {{
    border: none;
}}

/* 状态栏主题指示器按钮 */
QToolButton#themeIndicator {{
    background-color: {p.panel_bg};
    color: {p.window_text};
    border: 1px solid {p.border_light};
    border-radius: 4px;
    padding: 2px 8px;
    font-size: 12px;
    font-weight: bold;
}}

QToolButton#themeIndicator:hover {{
    background-color: {p.selection_bg};
    color: {p.selection_text};
    border-color: {p.primary};
}}

QToolButton#themeIndicator:pressed {{
    background-color: {p.primary};
    color: white;
    border-color: {p.primary};
}}

/* ============ 工具提示 ============ */
QToolTip {{
    background-color: {p.tooltip_bg};
    color: {p.tooltip_text};
    border: 1px solid {p.border};
    border-radius: 4px;
    padding: 4px 6px;
    font-size: 12px;
}}
"""


def get_palette(mode: str, system_dark: bool = None) -> ThemePalette:
    """根据主题模式获取调色板

    Args:
        mode: ThemeMode.LIGHT / ThemeMode.DARK / ThemeMode.AUTO
        system_dark: 当 mode == AUTO 时使用；为 None 时自动检测
    """
    if mode == ThemeMode.AUTO:
        if system_dark is None:
            system_dark = detect_system_dark_mode()
        return DARK_PALETTE if system_dark else LIGHT_PALETTE
    return PALETTES.get(mode, LIGHT_PALETTE)


# ----------------------------- 主题管理器 -----------------------------

class ThemeManager(QObject):
    """主题管理器 - 单例

    负责：
    - 加载/保存用户偏好
    - 维护当前主题状态
    - 监听系统主题变更（Auto 模式）
    - 通知 UI 更新
    """

    theme_changed = pyqtSignal(str, object)   # (effective_name, palette) - 调色板变化时
    mode_changed = pyqtSignal(str, object)    # (mode_name, palette) - 模式变化时（即使调色板未变）

    _instance = None

    @classmethod
    def instance(cls) -> "ThemeManager":
        if cls._instance is None:
            cls._instance = ThemeManager()
        return cls._instance

    def __init__(self):
        super().__init__()
        self._mode = ThemeMode.LIGHT
        self._current_palette: ThemePalette = LIGHT_PALETTE
        self._settings = QSettings("WatermarkRemover", "WatermarkRemover")
        self._load_pref()

        # 监听 QApplication 的调色板变更（用于 Auto 模式）
        app = QApplication.instance()
        if app is not None:
            app.installEventFilter(self)

    # ---- 偏好加载 / 保存 ----

    def _load_pref(self):
        saved = self._settings.value("ui/theme_mode", ThemeMode.LIGHT)
        if saved not in (ThemeMode.LIGHT, ThemeMode.DARK, ThemeMode.AUTO):
            saved = ThemeMode.LIGHT
        self.set_mode(saved, emit=False)

    def _save_pref(self):
        self._settings.setValue("ui/theme_mode", self._mode)
        self._settings.sync()

    # ---- 公开 API ----

    @property
    def mode(self) -> str:
        return self._mode

    @property
    def palette(self) -> ThemePalette:
        return self._current_palette

    @property
    def stylesheet(self) -> str:
        return build_stylesheet(self._current_palette)

    def set_mode(self, mode: str, emit: bool = True):
        """设置主题模式

        Args:
            mode: ThemeMode.LIGHT / DARK / AUTO
            emit: 是否触发 theme_changed 信号
        """
        if mode not in (ThemeMode.LIGHT, ThemeMode.DARK, ThemeMode.AUTO):
            mode = ThemeMode.LIGHT
        old_mode = self._mode
        self._mode = mode
        new_palette = get_palette(mode)
        changed = (new_palette.name != self._current_palette.name)
        self._current_palette = new_palette
        self._save_pref()
        if emit:
            if changed:
                self.theme_changed.emit(new_palette.name, new_palette)
            # 无论调色板是否变化，只要模式改变就通知（例如 DARK→AUTO 时模式标签需更新）
            if old_mode != mode or changed:
                self.mode_changed.emit(mode, new_palette)

    def notify_app_palette_changed(self):
        """外部（如系统切换）调用，触发 Auto 模式重新解析"""
        if self._mode != ThemeMode.AUTO:
            return
        new_palette = get_palette(ThemeMode.AUTO)
        if new_palette.name != self._current_palette.name:
            self._current_palette = new_palette
            self.theme_changed.emit(new_palette.name, new_palette)
            self.mode_changed.emit(self._mode, new_palette)

    # ---- 事件过滤：监听 QApplication 调色板变化（系统主题切换） ----

    def eventFilter(self, obj, event):
        if event is not None and event.type() == QEvent.ApplicationPaletteChange:
            # 系统主题变更时通知
            self.notify_app_palette_changed()
        return super().eventFilter(obj, event)


def get_manager() -> ThemeManager:
    """获取全局主题管理器"""
    return ThemeManager.instance()