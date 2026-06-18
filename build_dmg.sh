#!/usr/bin/env bash
#
# 将 dist/WatermarkRemover.app 打包为可分发的 .dmg 安装包
#
# 前置条件:
#   1. macOS 系统
#   2. 已运行 `python build.py` 生成 dist/WatermarkRemover.app
#   3. 已安装 create-dmg: `brew install create-dmg`
#
# 使用方法:
#   ./build_dmg.sh                # 默认: 跑 build.py 后打 DMG
#   ./build_dmg.sh --skip-build   # 跳过 build.py, 仅生成 DMG
#   ./build_dmg.sh path/to/X.app  # 指定自定义 .app 路径
#

set -e

# --------------------------------------------------------
# 配置
# --------------------------------------------------------
APP_NAME="WatermarkRemover"
DMG_NAME="WatermarkRemover.dmg"
VOLUME_NAME="WatermarkRemover 安装器"

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_ROOT"

APP_PATH="dist/${APP_NAME}.app"
DMG_PATH="dist/${DMG_NAME}"
LOGO_ICNS="watermark_remover/logo.icns"
LICENSE_FILE="LICENSE.txt"

# --------------------------------------------------------
# 参数解析
# --------------------------------------------------------
SKIP_BUILD=false
while [[ $# -gt 0 ]]; do
    case "$1" in
        --skip-build)
            SKIP_BUILD=true
            shift
            ;;
        *.app)
            APP_PATH="$1"
            shift
            ;;
        -h|--help)
            echo "用法: $0 [--skip-build] [path/to/App.app]"
            exit 0
            ;;
        *)
            echo "未知参数: $1"
            exit 1
            ;;
    esac
done

# --------------------------------------------------------
# 平台检查
# --------------------------------------------------------
if [[ "$(uname -s)" != "Darwin" ]]; then
    echo "❌ 错误: 仅支持 macOS"
    exit 1
fi

# --------------------------------------------------------
# create-dmg 检查
# --------------------------------------------------------
if ! command -v create-dmg >/dev/null 2>&1; then
    echo "❌ create-dmg 未安装"
    echo "   安装: brew install create-dmg"
    exit 1
fi

echo "=========================================="
echo "  构建 ${APP_NAME} DMG 安装包"
echo "=========================================="
echo "  平台: $(uname -s) $(uname -m)"
echo "  create-dmg: $(create-dmg --version)"
echo

# --------------------------------------------------------
# 1. 运行 build.py (可选)
# --------------------------------------------------------
if [[ "$SKIP_BUILD" == false ]]; then
    echo "[1/4] 打包应用..."
    if [[ ! -f "build.py" ]]; then
        echo "❌ build.py 不存在"
        exit 1
    fi
    "${PYTHON:-python3}" build.py
    echo
fi

# --------------------------------------------------------
# 2. 校验 .app
# --------------------------------------------------------
echo "[2/4] 校验应用..."
if [[ ! -d "$APP_PATH" ]]; then
    echo "❌ 找不到应用: $APP_PATH"
    echo "   请先运行: python build.py"
    exit 1
fi
echo "  ✓ 应用路径: $APP_PATH"
echo "  ✓ 应用大小: $(du -sh "$APP_PATH" | cut -f1)"

