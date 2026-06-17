#!/usr/bin/env python3
"""
一键打包脚本 — 将图片去水印工具打包为各平台可执行文件

使用方法:
    python build.py                  # 完整打包
    python build.py --onefile        # 打包为单个文件（体积更大，启动稍慢）
    python build.py --clean          # 清理临时文件后打包
    python build.py --distpath DIR   # 指定输出目录

各平台输出:
    Windows:  dist/WatermarkRemover/WatermarkRemover.exe
    macOS:    dist/WatermarkRemover.app
    Linux:    dist/WatermarkRemover/WatermarkRemover

前置依赖:
    pip install pyinstaller
"""

import os
import sys
import shutil
import argparse
import subprocess
import platform


def main():
    parser = argparse.ArgumentParser(description='打包图片去水印工具为可执行文件')
    parser.add_argument('--onefile', action='store_true',
                        help='打包为单个文件（体积更大，但方便分发）')
    parser.add_argument('--clean', action='store_true',
                        help='打包前清理临时文件')
    parser.add_argument('--distpath', type=str, default=None,
                        help='输出目录（默认: ./dist）')
    parser.add_argument('--icon', type=str, default=None,
                        help='应用图标路径（可选）')
    parser.add_argument('--name', type=str, default='WatermarkRemover',
                        help='应用名称（默认: WatermarkRemover）')
    args = parser.parse_args()

    # --------------------------------------------------------
    # 环境检查
    # --------------------------------------------------------
    print(f"[1/4] 检查环境 ...")
    print(f"  Python:   {sys.version}")
    print(f"  平台:     {platform.system()} {platform.release()}")
    print(f"  架构:     {platform.machine()}")

    # 检查 PyInstaller
    try:
        import PyInstaller
        print(f"  PyInstaller: {PyInstaller.__version__}")
    except ImportError:
        print("  PyInstaller 未安装，正在安装 ...")
        subprocess.run(
            [sys.executable, '-m', 'pip', 'install', 'pyinstaller'],
            check=True
        )
        print("  PyInstaller 安装完成")

    project_root = os.path.dirname(os.path.abspath(__file__))
    os.chdir(project_root)

    # --------------------------------------------------------
    # 清理
    # --------------------------------------------------------
    if args.clean:
        print(f"[2/4] 清理临时文件 ...")
        for d in ['build', 'dist']:
            p = os.path.join(project_root, d)
            if os.path.exists(p):
                shutil.rmtree(p)
                print(f"  已删除: {d}/")
        for f in ['WatermarkRemover.spec']:
            p = os.path.join(project_root, f)
            if os.path.exists(p):
                os.remove(p)
                print(f"  已删除: {f}")
    else:
        print(f"[2/4] 跳过清理 (使用 --clean 可清理)")

    # --------------------------------------------------------
    # 构建命令
    # --------------------------------------------------------
    print(f"[3/4] 构建打包命令 ...")

    cmd = [
        sys.executable, '-m', 'PyInstaller',
        '--name', args.name,
        '--windowed',                    # 无控制台窗口
        '--noconfirm',                   # 覆盖已存在的输出
    ]

    # 输出目录
    if args.distpath:
        cmd.extend(['--distpath', args.distpath])
        dist_dir = args.distpath
    else:
        dist_dir = os.path.join(project_root, 'dist')

    # 单文件模式
    if args.onefile:
        cmd.append('--onefile')
        print("  模式: 单文件")
    else:
        print("  模式: 目录 (推荐，启动更快)")

    # 图标 — 生成 .ico（Windows）或自动选择
    icon_path = args.icon
    if not icon_path:
        # 自动从 logo.png 生成 logo.ico（Windows 需要 .ico 格式作为 exe 图标）
        if sys.platform == 'win32':
            png_path = os.path.join(project_root, 'watermark_remover', 'logo.png')
            ico_path = os.path.join(project_root, 'watermark_remover', 'logo.ico')
            if os.path.exists(png_path) and not os.path.exists(ico_path):
                try:
                    from PIL import Image
                    Image.open(png_path).save(ico_path, format='ICO', sizes=[(256, 256)])
                except Exception:
                    pass
            if os.path.exists(ico_path):
                icon_path = ico_path
        elif sys.platform == 'darwin':
            icns = os.path.join(project_root, 'watermark_remover', 'logo.icns')
            if os.path.exists(icns):
                icon_path = icns

    if icon_path and os.path.exists(icon_path):
        cmd.extend(['--icon', os.path.abspath(icon_path)])
        print(f"  图标: {os.path.abspath(icon_path)}")
    else:
        print(f"  图标: 无（使用 PyInstaller 默认图标）")

    # 添加 logo.png 作为数据文件
    logo_src = os.path.join(project_root, 'watermark_remover', 'logo.png')
    if os.path.exists(logo_src):
        logo_dst = 'watermark_remover'
        if sys.platform == 'win32':
            cmd.extend(['--add-data', f'{logo_src};{logo_dst}'])
        else:
            cmd.extend(['--add-data', f'{logo_src}:{logo_dst}'])
        print(f"  logo: {logo_src}")

    # 收集子模块
    cmd.extend([
        '--collect-submodules', 'watermark_remover',
        '--collect-submodules', 'cv2',
    ])

    # 隐式依赖
    cmd.extend([
        '--hidden-import', 'PyQt5.sip',
        '--hidden-import', 'PIL._tkinter_finder',
    ])

    # macOS 特殊处理: 高 DPI
    if sys.platform == 'darwin':
        cmd.append('--high-dpi-support')

    # 入口文件
    cmd.append(os.path.join(project_root, 'run.py'))

    print(f"  命令: {' '.join(cmd)}")

    # --------------------------------------------------------
    # 执行打包
    # --------------------------------------------------------
    print(f"[4/4] 执行打包 (可能需要 2-5 分钟) ...")
    print(f"  {'='*50}")

    result = subprocess.run(cmd, cwd=project_root)

    if result.returncode != 0:
        print(f"\n❌ 打包失败! 错误代码: {result.returncode}")
        sys.exit(result.returncode)

    # --------------------------------------------------------
    # 输出结果
    # --------------------------------------------------------
    print(f"  {'='*50}")
    print(f"\n✅ 打包成功!")

    # 查找生成的可执行文件
    exe_name = {
        'Windows': f'{args.name}.exe',
        'Darwin':  f'{args.name}.app',
        'Linux':   args.name,
    }.get(platform.system(), args.name)

    exe_path = os.path.join(dist_dir, exe_name)
    dir_path = os.path.join(dist_dir, args.name)

    if os.path.exists(exe_path):
        print(f"   可执行文件: {exe_path}")
    elif os.path.exists(dir_path):
        possible = os.path.join(dir_path, exe_name)
        if os.path.exists(possible):
            print(f"   可执行文件: {possible}")
        else:
            print(f"   输出目录: {dir_path}")
    else:
        # 尝试找 app bundle (macOS)
        app_path = os.path.join(dist_dir, f'{args.name}.app')
        if os.path.exists(app_path):
            print(f"   应用包: {app_path}")

    print(f"\n分发方式:")
    if platform.system() == 'Windows':
        print(f"   - 直接运行 {args.name}.exe")
        print(f"   - 或将整个 {args.name}/ 目录压缩后分发")
    elif platform.system() == 'Darwin':
        print(f"   - 直接运行 {args.name}.app")
        print(f"   - 或用 create-dmg 制作安装包")
    else:
        print(f"   - 直接运行 ./{args.name}/{args.name}")
        print(f"   - 或用 appimagetool 打包成 AppImage")


if __name__ == '__main__':
    main()