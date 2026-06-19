"""
主窗口 - 图像去水印工具的图形用户界面

包含功能：
- 文件拖放和选择
- 图像预览和对比
- 水印区域框选
- 去水印算法选择和应用
- 撤销/恢复
- 批量处理
"""

import os
import cv2
import numpy as np
from typing import Optional, List

from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QComboBox, QSlider, QSpinBox,
    QGroupBox, QFileDialog, QMessageBox, QProgressBar,
    QScrollArea, QSplitter, QFrame, QCheckBox,
    QToolBar, QStatusBar, QAction, QActionGroup, QMenu, QToolButton,
    QListWidget, QListWidgetItem, QDialog, QDialogButtonBox,
    QTabWidget, QApplication, QSizePolicy, QGridLayout,
    QDoubleSpinBox, QLineEdit, QRadioButton, QButtonGroup,
    QProgressDialog
)
from PyQt5.QtCore import (
    Qt, QRect, QRectF, QPoint, QPointF, QSize, QTimer, pyqtSignal, QThread,
    QMimeData, QUrl
)
from PyQt5.QtGui import (
    QPixmap, QImage, QPainter, QPen, QColor, QBrush,
    QFont, QIcon, QDragEnterEvent, QDropEvent, QMouseEvent,
    QPaintEvent, QResizeEvent, QPalette, QCursor
)

from ..core.algorithms import AlgorithmType, get_algorithms
from ..core.image_processor import ImageProcessor
from ..utils.helpers import (
    generate_output_path, ensure_output_dir, is_image_file,
    format_file_size, resource_path
)
from .styles import get_style
from .theme import get_manager, ThemeMode, ThemePalette
from .icons import IconName, get_pixmap, get_icon, get_multi_size_icon


def _drop_area_qss(p: ThemePalette) -> str:
    """生成 DropArea 控件的样式表（使用主题调色板）"""
    return f"""
        DropArea {{
            border: 2px dashed {p.border_light};
            border-radius: 12px;
            background-color: {p.alternate_bg};
        }}
        DropArea[hover="true"] {{
            border: 2px dashed {p.primary};
            border-radius: 12px;
            background-color: {p.selection_bg};
        }}
        DropArea QLabel {{
            color: {p.window_text};
            background-color: transparent;
            border: none;
        }}
        DropArea QLabel#mutedLabel {{
            color: {p.muted_text};
        }}
        DropArea QLabel#infoLabel {{
            color: {p.info_text};
        }}
    """


class DropArea(QWidget):
    """拖放区域控件"""

    files_dropped = pyqtSignal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("DropArea")
        self.setAcceptDrops(True)
        self.setMinimumSize(300, 200)
        self.setMaximumHeight(250)
        self._hover = False

        # 设置样式
        self._refresh_style()

        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignCenter)

        self._icon_label = QLabel()
        self._icon_label.setAlignment(Qt.AlignCenter)
        self._icon_label.setStyleSheet("border: none; background: transparent;")
        self._icon_label.setPixmap(get_pixmap(IconName.FOLDER, size=64))
        layout.addWidget(self._icon_label)

        self._text_label = QLabel("拖拽图片到此处\n或点击下方按钮选择文件")
        self._text_label.setAlignment(Qt.AlignCenter)
        self._text_label.setObjectName("infoLabel")
        self._text_label.setStyleSheet("font-size: 14px; border: none; background: transparent;")
        layout.addWidget(self._text_label)

        self._format_label = QLabel("支持 JPG、PNG、BMP、TIFF、WEBP 等格式")
        self._format_label.setAlignment(Qt.AlignCenter)
        self._format_label.setObjectName("mutedLabel")
        self._format_label.setStyleSheet("font-size: 11px; border: none; background: transparent;")
        layout.addWidget(self._format_label)

    def _refresh_style(self):
        p = get_manager().palette
        self.setStyleSheet(_drop_area_qss(p))
        # 刷新图标（主题色已变化）
        if hasattr(self, '_icon_label'):
            self._icon_label.setPixmap(get_pixmap(IconName.FOLDER, size=64))

    def _apply_hover_state(self):
        """刷新 hover 动态属性（QSS 中通过 DropArea[hover="true"] 选择器使用）

        Qt 动态属性必须显式设置并 unpolish/polish 后才会重新匹配样式表。
        """
        self.setProperty("hover", bool(self._hover))
        # 重新 polish 让样式表重新解析
        self.style().unpolish(self)
        self.style().polish(self)

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            self._hover = True
            event.acceptProposedAction()
            self._apply_hover_state()

    def dragLeaveEvent(self, event):
        self._hover = False
        self._apply_hover_state()

    def dropEvent(self, event: QDropEvent):
        self._hover = False
        self._apply_hover_state()

        files = []
        for url in event.mimeData().urls():
            file_path = url.toLocalFile()
            if is_image_file(file_path):
                files.append(file_path)

        if files:
            self.files_dropped.emit(files)
        else:
            QMessageBox.information(self, "提示", "没有找到支持的图片文件。\n支持的格式：JPG、PNG、BMP、TIFF、WEBP 等")