# 自动生成缺失的资源 (首次运行时)
if [[ ! -f "$LOGO_ICNS" && -f "watermark_remover/logo.png" ]]; then
    echo "  • 自动生成 logo.icns..."
    if command -v sips >/dev/null 2>&1 && command -v iconutil >/dev/null 2>&1; then
        ICONSET_DIR="$(mktemp -d)/icon.iconset"
        mkdir -p "$ICONSET_DIR"
        sips -z 1024 1024 "watermark_remover/logo.png" \
            --out "${ICONSET_DIR}/icon_512x512@2x.png" >/dev/null 2>&1 || true
        sips -z 512 512 "watermark_remover/logo.png" \
            --out "${ICONSET_DIR}/icon_512x512.png" >/dev/null 2>&1 || true
        sips -z 512 512 "watermark_remover/logo.png" \
            --out "${ICONSET_DIR}/icon_256x256@2x.png" >/dev/null 2>&1 || true
        sips -z 256 256 "watermark_remover/logo.png" \
            --out "${ICONSET_DIR}/icon_256x256.png" >/dev/null 2>&1 || true
        sips -z 256 256 "watermark_remover/logo.png" \
            --out "${ICONSET_DIR}/icon_128x128@2x.png" >/dev/null 2>&1 || true
        sips -z 128 128 "watermark_remover/logo.png" \
            --out "${ICONSET_DIR}/icon_128x128.png" >/dev/null 2>&1 || true
        sips -z 64 64 "watermark_remover/logo.png" \
            --out "${ICONSET_DIR}/icon_32x32@2x.png" >/dev/null 2>&1 || true
        sips -z 32 32 "watermark_remover/logo.png" \
            --out "${ICONSET_DIR}/icon_32x32.png" >/dev/null 2>&1 || true
        sips -z 32 32 "watermark_remover/logo.png" \
            --out "${ICONSET_DIR}/icon_16x16@2x.png" >/dev/null 2>&1 || true
        sips -z 16 16 "watermark_remover/logo.png" \
            --out "${ICONSET_DIR}/icon_16x16.png" >/dev/null 2>&1 || true
        if iconutil -c icns "$ICONSET_DIR" -o "$LOGO_ICNS" 2>/dev/null; then
            echo "  ✓ 已生成: $LOGO_ICNS"
        else
            echo "  • iconutil 生成失败, 将跳过 --volicon"
            LOGO_ICNS=""
        fi
        rm -rf "$(dirname "$ICONSET_DIR")"
    else
        echo "  • sips/iconutil 不可用, 跳过 --volicon"
        LOGO_ICNS=""
    fi
fi

if [[ ! -f "$LICENSE_FILE" ]]; then
    echo "  • 生成默认 ${LICENSE_FILE}..."
    cat > "$LICENSE_FILE" <<EOF
${APP_NAME} License Agreement

This software is released under the MIT License.
You are free to use, modify, and distribute this software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND.

For the full license text, please refer to the LICENSE file
in the project repository.

By installing this software, you agree to the terms above.
EOF
    echo "  ✓ 已生成: $LICENSE_FILE"
fi

# --------------------------------------------------------
# 3. 清理旧 DMG
# --------------------------------------------------------
echo "[3/4] 清理旧产物..."
rm -f "$DMG_PATH"
ALT_DMG="$(dirname "$DMG_PATH")/$(basename "${APP_PATH}" .app).dmg"
rm -f "$ALT_DMG"

# --------------------------------------------------------
# 4. 生成 DMG
# --------------------------------------------------------
echo "[4/4] 生成 DMG..."

# 动态构建 create-dmg 命令, 资源缺失时自动降级
DMG_CMD=(create-dmg
    --volname "${VOLUME_NAME}"
    --window-pos 200 120
    --window-size 600 400
    --icon-size 100
    --icon "${APP_NAME}.app" 150 190
    --hide-extension "${APP_NAME}.app"
    --app-drop-link 450 185
)
[[ -f "$LOGO_ICNS" ]] && DMG_CMD+=(--volicon "${PROJECT_ROOT}/${LOGO_ICNS}")
[[ -f "$LICENSE_FILE" ]] && DMG_CMD+=(--eula "${PROJECT_ROOT}/${LICENSE_FILE}")

DMG_CMD+=("${DMG_PATH}" "${APP_PATH}")

"${DMG_CMD[@]}" 2>&1 | sed 's/^/  /'

# create-dmg 1.x 偶发返回非 0 但 DMG 已生成, 做存在性兜底
if [[ ! -f "$DMG_PATH" ]]; then
    if [[ -f "$ALT_DMG" ]]; then
        mv "$ALT_DMG" "$DMG_PATH"
        echo "  ✓ 重命名为: $DMG_PATH"
    else
        echo "❌ DMG 生成失败"
        exit 1
    fi
fi

echo
echo "=========================================="
echo "  ✅ DMG 生成成功"
echo "=========================================="
echo "  路径: ${PROJECT_ROOT}/${DMG_PATH}"
echo "  大小: $(du -sh "$DMG_PATH" | cut -f1)"
echo
echo "分发方式:"
echo "  - 直接将 ${DMG_NAME} 分发给最终用户"
echo "  - 用户双击挂载后将 ${APP_NAME}.app 拖入 /Applications 即可"
