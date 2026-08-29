"""首次启动免责声明与使用协议

设计要点：
    * 同意记录持久化到 data/consent.json，下次启动不再弹窗
    * 记录同意时间、consent 版本、应用版本
    * 若未来条款更新，bump CONSENT_VERSION 即可强制用户重新同意
    * 不同意直接退出程序
    * 对话框：滚动文本 + 必勾复选框 + 「继续」/「退出」按钮
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication, QDialog, QDialogButtonBox, QLabel, QCheckBox,
    QVBoxLayout, QScrollArea, QPushButton,
)

from .resource_manager import get_data_path


# ============================== 配置 ==============================

# 免责声明版本号：条款更新时 bump 这个数字即可强制用户重新同意
# - 例如加入新的爬虫平台、修改隐私政策等
CONSENT_VERSION = "1.0"

# 应用版本号（从 main_window 读取避免循环导入，用 env 兜底）
APP_VERSION = os.environ.get('PET_VERSION', '1.0.0')

# 同意记录文件路径（data/consent.json）
CONSENT_FILE = get_data_path('consent.json')


# ============================== 免责声明文本 ==============================

CONSENT_TEXT = """【一、性质声明】
本程序（桌面电子宠物）为个人开发者基于 MIT 协议开源的非商业项目，
仅供个人学习、研究、娱乐使用，禁止任何形式的商业用途。

【二、功能与风险提示】

1. 爬虫功能
   本程序集成 B 站（Bilibili）、抖音等平台的内容爬取功能：
   - 使用者需确保遵守目标平台的服务协议与相关法律法规
   - 因使用本爬虫功能产生的任何法律责任，由使用者自行承担
   - 请合理使用，避免高频请求对目标服务器造成压力
   - 下载的视频、图片等内容版权归原作者所有，仅供个人保存

2. 用户数据
   本程序会在本地保存以下数据，不会上传到任何服务器：
   - 登录态文件：data/douyin_cookies.txt、data/douyin_cookies.json
   - 浏览器用户资料：support/Chrome/Profile-Douyin/
   - 爬虫下载内容：output/bilibili/、output/douyin/
   - 代理配置：data/proxy.json
   用户可随时通过菜单「拓展功能 → 抖音 → 清除登录数据」一键清除。

3. 第三方工具
   本程序依赖 ffmpeg、Chrome、yt-dlp 等第三方工具，
   这些工具的版权与许可请参阅其官方网站。

【三、开源协议】
本程序基于 MIT License 开源，作者不对使用本程序产生的任何后果
承担责任。使用即表示您已阅读、理解并接受上述全部条款。

【四、知识产权】
本程序中出现的「净无欲」「王涵」等角色与名称源自游戏《美女，请别影响我成仙》，
相关权益归原作者所有。本程序仅作为粉丝向的非商业性二次创作，
不得用于任何侵犯原作者权益的行为。