class ImageViewer(QWidget):
    """
    图像查看器控件 - 整合图片显示、缩放、平移和水印区域框选功能

    功能：
    - 图片完整显示，保持原始宽高比
    - 滚轮缩放 / 按钮缩放，以鼠标位置为中心
    - 鼠标拖拽平移（VIEW模式）
    - 矩形框选水印区域（SELECT模式，自动完整显示图片）
    - 状态提示覆盖层
    """

    selection_finished = pyqtSignal(QRect)

    MODE_VIEW = 0     # 查看模式（可平移）
    MODE_SELECT = 1   # 选区模式（可框选）

    def __init__(self, parent=None):
        super().__init__(parent)
        self._pixmap: Optional[QPixmap] = None
        self._mode = self.MODE_SELECT

        # 缩放
        self._scale = 1.0

        # 拖拽平移偏移量（图像左上角在控件中的偏移）
        self._offset = QPointF(0, 0)
        self._is_dragging = False
        self._drag_start = QPointF(0, 0)

        # 选区
        self._is_selecting = False
        self._sel_start: Optional[QPointF] = None
        self._sel_end: Optional[QPointF] = None
        self._selections: List[QRect] = []

        self.setMouseTracking(True)
        self.setMinimumSize(300, 200)
        self._refresh_style()
        self._update_cursor()

    def _update_cursor(self):
        if self._mode == self.MODE_SELECT:
            self.setCursor(QCursor(Qt.CrossCursor))
        else:
            self.setCursor(QCursor(Qt.OpenHandCursor))

    def set_mode(self, mode: int):
        """设置模式：MODE_VIEW=平移查看，MODE_SELECT=框选（自动完整显示）"""
        self._mode = mode
        if mode == self.MODE_SELECT:
            self._auto_fit()
        self._update_cursor()
        self.update()

    def _refresh_style(self):
        """根据当前主题刷新样式"""
        p = get_manager().palette
        self.setStyleSheet(
            f"background-color: {p.viewer_bg}; border-radius: 4px;"
        )

    def apply_theme(self):
        """主题变更时由外部调用，重绘以更新占位文字颜色等"""
        self._refresh_style()
        self.update()

    def set_pixmap(self, pixmap: Optional[QPixmap]):
        """设置显示的图像，自动适配可视区域

        默认会清空已绘制的选区。如果要在更新图像后仍保留选区
        （如去水印后想继续看到水印位置），传入 ``keep_selections=True``。
        """
        self._pixmap = pixmap.copy() if pixmap else None
        self._selections.clear()
        self._auto_fit()
        self.update()

    def update_pixmap(self, pixmap: Optional[QPixmap]):
        """仅更新图像内容，保留选区"""
        self._pixmap = pixmap.copy() if pixmap else None
        self._auto_fit()
        self.update()

    def clear_selections(self):
        """清除所有选区"""
        self._selections.clear()
        self.update()

    def get_selections(self) -> List[QRect]:
        """获取所有选区（图像坐标系）"""
        return self._selections.copy()

    def _auto_fit(self):
        """自动缩放至适合控件大小，完整显示图片"""
        if not self._pixmap or self._pixmap.isNull():
            self._scale = 1.0
            self._offset = QPointF(0, 0)
            return
        if self.width() <= 0 or self.height() <= 0:
            return
        w_scale = self.width() / self._pixmap.width()
        h_scale = self.height() / self._pixmap.height()
        self._scale = min(w_scale, h_scale)
        self._offset = QPointF(0, 0)

    def zoom_in(self):
        """放大一级"""
        self._scale = max(0.05, min(20.0, self._scale * 1.4))
        self.update()

    def zoom_out(self):
        """缩小一级"""
        self._scale = max(0.05, min(20.0, self._scale / 1.4))
        self.update()

    def zoom_fit(self):
        """缩放至适合窗口"""
        self._auto_fit()
        self.update()

    # ----- 坐标变换（均包含 offset） -----

    def _img_pos(self) -> QPointF:
        """图像左上角在控件中的坐标（含offset偏移）"""
        if not self._pixmap:
            return QPointF(0, 0)
        sw = self._pixmap.width() * self._scale
        sh = self._pixmap.height() * self._scale
        cx = (self.width() - sw) / 2.0
        cy = (self.height() - sh) / 2.0
        return QPointF(cx + self._offset.x(), cy + self._offset.y())

    def _img_to_screen(self, p: QPointF) -> QPointF:
        """图像坐标 → 屏幕坐标"""
        tl = self._img_pos()
        return QPointF(p.x() * self._scale + tl.x(),
                       p.y() * self._scale + tl.y())

    def _screen_to_img(self, p: QPointF) -> QPointF:
        """屏幕坐标 → 图像坐标"""
        tl = self._img_pos()
        return QPointF((p.x() - tl.x()) / self._scale,
                       (p.y() - tl.y()) / self._scale)

    def _clamp_img(self, p: QPointF) -> QPointF:
        """将图像坐标限制在图像范围内"""
        if not self._pixmap:
            return p
        return QPointF(
            max(0.0, min(p.x(), self._pixmap.width() - 1)),
            max(0.0, min(p.y(), self._pixmap.height() - 1))
        )

    # ----- 绘制 -----

    def paintEvent(self, event: QPaintEvent):
        """绘制事件"""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)
        painter.setRenderHint(QPainter.Antialiasing)

        p = get_manager().palette
        viewer_bg = QColor(p.viewer_bg)
        painter.fillRect(self.rect(), viewer_bg)

        if self._pixmap and not self._pixmap.isNull():
            pw, ph = self._pixmap.width(), self._pixmap.height()
            tl = self._img_pos()
            sw = pw * self._scale
            sh = ph * self._scale

            # 绘制图片（保持宽高比）
            painter.drawPixmap(QRectF(tl.x(), tl.y(), sw, sh),
                               self._pixmap, QRectF(0, 0, pw, ph))

            # ----- 绘制选区 -----
            for rect in self._selections:
                r = QRectF(rect.x() * self._scale + tl.x(),
                           rect.y() * self._scale + tl.y(),
                           rect.width() * self._scale,
                           rect.height() * self._scale)
                self._paint_selection(painter, r)

            # 绘制正在拖动的选区
            if self._is_selecting and self._sel_start and self._sel_end:
                sx = min(self._sel_start.x(), self._sel_end.x())
                sy = min(self._sel_start.y(), self._sel_end.y())
                ex = max(self._sel_start.x(), self._sel_end.x())
                ey = max(self._sel_start.y(), self._sel_end.y())
                r = QRectF(sx * self._scale + tl.x(),
                           sy * self._scale + tl.y(),
                           (ex - sx) * self._scale,
                           (ey - sy) * self._scale)
                self._paint_selection(painter, r)

            # ----- 状态覆盖层 -----
            mode_text = "框选模式" if self._mode == self.MODE_SELECT else "查看模式"
            info = f"{100.0 * self._scale:.0f}%  {mode_text}"
            painter.setPen(QColor(p.info_text))
            painter.setFont(QFont("Microsoft YaHei", 10))
            painter.drawText(self.rect().adjusted(8, 8, -8, -8),
                             Qt.AlignTop | Qt.AlignLeft, info)
        else:
            painter.setPen(QColor(p.placeholder_text))
            painter.setFont(QFont("Microsoft YaHei", 14))
            painter.drawText(self.rect(), Qt.AlignCenter, "请先加载图片")

    def _paint_selection(self, painter: QPainter, rect: QRectF):
        """绘制选区（使用主题主色，在亮色和暗色主题下都清晰可见）"""
        p = get_manager().palette
        primary = QColor(p.primary)
        # 半透明填充
        fill_color = QColor(primary)
        fill_color.setAlpha(40)
        painter.fillRect(rect, fill_color)
        # 虚线边框
        pen = QPen(primary, 2)
        pen.setDashPattern([6, 3])
        painter.setPen(pen)
        painter.drawRect(rect)
        # 角点（用白色确保在亮色边框上可见）
        painter.setPen(QPen(QColor(255, 255, 255), 1))
        painter.setBrush(QBrush(primary))
        hs = 5
        for corner in [rect.topLeft(), rect.topRight(),
                       rect.bottomLeft(), rect.bottomRight()]:
            painter.drawRect(QRectF(corner.x() - hs, corner.y() - hs,
                                    hs * 2, hs * 2))

    # ----- 鼠标事件 -----

    def mousePressEvent(self, event: QMouseEvent):
        if not self._pixmap or event.button() != Qt.LeftButton:
            return
        if self._mode == self.MODE_SELECT:
            self._is_selecting = True
            self._sel_start = self._clamp_img(
                self._screen_to_img(QPointF(event.pos())))
            self._sel_end = self._sel_start
        else:
            self._is_dragging = True
            self._drag_start = QPointF(event.pos())
            self.setCursor(QCursor(Qt.ClosedHandCursor))

    def mouseMoveEvent(self, event: QMouseEvent):
        if not self._pixmap:
            return
        if self._is_selecting:
            self._sel_end = self._clamp_img(
                self._screen_to_img(QPointF(event.pos())))
            self.update()
        elif self._is_dragging:
            delta = QPointF(event.pos()) - self._drag_start
            self._drag_start = QPointF(event.pos())
            self._offset += delta
            self.update()

    def mouseReleaseEvent(self, event: QMouseEvent):
        if not self._pixmap or event.button() != Qt.LeftButton:
            return
        if self._is_selecting:
            self._is_selecting = False
            if self._sel_start and self._sel_end:
                sx = min(self._sel_start.x(), self._sel_end.x())
                sy = min(self._sel_start.y(), self._sel_end.y())
                ex = max(self._sel_start.x(), self._sel_end.x())
                ey = max(self._sel_start.y(), self._sel_end.y())
                if ex - sx > 3 and ey - sy > 3:
                    rect = QRect(int(sx), int(sy), int(ex - sx), int(ey - sy))
                    self._selections.append(rect)
                    self.selection_finished.emit(rect)
            self._sel_start = None
            self._sel_end = None
            self._update_cursor()
            self.update()
        elif self._is_dragging:
            self._is_dragging = False
            self._update_cursor()

    def wheelEvent(self, event):
        """滚轮缩放 - 以鼠标位置为中心"""
        if not self._pixmap or self._pixmap.isNull():
            return
        factor = 1.2 if event.angleDelta().y() > 0 else 1 / 1.2
        new_scale = max(0.05, min(20.0, self._scale * factor))
        mouse_pos = QPointF(event.pos())
        img_pos = self._screen_to_img(mouse_pos)
        self._scale = new_scale
        new_screen = self._img_to_screen(img_pos)
        self._offset += (mouse_pos - new_screen)
        self.update()

    def resizeEvent(self, event: QResizeEvent):
        old_w = event.oldSize().width()
        super().resizeEvent(event)
        if self._pixmap and not self._pixmap.isNull() and old_w > 0:
            if abs(self._offset.x()) < 1 and abs(self._offset.y()) < 1:
                fs = min(self.width() / self._pixmap.width(),
                         self.height() / self._pixmap.height())
                if abs(self._scale - fs) > 0.01:
                    self._scale = fs
        self.update()

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Delete, Qt.Key_Backspace):
            if self._selections:
                self._selections.pop()
                self.update()
        elif event.key() == Qt.Key_Escape:
            self._is_selecting = False
            self._sel_start = self._sel_end = None
            self.update()


