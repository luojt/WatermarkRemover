# 图片去水印工具 (Watermark Remover)

一个基于 Python 和 PyQt5 开发的跨平台图片去水印工具，提供图形化界面和多种去水印算法。

## 开发原因

由于 AI 的崛起，公司裁掉了 UI 设计，没办法，只好自己用 AI 进行设计，但是 AI 生成的图片都带有水印，所以需要一个去水印工具。

## 功能特性

### 核心功能
- **多种去水印算法**：提供 5 种不同算法适应不同场景
- **精准框选**：通过鼠标拖拽精确标记水印区域，支持框选/查看模式切换
- **批量处理**：支持同时处理多张图片，带进度显示
- **对比预览**：左右并排对比原图与处理结果，支持独立缩放、拖拽平移和同步模式

### 算法支持

| 算法 | 适用场景 |
|------|----------|
| **OpenCV 修复 (Telea)** | 较小面积的文字水印，边缘平滑过渡 |
| **OpenCV 修复 (NS)** | 边缘丰富的区域，基于流体力学方程 |
| **区域覆盖** | 纯色背景上的水印，用周围像素覆盖 |
| **纹理合成** | 纹理背景上的水印，基于块匹配填充 |
| **AI 智能修复** | 多种场景，结合多种修复策略 |

### 用户体验
- 拖拽图片到窗口即可加载
- 支持撤销/重做（最多 50 步历史）
- 图像预览支持滚轮缩放和鼠标拖拽平移
- 对比预览支持独立或同步缩放控制
- 支持独立放大查看弹窗
- 自定义输出路径和文件名格式
- 图片质量可调
- 支持 JPG/PNG/BMP/TIFF/WEBP 等常见格式

## 环境要求

- Python 3.8 或更高版本
- 操作系统：Windows / macOS / Linux

## 安装与运行

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

依赖包包括：
- PyQt5 - 图形用户界面框架
- opencv-python - 图像处理库
- Pillow - 图像格式支持
- numpy - 数值计算

### 2. 启动程序

```bash
python run.py
```

或直接运行模块：

```bash
python -m watermark_remover.main
```

## 使用指南

### 基本流程

1. **加载图片**：点击"打开图片"按钮或直接将图片拖入窗口
2. **框选水印**：确保处于"框选模式"（✏️ 框选 按钮按下），在预览区域用鼠标拖拽框选水印区域
3. **选择算法**：在右侧面板选择合适的去水印算法
4. **执行处理**：点击"执行去水印"按钮或按 `Ctrl+Enter`
5. **预览对比**：切换到"对比与输出"选项卡，点击"显示对比预览"查看处理前后效果
6. **保存结果**：预览满意后保存图像

### 图像查看操作

| 操作 | 说明 |
|------|------|
| **滚轮缩放** | 在图像区域滚动滚轮，以鼠标位置为中心缩放 |
| **拖拽平移** | 取消"✏️ 框选"按钮进入查看模式，按住鼠标左键拖拽平移 |
| **适应窗口** | 点击"🔍"按钮或切换回框选模式自动适应 |
| **对比预览缩放** | 进入对比预览后，左右两侧可独立滚轮缩放 |
| **对比预览拖拽** | 对比预览中可直接拖拽任意一侧平移 |
| **🔗 同步模式** | 点击后左右两侧缩放同步 |
| **放大查看** | 点击"放大查看"按钮在新弹窗中查看大图 |

### 快捷键

| 快捷键 | 功能 |
|--------|------|
| `Ctrl+O` | 打开图片 |
| `Ctrl+S` | 保存图像 |
| `Ctrl+Shift+S` | 另存为 |
| `Ctrl+Z` | 撤销 |
| `Ctrl+Y` | 重做 |
| `Ctrl+R` | 重置为原始图像 |
| `Ctrl+Enter` | 执行去水印 |
| `Ctrl+C` | 对比预览 |
| `Ctrl+B` | 批量处理 |
| `Ctrl+Q` | 退出程序 |
| `Delete` | 删除最后一个选区 |
| `Escape` | 取消选区操作 |

### 批量处理

1. 点击"批量处理"按钮或使用 `Ctrl+B`
2. 添加需要处理的图片文件
3. 选择输出目录和图片质量
4. 点击"开始处理"

