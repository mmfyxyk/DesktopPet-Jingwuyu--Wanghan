"""安装包打包脚本（第三步）- 调用 Inno Setup 编译 iss 生成 setup.exe

产物：
    release/DesktopPet-Setup-{version}.exe

设计要点：
    * 自动探测 Inno Setup 编译器（ISCC.exe）的安装位置
    * 通过命令行参数覆盖 iss 中的 MyAppVersion，让产物带正确版本号
    * 失败时给出详细的修复建议

用法：
    python scripts/build_installer.py
    python scripts/build_installer.py --version 1.2.0
    python scripts/build_installer.py --skip-build   # 跳过 build_exe.py

前置条件：
    * 已安装 Inno Setup 6+（https://jrsoftware.org/isdl.php）
    * 已执行 build_exe.py 生成 dist/pet/
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import winreg
from datetime import datetime
from pathlib import Path
from typing import Optional

SCRIPTS_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPTS_DIR.parent
ISS_FILE = SCRIPTS_DIR / 'build_installer.iss'
DIST_PET_DIR = PROJECT_ROOT / 'dist' / 'pet'
RELEASE_DIR = PROJECT_ROOT / 'release'

DEFAULT_VERSION = '0.0.0'


# ============================== 工具函数 ==============================

def _print_step(msg: str) -> None:
    print(f"\n>>> {msg}")


def _print_ok(msg: str) -> None:
    print(f"    [OK] {msg}")


def _print_err(msg: str) -> None:
    print(f"    [失败] {msg}", file=sys.stderr)


def get_version_from_iss() -> str:
    """从 build_installer.iss 读取版本号"""
    import re
    content = ISS_FILE.read_text(encoding='utf-8')
    m = re.search(r'#define MyAppVersion\s+"([^"]+)"', content)
    return m.group(1) if m else DEFAULT_VERSION


def find_iscc() -> Optional[str]:
    r"""探测 Inno Setup 编译器 ISCC.exe 路径

    探测顺序：
      1. PATH 环境变量（shutil.which）
      2. 注册表 HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\*
         里找 Inno Setup 的安装目录
      3. 常见安装路径兜底（Program Files、Program Files (x86)）
    """
    _print_step("探测 Inno Setup 编译器 (ISCC.exe)")

    # 方式 1：PATH
    iscc = shutil.which('ISCC') or shutil.which('iscc')
    if iscc:
        _print_ok(f"PATH 找到：{iscc}")
        return iscc

    # 方式 2：注册表（Inno Setup 6 + 7）
    candidates = [
        (winreg.HKEY_LOCAL_MACHINE,
         r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\Inno Setup 7_is1",
         "InstallLocation"),
        (winreg.HKEY_LOCAL_MACHINE,
         r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\Inno Setup 7_is1",
         "InstallLocation"),
        (winreg.HKEY_CURRENT_USER,
         r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\Inno Setup 7_is1",
         "InstallLocation"),
        (winreg.HKEY_LOCAL_MACHINE,
         r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\Inno Setup 6_is1",
         "InstallLocation"),
        (winreg.HKEY_LOCAL_MACHINE,
         r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\Inno Setup 6_is1",
         "InstallLocation"),
        (winreg.HKEY_CURRENT_USER,
         r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\Inno Setup 6_is1",
         "InstallLocation"),
    ]
    for hive, key_path, val_name in candidates:
        try:
            with winreg.OpenKey(hive, key_path) as key:
                install_loc, _ = winreg.QueryValueEx(key, val_name)
                if install_loc:
                    iscc_path = Path(install_loc) / 'ISCC.exe'
                    if iscc_path.is_file():
                        _print_ok(f"注册表找到：{iscc_path}")
                        return str(iscc_path)
        except FileNotFoundError:
            continue
        except OSError:
            continue

    # 方式 3：常见安装路径（Inno Setup 6 + 7）
    common_paths = [
        r"C:\Program Files\Inno Setup 7\ISCC.exe",
        r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
        r"C:\Program Files\Inno Setup 6\ISCC.exe",
        r"D:\Program Files\Inno Setup 7\ISCC.exe",
        r"D:\Program Files (x86)\Inno Setup 6\ISCC.exe",
        r"D:\Program Files\Inno Setup 6\ISCC.exe",
        r"E:\Program Files\Inno Setup 7\ISCC.exe",
        r"E:\Program Files (x86)\Inno Setup 6\ISCC.exe",
        r"E:\Program Files\Inno Setup 6\ISCC.exe",
    ]
    for p in common_paths:
        if Path(p).is_file():
            _print_ok(f"默认路径找到：{p}")
            return p

    _print_err("未找到 ISCC.exe")
    print(
        "    请确认已安装 Inno Setup 6+：\n"
        "      下载页：https://jrsoftware.org/isdl.php\n"
        "      安装后如未自动加入 PATH，可手动把 ISCC.exe 全路径传给本脚本：\n"
        '        python scripts/build_installer.py --iscc "C:\\Program Files\\Inno Setup 7\\ISCC.exe"'
    )
    return None


def run_build_exe() -> None:
    """调用第一步：build_exe.py"""
    _print_step("调用 build_exe.py 生成 exe")
    build_exe_script = SCRIPTS_DIR / 'build_exe.py'
    if not build_exe_script.is_file():
        raise SystemExit(f"未找到 build_exe.py：{build_exe_script}")

    ret = subprocess.call([sys.executable, str(build_exe_script)])
    if ret != 0:
        raise SystemExit(f"build_exe.py 失败，退出码 {ret}")
    _print_ok("exe 已生成")


def verify_pet_dist() -> None:
    """校验 PyInstaller 产物存在"""
    _print_step("校验 PyInstaller 产物")
    exe_path = DIST_PET_DIR / 'pet.exe'
    if not exe_path.is_file():
        raise SystemExit(
            f"未找到 {exe_path}\n"
            f"请先执行：python scripts/build_exe.py"
        )
    internal = DIST_PET_DIR / '_internal'
    if not internal.is_dir():
        print(f"    [警告] 未找到 {internal.relative_to(PROJECT_ROOT)}，"
              f"安装包可能不完整")
    _print_ok(f"找到 {exe_path.relative_to(PROJECT_ROOT)}")


def run_iscc(iscc_path: str) -> Path:
    """调用 ISCC.exe 编译 iss 文件（元数据由 iss #define 内联，无需 /D 传参）"""
    version = get_version_from_iss()
    _print_step(f"调用 ISCC 编译安装包（版本：{version}）")

    RELEASE_DIR.mkdir(parents=True, exist_ok=True)

    cmd = [iscc_path, "/Q", str(ISS_FILE)]
    print(f"    执行命令：{' '.join(cmd)}")

    proc = subprocess.run(
        cmd,
        cwd=str(PROJECT_ROOT),
        capture_output=True,
        text=True,
        encoding='gbk',
        errors='replace',
    )

    if proc.returncode != 0:
        print(proc.stdout, file=sys.stdout)
        print(proc.stderr, file=sys.stderr)
        raise SystemExit(f"ISCC 编译失败，退出码 {proc.returncode}")

    if proc.stdout.strip():
        print(proc.stdout)

    setup_exe = RELEASE_DIR / f'DesktopPet-Setup-{version}.exe'
    if not setup_exe.is_file():
        raise SystemExit(f"编译成功但未找到产物：{setup_exe}")

    size_mb = setup_exe.stat().st_size / (1024 * 1024)
    _print_ok(f"{setup_exe.relative_to(PROJECT_ROOT)}（{size_mb:.1f} MB）")
    return setup_exe