class PanZoomLabel(QWidget):
    """
    可平移缩放的可视区域控件 - 专为对比预览设计

    功能：
    - 自动完整显示图片，保持原始宽高比
    - 鼠标拖拽平移
    - 滚轮缩放（以鼠标位置为中心）
    - 状态覆盖层（缩放比例）
    - 支持外部 set_scale/pan_by 用于同步控制
    """

    # 用于同步控制的信号
    scale_changed = pyqtSignal(float, object)   # (scale, source_widget)
    pan_changed = pyqtSignal(float, float, object)  # (dx_ratio, dy_ratio, source)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._pixmap: Optional[QPixmap] = None
        self._placeholder_text = ""

        # 缩放与偏移（图像坐标系中的逻辑偏移量，用于裁剪显示）
        self._scale = 1.0
        self._offset = QPointF(0, 0)

        # 拖拽状态
        self._is_dragging = False
        self._drag_start = QPointF(0, 0)

        self.setMouseTracking(True)
        self.setCursor(QCursor(Qt.OpenHandCursor))
        self.setMinimumSize(200, 150)
        self._refresh_style()

    # ---- 公共接口 ----

    def set_pixmap(self, pixmap: QPixmap):
        self._pixmap = pixmap.copy() if pixmap else None
        self._auto_fit()
        self._offset = QPointF(0, 0)
        self.update()

    def set_placeholder(self, text: str):
        self._placeholder_text = text

    @property
    def scale(self) -> float:
        return self._scale

    @property
    def current_pixmap(self) -> Optional[QPixmap]:
        """获取当前显示的图像"""
        return self._pixmap

    @property
    def is_fit(self) -> bool:
        """是否处于完整显示状态（即缩放比为 auto_fit 值）"""
        if not self._pixmap:
            return True
        fit = min(self.width() / self._pixmap.width(),
                  self.height() / self._pixmap.height())
        return abs(self._scale - fit) < 0.01 and abs(self._offset.x()) < 1 and abs(self._offset.y()) < 1

    def clear(self):
        self._pixmap = None
        self._offset = QPointF(0, 0)
        self._scale = 1.0
        self.update()

    def _refresh_style(self):
        """根据当前主题刷新样式"""
        p = get_manager().palette
        self.setStyleSheet(
            f"background-color: {p.viewer_bg}; border-radius: 4px;"
        )

    def apply_theme(self):
        """主题变更时由外部调用"""
        self._refresh_style()
        self.update()

    def reset_view(self):
        """重置为完整视图"""
        self._auto_fit()
        self._offset = QPointF(0, 0)
        self.update()

    def set_scale(self, scale: float, source=None):
        """外部设置缩放比例（以控件中心为中心）"""
        self._scale = max(0.05, min(20.0, scale))
        self.update()
        self.scale_changed.emit(self._scale, source or self)

    def pan_by(self, dx_ratio: float, dy_ratio: float, source=None):
        """外部设置平移偏移（以图像尺寸比例）"""
        if self._pixmap:
            self._offset += QPointF(dx_ratio * self._pixmap.width(),
                                    dy_ratio * self._pixmap.height())
            self.update()
            self.pan_changed.emit(dx_ratio, dy_ratio, source or self)

    # ---- 内部坐标 ----

    def _auto_fit(self):
        if not self._pixmap or self._pixmap.isNull():
            self._scale = 1.0
            return
        if self.width() <= 0 or self.height() <= 0:
            return
        self._scale = min(self.width() / self._pixmap.width(),
                          self.height() / self._pixmap.height())

    def _img_pos(self) -> QPointF:
        """图像左上角在控件中的坐标"""
        if not self._pixmap:
            return QPointF(0, 0)
        sw = self._pixmap.width() * self._scale
        sh = self._pixmap.height() * self._scale
        cx = (self.width() - sw) / 2.0 + self._offset.x()
        cy = (self.height() - sh) / 2.0 + self._offset.y()
        return QPointF(cx, cy)

    def _screen_to_img(self, p: QPointF) -> QPointF:
        tl = self._img_pos()
        return QPointF((p.x() - tl.x()) / self._scale,
                       (p.y() - tl.y()) / self._scale)

    def _img_to_screen(self, p: QPointF) -> QPointF:
        tl = self._img_pos()
        return QPointF(p.x() * self._scale + tl.x(),
                       p.y() * self._scale + tl.y())

    # ---- 事件 ----

    def resizeEvent(self, event: QResizeEvent):
        old_w = event.oldSize().width()
        super().resizeEvent(event)
        if self._pixmap and not self._pixmap.isNull() and old_w > 0:
            if self.is_fit:
                self._auto_fit()
        self.update()

    def paintEvent(self, event: QPaintEvent):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)

        p = get_manager().palette
        viewer_bg = QColor(p.viewer_bg)
        painter.fillRect(self.rect(), viewer_bg)

        if self._pixmap and not self._pixmap.isNull():
            pw, ph = self._pixmap.width(), self._pixmap.height()
            tl = self._img_pos()
            sw, sh = pw * self._scale, ph * self._scale

            # 完整绘制（含偏移裁剪）
            painter.drawPixmap(QRectF(tl.x(), tl.y(), sw, sh),
                               self._pixmap, QRectF(0, 0, pw, ph))

            # 缩放比例覆盖层
            info = f"{100.0 * self._scale:.0f}%"
            painter.setPen(QColor(p.info_text))
            painter.setFont(QFont("Microsoft YaHei", 10))
            painter.drawText(self.rect().adjusted(6, 6, -6, -6),
                             Qt.AlignTop | Qt.AlignLeft, info)
        elif self._placeholder_text:
            painter.setPen(QColor(p.placeholder_text))
            painter.setFont(QFont("Microsoft YaHei", 14))
            painter.drawText(self.rect(), Qt.AlignCenter, self._placeholder_text)

    def mousePressEvent(self, event: QMouseEvent):
        if not self._pixmap or event.button() != Qt.LeftButton:
            return
        self._is_dragging = True
        self._drag_start = QPointF(event.pos())
        self.setCursor(QCursor(Qt.ClosedHandCursor))

    def mouseMoveEvent(self, event: QMouseEvent):
        if not self._pixmap or not self._is_dragging:
            return
        delta = QPointF(event.pos()) - self._drag_start
        self._drag_start = QPointF(event.pos())
        self._offset += delta
        self.update()

    def mouseReleaseEvent(self, event: QMouseEvent):
        if event.button() == Qt.LeftButton and self._is_dragging:
            self._is_dragging = False
            self.setCursor(QCursor(Qt.OpenHandCursor))

    def wheelEvent(self, event):
        if not self._pixmap:
            return
        factor = 1.2 if event.angleDelta().y() > 0 else 1 / 1.2
        new_scale = max(0.05, min(20.0, self._scale * factor))

        # 以鼠标位置为中心缩放
        mouse_pos = QPointF(event.pos())
        img_pos = self._screen_to_img(mouse_pos)
        self._scale = new_scale
        new_screen = self._img_to_screen(img_pos)
        self._offset += (mouse_pos - new_screen)
        self.update()
        self.scale_changed.emit(self._scale, self)


class ImagePreviewDialog(QDialog):
    """全尺寸图片预览对话框 - 支持拖拽平移和滚轮缩放"""

    def __init__(self, pixmap: QPixmap, title: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"预览: {title}")
        self.setMinimumSize(800, 600)
        self.resize(1000, 750)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(4)

        # 提示
        hint = QLabel("滚轮缩放 · 拖拽平移")
        hint.setObjectName("mutedLabel")
        hint.setStyleSheet("font-size: 11px;")
        layout.addWidget(hint)

        # 全尺寸 PanZoomLabel
        self._viewer = PanZoomLabel()
        self._viewer.set_pixmap(pixmap)
        layout.addWidget(self._viewer, 1)

        # 底部缩放信息 + 关闭
        bottom = QHBoxLayout()
        self._zoom_label = QLabel("100%")
        self._zoom_label.setObjectName("zoomLabel")
        self._zoom_label.setStyleSheet("font-size: 11px;")
        bottom.addWidget(self._zoom_label)

        self._viewer.scale_changed.connect(
            lambda s, _: self._zoom_label.setText(f"{100.0 * s:.0f}%"))

        bottom.addStretch()
        reset_btn = QPushButton("重置视图")
        reset_btn.setObjectName("btnSecondary")
        reset_btn.setMaximumHeight(28)
        reset_btn.clicked.connect(self._viewer.reset_view)
        bottom.addWidget(reset_btn)

        close_btn = QPushButton("关闭")
        close_btn.setMaximumHeight(28)
        close_btn.clicked.connect(self.accept)
        bottom.addWidget(close_btn)

        layout.addLayout(bottom)


