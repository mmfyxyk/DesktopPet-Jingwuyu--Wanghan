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


def get_tmp_path(platform: str, task_id: str, *relative_path: str) -> str:
    """统一的运行时临时目录。

    规则：
      - 统一落到 data/tmp/<platform>/<task_id>/…
      - 成功由调用方在成功后清理目录（哪怕里面还有 yt-dlp/.part 残留）；失败则保留
        → 用户能去 data/tmp/<platform>/ 里看现场、手动删、不会污染 output/<platform> 成品目录。
      - task_id 建议用 平台唯一 ID，比如 douyin aweme_id / bilibili bvid，方便排障。

    注意：这里 os.makedirs(full_path, exist_ok=True)，所以直接 return 具体绝对路径。
    """
    import re
    # 去掉任何路径分隔符与非法字符，避免 task_id 越界
    safe_platform = re.sub(r"[^\w\-]+", "_", (platform or "unknown").strip()) or "unknown"
    safe_task = re.sub(r"[^\w\-]+", "_", (task_id or "task").strip()) or "task"
    path = os.path.join(get_base_dir(), "data", "tmp", safe_platform, safe_task, *relative_path)
    os.makedirs(os.path.dirname(path) if relative_path else path, exist_ok=True)
    return path


def clear_tmp_dir(abs_dir: str) -> bool:
    """强制清理指定临时目录（成功后调用；即使里面有残留半成品也直接 rmtree）。

    返回 True=目录确实被清理/本来就不存在，False=清理失败。
    """
    import shutil
    if not abs_dir:
        return True
    if not os.path.isdir(abs_dir):
        return True
    # 只允许清理 data/tmp/ 下面的目录，防止手误把整个 data/ output/ 删了
    base = os.path.normpath(os.path.join(get_base_dir(), "data", "tmp"))
    cand = os.path.normpath(abs_dir)
    if not (cand + os.sep).startswith(base + os.sep):
        return False
    try:
        shutil.rmtree(cand, ignore_errors=False)
    except OSError:
        try:
            shutil.rmtree(cand, ignore_errors=True)
        except Exception:
            return False
    return True


def open_in_explorer(path: str, *, select_file: bool = False) -> tuple[bool, str]:
    """资源管理器打开路径（exe 打包下也能用，因为走的是用户 Windows shell）。

    select_file=True：高亮一个文件；False：直接打开一个目录。
    返回 (是否成功, 错误消息)；成功时错误消息为空串。
    """
    import subprocess
    if not path:
        return False, "path 为空"
    # 路径不存在时先兜底 mkdir（主要是 data / output 这两个根目录），避免 explorer 报错
    try:
        if select_file:
            # 高亮文件：要求父目录存在即可
            parent = os.path.dirname(path)
            if parent and not os.path.isdir(parent):
                os.makedirs(parent, exist_ok=True)
        else:
            # 打开目录：自身必须存在
            if not os.path.exists(path):
                os.makedirs(path, exist_ok=True)
    except Exception as e:
        return False, f"路径不存在且无法自动创建：{e}"

    try:
        if select_file:
            subprocess.Popen(["explorer", "/select,", path])
        else:
            os.startfile(path)  # type: ignore[attr-defined]
        return True, ""
    except Exception as e1:
        try:
            # 兜底
            subprocess.Popen(["explorer", path])
            return True, ""
        except Exception as e2:
            return False, f"{type(e1).__name__}: {e1}; 兜底也失败: {type(e2).__name__}: {e2}"


def get_support_path(*relative_path):
    """获取外部工具路径（support/ 目录，ffmpeg 等）"""
    path = os.path.join(get_base_dir(), 'support', *relative_path)
    return path


def get_asset_path(*relative_path):
    """获取 assets 目录下的资源路径"""
    return get_resource_path('assets', *relative_path)