# ============================== 主流程 ==============================

def main() -> int:
    parser = argparse.ArgumentParser(description='桌面电子宠物 - 安装包打包 (Inno Setup)')
    parser.add_argument('--iscc', default=None,
                        help='手动指定 ISCC.exe 路径（自动探测失败时使用）')
    parser.add_argument('--skip-build', action='store_true',
                        help='跳过 build_exe.py，直接使用 dist/pet/ 已有产物')
    args = parser.parse_args()

    print("=" * 60)
    print("  桌面电子宠物 - 第三步：安装包打包 (Inno Setup)")
    print("=" * 60)

    iscc_path = args.iscc or find_iscc()
    if not iscc_path:
        return 1

    version = get_version_from_iss()
    print(f"  版本号：{version}")

    RELEASE_DIR.mkdir(parents=True, exist_ok=True)

    try:
        if not args.skip_build:
            run_build_exe()
        else:
            print("\n>>> 跳过 build_exe.py（--skip-build）")
        verify_pet_dist()
        run_iscc(iscc_path)
    except SystemExit:
        raise
    except Exception as e:
        _print_err(f"未知异常：{type(e).__name__}: {e}")
        return 1

    print("\n" + "=" * 60)
    print("  安装包打包完成！")
    print(f"  产物：release/DesktopPet-Setup-{version}.exe")
    print("=" * 60)
    return 0


if __name__ == '__main__':
    sys.exit(main())
