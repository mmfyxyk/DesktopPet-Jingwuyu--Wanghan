"""一键打包三个产物（主入口）

依次执行：
    1. build_exe.py       → dist/pet/pet.exe                                 （代码打包）
    2. build_portable.py  → release/DesktopPet-Portable-{version}.zip        （绿色版）
    3. build_installer.py → release/DesktopPet-Setup-{version}.exe           （安装包）
    4. build_source.py    → release/DesktopPet-Source-{version}.zip          （源代码压缩包）

用法：
    python scripts/build_all.py
    python scripts/build_all.py --skip exe         # 跳过代码打包，复用已有 dist/pet/
    python scripts/build_all.py --only portable    # 只生成绿色版
    python scripts/build_all.py --only installer   # 只生成安装包
    python scripts/build_all.py --only source      # 只生成源代码压缩包

版本号来源：pet.spec 中的 VERSION 常量（改版本号 → 改 pet.spec）

前置条件：
    pip install pyinstaller
    已安装 Inno Setup 6+（仅安装包需要）

产物汇总：
    release/
    ├── DesktopPet-Portable-{version}.zip   （绿色版，解压即用）
    ├── DesktopPet-Setup-{version}.exe      （安装包，向导式安装）
    └── DesktopPet-Source-{version}.zip     （源代码压缩包，含全部源码）
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from datetime import datetime
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPTS_DIR.parent
RELEASE_DIR = PROJECT_ROOT / 'release'

DEFAULT_VERSION = '0.0.0'


# ============================== 工具函数 ==============================

def _print_step(msg: str) -> None:
    print(f"\n>>> {msg}")


def _print_ok(msg: str) -> None:
    print(f"    [OK] {msg}")


def _print_err(msg: str) -> None:
    print(f"    [失败] {msg}", file=sys.stderr)


def get_version_from_spec() -> str:
    """从 pet.spec 读取版本号（所有子脚本也从各自配置文件读取，不再传递）"""
    import re
    spec_file = SCRIPTS_DIR / 'pet.spec'
    content = spec_file.read_text(encoding='utf-8')
    m = re.search(r'^VERSION\s*=\s*["\']([^"\']+)["\']', content, re.MULTILINE)
    return m.group(1) if m else DEFAULT_VERSION


def run_script(script_name: str, skip_build: bool = False) -> int:
    """调用 scripts/ 下的另一个打包脚本（版本号由各脚本从 spec/iss 读取）"""
    script_path = SCRIPTS_DIR / script_name
    if not script_path.is_file():
        _print_err(f"未找到脚本：{script_path}")
        return 1

    cmd = [sys.executable, str(script_path)]
    if skip_build:
        cmd.append('--skip-build')

    _print_step(f"调用 {script_name}")
    print(f"    执行命令：{' '.join(cmd)}")
    return subprocess.call(cmd)


def print_summary(version: str) -> None:
    """打印 release/ 目录的产物清单"""
    _print_step("产物汇总")
    if not RELEASE_DIR.is_dir():
        _print_err(f"release 目录不存在：{RELEASE_DIR}")
        return

    print("    release/")
    for item in sorted(RELEASE_DIR.iterdir()):
        if item.is_file():
            size_mb = item.stat().st_size / (1024 * 1024)
            print(f"    ├── {item.name}  ({size_mb:.1f} MB)")


# ============================== 主流程 ==============================

def main() -> int:
    parser = argparse.ArgumentParser(description='桌面电子宠物 - 一键打包三个产物')
    parser.add_argument('--skip', choices=['exe', 'portable', 'installer', 'source'],
                        help='跳过指定阶段（exe=代码打包, portable=绿色版, installer=安装包, source=源码包）')
    parser.add_argument('--only', choices=['exe', 'portable', 'installer', 'source'],
                        help='只执行指定阶段')
    args = parser.parse_args()

    print("=" * 60)
    print("  桌面电子宠物 - 一键打包（代码打包 + 绿色版 + 安装包）")
    print("=" * 60)

    version = get_version_from_spec()
    print(f"  版本号：{version}\n")

    # —— 决定执行哪些阶段 ——
    stages = ['exe', 'portable', 'installer', 'source']
    if args.only:
        stages = [args.only]
    elif args.skip:
        stages = [s for s in stages if s != args.skip]

    failures = []
    exe_built = False

    for stage in stages:
        if stage == 'exe':
            ret = run_script('build_exe.py')
            if ret != 0:
                failures.append('exe')
                break              # exe 失败，后续阶段无意义
            exe_built = True

        elif stage == 'portable':
            skip_build = exe_built or args.skip == 'exe' or (args.only and args.only != 'exe')
            ret = run_script('build_portable.py', skip_build=skip_build)
            if ret != 0:
                failures.append('portable')

        elif stage == 'installer':
            skip_build = exe_built or args.skip == 'exe' or (args.only and args.only != 'exe')
            ret = run_script('build_installer.py', skip_build=skip_build)
            if ret != 0:
                failures.append('installer')

        elif stage == 'source':
            ret = run_script('build_source.py')
            if ret != 0:
                failures.append('source')

    print_summary(version)

    print("\n" + "=" * 60)
    if not failures:
        print("  全部打包完成！")
    else:
        print(f"  以下阶段失败：{', '.join(failures)}")
        print("  详见上方日志。")
    print("=" * 60)

    return 0 if not failures else 1


if __name__ == '__main__':
    sys.exit(main())