批量处理会使用当前选中的算法和水印区域设置（如果已设置）应用到所有图片。

## 项目结构

```
watermark_remover/
├── __init__.py                # 包初始化
├── main.py                    # 程序入口（含图标设置）
├── logo.png                   # 应用图标
├── core/
│   ├── __init__.py
│   ├── algorithms.py          # 5 种去水印算法实现
│   └── image_processor.py     # 图像加载、处理、历史管理（撤销/重做）
├── gui/
│   ├── __init__.py
│   ├── main_window.py         # 主窗口 GUI（ImageViewer/PanZoomLabel/CompareView 等）
│   └── styles.py              # 全局样式表
└── utils/
    ├── __init__.py
    └── helpers.py             # 工具函数（含 resource_path 资源路径解析）
run.py                         # 启动脚本
build.py                       # 一键打包脚本（PyInstaller）
build_dmg.sh                   # macOS DMG 安装包制作脚本
WatermarkRemover.spec          # PyInstaller 规格文件
requirements.txt               # Python 依赖列表
```

## 算法说明

### OpenCV 修复 (Telea)
基于 Fast Marching Method (FMM) 算法，从水印区域边缘向内部逐步修复，适合较小面积的文字水印。

### OpenCV 修复 (NS)
基于 Navier-Stokes 流体力学方程，通过等照度线（isophotes）方向引导修复，适合边缘丰富的区域。

### 区域覆盖
用周围像素的平均值或中位数直接覆盖水印区域，适合纯色或渐变背景上的水印。

### 纹理合成
基于块匹配的 Criminisi 算法简化版，从图像已知区域寻找最佳匹配纹理块进行填充。

### AI 智能修复
结合 Telea 和 NS 两种修复算法，并应用边缘感知的平滑处理和自适应颜色匹配。

## 跨平台说明

本工具使用纯 Python 开发，核心依赖（PyQt5、OpenCV、Pillow）均支持主流操作系统：

- **Windows**：已测试 Windows 10/11
- **macOS**：需要安装 Python 3.8+
- **Linux**：需要安装 Python 3.8+ 及系统 GUI 支持

## 打包为可执行文件

> 使用 `build.py` 或 `WatermarkRemover.spec` 可将本工具打包为各平台可直接运行的可执行文件，无需安装 Python 环境。

### 前置要求

```bash
pip install pyinstaller
```

### 方法一：使用打包脚本（推荐）

```bash
# 标准打包（输出为目录，启动更快）
python build.py

# 单文件打包（方便分发，但体积稍大、启动稍慢）
python build.py --onefile

# 打包前清理临时文件
python build.py --clean

# 自定义应用名和输出目录
python build.py --name 去水印工具 --onefile

python build.py --name 去水印工具 --onefile --clean --icon watermark_remover\logo.ico
```

### 方法二：使用 spec 文件

```bash
pyinstaller WatermarkRemover.spec
```

### 各平台输出

| 平台 | 输出路径 |
|------|----------|
| **Windows** | `dist/WatermarkRemover/WatermarkRemover.exe` |
| **macOS** | `dist/WatermarkRemover.app` |
| **Linux** | `dist/WatermarkRemover/WatermarkRemover` |

### 制作 macOS DMG 安装包 (可选)

macOS 用户可使用 `build_dmg.sh` 将 `.app` 进一步打包为可分发的 DMG 安装包，窗口化布局含 `/Applications` 软链接，用户双击挂载后拖入即可安装。

```bash
brew install create-dmg    # 一次性安装
./build_dmg.sh             # 默认: 运行 build.py 后再打 DMG
./build_dmg.sh --skip-build # 仅生成 DMG
```

输出文件: `dist/WatermarkRemover.dmg`

### 注意事项

- 首次打包需下载依赖，耗时 2-5 分钟
- OpenCV 体积较大（~40MB），最终打包约 80-150MB，属正常范围
- 建议在目标平台上打包（如在 Windows 上打包 Windows 版本），避免跨平台兼容问题
- `logo.png` 会自动通过 `--add-data` 打包进可执行文件，运行时通过 `resource_path()` 正确加载
- 如杀毒软件误报，可添加数字签名或提交白名单

## 关于

- **作者**：luojt
- **联系邮箱**：1337843618@qq.com
- **版本**：v1.0

## 许可证

MIT License