class CompareView(QWidget):
    """
    对比预览视图 - 左右并排显示原图和结果

    功能：
    - 独立缩放/平移（滚轮 + 拖拽）
    - 同步模式：一键同步左右两侧的缩放和平移
    - 独立重置视图
    - 缩放比例显示
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._sync_enabled = False
        self._updating_sync = False
        self.setVisible(False)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(4)

        # ---- 顶部工具栏 ----
        toolbar = QHBoxLayout()
        toolbar.setSpacing(6)

        self._sync_btn = QToolButton()
        self._sync_btn.setCheckable(True)
        self._sync_btn.setChecked(False)
        self._sync_btn.setIcon(get_icon(IconName.SYNC))
        self._sync_btn.setIconSize(QSize(16, 16))
        self._sync_btn.setText(" 同步")
        self._sync_btn.setToolTip("同步缩放和平移操作")
        self._sync_btn.setObjectName("syncBtn")
        self._refresh_sync_style()
        self._sync_btn.toggled.connect(self._on_sync_toggled)
        toolbar.addWidget(self._sync_btn)

        self._reset_all_btn = QToolButton()
        self._reset_all_btn.setIcon(get_icon(IconName.RESET))
        self._reset_all_btn.setIconSize(QSize(16, 16))
        self._reset_all_btn.setText(" 重置")
        self._reset_all_btn.setToolTip("重置两侧视图")
        self._reset_all_btn.setObjectName("resetAllBtn")
        self._refresh_reset_all_style()
        self._reset_all_btn.clicked.connect(self._reset_all)
        toolbar.addWidget(self._reset_all_btn)

        toolbar.addStretch()

        hint = QLabel("滚轮缩放 · 拖拽平移")
        hint.setObjectName("mutedLabel")
        hint.setStyleSheet("font-size: 11px;")
        toolbar.addWidget(hint)

        main_layout.addLayout(toolbar)

        # ---- 左右并排视图 ----
        view_layout = QHBoxLayout()
        view_layout.setSpacing(6)

        # 处理前
        orig_group = QGroupBox("处理前")
        orig_group.setObjectName("compactGroupBox")
        orig_layout = QVBoxLayout(orig_group)
        orig_layout.setContentsMargins(4, 16, 4, 4)
        orig_layout.setSpacing(4)

        self._orig_view = PanZoomLabel()
        self._orig_view.set_placeholder("处理前\n(原始图像)")
        orig_layout.addWidget(self._orig_view, 1)

        orig_btns = QHBoxLayout()
        orig_btns.setSpacing(4)
        orig_zoom_label = QLabel("100%")
        orig_zoom_label.setObjectName("zoomLabel")
        orig_zoom_label.setStyleSheet("font-size:10px;")
        orig_btns.addWidget(orig_zoom_label)
        orig_btns.addStretch()
        orig_full_btn = QPushButton("放大查看")
        orig_full_btn.setObjectName("btnSecondary")
        orig_full_btn.setFixedSize(64, 22)
        orig_full_btn.setStyleSheet("font-size:10px; padding:0 4px;")
        orig_full_btn.clicked.connect(
            lambda: self._open_preview_dialog(self._orig_view, "处理前"))
        orig_btns.addWidget(orig_full_btn)
        orig_reset = QToolButton()
        orig_reset.setIcon(get_icon(IconName.RESET))
        orig_reset.setIconSize(QSize(14, 14))
        orig_reset.setToolTip("重置此视图")
        orig_reset.setFixedSize(28, 22)
        orig_reset.clicked.connect(lambda: self._orig_view.reset_view())
        orig_btns.addWidget(orig_reset)
        orig_layout.addLayout(orig_btns)

        view_layout.addWidget(orig_group, 1)

        # 处理后
        rst_group = QGroupBox("处理后")
        rst_group.setObjectName("compactGroupBox")
        rst_layout = QVBoxLayout(rst_group)
        rst_layout.setContentsMargins(4, 16, 4, 4)
        rst_layout.setSpacing(4)

        self._rst_view = PanZoomLabel()
        self._rst_view.set_placeholder("处理后\n(等待处理结果)")
        rst_layout.addWidget(self._rst_view, 1)

        rst_btns = QHBoxLayout()
        rst_btns.setSpacing(4)
        rst_zoom_label = QLabel("100%")
        rst_zoom_label.setObjectName("zoomLabel")
        rst_zoom_label.setStyleSheet("font-size:10px;")
        rst_btns.addWidget(rst_zoom_label)
        rst_btns.addStretch()
        rst_full_btn = QPushButton("放大查看")
        rst_full_btn.setObjectName("btnSecondary")
        rst_full_btn.setFixedSize(64, 22)
        rst_full_btn.setStyleSheet("font-size:10px; padding:0 4px;")
        rst_full_btn.clicked.connect(
            lambda: self._open_preview_dialog(self._rst_view, "处理后"))
        rst_btns.addWidget(rst_full_btn)
        rst_reset = QToolButton()
        rst_reset.setIcon(get_icon(IconName.RESET))
        rst_reset.setIconSize(QSize(14, 14))
        rst_reset.setToolTip("重置此视图")
        rst_reset.setFixedSize(28, 22)
        rst_reset.clicked.connect(lambda: self._rst_view.reset_view())
        rst_btns.addWidget(rst_reset)
        rst_layout.addLayout(rst_btns)

        view_layout.addWidget(rst_group, 1)

        main_layout.addLayout(view_layout, 1)

        # ---- 连接缩放比例更新 ----
        self._orig_view.scale_changed.connect(
            lambda s, _: orig_zoom_label.setText(f"{100.0 * s:.0f}%"))
        self._rst_view.scale_changed.connect(
            lambda s, _: rst_zoom_label.setText(f"{100.0 * s:.0f}%"))

        # ---- 连接同步信号 ----
        self._orig_view.scale_changed.connect(self._on_scale_changed)
        self._rst_view.scale_changed.connect(self._on_scale_changed)

    def set_images(self, original: QPixmap, result: QPixmap):
        self._orig_view.set_pixmap(original)
        self._rst_view.set_pixmap(result)
        self._update_zoom_labels()

    def clear(self):
        self._orig_view.clear()
        self._rst_view.clear()

    def _update_zoom_labels(self):
        """更新缩放比例标签（通过信号自动处理，此为兜底）"""
        for child in self.findChildren(QLabel):
            pass  # labels are updated via scale_changed signal

    def _open_preview_dialog(self, viewer: PanZoomLabel, title: str):
        """打开全尺寸预览对话框"""
        pixmap = viewer.current_pixmap
        if not pixmap:
            return
        dialog = ImagePreviewDialog(pixmap, title, self.window())
        dialog.exec_()

    # ---- 同步控制 ----

    def _on_sync_toggled(self, checked: bool):
        self._sync_enabled = checked
        if checked:
            # 同步到当前比例
            self._sync_views(self._orig_view, self._rst_view)

    def _on_scale_changed(self, scale: float, source: PanZoomLabel):
        if not self._sync_enabled or self._updating_sync:
            return
        self._updating_sync = True
        target = self._rst_view if source is self._orig_view else self._orig_view
        target.set_scale(scale)
        self._updating_sync = False

    def _sync_views(self, source: PanZoomLabel, target: PanZoomLabel):
        """将 source 的缩放状态同步到 target"""
        target.set_scale(source.scale)

    def _reset_all(self):
        self._orig_view.reset_view()
        self._rst_view.reset_view()

    # ---- 主题适配 ----

    def _refresh_sync_style(self):
        """刷新同步按钮样式（使用主题色）"""
        p = get_manager().palette
        self._sync_btn.setStyleSheet(
            f"QToolButton {{ padding: 4px 10px; border: 1px solid {p.border_light};"
            f" border-radius: 4px; font-size: 11px; color: {p.window_text}; }}"
            f"QToolButton:checked {{ background-color: {p.primary}; color: white;"
            f" border-color: {p.primary}; }}"
            f"QToolButton:hover:!checked {{ background-color: {p.selection_bg};"
            f" color: {p.selection_text}; }}"
        )

    def _refresh_reset_all_style(self):
        """刷新重置按钮样式"""
        p = get_manager().palette
        self._reset_all_btn.setStyleSheet(
            f"QToolButton {{ padding: 4px 10px; border-radius: 4px; font-size: 11px;"
            f" color: {p.window_text}; }}"
            f"QToolButton:hover {{ background-color: {p.selection_bg};"
            f" color: {p.selection_text}; }}"
        )

    def apply_theme(self):
        """主题变更时调用，刷新子控件样式"""
        self._refresh_sync_style()
        self._refresh_reset_all_style()
        # 刷新图标
        if hasattr(self, '_sync_btn'):
            self._sync_btn.setIcon(get_icon(IconName.SYNC))
        if hasattr(self, '_reset_all_btn'):
            self._reset_all_btn.setIcon(get_icon(IconName.RESET))
        # 刷新左右两侧的重置按钮
        self._refresh_reset_buttons()
        self._orig_view.apply_theme()
        self._rst_view.apply_theme()
        # 触发 GroupBox 标题样式刷新（重新应用全局样式即可）

    def _refresh_reset_buttons(self):
        """刷新两个 "重置" 工具按钮的图标"""
        for btn in self.findChildren(QToolButton):
            if btn.toolTip() == "重置此视图":
                btn.setIcon(get_icon(IconName.RESET))


class BatchProcessor(QThread):
    """批量处理线程"""

    progress_updated = pyqtSignal(int, int, str)
    processing_complete = pyqtSignal(int, int)  # success, failed
    file_processed = pyqtSignal(str, bool)

    def __init__(self, files: List[str], output_dir: str,
                 algorithm: AlgorithmType, mask: np.ndarray = None,
                 quality: int = 95, suffix: str = "_processed",
                 include_date: bool = False, **kwargs):
        super().__init__()
        self._files = files
        self._output_dir = output_dir
        self._algorithm = algorithm
        self._mask = mask
        self._quality = quality
        self._suffix = suffix
        self._include_date = include_date
        self._kwargs = kwargs
        self._is_running = True

    def run(self):
        """运行批量处理"""
        total = len(self._files)
        success = 0
        failed = 0

        processor = ImageProcessor()

        for i, file_path in enumerate(self._files):
            if not self._is_running:
                break

            self.progress_updated.emit(i + 1, total,
                                       os.path.basename(file_path))

            try:
                # 加载图像
                img = cv2.imread(file_path, cv2.IMREAD_COLOR)
                if img is None:
                    failed += 1
                    self.file_processed.emit(file_path, False)
                    continue

                # 应用算法
                mask = self._mask
                output_path = generate_output_path(
                    self._output_dir, file_path,
                    self._suffix, self._include_date)

                if mask is not None:
                    result = processor.apply_algorithm_to_image(
                        img, mask, self._algorithm, **self._kwargs)
                else:
                    result = img.copy()

                # 保存（复用 ImageProcessor.save_image 以保证 PNG/JPEG 压缩参数一致）
                if not ImageProcessor.save_image(result, output_path, self._quality):
                    raise IOError(f"cv2.imwrite 未能生成文件: {output_path}")

                if os.path.exists(output_path):
                    success += 1
                    self.file_processed.emit(file_path, True)
                else:
                    failed += 1
                    self.file_processed.emit(file_path, False)

            except Exception as e:
                failed += 1
                self.file_processed.emit(file_path, False)
                print(f"处理失败 {file_path}: {e}")

        self.processing_complete.emit(success, failed)

    def stop(self):
        """停止处理"""
        self._is_running = False


class BatchDialog(QDialog):
    """批量处理对话框"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("批量处理")
        self.setMinimumSize(600, 400)
        self._files: List[str] = []
        self._processor: Optional[BatchProcessor] = None
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        # 文件列表
        file_group = QGroupBox("待处理文件")
        file_layout = QVBoxLayout(file_group)

        btn_layout = QHBoxLayout()
        self._add_btn = QPushButton("添加文件")
        self._add_btn.clicked.connect(self._add_files)
        self._clear_btn = QPushButton("清空列表")
        self._clear_btn.clicked.connect(self._clear_files)
        btn_layout.addWidget(self._add_btn)
        btn_layout.addWidget(self._clear_btn)
        btn_layout.addStretch()
        file_layout.addLayout(btn_layout)

        self._file_list = QListWidget()
        self._file_list.setAlternatingRowColors(True)
        file_layout.addWidget(self._file_list)

        layout.addWidget(file_group)

        # 输出设置
        output_group = QGroupBox("输出设置")
        output_layout = QGridLayout(output_group)

        output_layout.addWidget(QLabel("输出目录:"), 0, 0)
        self._output_dir_edit = QLineEdit()
        output_layout.addWidget(self._output_dir_edit, 0, 1)
        self._browse_btn = QPushButton("浏览...")
        self._browse_btn.clicked.connect(self._browse_output)
        output_layout.addWidget(self._browse_btn, 0, 2)

        output_layout.addWidget(QLabel("图片质量:"), 1, 0)
        self._quality_spin = QSpinBox()
        self._quality_spin.setRange(1, 100)
        self._quality_spin.setValue(95)
        self._quality_spin.setSuffix("%")
        output_layout.addWidget(self._quality_spin, 1, 1)

        layout.addWidget(output_group)

        # 进度
        progress_group = QGroupBox("处理进度")
        progress_layout = QVBoxLayout(progress_group)
        self._progress_bar = QProgressBar()
        self._progress_bar.setVisible(False)
        progress_layout.addWidget(self._progress_bar)
        self._status_label = QLabel("就绪")
        progress_layout.addWidget(self._status_label)
        layout.addWidget(progress_group)

        # 按钮
        btn_layout = QHBoxLayout()
        self._start_btn = QPushButton("开始处理")
        self._start_btn.clicked.connect(self._start_processing)
        self._start_btn.setEnabled(False)
        self._close_btn = QPushButton("关闭")
        self._close_btn.clicked.connect(self.close)
        btn_layout.addStretch()
        btn_layout.addWidget(self._start_btn)
        btn_layout.addWidget(self._close_btn)
        layout.addLayout(btn_layout)

    def set_files(self, files: List[str]):
        """设置文件列表"""
        self._files = files
        self._file_list.clear()
        for f in files:
            item = QListWidgetItem(f"{os.path.basename(f)}  ({os.path.dirname(f)})")
            item.setToolTip(f)
            self._file_list.addItem(item)
        self._start_btn.setEnabled(len(files) > 0)

    def _add_files(self):
        files, _ = QFileDialog.getOpenFileNames(
            self, "选择图片文件",
            "",
            "图片文件 (*.jpg *.jpeg *.png *.bmp *.tiff *.tif *.webp)"
        )
        if files:
            self._files.extend(files)
            for f in files:
                item = QListWidgetItem(f"{os.path.basename(f)}  ({os.path.dirname(f)})")
                item.setToolTip(f)
                self._file_list.addItem(item)
            self._start_btn.setEnabled(len(self._files) > 0)

    def _clear_files(self):
        self._files.clear()
        self._file_list.clear()
        self._start_btn.setEnabled(False)

    def _browse_output(self):
        directory = QFileDialog.getExistingDirectory(self, "选择输出目录")
        if directory:
            self._output_dir_edit.setText(directory)

    def _start_processing(self):
        if not self._files:
            QMessageBox.warning(self, "警告", "请添加待处理的文件")
            return

        output_dir = self._output_dir_edit.text().strip()
        if not output_dir:
            output_dir = os.path.dirname(self._files[0])
            self._output_dir_edit.setText(output_dir)

        if not os.path.exists(output_dir):
            try:
                os.makedirs(output_dir)
            except Exception as e:
                QMessageBox.critical(self, "错误", f"无法创建输出目录: {e}")
                return

        # 禁用按钮
        self._start_btn.setEnabled(False)
        self._add_btn.setEnabled(False)
        self._clear_btn.setEnabled(False)
        self._progress_bar.setVisible(True)
        self._progress_bar.setValue(0)

        # 获取主窗口的算法和掩码设置
        main_window = self.parent()
        algorithm = AlgorithmType.INPAINT_TELEA
        mask = None
        quality = self._quality_spin.value()
        kwargs = {}

        if hasattr(main_window, '_processor'):
            proc = main_window._processor
            mask = proc.mask
        if hasattr(main_window, '_algorithm_combo'):
            algo_text = main_window._algorithm_combo.currentText()
            for algo in AlgorithmType:
                if algo.value == algo_text:
                    algorithm = algo
                    break

        # 透传算法特定参数
        if algorithm == AlgorithmType.AREA_COVER and hasattr(
                main_window, '_cover_method_combo'):
            kwargs['method'] = main_window._cover_method_combo.currentText()
        elif algorithm == AlgorithmType.AI_REPAIR and hasattr(
                main_window, '_strength_spin'):
            kwargs['strength'] = main_window._strength_spin.value()

        # 文件命名配置（与主界面保存一致）
        suffix = "_processed"
        include_date = False
        if hasattr(main_window, '_suffix_edit'):
            text = main_window._suffix_edit.text().strip()
            if text:
                suffix = text
        if hasattr(main_window, '_include_date_cb'):
            include_date = main_window._include_date_cb.isChecked()

        # 创建并启动处理线程
        self._processor = BatchProcessor(
            self._files, output_dir, algorithm, mask, quality,
            suffix=suffix, include_date=include_date, **kwargs,
        )
        self._processor.progress_updated.connect(self._on_progress)
        self._processor.processing_complete.connect(self._on_complete)
        self._processor.file_processed.connect(self._on_file_processed)
        self._processor.start()

    def _on_progress(self, current: int, total: int, filename: str):
        self._progress_bar.setMaximum(total)
        self._progress_bar.setValue(current)
        self._status_label.setText(f"正在处理: {filename} ({current}/{total})")

    def _on_file_processed(self, file_path: str, success: bool):
        status = "[OK]" if success else "[X]"
        for i in range(self._file_list.count()):
            item = self._file_list.item(i)
            if item and file_path in item.toolTip():
                item.setText(f"{status} {item.text()}")
                break
        QApplication.processEvents()

    def _on_complete(self, success: int, failed: int):
        self._start_btn.setEnabled(True)
        self._add_btn.setEnabled(True)
        self._clear_btn.setEnabled(True)
        self._status_label.setText(
            f"处理完成: {success} 成功, {failed} 失败"
        )
        QMessageBox.information(
            self, "处理完成",
            f"批量处理完成!\n\n成功: {success} 个文件\n失败: {failed} 个文件"
        )

    def closeEvent(self, event):
        if self._processor and self._processor.isRunning():
            reply = QMessageBox.question(
                self, "确认", "批量处理正在进行中，确定要关闭吗？",
                QMessageBox.Yes | QMessageBox.No
            )
            if reply == QMessageBox.Yes:
                self._processor.stop()
                # 先断开信号，避免 wait() 后仍有信号触发到即将销毁的对话框
                for sig in (self._processor.progress_updated,
                            self._processor.file_processed,
                            self._processor.processing_complete):
                    try:
                        sig.disconnect()
                    except (TypeError, RuntimeError):
                        pass
                self._processor.wait()
                event.accept()
            else:
                event.ignore()
        else:
            event.accept()


