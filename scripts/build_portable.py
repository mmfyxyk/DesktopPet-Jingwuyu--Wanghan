"""绿色版打包脚本（第二步）- 生成解压即用的 zip 包

产物：
    release/DesktopPet-Portable-{version}.zip

绿色版内容：
    DesktopPet/
    ├── pet.exe                    # 主程序（PyInstaller 产物）
    ├── _internal/                # PySide6 / Python 依赖
    ├── assets/                   # 已打包进 exe，但额外保留一份方便用户替换素材（可选）
    ├── support/                  # 外部工具（打包时自动从项目 support/ 一起拷贝）
    │   ├── ffmpeg/ffmpeg.exe     # 视频合并（开发机准备好→直接拷过来）
    │   ├── Chrome/chrome.exe     # 便携 Chrome（抖音登录用）
    │   └── README.md             # 外部工具说明
    ├── data/                     # 运行时数据（自动创建）
    ├── output/                   # 爬虫输出（自动创建）
    └── 启动宠物.bat               # 双击启动（避免用户找 pet.exe）

用法：
    python scripts/build_portable.py
    python scripts/build_portable.py --version 1.0.0     # 指定版本号
    python scripts/build_portable.py --skip-build        # 跳过 build_exe.py
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import zipfile
from datetime import datetime
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPTS_DIR.parent
DIST_DIR = PROJECT_ROOT / 'dist'
PET_DIST_DIR = DIST_DIR / 'pet'
RELEASE_DIR = PROJECT_ROOT / 'release'
SUPPORT_DIR_SRC = PROJECT_ROOT / 'support'        # 项目里的 support/（含 ffmpeg/Chrome 等外部工具）

# 默认版本号：若 git 有 tag 用 tag，否则用日期
DEFAULT_VERSION = '1.0.0'


# ============================== 工具函数 ==============================

def _print_step(msg: str) -> None:
    print(f"\n>>> {msg}")


def _print_ok(msg: str) -> None:
    print(f"    [OK] {msg}")


def _print_err(msg: str) -> None:
    print(f"    [失败] {msg}", file=sys.stderr)


# 拷贝 support/ 时排除的目录/文件——防止把开发机的 Chrome 登录态（cookies、
# 历史记录、缓存等）带进发布包泄露隐私
_EXCLUDE_DIRS = {
    'profile-douyin',      # 抖音爬虫登录后的 Chrome 用户资料（含 cookies/历史/缓存）
    'profile-*',           # 万一以后有其它 Profile-* 也一并排除
    'default',             # Chrome 默认 Profile（开发机残留）
    'cache', 'code cache',  # 缓存目录
    'gpucache',
    '__pycache__',
    '.git',
}
_EXCLUDE_FILES = {
    '.gitkeep',
    'thumbs.db', 'desktop.ini',
}


def _support_ignore(directory: str, names: list[str]) -> set[str]:
    """shutil.copytree 的 ignore 回调：排除 Chrome 用户数据等敏感内容"""
    excluded = set()
    for name in names:
        lower = name.lower()
        # 排除 Profile-* 模式
        if lower.startswith('profile-') or lower in _EXCLUDE_DIRS:
            excluded.add(name)
        elif lower in _EXCLUDE_FILES:
            excluded.add(name)
        # 排除 cookies / 登录态等敏感文件（如果出现在 Chrome 根目录）
        elif lower in ('cookies', 'cookies-journal', 'login data',
                       'login data-journal', 'web data', 'history',
                       'history-journal', 'preferences', 'secure preferences'):
            excluded.add(name)
    return excluded


def get_version_from_spec() -> str:
    """从 pet.spec 读取版本号"""
    import re
    spec_file = SCRIPTS_DIR / 'pet.spec'
    content = spec_file.read_text(encoding='utf-8')
    m = re.search(r'^VERSION\s*=\s*["\']([^"\']+)["\']', content, re.MULTILINE)
    return m.group(1) if m else DEFAULT_VERSION


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
    exe_path = PET_DIST_DIR / 'pet.exe'
    if not exe_path.is_file():
        raise SystemExit(
            f"未找到 {exe_path}\n"
            f"请先执行：python scripts/build_exe.py"
        )
    _print_ok(f"找到 {exe_path.relative_to(PROJECT_ROOT)}")


def prepare_staging(version: str) -> Path:
    """准备绿色版暂存目录，返回暂存根目录路径"""
    _print_step(f"准备绿色版暂存目录（版本：{version}）")

    staging_root = RELEASE_DIR / 'staging'
    app_root = staging_root / 'DesktopPet'

    # 清空旧暂存
    if staging_root.exists():
        shutil.rmtree(staging_root, ignore_errors=True)
    app_root.mkdir(parents=True, exist_ok=True)
    _print_ok(f"暂存目录：{app_root.relative_to(PROJECT_ROOT)}")

    # —— 拷贝 PyInstaller 产物 ——
    _print_step("拷贝 PyInstaller 产物")
    for item in PET_DIST_DIR.iterdir():
        target = app_root / item.name
        if item.is_dir():
            shutil.copytree(item, target)
        else:
            shutil.copy2(item, target)
        _print_ok(f"  {item.name}")

    # —— 拷贝 support/（整个目录，含 ffmpeg/Chrome 等外部工具） ——
    # 排除 Chrome 用户数据（Profile-Douyin 含 cookies/历史记录等，不能带进发布包）
    _print_step("拷贝 support/ 外部工具目录（排除 Chrome 用户数据）")
    support_dst = app_root / 'support'
    if SUPPORT_DIR_SRC.is_dir():
        # PyInstaller 产物里可能有个空的 support 占位目录，先删掉再拷
        if support_dst.exists():
            shutil.rmtree(support_dst, ignore_errors=True)
        shutil.copytree(SUPPORT_DIR_SRC, support_dst, ignore=_support_ignore)
        # 统计拷贝了哪些内容
        for item in sorted(support_dst.iterdir()):
            _print_ok(f"  support/{item.name}")
        # 确保 Chrome/ 目录存在（即使用户数据被排除，目录结构要保留）
        chrome_dst = support_dst / 'Chrome'
        chrome_dst.mkdir(exist_ok=True)
    else:
        support_dst.mkdir(exist_ok=True)
        _print_ok("support 源目录不存在，仅创建空目录（请开发机先准备好 support/ffmpeg + support/Chrome）")

    # —— 创建 data/、output/ 占位 ——
    _print_step("创建 data/、output/ 占位目录")
    for sub in ('data', 'output'):
        d = app_root / sub
        d.mkdir(exist_ok=True)
        gitkeep = d / '.gitkeep'
        if not gitkeep.exists():
            gitkeep.write_text('', encoding='utf-8')
        _print_ok(f"  {sub}/.gitkeep")

    # —— 写入「启动宠物.bat」 ——
    _print_step("写入启动脚本 启动宠物.bat")
    _write_launcher_bat(app_root)

    # —— 写入 README.txt（绿色版使用说明） ——
    _print_step("写入 README.txt")
    _write_portable_readme(app_root, version)

    return app_root


def _write_launcher_bat(app_root: Path) -> None:
    """生成双击启动的 bat 脚本"""
    bat_path = app_root / '启动宠物.bat'
    bat_path.write_text(
        '@echo off\n'
        'chcp 65001 >nul\n'
        'cd /d "%~dp0"\n'
        'start "" "pet.exe"\n',
        encoding='gbk',   # bat 文件在 Windows 下默认 GBK，避免乱码
    )


def _write_portable_readme(app_root: Path, version: str) -> None:
    """生成绿色版使用说明"""
    readme = app_root / 'README.txt'
    readme.write_text(
        f"桌面电子宠物（净无欲-王涵）绿色版 v{version}\n"
        f"{'=' * 50}\n\n"
        "【启动方法】\n"
        "  双击「启动宠物.bat」或直接双击 pet.exe\n\n"
        "【首次使用必看】\n"
        "  1. 爬虫所需的外部工具已内置，无需额外下载：\n"
        "     - support/ffmpeg/ffmpeg.exe   视频合并（已附带）\n"
        "     - support/Chrome/chrome.exe   便携 Chrome（已附带，抖音登录用）\n"
        "  2. 首次使用抖音爬虫：右键 → 拓展功能 → 抖音 → 登录（扫码）\n\n"
        "【目录说明】\n"
        "  - pet.exe        主程序\n"
        "  - _internal/     依赖文件（不要删）\n"
        "  - assets/        动画资源（可替换为你的素材）\n"
        "  - support/       外部工具（ffmpeg + Chrome，已附带）\n"
        "  - data/          运行时配置（自动生成）\n"
        "  - output/        爬虫下载的视频（自动生成）\n\n"
        "【隐私】\n"
        "  data/ 下的 cookies 文件属于登录态，请勿分享给别人。\n"
        "  可通过菜单：拓展功能 → 抖音 → 清除登录数据 一键清除。\n\n"
        "【卸载】\n"
        "  绿色版无需卸载，删除整个文件夹即可。\n\n"
        f"项目主页：https://github.com/mmfyxyk/DesktopPet-Jingwuyu--Wanghan\n",
        encoding='utf-8',
    )


def create_zip(app_root: Path, version: str) -> Path:
    """把暂存目录打包成 zip"""
    _print_step("打包 zip")

    RELEASE_DIR.mkdir(parents=True, exist_ok=True)
    zip_path = RELEASE_DIR / f'DesktopPet-Portable-{version}.zip'

    # 清掉旧 zip
    if zip_path.exists():
        zip_path.unlink()

    staging_root = app_root.parent
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for root, dirs, files in os.walk(app_root):
            for name in files:
                file_path = Path(root) / name
                # 相对 staging_root，让 zip 内顶层就是 DesktopPet/
                arcname = file_path.relative_to(staging_root)
                zf.write(file_path, arcname)

    size_mb = zip_path.stat().st_size / (1024 * 1024)
    _print_ok(f"{zip_path.relative_to(PROJECT_ROOT)}（{size_mb:.1f} MB）")
    return zip_path


def cleanup_staging() -> None:
    """清理暂存目录"""
    _print_step("清理暂存目录")
    staging_root = RELEASE_DIR / 'staging'
    if staging_root.exists():
        shutil.rmtree(staging_root, ignore_errors=True)
        _print_ok("已清理")


# ============================== 主流程 ==============================

def main() -> int:
    parser = argparse.ArgumentParser(description='桌面电子宠物 - 绿色版打包')
    parser.add_argument('--version', default=None,
                        help='版本号（默认：git tag 或日期 YYYYMMDD）')
    parser.add_argument('--skip-build', action='store_true',
                        help='跳过 build_exe.py，直接使用 dist/pet/ 已有产物')
    args = parser.parse_args()

    print("=" * 60)
    print("  桌面电子宠物 - 第二步：绿色版打包 (zip)")
    print("=" * 60)

    version = args.version or get_version_from_spec()
    print(f"  版本号：{version}")

    # 提前创建 release 目录，即使后续失败也存在
    RELEASE_DIR.mkdir(parents=True, exist_ok=True)

    try:
        if not args.skip_build:
            run_build_exe()
        else:
            print("\n>>> 跳过 build_exe.py（--skip-build）")
        verify_pet_dist()
        app_root = prepare_staging(version)
        zip_path = create_zip(app_root, version)
        cleanup_staging()
    except SystemExit:
        raise
    except Exception as e:
        _print_err(f"未知异常：{type(e).__name__}: {e}")
        return 1

    print("\n" + "=" * 60)
    print(f"  绿色版打包完成！")
    print(f"  产物：{zip_path.relative_to(PROJECT_ROOT)}")
    print("  下一步：python scripts/build_installer.py  # 生成安装包")
    print("=" * 60)
    return 0


if __name__ == '__main__':
    sys.exit(main())
