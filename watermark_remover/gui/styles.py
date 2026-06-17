"""
全局样式表
"""

STYLESHEET = """
/* 全局样式 */
QMainWindow, QDialog {
    background-color: #f5f5f5;
}

QWidget {
    font-family: "Microsoft YaHei", "Segoe UI", "PingFang SC", sans-serif;
}

/* 菜单栏 */
QMenuBar {
    background-color: #ffffff;
    border-bottom: 1px solid #e0e0e0;
    padding: 2px;
}

QMenuBar::item {
    padding: 6px 12px;
    border-radius: 4px;
}

QMenuBar::item:selected {
    background-color: #e3f2fd;
    color: #1565c0;
}

QMenu {
    background-color: #ffffff;
    border: 1px solid #e0e0e0;
    border-radius: 6px;
    padding: 4px;
}

QMenu::item {
    padding: 8px 32px 8px 16px;
    border-radius: 4px;
}

QMenu::item:selected {
    background-color: #e3f2fd;
    color: #1565c0;
}

/* 按钮 */
QPushButton {
    background-color: #1976d2;
    color: white;
    border: none;
    border-radius: 4px;
    padding: 8px 16px;
    font-size: 13px;
    min-height: 20px;
}

QPushButton:hover {
    background-color: #1565c0;
}

QPushButton:pressed {
    background-color: #0d47a1;
}

QPushButton:disabled {
    background-color: #bdbdbd;
    color: #ffffff;
}

QPushButton#btnSecondary {
    background-color: #ffffff;
    color: #1976d2;
    border: 1px solid #1976d2;
}

QPushButton#btnSecondary:hover {
    background-color: #e3f2fd;
}

QPushButton#btnDanger {
    background-color: #d32f2f;
}

QPushButton#btnDanger:hover {
    background-color: #c62828;
}

QPushButton#btnSuccess {
    background-color: #388e3c;
}

QPushButton#btnSuccess:hover {
    background-color: #2e7d32;
}

/* 工具按钮 */
QToolButton {
    background-color: transparent;
    border: 1px solid transparent;
    border-radius: 4px;
    padding: 6px;
    font-size: 13px;
}

QToolButton:hover {
    background-color: #e3f2fd;
    border-color: #bbdefb;
}

QToolButton:checked {
    background-color: #bbdefb;
    border-color: #1976d2;
}

/* 组合框 */
QComboBox {
    background-color: #ffffff;
    border: 1px solid #bdbdbd;
    border-radius: 4px;
    padding: 6px 12px;
    font-size: 13px;
    min-height: 20px;
}

QComboBox:hover {
    border-color: #1976d2;
}

QComboBox::drop-down {
    border: none;
    width: 24px;
}

QComboBox::down-arrow {
    image: none;
    border-left: 5px solid transparent;
    border-right: 5px solid transparent;
    border-top: 6px solid #666;
    margin-right: 6px;
}

QComboBox QAbstractItemView {
    background-color: #ffffff;
    border: 1px solid #e0e0e0;
    border-radius: 4px;
    selection-background-color: #e3f2fd;
    selection-color: #1565c0;
    padding: 4px;
    outline: none;
}

/* 滑块 */
QSlider::groove:horizontal {
    background: #e0e0e0;
    height: 6px;
    border-radius: 3px;
}

QSlider::handle:horizontal {
    background: #1976d2;
    width: 18px;
    height: 18px;
    margin: -6px 0;
    border-radius: 9px;
}

QSlider::handle:horizontal:hover {
    background: #1565c0;
}

QSlider::sub-page:horizontal {
    background: #1976d2;
    border-radius: 3px;
}

/* 标签 */
QLabel {
    font-size: 13px;
    color: #333333;
}

QLabel#titleLabel {
    font-size: 18px;
    font-weight: bold;
    color: #1565c0;
}

QLabel#statusLabel {
    font-size: 12px;
    color: #666666;
}

QLabel#errorLabel {
    font-size: 12px;
    color: #d32f2f;
}

QLabel#successLabel {
    font-size: 12px;
    color: #388e3c;
}

/* 分组框 */
QGroupBox {
    background-color: #ffffff;
    border: 1px solid #e0e0e0;
    border-radius: 8px;
    margin-top: 12px;
    padding: 16px 12px 12px 12px;
    font-size: 14px;
    font-weight: bold;
}

QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    padding: 4px 12px;
    background-color: #ffffff;
    border: 1px solid #e0e0e0;
    border-radius: 4px;
    color: #1565c0;
}

/* 进度条 */
QProgressBar {
    background-color: #e0e0e0;
    border: none;
    border-radius: 4px;
    text-align: center;
    font-size: 12px;
    height: 20px;
}

QProgressBar::chunk {
    background-color: #1976d2;
    border-radius: 4px;
}

/* 滚动区域 */
QScrollArea {
    border: none;
    background-color: transparent;
}

/* 分割线 */
QFrame#separator {
    background-color: #e0e0e0;
    max-height: 1px;
}

/* 复选框 */
QCheckBox {
    font-size: 13px;
    spacing: 8px;
}

QCheckBox::indicator {
    width: 18px;
    height: 18px;
    border: 2px solid #bdbdbd;
    border-radius: 3px;
}

QCheckBox::indicator:checked {
    background-color: #1976d2;
    border-color: #1976d2;
}

/* 文本编辑 */
QTextEdit, QPlainTextEdit {
    background-color: #ffffff;
    border: 1px solid #bdbdbd;
    border-radius: 4px;
    padding: 6px;
    font-size: 13px;
}

QTextEdit:focus, QPlainTextEdit:focus {
    border-color: #1976d2;
}

/* 列表 */
QListWidget {
    background-color: #ffffff;
    border: 1px solid #e0e0e0;
    border-radius: 4px;
    padding: 4px;
    outline: none;
}

QListWidget::item {
    padding: 8px;
    border-radius: 4px;
}

QListWidget::item:selected {
    background-color: #e3f2fd;
    color: #1565c0;
}

QListWidget::item:hover {
    background-color: #f5f5f5;
}

/* 选项卡 */
QTabWidget::pane {
    background-color: #ffffff;
    border: 1px solid #e0e0e0;
    border-radius: 4px;
    top: -1px;
}

QTabBar::tab {
    background-color: #f5f5f5;
    border: 1px solid #e0e0e0;
    border-bottom: none;
    border-top-left-radius: 4px;
    border-top-right-radius: 4px;
    padding: 8px 20px;
    margin-right: 2px;
    font-size: 13px;
    min-width: 100px;
}

QTabBar::tab:selected {
    background-color: #ffffff;
    color: #1565c0;
    font-weight: bold;
}

QTabBar::tab:hover:!selected {
    background-color: #e3f2fd;
}

/* 微调框 */
QSpinBox, QDoubleSpinBox {
    background-color: #ffffff;
    border: 1px solid #bdbdbd;
    border-radius: 4px;
    padding: 4px 8px;
    font-size: 13px;
    min-height: 20px;
}

QSpinBox:focus, QDoubleSpinBox:focus {
    border-color: #1976d2;
}
"""


def get_style():
    """获取全局样式表"""
    return STYLESHEET