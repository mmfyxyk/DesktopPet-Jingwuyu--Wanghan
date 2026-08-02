"""资源路径管理模块.

按照框架文档 6.2 节的资源路径函数设计，区分开发态与打包态：
- 只读资源（assets/）：打包进 exe，运行时从 sys._MEIPASS 读取
- 运行时数据（data/）：开发态在项目根目录，打包后在 exe 同目录
- 输出目录（output/）：同上
- 外部工具（support/）：同上
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


def _is_frozen() -> bool:
    """判断当前是否为 PyInstaller 打包后的运行环境."""
    return getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS")


def get_resource_path(relative_path: str | os.PathLike) -> Path:
    """获取只读资源路径（图片、动画帧等，打包进 exe）。

    - 开发态：项目根目录 / relative_path
    - 打包后：sys._MEIPASS / relative_path
    """
    if _is_frozen():
        base = Path(sys._MEIPASS)  # type: ignore[attr-defined]
    else:
        base = Path(__file__).resolve().parent.parent
    return base / relative_path


def get_data_path(relative_path: str | os.PathLike = "") -> Path:
    """获取运行时数据路径（settings.json 等可写数据）。

    - 开发态：项目根目录 / data / relative_path
    - 打包后：exe 同目录 / data / relative_path
    """
    if _is_frozen():
        base = Path(sys.executable).resolve().parent
    else:
        base = Path(__file__).resolve().parent.parent
    return base / "data" / relative_path


def get_output_path(relative_path: str | os.PathLike = "") -> Path:
    """获取输出目录路径（爬虫下载的视频等）。

    - 开发态：项目根目录 / output / relative_path
    - 打包后：exe 同目录 / output / relative_path
    """
    if _is_frozen():
        base = Path(sys.executable).resolve().parent
    else:
        base = Path(__file__).resolve().parent.parent
    return base / "output" / relative_path


def get_support_path(relative_path: str | os.PathLike = "") -> Path:
    """获取外部工具路径（ffmpeg 等可执行文件）。

    - 开发态：项目根目录 / support / relative_path
    - 打包后：exe 同目录 / support / relative_path
    """
    if _is_frozen():
        base = Path(sys.executable).resolve().parent
    else:
        base = Path(__file__).resolve().parent.parent
    return base / "support" / relative_path


def ensure_runtime_dirs() -> None:
    """确保运行时目录存在（data/、output/、support/）.

    在程序启动时调用一次，避免后续写入文件时因目录缺失而报错。
    """
    for path in (get_data_path(), get_output_path(), get_support_path()):
        path.mkdir(parents=True, exist_ok=True)


def get_assets_dir(state: str) -> Path:
    """获取指定状态的动画帧目录.

    Args:
        state: 状态名称（如 "idle"、"walking"），对应框架 3.3 节的动画帧目录。

    Returns:
        assets/<state>/ 的完整路径。
    """
    return get_resource_path("assets") / state


__all__ = [
    "get_resource_path",
    "get_data_path",
    "get_output_path",
    "get_support_path",
    "ensure_runtime_dirs",
    "get_assets_dir",
]
