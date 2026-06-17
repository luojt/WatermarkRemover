"""
主窗口 - 图像去水印工具的图形用户界面

包含功能：
- 文件拖放和选择
- 图像预览和对比
- 水印区域框选
- 去水印算法选择和应用
- 撤销/重做
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
    QToolBar, QStatusBar, QAction, QMenu, QToolButton,
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
    format_file_size, limit_image_size, resource_path
)
from .styles import get_style


class DropArea(QWidget):
    """拖放区域控件"""

    files_dropped = pyqtSignal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setMinimumSize(300, 200)
        self.setMaximumHeight(250)
        self._hover = False

        # 设置样式
        self.setStyleSheet("""
            DropArea {
                border: 2px dashed #bdbdbd;
                border-radius: 12px;
                background-color: #fafafa;
            }
            DropArea:hover {
                border-color: #1976d2;
                background-color: #e3f2fd;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignCenter)

        self._icon_label = QLabel("📁")
        self._icon_label.setAlignment(Qt.AlignCenter)
        self._icon_label.setStyleSheet("font-size: 48px; border: none;")
        layout.addWidget(self._icon_label)

        self._text_label = QLabel("拖拽图片到此处\n或点击下方按钮选择文件")
        self._text_label.setAlignment(Qt.AlignCenter)
        self._text_label.setStyleSheet("font-size: 14px; color: #666; border: none;")
        layout.addWidget(self._text_label)

        self._format_label = QLabel("支持 JPG、PNG、BMP、TIFF、WEBP 等格式")
        self._format_label.setAlignment(Qt.AlignCenter)
        self._format_label.setStyleSheet("font-size: 11px; color: #999; border: none;")
        layout.addWidget(self._format_label)

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            self._hover = True
            event.acceptProposedAction()
            self.setStyleSheet("""
                DropArea {
                    border: 2px dashed #1976d2;
                    border-radius: 12px;
                    background-color: #bbdefb;
                }
            """)

    def dragLeaveEvent(self, event):
        self._hover = False
        self.setStyleSheet("""
            DropArea {
                border: 2px dashed #bdbdbd;
                border-radius: 12px;
                background-color: #fafafa;
            }
        """)

    def dropEvent(self, event: QDropEvent):
        self._hover = False
        self.setStyleSheet("""
            DropArea {
                border: 2px dashed #bdbdbd;
                border-radius: 12px;
                background-color: #fafafa;
            }
        """)

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
        self.setStyleSheet("background-color: #333; border-radius: 4px;")
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

    def set_pixmap(self, pixmap: Optional[QPixmap]):
        """设置显示的图像，自动适配可视区域"""
        self._pixmap = pixmap.copy() if pixmap else None
        self._selections.clear()
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

        painter.fillRect(self.rect(), QColor(50, 50, 50))

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
            painter.setPen(QColor(200, 200, 200, 200))
            painter.setFont(QFont("Microsoft YaHei", 10))
            painter.drawText(self.rect().adjusted(8, 8, -8, -8),
                             Qt.AlignTop | Qt.AlignLeft, info)
        else:
            painter.setPen(QColor(180, 180, 180))
            painter.setFont(QFont("Microsoft YaHei", 14))
            painter.drawText(self.rect(), Qt.AlignCenter, "请先加载图片")

    def _paint_selection(self, painter: QPainter, rect: QRectF):
        """绘制选区"""
        painter.fillRect(rect, QColor(30, 100, 200, 40))
        pen = QPen(QColor(30, 136, 229), 2)
        pen.setDashPattern([6, 3])
        painter.setPen(pen)
        painter.drawRect(rect)
        painter.setPen(QPen(QColor(255, 255, 255), 1))
        painter.setBrush(QBrush(QColor(30, 136, 229)))
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
        self.setStyleSheet("background-color: #333; border-radius: 4px;")

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

        painter.fillRect(self.rect(), QColor(50, 50, 50))

        if self._pixmap and not self._pixmap.isNull():
            pw, ph = self._pixmap.width(), self._pixmap.height()
            tl = self._img_pos()
            sw, sh = pw * self._scale, ph * self._scale

            # 完整绘制（含偏移裁剪）
            painter.drawPixmap(QRectF(tl.x(), tl.y(), sw, sh),
                               self._pixmap, QRectF(0, 0, pw, ph))

            # 缩放比例覆盖层
            info = f"{100.0 * self._scale:.0f}%"
            painter.setPen(QColor(200, 200, 200, 200))
            painter.setFont(QFont("Microsoft YaHei", 10))
            painter.drawText(self.rect().adjusted(6, 6, -6, -6),
                             Qt.AlignTop | Qt.AlignLeft, info)
        elif self._placeholder_text:
            painter.setPen(QColor(180, 180, 180))
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
        hint.setStyleSheet("color: #888; font-size: 11px;")
        layout.addWidget(hint)

        # 全尺寸 PanZoomLabel
        self._viewer = PanZoomLabel()
        self._viewer.set_pixmap(pixmap)
        layout.addWidget(self._viewer, 1)

        # 底部缩放信息 + 关闭
        bottom = QHBoxLayout()
        self._zoom_label = QLabel("100%")
        self._zoom_label.setStyleSheet("color: #aaa; font-size: 11px;")
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
        self._sync_btn.setText("□ 同步")
        self._sync_btn.setToolTip("同步缩放和平移操作")
        self._sync_btn.setStyleSheet("""
            QToolButton { padding: 4px 10px; border: 1px solid #888;
                          border-radius: 4px; font-size: 11px; }
            QToolButton:checked { background-color: #1565c0; color: white;
                                  border-color: #1565c0; }
        """)
        self._sync_btn.toggled.connect(self._on_sync_toggled)
        toolbar.addWidget(self._sync_btn)

        self._reset_all_btn = QToolButton()
        self._reset_all_btn.setText("↺ 重置")
        self._reset_all_btn.setToolTip("重置两侧视图")
        self._reset_all_btn.setStyleSheet(
            "QToolButton { padding: 4px 10px; border-radius: 4px; font-size: 11px; }")
        self._reset_all_btn.clicked.connect(self._reset_all)
        toolbar.addWidget(self._reset_all_btn)

        toolbar.addStretch()

        hint = QLabel("滚轮缩放 · 拖拽平移")
        hint.setStyleSheet("color: #888; font-size: 11px;")
        toolbar.addWidget(hint)

        main_layout.addLayout(toolbar)

        # ---- 左右并排视图 ----
        view_layout = QHBoxLayout()
        view_layout.setSpacing(6)

        # 处理前
        orig_group = QGroupBox("处理前")
        orig_group.setStyleSheet("QGroupBox{font-size:12px;font-weight:bold;}")
        orig_layout = QVBoxLayout(orig_group)
        orig_layout.setContentsMargins(4, 16, 4, 4)
        orig_layout.setSpacing(4)

        self._orig_view = PanZoomLabel()
        self._orig_view.set_placeholder("处理前\n(原始图像)")
        orig_layout.addWidget(self._orig_view, 1)

        orig_btns = QHBoxLayout()
        orig_btns.setSpacing(4)
        orig_zoom_label = QLabel("100%")
        orig_zoom_label.setStyleSheet("color:#aaa; font-size:10px;")
        orig_btns.addWidget(orig_zoom_label)
        orig_btns.addStretch()
        orig_full_btn = QPushButton("放大查看")
        orig_full_btn.setFixedSize(64, 22)
        orig_full_btn.setStyleSheet("font-size:10px; padding:0 4px;")
        orig_full_btn.clicked.connect(
            lambda: self._open_preview_dialog(self._orig_view, "处理前"))
        orig_btns.addWidget(orig_full_btn)
        orig_reset = QToolButton()
        orig_reset.setText("↺")
        orig_reset.setToolTip("重置此视图")
        orig_reset.setFixedSize(24, 22)
        orig_reset.clicked.connect(lambda: self._orig_view.reset_view())
        orig_btns.addWidget(orig_reset)
        orig_layout.addLayout(orig_btns)

        view_layout.addWidget(orig_group, 1)

        # 处理后
        rst_group = QGroupBox("处理后")
        rst_group.setStyleSheet("QGroupBox{font-size:12px;font-weight:bold;}")
        rst_layout = QVBoxLayout(rst_group)
        rst_layout.setContentsMargins(4, 16, 4, 4)
        rst_layout.setSpacing(4)

        self._rst_view = PanZoomLabel()
        self._rst_view.set_placeholder("处理后\n(等待处理结果)")
        rst_layout.addWidget(self._rst_view, 1)

        rst_btns = QHBoxLayout()
        rst_btns.setSpacing(4)
        rst_zoom_label = QLabel("100%")
        rst_zoom_label.setStyleSheet("color:#aaa; font-size:10px;")
        rst_btns.addWidget(rst_zoom_label)
        rst_btns.addStretch()
        rst_full_btn = QPushButton("放大查看")
        rst_full_btn.setFixedSize(64, 22)
        rst_full_btn.setStyleSheet("font-size:10px; padding:0 4px;")
        rst_full_btn.clicked.connect(
            lambda: self._open_preview_dialog(self._rst_view, "处理后"))
        rst_btns.addWidget(rst_full_btn)
        rst_reset = QToolButton()
        rst_reset.setText("↺")
        rst_reset.setToolTip("重置此视图")
        rst_reset.setFixedSize(24, 22)
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


class BatchProcessor(QThread):
    """批量处理线程"""

    progress_updated = pyqtSignal(int, int, str)
    processing_complete = pyqtSignal(int, int)  # success, failed
    file_processed = pyqtSignal(str, bool)

    def __init__(self, files: List[str], output_dir: str,
                 algorithm: AlgorithmType, mask: np.ndarray = None,
                 quality: int = 95, **kwargs):
        super().__init__()
        self._files = files
        self._output_dir = output_dir
        self._algorithm = algorithm
        self._mask = mask
        self._quality = quality
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
                    self._output_dir, file_path)

                if mask is not None:
                    result = processor.apply_algorithm_to_image(
                        img, mask, self._algorithm, **self._kwargs)
                else:
                    result = img.copy()

                # 保存
                if self._quality > 0:
                    ext = os.path.splitext(output_path)[1].lower()
                    if ext in ['.jpg', '.jpeg']:
                        cv2.imwrite(output_path, result,
                                    [cv2.IMWRITE_JPEG_QUALITY, self._quality])
                    elif ext == '.png':
                        cv2.imwrite(output_path, result,
                                    [cv2.IMWRITE_PNG_COMPRESSION, 3])
                    else:
                        cv2.imwrite(output_path, result)
                else:
                    cv2.imwrite(output_path, result)

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

        if hasattr(main_window, '_processor'):
            proc = main_window._processor
            mask = proc.mask
        if hasattr(main_window, '_algorithm_combo'):
            algo_text = main_window._algorithm_combo.currentText()
            for algo in AlgorithmType:
                if algo.value == algo_text:
                    algorithm = algo
                    break

        # 创建并启动处理线程
        self._processor = BatchProcessor(
            self._files, output_dir, algorithm, mask, quality
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
        status = "✓" if success else "✗"
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

        self._setup_ui()
        self._setup_menu()
        self._setup_connections()
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
        self._zoom_in_btn = QToolButton()
        self._zoom_in_btn.setText("🔍+")
        self._zoom_in_btn.setToolTip("放大")
        self._zoom_in_btn.clicked.connect(self._zoom_in)

        self._zoom_out_btn = QToolButton()
        self._zoom_out_btn.setText("🔍-")
        self._zoom_out_btn.setToolTip("缩小")
        self._zoom_out_btn.clicked.connect(self._zoom_out)

        self._zoom_fit_btn = QToolButton()
        self._zoom_fit_btn.setText("🔍")
        self._zoom_fit_btn.setToolTip("适合窗口")
        self._zoom_fit_btn.clicked.connect(self._zoom_fit)

        self._select_mode_btn = QToolButton()
        self._select_mode_btn.setText("✏️ 框选")
        self._select_mode_btn.setToolTip("框选水印区域")
        self._select_mode_btn.setCheckable(True)
        self._select_mode_btn.setChecked(True)

        self._clear_select_btn = QToolButton()
        self._clear_select_btn.setText("🗑️ 清除选区")
        self._clear_select_btn.setToolTip("清除所有选区")

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
        self._algo_desc.setStyleSheet("font-size: 11px; color: #888; padding: 4px;")
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

        self._apply_btn = QPushButton("▶ 执行去水印")
        self._apply_btn.setObjectName("btnSuccess")
        self._apply_btn.setMinimumHeight(40)
        btn_layout.addWidget(self._apply_btn)

        action_row = QHBoxLayout()
        self._undo_btn = QPushButton("↩ 撤销")
        self._undo_btn.setObjectName("btnSecondary")
        self._redo_btn = QPushButton("↪ 重做")
        self._redo_btn.setObjectName("btnSecondary")
        self._reset_btn = QPushButton("↺ 重置")
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

        self._toggle_compare_btn = QPushButton("显示对比预览")
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

        include_date_cb = QCheckBox("文件名包含日期")
        save_layout.addWidget(include_date_cb, 2, 2)

        output_layout.addWidget(save_group)

        # 保存和批量按钮行
        action_row = QHBoxLayout()
        self._save_btn = QPushButton("💾 保存图像")
        self._save_btn.setObjectName("btnSuccess")
        self._save_btn.setMinimumHeight(32)
        action_row.addWidget(self._save_btn)

        self._save_as_btn = QPushButton("另存为...")
        self._save_as_btn.setObjectName("btnSecondary")
        self._save_as_btn.setMinimumHeight(32)
        action_row.addWidget(self._save_as_btn)

        self._batch_btn = QPushButton("📦 批量处理")
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
        self._file_info_label.setStyleSheet("color: #666;")
        self._status_bar.addPermanentWidget(self._file_info_label)

        # 应用全局样式
        self.setStyleSheet(get_style())

    def _setup_menu(self):
        """设置菜单栏"""
        menubar = self.menuBar()

        # 文件菜单
        file_menu = menubar.addMenu("文件(&F)")

        open_action = QAction("打开图片(&O)...", self)
        open_action.setShortcut("Ctrl+O")
        open_action.triggered.connect(self._open_file)
        file_menu.addAction(open_action)

        save_action = QAction("保存(&S)", self)
        save_action.setShortcut("Ctrl+S")
        save_action.triggered.connect(self._save_image)
        file_menu.addAction(save_action)

        save_as_action = QAction("另存为(&A)...", self)
        save_as_action.setShortcut("Ctrl+Shift+S")
        save_as_action.triggered.connect(self._save_image_as)
        file_menu.addAction(save_as_action)

        file_menu.addSeparator()

        batch_action = QAction("批量处理(&B)...", self)
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

        undo_action = QAction("撤销(&U)", self)
        undo_action.setShortcut("Ctrl+Z")
        undo_action.triggered.connect(self._undo)
        edit_menu.addAction(undo_action)

        redo_action = QAction("重做(&R)", self)
        redo_action.setShortcut("Ctrl+Y")
        redo_action.triggered.connect(self._redo)
        edit_menu.addAction(redo_action)

        edit_menu.addSeparator()

        reset_action = QAction("重置为原始图像", self)
        reset_action.setShortcut("Ctrl+R")
        reset_action.triggered.connect(self._reset)
        edit_menu.addAction(reset_action)

        # 处理菜单
        process_menu = menubar.addMenu("处理(&P)")

        apply_action = QAction("执行去水印", self)
        apply_action.setShortcut("Ctrl+Enter")
        apply_action.triggered.connect(self._apply_algorithm)
        process_menu.addAction(apply_action)

        # 视图菜单
        view_menu = menubar.addMenu("视图(&V)")

        compare_action = QAction("对比预览", self)
        compare_action.setShortcut("Ctrl+C")
        compare_action.triggered.connect(self._toggle_compare)
        view_menu.addAction(compare_action)

        # 帮助菜单
        help_menu = menubar.addMenu("帮助(&H)")

        about_action = QAction("关于(&A)", self)
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

    def _refresh_preview(self):
        """刷新预览"""
        img = self._processor.current_image
        if img is not None:
            pixmap = QPixmap.fromImage(
                ImageProcessor.image_to_qimage(img)
            )
            self._current_pixmap = pixmap
            self._image_viewer.set_pixmap(pixmap)

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
            self._status_label.setText(f"处理完成: {algo_text}")
        else:
            self._status_label.setText("处理失败")
            QMessageBox.warning(self, "处理失败", "图像处理失败，请重试或选择其他算法。")

    def _undo(self):
        if self._processor.undo():
            self._status_label.setText("已撤销")

    def _redo(self):
        if self._processor.redo():
            self._status_label.setText("已重做")

    def _reset(self):
        reply = QMessageBox.question(
            self, "确认重置",
            "确定要重置为原始图像吗？当前处理结果将丢失。",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        if reply == QMessageBox.Yes:
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
            self._toggle_compare_btn.setText("隐藏对比预览")
            self._refresh_preview()
        else:
            self._toggle_compare_btn.setText("显示对比预览")

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
        output_path = generate_output_path(output_dir, original_path, suffix)

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
            "<li>撤销/重做</li>"
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

    def closeEvent(self, event):
        """关闭事件"""
        event.accept()