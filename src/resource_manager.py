"""资源路径管理模块

区分开发态和打包态的资源路径：
- 只读资源（assets/）打包后从 sys._MEIPASS 读取
- 运行时数据（data/、output/、support/）放在 exe 同目录
"""

import os
import sys


def _is_frozen():
    """判断是否为 PyInstaller 打包环境"""
    return hasattr(sys, '_MEIPASS')


def get_base_dir():
    """获取项目根目录（开发态）或 exe 所在目录（打包态）"""
    if _is_frozen():
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def get_resource_path(*relative_path):
    """获取只读资源路径（assets 等，打包进 exe 的资源）

    开发态：项目根目录/relative_path
    打包态：sys._MEIPASS/relative_path
    """
    if _is_frozen():
        return os.path.join(sys._MEIPASS, *relative_path)
    return os.path.join(get_base_dir(), *relative_path)


def get_data_path(*relative_path):
    """获取运行时数据路径（data/ 目录）

    开发态和打包态都在 exe 同目录（或项目根目录）下
    """
    path = os.path.join(get_base_dir(), 'data', *relative_path)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    return path


def get_output_path(*relative_path):
    """获取输出路径（output/ 目录，爬虫等输出结果）"""
    path = os.path.join(get_base_dir(), 'output', *relative_path)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    return path


def get_support_path(*relative_path):
    """获取外部工具路径（support/ 目录，ffmpeg 等）"""
    path = os.path.join(get_base_dir(), 'support', *relative_path)
    return path


def get_asset_path(*relative_path):
    """获取 assets 目录下的资源路径"""
    return get_resource_path('assets', *relative_path)
