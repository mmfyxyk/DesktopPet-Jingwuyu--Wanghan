"""源代码压缩包打包

生成 release/DesktopPet-Source-{version}.zip（不含虚拟环境、构建产物、临时文件）。
用于：发布到 GitHub Release 的源码包（虽然 GitHub 会自动生成 Source code.zip，
但手动打包可以自定义排除项，比如排除 assets-collect/、试验素材等）。

用法：
    python scripts/build_source.py
    python scripts/build_source.py --version 1.0.0
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import zipfile
from datetime import datetime
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPTS_DIR.parent
RELEASE_DIR = PROJECT_ROOT / 'release'

DEFAULT_VERSION = '0.0.0'


# —— 打包时排除的目录/文件 ——
EXCLUDE_DIRS = {
    '.venv', 'venv',                 # 虚拟环境
    'dist', 'build', 'release',      # 构建产物
    '__pycache__', '.pytest_cache',  # Python 缓存
    '.git',                          # git 仓库
    '.idea', '.vscode',              # IDE 配置
    'assets-collect',                # 素材收集工具（不属于项目）
    'assets',                        # 素材目录（试验素材，发布前替换/移除）
    'support',                       # 外部工具（ffmpeg/Chrome，体积大，发布包内自带）
    'data',                          # 运行时数据（cookies/设置/历史，含隐私）
    'output',                        # 爬虫下载的视频
    '.trae',                         # AI 配置
    'scripts',
}

EXCLUDE_FILES = {
    '.gitignore', '.gitattributes',
    '*.pyc', '*.pyo', '*.egg-info',
    '.DS_Store', 'Thumbs.db', 'desktop.ini',
}


def _print_step(msg: str) -> None:
    print(f"\n>>> {msg}")


def _print_ok(msg: str) -> None:
    print(f"    [OK] {msg}")


def get_version_from_spec() -> str:
    """从 pet.spec 读取版本号"""
    import re
    spec_file = SCRIPTS_DIR / 'pet.spec'
    content = spec_file.read_text(encoding='utf-8')
    m = re.search(r'^VERSION\s*=\s*["\']([^"\']+)["\']', content, re.MULTILINE)
    return m.group(1) if m else DEFAULT_VERSION


def should_exclude(name: str) -> bool:
    """判断目录/文件是否应该排除"""
    if name in EXCLUDE_DIRS:
        return True
    for ext in EXCLUDE_FILES:
        if name.endswith(ext.lstrip('*')):
            return True
    return False


def create_source_zip(version: str) -> Path:
    """打包源代码 zip"""
    _print_step("打包源代码 zip")

    RELEASE_DIR.mkdir(parents=True, exist_ok=True)
    zip_path = RELEASE_DIR / f'DesktopPet-Source-{version}.zip'

    if zip_path.exists():
        zip_path.unlink()

    # 根目录名（zip 内部的顶层文件夹）
    root_name = f'DesktopPet-{version}'

    added = 0
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
        for file_path in PROJECT_ROOT.rglob('*'):
            # 跳过目录（只打包文件）
            if file_path.is_dir():
                continue

            # 计算相对路径
            rel = file_path.relative_to(PROJECT_ROOT)
            parts = rel.parts

            # 检查是否在排除目录内
            if any(should_exclude(p) for p in parts):
                continue

            # 写入 zip（顶层加版本目录名）
            arcname = Path(root_name) / rel
            zf.write(file_path, arcname)
            added += 1

    size_mb = zip_path.stat().st_size / (1024 * 1024)
    _print_ok(f"{zip_path.name}（{size_mb:.1f} MB，{added} 个文件）")
    return zip_path


def main() -> int:
    parser = argparse.ArgumentParser(description='桌面电子宠物 - 源代码压缩包打包')
    parser.add_argument('--version', default=None,
                        help='版本号（默认：git tag 或日期 YYYYMMDD）')
    args = parser.parse_args()

    print("=" * 60)
    print("  桌面电子宠物 - 源代码压缩包打包")
    print("=" * 60)

    version = args.version or get_version_from_spec()
    print(f"  版本号：{version}")

    try:
        create_source_zip(version)
    except Exception as e:
        print(f"\n    [失败] {type(e).__name__}: {e}", file=sys.stderr)
        return 1

    print("\n" + "=" * 60)
    print("  源代码打包完成！")
    print("=" * 60)
    return 0


if __name__ == '__main__':
    sys.exit(main())
