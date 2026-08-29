"""一键打包三个产物（主入口）

依次执行：
    1. build_exe.py       → dist/pet/pet.exe         （代码打包）
    2. build_portable.py  → release/DesktopPet-Portable-{version}.zip  （绿色版）
    3. build_installer.py → release/DesktopPet-Setup-{version}.exe    （安装包）

用法：
    python scripts/build_all.py
    python scripts/build_all.py --version 1.0.0
    python scripts/build_all.py --skip exe         # 跳过代码打包，复用已有 dist/pet/
    python scripts/build_all.py --only portable    # 只生成绿色版
    python scripts/build_all.py --only installer   # 只生成安装包

前置条件：
    pip install pyinstaller
    已安装 Inno Setup 6+（仅安装包需要）

产物汇总：
    release/
    ├── DesktopPet-Portable-{version}.zip   （绿色版，解压即用）
    └── DesktopPet-Setup-{version}.exe     （安装包，向导式安装）
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

DEFAULT_VERSION = datetime.now().strftime('%Y%m%d')


# ============================== 工具函数 ==============================

def _print_step(msg: str) -> None:
    print(f"\n>>> {msg}")


def _print_ok(msg: str) -> None:
    print(f"    [OK] {msg}")


def _print_err(msg: str) -> None:
    print(f"    [失败] {msg}", file=sys.stderr)


def get_version_from_git() -> str:
    """优先使用 git tag 作为版本号"""
    try:
        proc = subprocess.run(
            ['git', 'describe', '--tags', '--always'],
            cwd=str(PROJECT_ROOT),
            capture_output=True, text=True, timeout=5,
        )
        if proc.returncode == 0 and proc.stdout.strip():
            return proc.stdout.strip()
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    return DEFAULT_VERSION


def run_script(script_name: str, version: str, skip_build: bool = False) -> int:
    """调用 scripts/ 下的另一个打包脚本

    :param script_name: 脚本文件名（如 build_exe.py）
    :param version: 版本号（None 表示不传 --version）
    :param skip_build: 是否传 --skip-build（仅 portable/installer 支持）
    :return: 子进程退出码
    """
    script_path = SCRIPTS_DIR / script_name
    if not script_path.is_file():
        _print_err(f"未找到脚本：{script_path}")
        return 1

    cmd = [sys.executable, str(script_path)]
    if version:
        cmd.extend(['--version', version])
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
    parser.add_argument('--version', default=None,
                        help='版本号（默认：git tag 或日期 YYYYMMDD）')
    parser.add_argument('--skip', choices=['exe', 'portable', 'installer'],
                        help='跳过指定阶段（exe=代码打包, portable=绿色版, installer=安装包）')
    parser.add_argument('--only', choices=['exe', 'portable', 'installer'],
                        help='只执行指定阶段')
    args = parser.parse_args()

    print("=" * 60)
    print("  桌面电子宠物 - 一键打包（代码打包 + 绿色版 + 安装包）")
    print("=" * 60)

    version = args.version or get_version_from_git()
    print(f"  版本号：{version}\n")

    # —— 决定执行哪些阶段 ——
    stages = ['exe', 'portable', 'installer']
    if args.only:
        stages = [args.only]
    elif args.skip:
        stages = [s for s in stages if s != args.skip]

    failures = []
    exe_built = False

    for stage in stages:
        if stage == 'exe':
            ret = run_script('build_exe.py', version)
            if ret != 0:
                failures.append('exe')
                break              # exe 失败，后续阶段无意义
            exe_built = True

        elif stage == 'portable':
            # 如果 exe 已在本轮跑过，跳过 portable 内部重复调用 build_exe
            skip_build = exe_built or args.skip == 'exe' or (args.only and args.only != 'exe')
            ret = run_script('build_portable.py', version, skip_build=skip_build)
            if ret != 0:
                failures.append('portable')

        elif stage == 'installer':
            skip_build = exe_built or args.skip == 'exe' or (args.only and args.only != 'exe')
            ret = run_script('build_installer.py', version, skip_build=skip_build)
            if ret != 0:
                failures.append('installer')

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