————————————————————————————————
请阅读并同意上述条款后继续使用本程序。"""


# ============================== 同意记录读写 ==============================

def load_consent_record() -> Optional[dict]:
    """读取同意记录，返回 None 表示从未同意过"""
    if not os.path.exists(CONSENT_FILE):
        return None
    try:
        with open(CONSENT_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None


def save_consent_record() -> None:
    """写入同意记录"""
    record = {
        "accepted": True,
        "accepted_at": datetime.now().isoformat(timespec='seconds'),
        "consent_version": CONSENT_VERSION,
        "app_version": APP_VERSION,
    }
    try:
        with open(CONSENT_FILE, 'w', encoding='utf-8') as f:
            json.dump(record, f, ensure_ascii=False, indent=2)
    except OSError:
        # 写入失败不影响程序启动（下次还会再弹一次，但能继续运行）
        pass


def is_consent_valid() -> bool:
    """判断当前同意记录是否仍然有效

    - 未记录过 → False
    - consent_version 不匹配 → False（条款更新后强制重新同意）
    - accepted != True → False
    """
    record = load_consent_record()
    if not record:
        return False
    if not record.get('accepted'):
        return False
    if record.get('consent_version') != CONSENT_VERSION:
        return False
    return True


# ============================== 对话框 UI ==============================

class ConsentDialog(QDialog):
    """免责声明对话框

    UI 结构：
        ┌────────────────────────────────────┐
        │  桌面电子宠物 - 使用前须知            │
        │  ┌──────────────────────────────┐  │
        │  │  （可滚动文本区，显示声明内容）  │  │
        │  │                              │  │
        │  └──────────────────────────────┘  │
        │  ☐ 我已阅读并同意上述全部条款        │
        │              [退出]      [继续]    │
        └────────────────────────────────────┘
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("桌面电子宠物 - 使用前须知")
        self.setModal(True)
        self.setMinimumSize(560, 480)
        self.resize(620, 560)

        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 16)
        layout.setSpacing(12)

        # —— 标题 ——
        title = QLabel("⚠ 使用前须知")
        title.setStyleSheet("font-size: 16px; font-weight: bold; color: #c0392b;")
        layout.addWidget(title)

        # —— 副标题 ——
        subtitle = QLabel(
            "首次启动需要您阅读并同意以下条款，才能继续使用本程序。"
        )
        subtitle.setWordWrap(True)
        subtitle.setStyleSheet("color: #555;")
        layout.addWidget(subtitle)

        # —— 可滚动文本区 ——
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet(
            "QScrollArea { border: 1px solid #ddd; background: #fafafa; }"
        )

        content_label = QLabel(CONSENT_TEXT)
        content_label.setWordWrap(True)
        content_label.setTextFormat(Qt.PlainText)
        content_label.setStyleSheet(
            "QLabel { padding: 12px; font-size: 13px; line-height: 160%; }"
        )
        content_label.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        scroll.setWidget(content_label)
        layout.addWidget(scroll, 1)

        # —— 同意复选框 ——
        self.accept_checkbox = QCheckBox("我已阅读并同意上述全部条款")
        self.accept_checkbox.setStyleSheet("font-size: 14px; padding: 4px 0;")
        self.accept_checkbox.toggled.connect(self._on_checkbox_toggled)
        layout.addWidget(self.accept_checkbox)

        # —— 按钮区 ——
        btn_layout = QVBoxLayout()
        btn_layout.setSpacing(8)

        # 「继续」按钮（默认禁用）
        self.continue_btn = QPushButton("继续使用")
        self.continue_btn.setEnabled(False)
        self.continue_btn.setMinimumHeight(36)
        self.continue_btn.setStyleSheet(
            "QPushButton {"
            "  background: #27ae60; color: white; border: none;"
            "  border-radius: 4px; font-size: 14px; padding: 6px 16px;"
            "}"
            "QPushButton:disabled { background: #bdc3c7; }"
            "QPushButton:hover:enabled { background: #229954; }"
        )
        self.continue_btn.clicked.connect(self.accept)
        btn_layout.addWidget(self.continue_btn)

        # 「退出」按钮
        exit_btn = QPushButton("不同意，退出程序")
        exit_btn.setMinimumHeight(36)
        exit_btn.setStyleSheet(
            "QPushButton {"
            "  background: #e74c3c; color: white; border: none;"
            "  border-radius: 4px; font-size: 14px; padding: 6px 16px;"
            "}"
            "QPushButton:hover { background: #c0392b; }"
        )
        exit_btn.clicked.connect(self.reject)
        btn_layout.addWidget(exit_btn)

        layout.addLayout(btn_layout)

    def _on_checkbox_toggled(self, checked: bool) -> None:
        """复选框状态变化时启用/禁用「继续」按钮"""
        self.continue_btn.setEnabled(checked)


# ============================== 入口函数 ==============================

def check_consent_or_quit() -> bool:
    """启动时检查同意状态，未同意则弹窗

    返回 True 表示已同意（或本次同意），可以继续启动主程序
    返回 False 表示用户拒绝，调用方应退出程序

    用法（在 main.py 里）：
        if not check_consent_or_quit():
            sys.exit(0)
    """
    if is_consent_valid():
        return True

    dialog = ConsentDialog()
    result = dialog.exec()

    if result == QDialog.Accepted:
        save_consent_record()
        return True
    return False
