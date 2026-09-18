# -*- mode: python ; coding: utf-8 -*-
"""桌面电子宠物 - PyInstaller spec 配置文件

打包策略（对应 docs/Desktop pet frame v2.md §6）：
    * 只读资源（assets/）通过 datas 打包进 exe，运行时从 sys._MEIPASS 读取
    * 运行时数据（data/、output/、support/）放在 exe 同目录，由 src/resource_manager.py 自动处理
    * 采用 onedir 模式：启动比 onefile 快很多，且排错方便
      （如后续需要 onefile，把 COLLECT 改成 EXE 即可，但启动时会解压到 temp）

用法：
    pyinstaller scripts/pet.spec --noconfirm --clean
或通过脚本：
    python scripts/build_exe.py
"""

import os
import sys

# spec 文件所在目录（scripts/），项目根目录是它的上一级
PROJECT_ROOT = os.path.abspath(os.path.join(SPECPATH, '..'))

# ============================== 元数据配置 ==============================
# 改产品名/公司名/版本号 → 改这里（build_installer.iss 也要同步改）
VERSION = "0.4.0.1"
PRODUCT_VERSION = "0.4.0"
PRODUCT_NAME = "净无欲-王涵桌面电子宠物"
COMPANY_NAME = "锐尘ruichen"
EXE_FILE_DESCRIPTION = "净无欲-王涵桌面电子宠物"
INTERNAL_NAME = "pet"
ORIGINAL_FILENAME = "pet.exe"
LEGAL_COPYRIGHT = "© 2025-2026 mmfyxyk. 基于 MIT License 开源。"

ASSETS_DIR = os.path.join(PROJECT_ROOT, 'assets')
APP_ICON = os.path.join(ASSETS_DIR, 'WangHan', 'JingWuyu', 'icons', 'app.ico')
icon_arg = APP_ICON if os.path.exists(APP_ICON) else None

block_cipher = None

from PyInstaller.utils.win32.versioninfo import (
    VSVersionInfo, FixedFileInfo, StringFileInfo,
    StringTable, StringStruct, VarFileInfo, VarStruct,
)

# ============================== 版本信息资源 ==============================
# 嵌入 pet.exe 的 VS_VERSIONINFO 资源块。
# 右键 pet.exe → 属性 → 详细信息 里看到的字段就来自这里。
# StringTable ID '080404B0'：0804=简体中文, 04B0=Unicode(1200的十六进制)

def _to_quad(v: str) -> tuple:
    parts = (v + '.0.0.0').split('.')[:4]
    try:
        return tuple(int(p) for p in parts)
    except ValueError:
        return (1, 0, 0, 0)

version_info = VSVersionInfo(
    ffi=FixedFileInfo(
        filevers=_to_quad(VERSION),
        prodvers=_to_quad(PRODUCT_VERSION),
        mask=0x3F,
        flags=0x0,
        OS=0x40004,
        fileType=0x1,
        subtype=0x0,
        date=(0, 0),
    ),
    kids=[
        StringFileInfo([
            StringTable('080404B0', [
                StringStruct('CompanyName', COMPANY_NAME),
                StringStruct('FileDescription', EXE_FILE_DESCRIPTION),
                StringStruct('FileVersion', VERSION),
                StringStruct('InternalName', INTERNAL_NAME),
                StringStruct('LegalCopyright', LEGAL_COPYRIGHT),
                StringStruct('OriginalFilename', ORIGINAL_FILENAME),
                StringStruct('ProductName', PRODUCT_NAME),
                StringStruct('ProductVersion', PRODUCT_VERSION),
            ]),
        ]),
        VarFileInfo([VarStruct('Translation', [0x0804, 1200])]),
    ],
)


a = Analysis(
    # 入口脚本
    [os.path.join(PROJECT_ROOT, 'main.py')],

    pathex=[PROJECT_ROOT],

    binaries=[],

    datas=[
        # (源路径, 目标目录名)
        # 只读资源：assets 整个目录原样打包进 _MEIPASS/assets/
        (ASSETS_DIR, 'assets'),
    ],

    hiddenimports=[
        # —— PySide6 隐藏导入（PyInstaller 一般能自动跟踪，显式声明更稳） ——
        'PySide6.QtCore',
        'PySide6.QtGui',
        'PySide6.QtWidgets',
        'PySide6.QtSvg',           # SVG 图标渲染（如未来用 SVG 素材）
        'PySide6.QtSvgWidgets',

        # —— 爬虫相关 ——
        'selenium',                # B 站 / 抖音 Selenium 驱动
        'selenium.webdriver',
        'selenium.webdriver.chrome',
        'selenium.webdriver.chrome.webdriver',
        'selenium.webdriver.chrome.service',
        'selenium.webdriver.chrome.options',
        'selenium.webdriver.remote',
        'selenium.webdriver.remote.webdriver',
        'selenium.webdriver.remote.command',
        'selenium.webdriver.common',
        'selenium.webdriver.common.by',
        'selenium.webdriver.common.keys',
        'selenium.webdriver.common.service',
        'selenium.webdriver.support',
        'selenium.webdriver.support.ui',
        'selenium.webdriver.support.wait',
        'selenium.webdriver.support.expected_conditions',
        'requests',                # HTTP 请求
        'requests.exceptions',
        # yt-dlp 仅作子进程调用，不需要作为 hidden import，但若以后改成 import yt_dlp 需要补上

        # —— 后续扩展预留 ——
        # 'PIL',                   # Pillow 图像处理（若启用抠图/帧后处理）
        # 'PyYAML',                # 若 settings 改用 yaml
    ],

    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # 排除不用的标准库模块，减小体积
        'tkinter',
        'unittest',
        'pydoc',
        'test',
        'lib2to3',
        # 注意：不要排除 distutils，Python 3.12+ 已移除，PyInstaller 会用 setuptools._distutils 别名兼容
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)


exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='pet',                   # 输出 exe 名：dist/pet/pet.exe
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,                     # UPX 压缩，减小体积（机器需安装 UPX 或 PyInstaller 自带）
    upx_exclude=[
        # UPX 压缩 Qt/PySide6 dll 会引起启动崩溃，必须排除
        'Qt6Core.dll', 'Qt6Gui.dll', 'Qt6Widgets.dll',
        'Qt6Svg.dll', 'Qt6Network.dll', 'Qt6OpenGL.dll',
        'Qt6Multimedia.dll', 'Qt6MultimediaWidgets.dll',
        'vcruntime140.dll', 'vcruntime140_1.dll',
        'python3.dll', 'python313.dll',
    ],
    console=False,                # --windowed：不弹控制台
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=icon_arg,
    version=version_info,            # 嵌入 VS_VERSIONINFO 资源（元数据来自环境变量）
)


coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[
        'Qt6Core.dll', 'Qt6Gui.dll', 'Qt6Widgets.dll',
        'Qt6Svg.dll', 'Qt6Network.dll', 'Qt6OpenGL.dll',
        'Qt6Multimedia.dll', 'Qt6MultimediaWidgets.dll',
        'vcruntime140.dll', 'vcruntime140_1.dll',
        'python3.dll', 'python313.dll',
    ],
    name='pet',                   # 输出目录名：dist/pet/
)
