#!/usr/bin/env python3
"""
图片去水印工具 - 启动脚本

运行此脚本启动应用程序：
    python run.py
"""

import sys
import os

# 将项目根目录添加到系统路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from watermark_remover.main import main

if __name__ == "__main__":
    main()