"""下载历史记录（解决"不定时更新 → 最新视频仍是已爬过的 → 反复下载"的重复下载问题）。

存储：data/download_history.json（data/ 已经 gitignore，且打包 exe 后在 exe 同目录 data/ 下，用户随便删）。
格式：
{
  "bilibili:BV1xxxxx": {
      "ts": 1712345678,            # 最后一次下载成功的 unix 时间戳
      "output_path": "C:\\...\\output\\bilibili\\xxx.mp4",   # 成品绝对路径
      "title": "作品标题",
      "page_url": "https://www.bilibili.com/video/BV1xxxxx",
  },
  "douyin:7416510000000000000": {
      "ts": ...,
      "output_path": "C:\\...\\output\\douyin\\xxx.mp4",
      "title": ...,
      "web_url": "https://www.douyin.com/video/7416...",
  }
}

对外：
  - key_for_douyin(aweme_id)      -> "douyin:xxx"
  - key_for_bilibili(bvid)        -> "bilibili:xxx"
  - lookup(key)                   -> info dict，如果命中且 info.output_path 仍然是真实文件，否则 None
  - record(key, info)             -> 写入 json
  - forget(key)                   -> 删除某条（比如用户手动删了成品，历史记录也跟着删）
  - forget_broken_entries()       -> 清理所有 output_path 不存在的条目（手动调用也行，程序启动自动调也行）
"""

from __future__ import annotations

import json
import os
import threading
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Optional

from .resource_manager import get_data_path

_HISTORY_FILE = get_data_path("download_history.json")
_LOCK = threading.Lock()


def key_for_douyin(aweme_id: str) -> str:
    return f"douyin:{(aweme_id or '').strip()}"


def key_for_bilibili(bvid: str) -> str:
    return f"bilibili:{(bvid or '').strip()}"


def _load() -> dict[str, Any]:
    if not os.path.isfile(_HISTORY_FILE):
        return {}
    try:
        with open(_HISTORY_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            return data
        return {}
    except Exception:
        # 坏文件就丢，不要让历史记录阻塞下载
        try:
            os.replace(_HISTORY_FILE, _HISTORY_FILE + ".broken")
        except Exception:
            pass
        return {}


def _save(data: dict[str, Any]) -> None:
    tmp = _HISTORY_FILE + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, _HISTORY_FILE)
    except Exception:
        # 写失败也不抛异常让用户继续下一次下载
        try:
            os.unlink(tmp)
        except Exception:
            pass


@dataclass
class DownloadRecord:
    ts: int
    output_path: str
    title: str = ""
    page_url: str = ""
    extra: dict[str, Any] = field(default_factory=dict)

    def still_valid(self) -> bool:
        return bool(self.output_path) and Path(self.output_path).is_file()


def lookup(key: str) -> Optional[DownloadRecord]:
    """命中返回 record（且 output_path 仍在磁盘上），否则 None。"""
    if not key:
        return None
    with _LOCK:
        data = _load()
    raw = data.get(key)
    if not isinstance(raw, dict):
        return None
    try:
        rec = DownloadRecord(
            ts=int(raw.get("ts", 0) or 0),
            output_path=str(raw.get("output_path", "") or ""),
            title=str(raw.get("title", "") or ""),
            page_url=str(raw.get("page_url") or raw.get("web_url") or ""),
            extra=dict(raw.get("extra") or {}),
        )
    except Exception:
        return None
    return rec if rec.still_valid() else None


def record(key: str, rec: DownloadRecord) -> None:
    if not key:
        return
    with _LOCK:
        data = _load()
        data[key] = asdict(rec)
        _save(data)


def forget(key: str) -> bool:
    if not key:
        return False
    with _LOCK:
        data = _load()
        if key not in data:
            return False
        del data[key]
        _save(data)
        return True


def forget_broken_entries() -> int:
    """清理所有 output_path 不再存在的条目；返回被清理的条目数。"""
    with _LOCK:
        data = _load()
        before = len(data)
        for k in list(data.keys()):
            raw = data.get(k) or {}
            p = str(raw.get("output_path", "") or "")
            if not p or not Path(p).is_file():
                data.pop(k, None)
        removed = before - len(data)
        if removed > 0:
            _save(data)
        return removed


def history_file_path() -> str:
    """给 UI 用：显示文件位置 / 打开 data 目录。"""
    return _HISTORY_FILE


__all__ = [
    "DownloadRecord",
    "key_for_bilibili",
    "key_for_douyin",
    "lookup",
    "record",
    "forget",
    "forget_broken_entries",
    "history_file_path",
]
