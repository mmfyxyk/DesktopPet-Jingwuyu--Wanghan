"""全局运行时配置：代理设置、默认值、持久化到 data/proxy.json。

目前只暴露「代理配置」。后面要加的默认值（宠物尺寸 / 语言 / 桌面通知偏好等）也放这里。
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from typing import Optional

from .resource_manager import get_data_path


# 代理三种模式
PROXY_MODE_DIRECT = "direct"           # 不走任何代理（强制直连）
PROXY_MODE_SYSTEM = "system"           # 跟随 Windows 系统代理/系统 VPN（默认）
PROXY_MODE_MANUAL = "manual"           # 手动填 host/port/username/password


@dataclass
class ProxyConfig:
    """爬虫模块使用的代理设置。

    - mode ∈ {direct, system, manual}
    - manual 模式需要填 host/port；username/password 可留空。
    - url() 返回统一代理串，供 selenium / requests / yt-dlp 直接消费；
      system 模式下 url() 返回 None，由 OS/库自动跟随系统代理。
      direct 模式下 url() 返回空串 ""；调用方把它塞给 proxies 即可强制直连。
    """
    mode: str = PROXY_MODE_SYSTEM
    host: str = ""
    port: int = 0
    username: str = ""
    password: str = ""
    # 保留位：后面加 SOCKS5 开关 / 代理池 / 健康检查周期
    extras: dict = field(default_factory=dict)

    # ------------------------------------------------------------------ API

    @property
    def scheme(self) -> str:
        return self.extras.get("scheme", "http")   # http / https / socks5 / socks5h

    def url(self) -> Optional[str]:
        """按模式返回代理 URL。None=走系统；空串=强制直连。"""
        if self.mode == PROXY_MODE_SYSTEM:
            return None
        if self.mode == PROXY_MODE_DIRECT:
            return ""   # 调用方把它放进 requests.Session.proxies 的 http/https 即直连
        # manual
        if not self.host or self.port <= 0:
            # 填得不全 → 当系统代理处理，避免误配
            return None
        auth = ""
        if self.username:
            from urllib.parse import quote
            u = quote(self.username, safe="")
            p = quote(self.password or "", safe="")
            auth = f"{u}:{p}@"
        return f"{self.scheme}://{auth}{self.host}:{self.port}"

    def requests_proxies(self) -> Optional[dict]:
        """构造 requests.Session.proxies 字典。"""
        u = self.url()
        if u is None:
            return None          # 跟随系统
        if u == "":
            return {"http": "", "https": ""}   # 强制直连
        return {"http": u, "https": u}


PROXY_JSON = get_data_path("proxy.json")


def load_proxy_config() -> ProxyConfig:
    """从 data/proxy.json 读配置；文件不存在/字段无效/缺字都返回默认值。"""
    if not os.path.isfile(PROXY_JSON):
        return ProxyConfig()
    try:
        with open(PROXY_JSON, "r", encoding="utf-8") as f:
            raw = json.load(f)
    except Exception:
        return ProxyConfig()

    cfg = ProxyConfig()
    mode = raw.get("mode")
    if mode in {PROXY_MODE_DIRECT, PROXY_MODE_SYSTEM, PROXY_MODE_MANUAL}:
        cfg.mode = mode
    # 允许填字符串 port，兼容用户手写 JSON
    try:
        cfg.host = str(raw.get("host", "") or "").strip()
        cfg.port = int(raw.get("port") or 0)
    except Exception:
        cfg.port = 0
    cfg.username = str(raw.get("username", "") or "")
    cfg.password = str(raw.get("password", "") or "")
    extras = raw.get("extras")
    if isinstance(extras, dict):
        cfg.extras = dict(extras)
    scheme = raw.get("scheme")
    if scheme in {"http", "https", "socks5", "socks5h"}:
        cfg.extras["scheme"] = scheme
    return cfg


def save_proxy_config(cfg: ProxyConfig) -> str:
    """保存配置并返回最终写入的路径。"""
    payload = {
        "mode": cfg.mode,
        "host": cfg.host,
        "port": cfg.port,
        "username": cfg.username,
        "password": cfg.password,
        "scheme": cfg.scheme,
        "extras": cfg.extras,
    }
    os.makedirs(os.path.dirname(PROXY_JSON), exist_ok=True)
    tmp = PROXY_JSON + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    os.replace(tmp, PROXY_JSON)
    return PROXY_JSON


def clear_proxy_config_file() -> bool:
    """删除 data/proxy.json（可能写了明文账号密码）。删除成功返回 True，不存在也返回 True。"""
    if not os.path.isfile(PROXY_JSON):
        return True
    try:
        os.remove(PROXY_JSON)
        return True
    except OSError:
        return False


# ------------------------------------------------------------------ helpers

def resolve_runtime_proxy(cfg: Optional[ProxyConfig] = None) -> Optional[str]:
    """给 main_window 里 CRAWLER_PROXY、以及各 Worker 启动时统一调用。

    返回值语义：
      None   → 跟随系统代理/系统 VPN（推荐默认）
      ""     → 强制直连
      "http://..." / "socks5://..." → 手动代理
    """
    if cfg is None:
        cfg = load_proxy_config()
    return cfg.url()
