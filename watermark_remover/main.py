#!/usr/bin/env python3
"""
图片去水印工具 - 主入口

一个具有图形用户界面(GUI)的图片去水印工具。
支持多种去水印算法、批量处理、撤销/恢复等功能。

使用方法:
    python main.py

依赖:
    - PyQt5
    - opencv-python
    - Pillow
    - numpy
"""

import sys
import os

# 确保可以找到模块
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt5.QtWidgets import QApplication
from PyQt5.QtGui import QIcon
from PyQt5.QtCore import Qt

from watermark_remover.gui.main_window import MainWindow
from watermark_remover.utils.helpers import resource_path


def main():
    """程序入口函数"""
    # 启用高分屏支持
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)

    app = QApplication(sys.argv)
    app.setApplicationName("图片去水印工具")
    app.setApplicationVersion("1.0.0")
    app.setOrganizationName("WatermarkRemover")

    # 设置应用图标
    logo_path = resource_path("watermark_remover/logo.png")
    if os.path.exists(logo_path):
        app.setWindowIcon(QIcon(logo_path))

    window = MainWindow()
    window.show()

    sys.exit(app.exec_())


if __name__ == "__main__":
    main()