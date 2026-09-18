"""代码打包脚本（第一步）- 调用 PyInstaller 生成 exe

产物：
    dist/pet/pet.exe
    dist/pet/_internal/   （PySide6、Python 等依赖）

设计要点：
    * 用 spec 文件而不是命令行参数，方便版本控制
    * --noconfirm：覆盖上次构建输出
    * --clean：清空 PyInstaller 缓存，避免旧 hook 残留导致打包异常
    * 打包前先校验环境（Python 版本、PyInstaller 是否安装）

用法：
    python scripts/build_exe.py

前置条件：
    pip install pyinstaller
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import shutil
from datetime import datetime
from pathlib import Path

# —— 路径常量 ——
SCRIPTS_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPTS_DIR.parent
SPEC_FILE = SCRIPTS_DIR / 'pet.spec'
DIST_DIR = PROJECT_ROOT / 'dist'
BUILD_DIR = PROJECT_ROOT / 'build'
PET_DIST_DIR = DIST_DIR / 'pet'          # 最终 exe 输出目录




# ============================== 工具函数 ==============================

def _print_step(msg: str) -> None:
    print(f"\n>>> {msg}")


def _print_ok(msg: str) -> None:
    print(f"    [OK] {msg}")


def _print_err(msg: str) -> None:
    print(f"    [失败] {msg}", file=sys.stderr)


def check_python_version() -> None:
    """校验 Python 版本（项目要求 3.13，至少 3.10 才能跑 PySide6）"""
    _print_step("校验 Python 版本")
    major, minor = sys.version_info[:2]
    if major < 3 or (major == 3 and minor < 10):
        raise SystemExit(
            f"Python 版本过低：当前 {major}.{minor}，至少需要 3.10"
        )
    _print_ok(f"Python {major}.{minor}")


def check_pyinstaller() -> str:
    """检查 PyInstaller 是否安装，返回其可执行路径"""
    _print_step("校验 PyInstaller")
    # 优先使用 venv 里的 pyinstaller
    pyinstaller = shutil.which('pyinstaller')
    if pyinstaller:
        _print_ok(f"找到 pyinstaller: {pyinstaller}")
        return pyinstaller

    # 兜底：通过 python -m 调用
    try:
        subprocess.run(
            [sys.executable, '-m', 'PyInstaller', '--version'],
            check=True, capture_output=True
        )
        cmd = f"{sys.executable} -m PyInstaller"
        _print_ok(f"通过 python -m 调用：{cmd}")
        return cmd
    except subprocess.CalledProcessError:
        raise SystemExit(
            "未安装 PyInstaller，请先执行：pip install pyinstaller"
        )


def check_spec_file() -> None:
    """校验 spec 文件存在"""
    _print_step("校验 spec 文件")
    if not SPEC_FILE.is_file():
        raise SystemExit(f"spec 文件不存在：{SPEC_FILE}")
    _print_ok(f"{SPEC_FILE.relative_to(PROJECT_ROOT)}")


def clean_old_output() -> None:
    """清理上次构建产物，避免文件残留"""
    _print_step("清理上次构建产物")
    for d in (PET_DIST_DIR, BUILD_DIR):
        if d.exists():
            shutil.rmtree(d, ignore_errors=True)
            _print_ok(f"已删除 {d.relative_to(PROJECT_ROOT)}")
        else:
            _print_ok(f"无需清理 {d.relative_to(PROJECT_ROOT)}（不存在）")


def run_pyinstaller(pyinstaller_cmd: str) -> None:
    """调用 PyInstaller 进行打包（版本信息由 pet.spec 内联，无需环境变量）"""
    _print_step("开始 PyInstaller 打包（首次可能需要 2-5 分钟）")

    if ' ' in pyinstaller_cmd:
        cmd = pyinstaller_cmd.split() + [
            str(SPEC_FILE),
            '--noconfirm',
            '--clean',
            '--distpath', str(DIST_DIR),
            '--workpath', str(BUILD_DIR),
        ]
    else:
        cmd = [
            pyinstaller_cmd,
            str(SPEC_FILE),
            '--noconfirm',
            '--clean',
            '--distpath', str(DIST_DIR),
            '--workpath', str(BUILD_DIR),
        ]

    print(f"    执行命令：{' '.join(cmd)}")

    proc = subprocess.Popen(
        cmd,
        cwd=str(PROJECT_ROOT),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding='utf-8',
        errors='replace',
        bufsize=1,
    )
    for line in proc.stdout:           # type: ignore
        sys.stdout.write(line)
        sys.stdout.flush()
    ret = proc.wait()
    if ret != 0:
        raise SystemExit(f"PyInstaller 打包失败，退出码 {ret}")


def verify_output() -> None:
    """校验打包产物"""
    _print_step("校验打包产物")
    exe_path = PET_DIST_DIR / 'pet.exe'
    if not exe_path.is_file():
        raise SystemExit(f"未找到产物：{exe_path}")
    size_mb = exe_path.stat().st_size / (1024 * 1024)
    _print_ok(f"{exe_path.relative_to(PROJECT_ROOT)}（{size_mb:.1f} MB）")

    # 校验 assets 是否打包进 _internal（PyInstaller 6.x 后 datas 落到 _internal）
    internal_dir = PET_DIST_DIR / '_internal'
    assets_check = internal_dir / 'assets'
    if not assets_check.is_dir():
        # 老版本 PyInstaller 直接落到 dist/pet/assets/
        assets_check = PET_DIST_DIR / 'assets'
    if assets_check.is_dir():
        _print_ok(f"assets 已打包：{assets_check.relative_to(PROJECT_ROOT)}")
    else:
        print("    [警告] 未找到打包后的 assets 目录，运行时可能无法加载资源")

    # 运行时目录占位（避免用户首次启动报错）
    for sub in ('data', 'output', 'support'):
        d = PET_DIST_DIR / sub
        d.mkdir(exist_ok=True)
        _print_ok(f"已创建占位目录：{d.relative_to(PROJECT_ROOT)}")


# ============================== 主流程 ==============================

def main() -> int:
    parser = argparse.ArgumentParser(description='桌面电子宠物 - 代码打包 (PyInstaller)')
    parser.add_argument('--version', default=None,
                        help='版本号（已内联在 pet.spec 中，请直接修改该文件）')
    args = parser.parse_args()

    print("=" * 60)
    print("  桌面电子宠物 - 第一步：代码打包 (PyInstaller)")
    print("=" * 60)

    # 如果命令行指定了版本号，提示用户去改 spec
    if args.version:
        print(f"  提示：版本号已内联在 pet.spec 中（VERSION = ...），请直接修改该文件")
        print(f"  传入的 --version={args.version} 将被忽略")

    try:
        check_python_version()
        pyinstaller_cmd = check_pyinstaller()
        check_spec_file()
        clean_old_output()
        run_pyinstaller(pyinstaller_cmd)
        verify_output()
    except SystemExit:
        raise
    except Exception as e:
        _print_err(f"未知异常：{type(e).__name__}: {e}")
        return 1

    print("\n" + "=" * 60)
    print(f"  打包完成！产物目录：{PET_DIST_DIR.relative_to(PROJECT_ROOT)}")
    print("  下一步：")
    print("    1) python scripts/build_portable.py --skip-build   # 生成绿色版 zip（跳过软件打包）")
    print("    2) python scripts/build_installer.py  # 生成安装包 exe")
    print("=" * 60)
    return 0


if __name__ == '__main__':
    sys.exit(main())