class MainWindow(QMainWindow):
    """主窗口"""

    def __init__(self):
        super().__init__()
        self._processor = ImageProcessor()
        self._processor.set_callback(self._on_image_changed)

        self._current_pixmap: Optional[QPixmap] = None
        self._result_pixmap: Optional[QPixmap] = None
        self._is_comparing = False

        # 标识下次 _refresh_preview 是"整体替换图片"（加载/重置）还是
        # "算法结果更新"（仅刷新像素、保留选区）
        self._is_replacing_image = False

        self._setup_ui()
        self._setup_menu()
        self._init_theme_menu()
        self._setup_connections()
        self._connect_theme_signals()
        self._update_ui_state()

    def _setup_ui(self):
        """设置用户界面"""
        self.setWindowTitle("图片去水印工具 v1.0")

        # 设置窗口图标
        logo_path = resource_path("watermark_remover/logo.png")
        if os.path.exists(logo_path):
            self.setWindowIcon(QIcon(logo_path))
        self.setMinimumSize(1200, 800)

        # 中央部件
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QHBoxLayout(central)
        main_layout.setSpacing(8)
        main_layout.setContentsMargins(8, 8, 8, 8)

        # ========== 左侧面板 - 预览区 ==========
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(8)

        # 拖放区域
        self._drop_area = DropArea()
        left_layout.addWidget(self._drop_area)

        # 预览区域（整合显示、缩放、平移、选区）
        self._image_viewer = ImageViewer()
        left_layout.addWidget(self._image_viewer, 1)

        # 预览控制栏
        preview_controls = QHBoxLayout()

        # 工具栏按钮统一使用图标，图标随主题自动着色
        self._zoom_in_btn = QToolButton()
        self._zoom_in_btn.setIcon(get_icon(IconName.ZOOM_IN))
        self._zoom_in_btn.setIconSize(QSize(20, 20))
        self._zoom_in_btn.setToolTip("放大")
        self._zoom_in_btn.clicked.connect(self._zoom_in)

        self._zoom_out_btn = QToolButton()
        self._zoom_out_btn.setIcon(get_icon(IconName.ZOOM_OUT))
        self._zoom_out_btn.setIconSize(QSize(20, 20))
        self._zoom_out_btn.setToolTip("缩小")
        self._zoom_out_btn.clicked.connect(self._zoom_out)

        self._zoom_fit_btn = QToolButton()
        self._zoom_fit_btn.setIcon(get_icon(IconName.ZOOM_FIT))
        self._zoom_fit_btn.setIconSize(QSize(20, 20))
        self._zoom_fit_btn.setToolTip("适合窗口")
        self._zoom_fit_btn.clicked.connect(self._zoom_fit)

        self._select_mode_btn = QToolButton()
        self._select_mode_btn.setIcon(get_icon(IconName.SELECT))
        self._select_mode_btn.setIconSize(QSize(20, 20))
        self._select_mode_btn.setText(" 框选")
        self._select_mode_btn.setToolTip("框选水印区域")
        self._select_mode_btn.setCheckable(True)
        self._select_mode_btn.setChecked(True)
        self._select_mode_btn.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)

        self._clear_select_btn = QToolButton()
        self._clear_select_btn.setIcon(get_icon(IconName.TRASH))
        self._clear_select_btn.setIconSize(QSize(20, 20))
        self._clear_select_btn.setText(" 清除选区")
        self._clear_select_btn.setToolTip("清除所有选区")
        self._clear_select_btn.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)

        preview_controls.addWidget(self._zoom_in_btn)
        preview_controls.addWidget(self._zoom_out_btn)
        preview_controls.addWidget(self._zoom_fit_btn)
        preview_controls.addWidget(self._select_mode_btn)
        preview_controls.addWidget(self._clear_select_btn)
        preview_controls.addStretch()

        left_layout.addLayout(preview_controls)

        # ========== 右侧面板 - 控制区 ==========
        right_panel = QWidget()
        right_panel.setMaximumWidth(380)
        right_panel.setMinimumWidth(300)
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(8)

        # 标题
        title = QLabel("图片去水印工具")
        title.setObjectName("titleLabel")
        right_layout.addWidget(title)

        # 功能区 - 使用选项卡
        self._tab_widget = QTabWidget()
        right_layout.addWidget(self._tab_widget, 1)

        # --- 标签1: 基本处理 ---
        basic_tab = QWidget()
        basic_layout = QVBoxLayout(basic_tab)
        basic_layout.setSpacing(8)

        # 算法选择
        algo_group = QGroupBox("去水印算法")
        algo_layout = QVBoxLayout(algo_group)
        self._algorithm_combo = QComboBox()
        for algo_name in get_algorithms():
            self._algorithm_combo.addItem(algo_name)
        algo_layout.addWidget(self._algorithm_combo)

        # 算法说明
        self._algo_desc = QLabel("使用 OpenCV 的 Telea 算法进行图像修复，适合去除较小面积的文字水印。")
        self._algo_desc.setWordWrap(True)
        self._algo_desc.setObjectName("mutedLabel")
        self._algo_desc.setStyleSheet("font-size: 11px; padding: 4px;")
        algo_layout.addWidget(self._algo_desc)
        basic_layout.addWidget(algo_group)

        # 参数设置
        param_group = QGroupBox("参数设置")
        param_layout = QGridLayout(param_group)

        param_layout.addWidget(QLabel("修复强度:"), 0, 0)
        self._strength_spin = QDoubleSpinBox()
        self._strength_spin.setRange(0.1, 1.0)
        self._strength_spin.setSingleStep(0.1)
        self._strength_spin.setValue(0.5)
        param_layout.addWidget(self._strength_spin, 0, 1)

        param_layout.addWidget(QLabel("覆盖方式:"), 1, 0)
        self._cover_method_combo = QComboBox()
        self._cover_method_combo.addItems(["average", "median", "edge"])
        self._cover_method_combo.setVisible(False)
        param_layout.addWidget(self._cover_method_combo, 1, 1)

        basic_layout.addWidget(param_group)

        # 操作按钮
        btn_group = QGroupBox("操作")
        btn_layout = QVBoxLayout(btn_group)

        self._apply_btn = QPushButton(" 执行去水印")
        self._apply_btn.setIcon(get_icon(IconName.PLAY))
        self._apply_btn.setIconSize(QSize(18, 18))
        self._apply_btn.setObjectName("btnSuccess")
        self._apply_btn.setMinimumHeight(40)
        btn_layout.addWidget(self._apply_btn)

        action_row = QHBoxLayout()
        self._undo_btn = QPushButton(" 撤销")
        self._undo_btn.setIcon(get_icon(IconName.UNDO))
        self._undo_btn.setIconSize(QSize(16, 16))
        self._undo_btn.setObjectName("btnSecondary")
        self._redo_btn = QPushButton(" 恢复")
        self._redo_btn.setIcon(get_icon(IconName.REDO))
        self._redo_btn.setIconSize(QSize(16, 16))
        self._redo_btn.setObjectName("btnSecondary")
        self._reset_btn = QPushButton(" 重置")
        self._reset_btn.setIcon(get_icon(IconName.RESET))
        self._reset_btn.setIconSize(QSize(16, 16))
        self._reset_btn.setObjectName("btnDanger")
        action_row.addWidget(self._undo_btn)
        action_row.addWidget(self._redo_btn)
        action_row.addWidget(self._reset_btn)
        btn_layout.addLayout(action_row)

        basic_layout.addWidget(btn_group)
        basic_layout.addStretch()

        # --- 标签2: 对比和输出 ---
        output_tab = QWidget()
        output_layout = QVBoxLayout(output_tab)
        output_layout.setSpacing(6)

        # 对比预览 - 占据大部分空间
        compare_group = QGroupBox("对比预览")
        compare_layout = QVBoxLayout(compare_group)
        compare_layout.setContentsMargins(6, 18, 6, 6)
        self._compare_view = CompareView()
        compare_layout.addWidget(self._compare_view, 1)

        self._toggle_compare_btn = QPushButton(" 显示对比预览")
        self._toggle_compare_btn.setIcon(get_icon(IconName.COMPARE))
        self._toggle_compare_btn.setIconSize(QSize(14, 14))
        self._toggle_compare_btn.setObjectName("btnSecondary")
        self._toggle_compare_btn.setMaximumHeight(28)
        compare_layout.addWidget(self._toggle_compare_btn)
        output_layout.addWidget(compare_group, 1)

        # 输出设置
        save_group = QGroupBox("输出设置")
        save_layout = QGridLayout(save_group)

        save_layout.addWidget(QLabel("输出目录:"), 0, 0)
        self._output_dir_edit = QLineEdit()
        self._output_dir_edit.setPlaceholderText("默认: 原文件目录")
        save_layout.addWidget(self._output_dir_edit, 0, 1)
        self._browse_output_btn = QPushButton("浏览...")
        self._browse_output_btn.setMaximumHeight(24)
        self._browse_output_btn.clicked.connect(self._browse_output_dir)
        save_layout.addWidget(self._browse_output_btn, 0, 2)

        save_layout.addWidget(QLabel("文件名后缀:"), 1, 0)
        self._suffix_edit = QLineEdit("_nwm")
        save_layout.addWidget(self._suffix_edit, 1, 1)

        save_layout.addWidget(QLabel("图片质量:"), 2, 0)
        self._quality_spin = QSpinBox()
        self._quality_spin.setRange(10, 100)
        self._quality_spin.setValue(95)
        self._quality_spin.setSuffix("%")
        save_layout.addWidget(self._quality_spin, 2, 1)

        self._include_date_cb = QCheckBox("文件名包含日期")
        save_layout.addWidget(self._include_date_cb, 2, 2)

        output_layout.addWidget(save_group)

        # 保存和批量按钮行
        action_row = QHBoxLayout()
        self._save_btn = QPushButton(" 保存图像")
        self._save_btn.setIcon(get_icon(IconName.SAVE))
        self._save_btn.setIconSize(QSize(16, 16))
        self._save_btn.setObjectName("btnSuccess")
        self._save_btn.setMinimumHeight(32)
        action_row.addWidget(self._save_btn)

        self._save_as_btn = QPushButton(" 另存为...")
        self._save_as_btn.setObjectName("btnSecondary")
        self._save_as_btn.setMinimumHeight(32)
        action_row.addWidget(self._save_as_btn)

        self._batch_btn = QPushButton(" 批量处理")
        self._batch_btn.setIcon(get_icon(IconName.BATCH))
        self._batch_btn.setIconSize(QSize(16, 16))
        self._batch_btn.setMinimumHeight(32)
        action_row.addWidget(self._batch_btn)

        output_layout.addLayout(action_row)

        # 添加选项卡
        self._tab_widget.addTab(basic_tab, "基本处理")
        self._tab_widget.addTab(output_tab, "对比与输出")

        # ========== 添加到主布局 ==========
        main_layout.addWidget(left_panel, 1)
        main_layout.addWidget(right_panel)

        # 状态栏
        self._status_bar = QStatusBar()
        self.setStatusBar(self._status_bar)
        self._status_label = QLabel("就绪")
        self._status_bar.addWidget(self._status_label, 1)

        self._file_info_label = QLabel("")
        self._file_info_label.setObjectName("infoLabel")
        self._status_bar.addPermanentWidget(self._file_info_label)

        # 主题状态指示器（按钮形式，点击打开主题菜单）
        # 注意：_theme_menu 在 _setup_menu 中才创建，这里只创建占位按钮，
        # _init_theme_menu 之后再绑定菜单和刷新图标
        self._theme_indicator_btn = QToolButton()
        self._theme_indicator_btn.setObjectName("themeIndicator")
        self._theme_indicator_btn.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self._theme_indicator_btn.setPopupMode(QToolButton.InstantPopup)
        self._status_bar.addPermanentWidget(self._theme_indicator_btn)

        # 应用全局样式
        self.setStyleSheet(get_style())

    def _setup_menu(self):
        """设置菜单栏"""
        menubar = self.menuBar()

        # 文件菜单
        file_menu = menubar.addMenu("文件(&F)")

        open_action = QAction(get_icon(IconName.OPEN), "打开图片(&O)...", self)
        open_action.setShortcut("Ctrl+O")
        open_action.triggered.connect(self._open_file)
        file_menu.addAction(open_action)

        save_action = QAction(get_icon(IconName.SAVE), "保存(&S)", self)
        save_action.setShortcut("Ctrl+S")
        save_action.triggered.connect(self._save_image)
        file_menu.addAction(save_action)

        save_as_action = QAction(get_icon(IconName.SAVE), "另存为(&A)...", self)
        save_as_action.setShortcut("Ctrl+Shift+S")
        save_as_action.triggered.connect(self._save_image_as)
        file_menu.addAction(save_as_action)

        file_menu.addSeparator()

        batch_action = QAction(get_icon(IconName.BATCH), "批量处理(&B)...", self)
        batch_action.setShortcut("Ctrl+B")
        batch_action.triggered.connect(self._open_batch_dialog)
        file_menu.addAction(batch_action)

        file_menu.addSeparator()

        exit_action = QAction("退出(&X)", self)
        exit_action.setShortcut("Ctrl+Q")
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        # 编辑菜单
        edit_menu = menubar.addMenu("编辑(&E)")

        undo_action = QAction(get_icon(IconName.UNDO), "撤销(&U)", self)
        undo_action.setShortcut("Ctrl+Z")
        undo_action.triggered.connect(self._undo)
        edit_menu.addAction(undo_action)

        redo_action = QAction(get_icon(IconName.REDO), "恢复(&R)", self)
        redo_action.setShortcut("Ctrl+Y")
        redo_action.triggered.connect(self._redo)
        edit_menu.addAction(redo_action)

        edit_menu.addSeparator()

        reset_action = QAction(get_icon(IconName.RESET), "重置为原始图像", self)
        reset_action.setShortcut("Ctrl+R")
        reset_action.triggered.connect(self._reset)
        edit_menu.addAction(reset_action)

        # 处理菜单
        process_menu = menubar.addMenu("处理(&P)")

        apply_action = QAction(get_icon(IconName.PLAY), "执行去水印", self)
        apply_action.setShortcut("Ctrl+Enter")
        apply_action.triggered.connect(self._apply_algorithm)
        process_menu.addAction(apply_action)

        # 视图菜单
        view_menu = menubar.addMenu("视图(&V)")

        compare_action = QAction(get_icon(IconName.COMPARE), "对比预览", self)
        compare_action.setShortcut("Ctrl+C")
        compare_action.triggered.connect(self._toggle_compare)
        view_menu.addAction(compare_action)

        # 主题子菜单（占位，_init_theme_menu 中填充内容）
        self._theme_menu = view_menu.addMenu("主题(&T)")
        self._theme_actions = {}

        # 帮助菜单
        help_menu = menubar.addMenu("帮助(&H)")

        about_action = QAction(get_icon(IconName.INFO), "关于(&A)", self)
        about_action.triggered.connect(self._show_about)
        help_menu.addAction(about_action)

    def _setup_connections(self):
        """设置信号连接"""
        # 拖放区域
        self._drop_area.files_dropped.connect(self._on_files_dropped)

        # 算法切换
        self._algorithm_combo.currentTextChanged.connect(self._on_algorithm_changed)

        # 图像查看器信号
        self._image_viewer.selection_finished.connect(self._on_selection_finished)
        self._select_mode_btn.toggled.connect(self._on_select_mode_toggled)

        # 按钮
        self._apply_btn.clicked.connect(self._apply_algorithm)
        self._undo_btn.clicked.connect(self._undo)
        self._redo_btn.clicked.connect(self._redo)
        self._reset_btn.clicked.connect(self._reset)
        self._save_btn.clicked.connect(self._save_image)
        self._save_as_btn.clicked.connect(self._save_image_as)
        self._batch_btn.clicked.connect(self._open_batch_dialog)
        self._clear_select_btn.clicked.connect(self._clear_selections)
        self._toggle_compare_btn.clicked.connect(self._toggle_compare)

        # 输出目录
        self._output_dir_edit.setText(
            os.path.join(os.path.expanduser("~"), "Desktop")
        )

    def _update_ui_state(self):
        """更新界面状态"""
        has_image = self._processor.has_image
        can_undo = self._processor.can_undo()
        can_redo = self._processor.can_redo()

        self._image_viewer.setVisible(has_image)
        self._drop_area.setVisible(not has_image)

        self._apply_btn.setEnabled(has_image)
        self._undo_btn.setEnabled(can_undo)
        self._redo_btn.setEnabled(can_redo)
        self._reset_btn.setEnabled(has_image)
        self._save_btn.setEnabled(has_image)
        self._save_as_btn.setEnabled(has_image)

        self._zoom_in_btn.setEnabled(has_image)
        self._zoom_out_btn.setEnabled(has_image)
        self._zoom_fit_btn.setEnabled(has_image)
        self._select_mode_btn.setEnabled(has_image)
        self._clear_select_btn.setEnabled(has_image)

    def _on_image_changed(self):
        """图像状态变更回调"""
        self._update_ui_state()
        self._refresh_preview()
        # 一次性标志：用完后重置，避免影响后续"算法结果"刷新
        self._is_replacing_image = False

    def _refresh_preview(self):
        """刷新预览"""
        img = self._processor.current_image
        if img is not None:
            pixmap = QPixmap.fromImage(
                ImageProcessor.image_to_qimage(img)
            )
            self._current_pixmap = pixmap
            # 区分"首次加载/重置"和"算法结果刷新"：
            # - 首次加载与重置：清空选区（图片已整体更换）
            # - 算法结果：保留选区叠加，便于查看水印位置
            if self._is_replacing_image:
                self._image_viewer.set_pixmap(pixmap)
            else:
                self._image_viewer.update_pixmap(pixmap)

            # 更新状态信息
            h, w = img.shape[:2]
            self._file_info_label.setText(
                f"{self._processor.file_name} | {w}×{h} | "
                f"历史: {len(self._processor.get_history_info())}步"
            )

            # 更新对比视图
            if self._is_comparing:
                original_img = self._processor.original_image
                if original_img is not None:
                    original_pixmap = QPixmap.fromImage(
                        ImageProcessor.image_to_qimage(original_img)
                    )
                    self._compare_view.set_images(original_pixmap, pixmap)
        else:
            self._current_pixmap = None
            self._file_info_label.setText("")

    def _on_files_dropped(self, files: List[str]):
        """文件被拖入"""
        if len(files) == 1:
            self._load_image(files[0])
        elif len(files) > 1:
            self._open_batch_dialog(files)

    def _on_algorithm_changed(self, text: str):
        """算法选择变更"""
        descriptions = {
            "OpenCV 修复 (Telea)": "使用 Fast Marching Method 算法修复图像边缘向内部扩散，适合较小面积的文字水印。",
            "OpenCV 修复 (NS)": "使用 Navier-Stokes 流体力学方程修复图像，适合边缘丰富的区域。",
            "区域覆盖": "使用周围像素的平均值或中位数直接覆盖水印区域，适合纯色背景上的水印。",
            "纹理合成": "基于块匹配的纹理合成算法，从图像已知区域寻找最佳匹配块填充，适合纹理背景。",
            "AI 智能修复": "结合多种修复策略的增强型修复算法，适应多种场景，推荐优先尝试。",
        }
        self._algo_desc.setText(
            descriptions.get(text, "请选择适合的去水印算法。")
        )

        # 显示/隐藏特定参数
        is_area_cover = "区域覆盖" in text
        self._cover_method_combo.setVisible(is_area_cover)

    def _on_selection_finished(self, rect: QRect):
        """选择完成"""
        if not self._processor.has_image:
            return

        pixmap = self._current_pixmap
        if pixmap is None:
            return

        # 创建掩码
        mask = np.zeros((pixmap.height(), pixmap.width()), dtype=np.uint8)
        mask[rect.y():rect.y() + rect.height(),
             rect.x():rect.x() + rect.width()] = 255

        if self._processor.mask is not None:
            existing_mask = self._processor.mask
            mask = cv2.bitwise_or(existing_mask, mask)

        self._processor.set_mask(mask)
        self._status_label.setText(f"已标记水印区域: ({rect.x()}, {rect.y()}) - "
                                   f"({rect.width()}×{rect.height()})")

    def _on_select_mode_toggled(self, checked: bool):
        """选择模式切换"""
        if checked:
            self._image_viewer.set_mode(ImageViewer.MODE_SELECT)
        else:
            self._image_viewer.set_mode(ImageViewer.MODE_VIEW)

    def _clear_selections(self):
        """清除所有选区"""
        self._image_viewer.clear_selections()
        self._processor.clear_mask()
        self._status_label.setText("已清除水印选区")

    def _load_image(self, file_path: str):
        """加载图片"""
        if self._processor.load_image(file_path):
            self._is_replacing_image = True
            self._status_label.setText(f"已加载: {os.path.basename(file_path)}")
            # 恢复选择模式
            self._image_viewer.set_mode(ImageViewer.MODE_SELECT)
            self._select_mode_btn.setChecked(True)
        else:
            QMessageBox.critical(self, "错误", f"无法加载图片文件:\n{file_path}")

    def _open_file(self):
        """打开文件对话框"""
        files, _ = QFileDialog.getOpenFileName(
            self, "选择图片",
            "",
            "图片文件 (*.jpg *.jpeg *.png *.bmp *.tiff *.tif *.webp);;所有文件 (*.*)"
        )
        if files:
            self._load_image(files)

    def _apply_algorithm(self):
        """应用去水印算法"""
        if not self._processor.has_image:
            return

        algo_text = self._algorithm_combo.currentText()
        algorithm = None
        for algo in AlgorithmType:
            if algo.value == algo_text:
                algorithm = algo
                break

        if algorithm is None:
            return

        # 准备参数
        kwargs = {}
        if algorithm == AlgorithmType.AREA_COVER:
            kwargs['method'] = self._cover_method_combo.currentText()
        elif algorithm == AlgorithmType.AI_REPAIR:
            kwargs['strength'] = self._strength_spin.value()

        self._status_label.setText(f"正在处理: {algo_text}...")
        QApplication.processEvents()

        success = self._processor.apply_algorithm(algorithm, **kwargs)

        if success:
            # 去水印成功后自动清除选区（视觉矩形 + mask），界面显示无选区状态
            self._clear_selections()
            self._status_label.setText(f"处理完成: {algo_text}")
        else:
            self._status_label.setText("处理失败")
            QMessageBox.warning(self, "处理失败",
                                "图像处理失败，请重试或选择其他算法。")

    def _undo(self):
        if self._processor.undo():
            self._status_label.setText("已撤销")

    def _redo(self):
        if self._processor.redo():
            self._status_label.setText("已恢复")

    def _reset(self):
        reply = QMessageBox.question(
            self, "确认重置",
            "确定要重置为原始图像吗？当前处理结果将丢失。",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            self._is_replacing_image = True
            self._processor.reset_to_original()
            self._clear_selections()
            self._status_label.setText("已重置为原始图像")

    def _zoom_in(self):
        self._image_viewer.zoom_in()

    def _zoom_out(self):
        self._image_viewer.zoom_out()

    def _zoom_fit(self):
        self._image_viewer.zoom_fit()

    def _toggle_compare(self):
        """切换对比预览"""
        self._is_comparing = not self._is_comparing
        self._compare_view.setVisible(self._is_comparing)

        if self._is_comparing:
            self._toggle_compare_btn.setText(" 隐藏对比预览")
            self._refresh_preview()
        else:
            self._toggle_compare_btn.setText(" 显示对比预览")

    def _save_image(self):
        """保存图像"""
        if not self._processor.has_image:
            return

        current = self._processor.current_image
        if current is None:
            return

        original_path = self._processor.file_path
        output_dir = self._output_dir_edit.text().strip()
        if not output_dir or not os.path.exists(output_dir):
            output_dir = os.path.dirname(original_path)

        suffix = self._suffix_edit.text().strip() or "_nwm"
        output_path = generate_output_path(
            output_dir, original_path, suffix,
            include_date=self._include_date_cb.isChecked(),
        )

        quality = self._quality_spin.value()
        if ImageProcessor.save_image(current, output_path, quality):
            self._status_label.setText(f"已保存: {os.path.basename(output_path)}")
        else:
            QMessageBox.critical(self, "保存失败", f"无法保存到:\n{output_path}")

    def _save_image_as(self):
        """另存为"""
        if not self._processor.has_image:
            return

        current = self._processor.current_image
        if current is None:
            return

        file_path, selected_filter = QFileDialog.getSaveFileName(
            self, "另存为",
            "",
            "JPEG 图片 (*.jpg);;PNG 图片 (*.png);;BMP 图片 (*.bmp);;TIFF 图片 (*.tiff);;所有文件 (*.*)"
        )
        if file_path:
            quality = self._quality_spin.value()
            if ImageProcessor.save_image(current, file_path, quality):
                self._status_label.setText(f"已保存: {os.path.basename(file_path)}")
            else:
                QMessageBox.critical(self, "保存失败", f"无法保存到:\n{file_path}")

    def _browse_output_dir(self):
        """浏览输出目录"""
        directory = QFileDialog.getExistingDirectory(
            self, "选择输出目录",
            self._output_dir_edit.text()
        )
        if directory:
            self._output_dir_edit.setText(directory)

    def _open_batch_dialog(self, files: Optional[List[str]] = None):
        """打开批量处理对话框"""
        dialog = BatchDialog(self)
        if files:
            dialog.set_files(files)
        dialog.exec_()

    def _show_about(self):
        """显示关于信息"""
        QMessageBox.about(
            self, "关于 图片去水印工具",
            "<h3>图片去水印工具 v1.0</h3>"
            "<p>一个简单易用的图片去水印工具</p>"
            "<hr>"
            "<p><b>作者：</b>luojt</p>"
            "<p><b>联系邮箱：</b>1337843618@qq.com</p>"
            "<hr>"
            "<p><b>技术栈:</b></p>"
            "<ul>"
            "<li>PyQt5 - 图形用户界面</li>"
            "<li>OpenCV - 图像处理</li>"
            "<li>Pillow - 图像格式支持</li>"
            "</ul>"
            "<hr>"
            "<p><b>功能特色:</b></p>"
            "<ul>"
            "<li>多种去水印算法</li>"
            "<li>精确框选水印区域</li>"
            "<li>批量处理</li>"
            "<li>撤销/恢复</li>"
            "<li>前后对比预览</li>"
            "</ul>"
        )

    def dragEnterEvent(self, event: QDragEnterEvent):
        """窗口级别拖入事件"""
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent):
        """窗口级别放置事件"""
        files = []
        for url in event.mimeData().urls():
            file_path = url.toLocalFile()
            if is_image_file(file_path):
                files.append(file_path)
        if files:
            self._on_files_dropped(files)

    # ---- 主题切换 ----

    def _init_theme_menu(self):
        """初始化主题菜单（三个互斥选项 + Auto 当前指示）

        每个主题有"轮廓版"和"填充版"两套图标：
        - 轮廓版：未选中时显示（普通状态）
        - 填充版：选中时显示（强调状态，与 menu_selected_bg 背景形成强烈对比）
        """
        self._theme_action_group = QActionGroup(self)
        self._theme_action_group.setExclusive(True)

        # (mode, 显示文本, 轮廓图标, 填充图标, 提示)
        theme_defs = [
            (ThemeMode.LIGHT, " 亮色主题",
             IconName.SUN, IconName.SUN_FILLED,
             "使用浅色界面（默认）"),
            (ThemeMode.DARK,  " 暗色主题",
             IconName.MOON, IconName.MOON_FILLED,
             "使用深色界面，更适合夜间使用"),
            (ThemeMode.AUTO,  " 跟随系统",
             IconName.MONITOR, IconName.MONITOR_FILLED,
             "根据操作系统的外观设置自动切换"),
        ]

        for mode, label, outline_icon, filled_icon, tip in theme_defs:
            action = QAction(label, self, checkable=True)
            # 保存当前主题对应的两个图标名，便于切换
            action.setData((mode, outline_icon, filled_icon))
            action.setToolTip(tip)
            # 监听 toggled 信号动态切换图标
            action.toggled.connect(
                lambda checked, a=action: self._update_theme_action_icon(a, checked)
            )
            action.triggered.connect(
                lambda checked, m=mode: self._on_theme_selected(m)
            )
            self._theme_action_group.addAction(action)
            self._theme_menu.addAction(action)
            self._theme_actions[mode] = action

        # 同步当前选中状态（会触发 toggled 信号，调用 _update_theme_action_icon）
        current_mode = get_manager().mode
        if current_mode in self._theme_actions:
            self._theme_actions[current_mode].setChecked(True)

        # 为其他未选中的 action 设置初始轮廓图标
        for mode, action in self._theme_actions.items():
            if not action.isChecked():
                _, outline_icon, _ = action.data()
                action.setIcon(get_icon(outline_icon))

        # 绑定主题菜单到状态栏指示器按钮，并刷新初始显示
        if hasattr(self, '_theme_indicator_btn'):
            self._theme_indicator_btn.setMenu(self._theme_menu)
            self._refresh_theme_indicator()

    def _update_theme_action_icon(self, action: QAction, checked: bool):
        """根据选中状态切换主题图标的轮廓/填充版本"""
        data = action.data()
        if not data or not isinstance(data, tuple):
            return
        _, outline_icon, filled_icon = data
        action.setIcon(get_icon(filled_icon if checked else outline_icon))

    def _refresh_theme_indicator(self):
        """刷新状态栏的主题指示器按钮

        显示当前主题的填充图标 + 文本标签，提供清晰的视觉反馈。
        """
        if not hasattr(self, '_theme_indicator_btn'):
            return

        mode = get_manager().mode
        info = {
            ThemeMode.LIGHT: (IconName.SUN_FILLED, "亮色"),
            ThemeMode.DARK:  (IconName.MOON_FILLED, "暗色"),
            ThemeMode.AUTO:  (IconName.MONITOR_FILLED, "自动"),
        }
        icon_name, label = info[mode]

        self._theme_indicator_btn.setIcon(get_icon(icon_name))
        self._theme_indicator_btn.setIconSize(QSize(16, 16))
        self._theme_indicator_btn.setText(f" {label}")
        self._theme_indicator_btn.setToolTip(
            f"当前主题: {label}\n点击切换主题模式"
        )

    def _connect_theme_signals(self):
        """连接主题变更信号"""
        get_manager().theme_changed.connect(self._apply_theme)
        # 模式切换信号（即使调色板未变也要触发，用于刷新指示器文本）
        get_manager().mode_changed.connect(self._on_mode_changed)

    def _on_mode_changed(self, mode: str, palette: ThemePalette):
        """模式切换时调用（可能调色板未变，如 DARK→AUTO 在深色系统下）

        负责：菜单选中状态同步 + 状态栏指示器刷新 + 主题图标重新应用
        """
        # 同步菜单选中状态（QActionGroup 自身会处理互斥）
        if mode in self._theme_actions:
            action = self._theme_actions[mode]
            # blockSignals 防止 toggled 信号递归触发图标切换（图标切换将由 _refresh_all_icons 统一处理）
            action.blockSignals(True)
            action.setChecked(True)
            action.blockSignals(False)
            # 立即更新此 action 的图标（反映新选中状态）
            self._update_theme_action_icon(action, True)
            # 同时把其他 action 切回轮廓图标
            for other_mode, other_action in self._theme_actions.items():
                if other_mode != mode:
                    self._update_theme_action_icon(other_action, False)
        # 刷新状态栏指示器
        self._refresh_theme_indicator()

    def _on_theme_selected(self, mode: str):
        """用户从菜单选择主题"""
        if mode != get_manager().mode:
            get_manager().set_mode(mode)

    def _apply_theme(self, name: str, palette: ThemePalette):
        """应用主题 - 刷新所有需要主题感知的控件"""
        # 重新应用全局 QSS（作用于整个窗口）
        self.setStyleSheet(get_style())

        # 刷新所有具有内联样式的子控件
        self._drop_area._refresh_style()
        self._image_viewer.apply_theme()
        self._compare_view.apply_theme()

        # 刷新所有图标（图标缓存已由 IconManager 自动清空）
        self._refresh_all_icons()
        # 刷新状态栏主题指示器
        self._refresh_theme_indicator()

        # 状态栏提示
        mode_label = {
            ThemeMode.LIGHT: "亮色",
            ThemeMode.DARK: "暗色",
            ThemeMode.AUTO: "跟随系统",
        }.get(get_manager().mode, "亮色")
        self._status_label.setText(f"已切换至{mode_label}主题")

    def _refresh_all_icons(self):
        """主题切换后刷新所有按钮/动作的图标"""
        # 预览工具栏按钮
        self._zoom_in_btn.setIcon(get_icon(IconName.ZOOM_IN))
        self._zoom_out_btn.setIcon(get_icon(IconName.ZOOM_OUT))
        self._zoom_fit_btn.setIcon(get_icon(IconName.ZOOM_FIT))
        self._select_mode_btn.setIcon(get_icon(IconName.SELECT))
        self._clear_select_btn.setIcon(get_icon(IconName.TRASH))

        # 主操作按钮
        self._apply_btn.setIcon(get_icon(IconName.PLAY))
        self._undo_btn.setIcon(get_icon(IconName.UNDO))
        self._redo_btn.setIcon(get_icon(IconName.REDO))
        self._reset_btn.setIcon(get_icon(IconName.RESET))

        # 保存与批量按钮
        self._save_btn.setIcon(get_icon(IconName.SAVE))
        self._batch_btn.setIcon(get_icon(IconName.BATCH))
        self._toggle_compare_btn.setIcon(get_icon(IconName.COMPARE))

        # 主题菜单项图标（根据选中状态使用填充或轮廓版）
        if self._theme_actions:
            for mode, action in self._theme_actions.items():
                self._update_theme_action_icon(action, action.isChecked())

    def closeEvent(self, event):
        """关闭事件"""
        event.accept()