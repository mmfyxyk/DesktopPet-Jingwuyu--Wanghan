"""首次启动免责声明与使用协议

设计要点：
    * 同意记录持久化到 data/consent.json，下次启动不再弹窗
    * 记录同意时间、consent 版本、应用版本
    * 若未来条款更新，bump CONSENT_VERSION 即可强制用户重新同意
    * 不同意直接退出程序
    * 对话框：QTextEdit 显示长文本（尺寸计算比 QLabel 准确，不会出现"视觉没到底但滚动条判底"）
             + 阅读倒计时（默认 10 秒）+ 强制滚到底部后才点亮继续按钮
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from typing import Optional

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont, QTextOption, QTextCursor, QPalette, QColor
from PySide6.QtWidgets import (
    QApplication, QDialog, QLabel, QVBoxLayout, QPushButton, QFrame, QTextEdit,
)

from .resource_manager import get_data_path


# ============================== 配置 ==============================

# 免责声明版本号：条款更新时 bump 这个数字即可强制用户重新同意
CONSENT_VERSION = "1.4"

# 应用版本号（从 env 兜底）
APP_VERSION = os.environ.get('PET_VERSION', '1.0.0')

# 同意记录文件路径（data/consent.json）
CONSENT_FILE = get_data_path('consent.json')

# 协议 UI：阅读倒计时（秒）。打开后此时间内主按钮保持禁用。
READ_COUNTDOWN_SEC = 10

# 协议 UI：滚动条是否必须拉到底才能点亮继续按钮
REQUIRE_SCROLL_TO_BOTTOM = True

# 布局冷冻期（毫秒）：前 1800ms 内 Qt 还在做 text document 布局，滚动条 maximum 可能不稳定，
# 这段时间内所有判底都走严格模式。
_LAYOUT_FREEZE_MS = 1800


# ============================== 免责声明文本 ==============================

CONSENT_TEXT = """【一、软件性质】
本程序（桌面电子宠物）为个人开源项目，基于 MIT 协议向公众开放，仅供个人学习、研究、娱乐使用，禁止任何形式的商用。
使用即表示您已阅读、理解并同意本声明的全部内容。

【二、爬虫功能与合规使用】
本程序集成 B 站（Bilibili）、抖音等平台的公开作品浏览与本地下载功能。使用时请注意：
• 遵守国家法律法规，以及目标平台的《服务协议》《用户协议》《隐私政策》；
• 合理克制地发起请求，避免对目标平台服务器造成不当压力；
• 下载内容的著作权归原作者或平台所有，仅限个人欣赏、学习与备份，不得二次传播、分享或商用；
• 因违规使用引发的一切法律责任由使用者自行承担。

【三、数据与隐私】
本程序遵循「本地存储、零上传」原则：运行中产生的全部数据均仅保存在您的本机，不会上传至任何服务器。
本地保存的数据包括：
• 抖音登录态：data/douyin_cookies.(json|txt)
• Chrome 独立用户资料：support/Chrome/Profile-Douyin/
• 下载的视频作品：output/bilibili/ 与 output/douyin/
• 代理配置：data/proxy.json
• 协议同意记录：data/consent.json
• 下载历史：data/download_history.json
清除入口：「拓展功能 → 清除隐私数据...」「拓展功能 → 抖音 → 清除登录数据」。
（output/ 中的视频文件为避免误删，需由您手动清理。）

【四、第三方依赖】
本程序依赖 PySide6/Qt、ffmpeg、Chromium/Chrome、ChromeDriver、yt-dlp、Selenium 等
第三方组件，其各自版权与许可协议请参阅对应官方网站。

【五、免责声明】
在法律允许的最大范围内，开发者不对因使用或无法使用本程序产生的任何直接或间接损失承担责任，
包括但不限于数据丢失、中断、网络/代理问题、平台改版或风控导致爬虫失效，以及违规使用引发的第三方索赔。
本程序按「现状（AS IS）」提供，不担保无缺陷或无中断运行。

【六、知识产权与角色声明】
本程序源代码、UI 设计、动画脚本、文档等原创内容由开发者享有著作权，按 MIT 协议开放使用。
以下内容的相关权益归对应权利人所有：
• 「王涵」真实人物的姓名与肖像：姓名权、肖像权等人格权利均归王涵本人所有；
  本程序仅作非商业、非贬低的参考使用，如相关方认为权益受影响，请按上文渠道提出。
• 角色「净无欲」及所属作品《美女，请别影响我成仙》的名称、世界观、剧情元素：
  其著作权归作品原作者所有；角色「净无欲」由演员王涵饰演。
  本程序为粉丝向的个人非商业性二次创作，不得侵害原作者及扮演者的合法权益。
• B 站、抖音、Chrome 等商标归各自注册人所有，本程序仅作兼容性描述，不构成任何关联声明。
未经对应权利人书面许可，您不得将上述命名、标识、肖像、角色形象等用于超出本协议范围的用途。

【七、协议更新】
条款修订后会在下次启动时重新弹窗，请您再次确认。不同意或不同意新版本，请停止使用本程序并删除本地副本。

——————————————————————
点击下方绿色按钮表示您已阅读并同意以上全部内容。"""


# ============================== 同意记录读写 ==============================

def load_consent_record() -> Optional[dict]:
    if not os.path.exists(CONSENT_FILE):
        return None
    try:
        with open(CONSENT_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None


def save_consent_record() -> None:
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
        pass


def is_consent_valid() -> bool:
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
    """免责声明对话框（QTextEdit 承载文本，尺寸计算稳定）

    两重启用条件：
      1. 倒计时（默认 10s）走完；
      2. 文本滚动条真正拉到底部；
    满足后「继续使用（我已阅读并同意上述条款）」按钮才会由灰变绿点亮。
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("桌面电子宠物 - 用户协议与免责声明")
        self.setModal(True)
        self.setMinimumSize(620, 600)
        self.resize(700, 700)

        # 初始强制 False —— 永远不让布局初始化时"自动到底"
        self._scrolled_to_bottom: bool = False
        self._countdown_remain: int = max(1, int(READ_COUNTDOWN_SEC))
        self._layout_frozen: bool = True

        self._build_ui()
        self._refresh_enable_state()

        # 倒计时
        self._timer = QTimer(self)
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self._on_countdown_tick)
        self._timer.start()
        self._on_countdown_tick()

        # 布局冷冻期结束（QTextDocument 首帧布局应该稳定了）
        QTimer.singleShot(_LAYOUT_FREEZE_MS, self._thaw_layout_frozen)
        # 冷冻期结束前，再做 3 次"内容是否一屏装得下"的客观检测
        for delay_ms in (700, 1100, _LAYOUT_FREEZE_MS):
            QTimer.singleShot(delay_ms, lambda: self._check_scroll_bottom_objectively())

    # --------------------------------------------------------------- UI

    def _build_ui(self) -> None:
        # —— 外层对话框底色（你说的"文档背景外那一圈"）：统一成和文档接近的灰色 ——
        #    之前 dialog 透明继承主窗口，视觉上"灰文档外面是白桌面"的对比很突兀。
        #    现在设成略深一档的灰：外层灰 → 文档稍亮一档，对比柔和没"边框感"。
        DIALOG_BG = "#E2E3E8"  # 对话框最外层（margin / spacing 区）底色
        DOC_BG    = "#ECECF0"  # QTextEdit 文档正文底色，比外层亮一档
        FG        = "#1F2937"  # 文字
        self.setObjectName("ConsentDialogRoot")
        # 对话框本体调色板（防止主窗口透明属性渗透过来）
        self.setAutoFillBackground(True)
        dlg_pal = self.palette()
        dlg_pal.setColor(QPalette.Window, QColor(DIALOG_BG))
        self.setPalette(dlg_pal)
        self.setStyleSheet(
            f"#ConsentDialogRoot {{ background-color: {DIALOG_BG}; }}"
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 20, 22, 16)
        layout.setSpacing(12)

        # 主标题
        title = QLabel("用户协议与免责声明")
        title.setStyleSheet("font-size: 18px; font-weight: bold; color: #2c3e50;")
        title.setAlignment(Qt.AlignHCenter)
        layout.addWidget(title)

        # 分隔线
        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setFrameShadow(QFrame.Plain)
        sep.setStyleSheet("color: #ddd; background: #ddd; max-height: 1px;")
        layout.addWidget(sep)

        # 状态提示条
        self.hint_label = QLabel("正在加载协议条款……")
        self.hint_label.setWordWrap(True)
        self.hint_label.setStyleSheet("color: #7f8c8d; padding: 2px 2px; font-size: 13px;")
        layout.addWidget(self.hint_label)

        # —— QTextEdit（只读）承载协议正文 ——
        self.text_edit = QTextEdit()
        self.text_edit.setReadOnly(True)

        # 字体先设置，再 fill document
        font = QFont()
        font.setPointSize(10)
        self.text_edit.setFont(font)

        # 文档属性：word wrap + 页边距
        self.text_edit.setWordWrapMode(QTextOption.WordWrap)
        doc = self.text_edit.document()
        doc.setDocumentMargin(12)
        doc.setDefaultFont(font)

        # 颜色：文档底色 DOC_BG（比外层对话框亮一档），文字 FG
        self.text_edit.setAutoFillBackground(True)
        self.text_edit.viewport().setAutoFillBackground(True)
        pal = self.text_edit.palette()
        pal.setColor(QPalette.Base,   QColor(DOC_BG))
        pal.setColor(QPalette.Text,   QColor(FG))
        pal.setColor(QPalette.Window, QColor(DOC_BG))
        self.text_edit.setPalette(pal)
        self.text_edit.viewport().setPalette(pal)
        self.text_edit.setTextColor(QColor(FG))

        # 文档边框：柔灰 1px；滚动条：和常见 Windows 程序一致的朴素灰。
        BDR_SOFT       = "#D8DAE0"   # 文档 1px 边：几乎和外层灰底贴在一起
        SCROLL_BG      = "#F1F2F5"   # 轨道背景：极淡
        SCROLL_HAND    = "#C4C7CE"   # 滑块：常见 Qt/Windows 默认灰色
        SCROLL_HAND_HV = "#B2B6BF"   # hover 略深
        self.text_edit.setStyleSheet(
            f"QTextEdit {{"
            f"  border: 1px solid {BDR_SOFT};"
            f"  background-color: {DOC_BG};"
            f"  color: {FG};"
            f"  border-radius: 5px;"
            f"  padding: 4px 8px;"
            f"  font-size: 13px;"
            f"}}"
            f"QScrollBar:vertical {{"
            f"  width: 12px;"
            f"  background: {SCROLL_BG};"
            f"  margin: 2px 0px 2px 0px;"
            f"  border: none;"
            f"}}"
            f"QScrollBar::handle:vertical {{"
            f"  background: {SCROLL_HAND};"
            f"  border-radius: 5px;"
            f"  min-height: 30px;"
            f"  margin: 1px 1px 1px 1px;"
            f"}}"
            f"QScrollBar::handle:vertical:hover {{"
            f"  background: {SCROLL_HAND_HV};"
            f"}}"
            "QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }"
            "QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: none; }"
        )

        # 等 UI 配置稳定后再填文本，最后 30ms 后滚到开头
        self.text_edit.setPlainText(CONSENT_TEXT)
        QTimer.singleShot(30, self._force_scroll_to_top)

        # 监听滚动信号：sliderMoved（用户真实操作）+ valueChanged（任何变化，冷冻期内判底严格）
        self.text_edit.verticalScrollBar().sliderMoved.connect(self._on_user_scroll_interact)
        self.text_edit.verticalScrollBar().valueChanged.connect(self._on_scroll_changed)
        layout.addWidget(self.text_edit, 1)

        # 按钮区
        btn_layout = QVBoxLayout()
        btn_layout.setSpacing(8)

        # 主按钮：灰/绿切换
        self.continue_btn = QPushButton()
        self.continue_btn.setEnabled(False)
        self.continue_btn.setMinimumHeight(40)
        self.continue_btn.setStyleSheet(
            "QPushButton {"
            "  background: #27ae60; color: white; border: none;"
            "  border-radius: 4px; font-size: 14px; padding: 8px 16px;"
            "}"
            "QPushButton:disabled { background: #95a5a6; color: #ecf0f1; }"
            "QPushButton:hover:enabled { background: #229954; }"
        )
        self.continue_btn.clicked.connect(self.accept)
        btn_layout.addWidget(self.continue_btn)

        # 退出按钮
        exit_btn = QPushButton("不同意并退出")
        exit_btn.setMinimumHeight(38)
        exit_btn.setStyleSheet(
            "QPushButton {"
            "  background: #ecf0f1; color: #c0392b; border: 1px solid #e67e22;"
            "  border-radius: 4px; font-size: 14px; padding: 6px 16px;"
            "}"
            "QPushButton:hover { background: #e74c3c; color: white; border-color: #c0392b; }"
        )
        exit_btn.clicked.connect(self.reject)
        btn_layout.addWidget(exit_btn)

        layout.addLayout(btn_layout)

    # ------------------------------------------------------------ 逻辑

    def _force_scroll_to_top(self) -> None:
        """初始化后把滚动条 + 光标都强制回到最开头。"""
        try:
            self.text_edit.moveCursor(QTextCursor.Start)
            self.text_edit.verticalScrollBar().setValue(0)
        except Exception:
            pass

    def _thaw_layout_frozen(self) -> None:
        self._layout_frozen = False
        self._check_scroll_bottom_objectively()

    # —— 文档真实尺寸判底（不再信 QScrollBar.maximum 被低估的那套）——
    #    直接拿 QTextDocument.size().height()  与  viewport.height() 比较：
    #    • document_height <= viewport_height + 容差 → 真·一页装完 → 自动满足滚动
    #    • document_height >  viewport_height + 容差 → 必须用户滚动
    #        此时真的到底的条件：
    #          scroll_value + viewport_height(px) >= document_height - 容差

    _NO_SCROLL_TOLERANCE_PX = 16   # 小于这个高度差就算"基本一屏装完"
    _BOTTOM_TOLERANCE_PX   = 24    # 滚到这里或以下就算"看到最末行了"

    def _get_physical_scroll_state(self) -> tuple[float, float, float]:
        """返回 (scroll_y_px, viewport_h_px, doc_h_px)，全部物理像素。

        注意：QAbstractSlider 的 value()/pageStep()/maximum() 是"文档逻辑像素步长"，
        和 QTextDocument.size().height() 同一单位（逻辑像素 pt × devicePixelRatio 后
        一般等于物理像素），直接比较是成立的。
        但为了更稳，直接用 viewport/viewport 的 height() 与 document.size() 对。
        """
        try:
            doc_h = float(self.text_edit.document().size().height())
            vp_h  = float(self.text_edit.viewport().height())
            sb_y  = float(self.text_edit.verticalScrollBar().value())
            return sb_y, vp_h, doc_h
        except Exception:
            return 0.0, 0.0, 0.0

    def _check_scroll_bottom_objectively(self) -> None:
        """**客观检测**：基于文档真实高度 vs 视口高度。

        只在以下情况才把 `_scrolled_to_bottom` 置 True：
          1) REQUIRE_SCROLL_TO_BOTTOM=False；
          2) doc_h <= vp_h + TOLERANCE（客观上一屏装得下，用户无法滚动）；
          3) doc_h > vp_h 且 scroll_y + vp_h >= doc_h - BOTTOM_TOL（视觉真的看到最末行了）。
        其他情况一律不修改 _scrolled_to_bottom（保持 False，严格）。
        """
        if not REQUIRE_SCROLL_TO_BOTTOM:
            self._scrolled_to_bottom = True
            self._refresh_enable_state()
            return
        sb_y, vp_h, doc_h = self._get_physical_scroll_state()
        # 文档高度太小（未 layout 完）→ 暂时不要判底。按经验 layout 完的正文应该有 400+ px。
        if doc_h < 60.0:
            return
        # 真·一页装完（容差 NO_SCROLL_TOLERANCE_PX）
        if doc_h <= vp_h + self._NO_SCROLL_TOLERANCE_PX:
            self._scrolled_to_bottom = True
            self._refresh_enable_state()
            return
        # 真的滚到底部了
        if sb_y + vp_h >= doc_h - self._BOTTOM_TOLERANCE_PX:
            self._scrolled_to_bottom = True
            self._refresh_enable_state()
        # 其他情况一律不动 _scrolled_to_bottom（保持 False）

    def _on_user_scroll_interact(self, _value: int) -> None:
        """sliderMoved：用户真实拖滚轮/滑块 → 走严格判底。"""
        self._check_scroll_bottom_objectively()

    def _on_scroll_changed(self, _value: int) -> None:
        """valueChanged：任何变化 → 也走严格判底（冷冻期也一样）。"""
        self._check_scroll_bottom_objectively()

    def _on_countdown_tick(self) -> None:
        if self._countdown_remain > 0:
            self._countdown_remain -= 1
            self._refresh_enable_state()
            return
        if self._timer.isActive():
            self._timer.stop()
        self._refresh_enable_state()

    def _refresh_enable_state(self) -> None:
        countdown_ok = self._countdown_remain <= 0
        scroll_ok = (not REQUIRE_SCROLL_TO_BOTTOM) or self._scrolled_to_bottom
        can_continue = countdown_ok and scroll_ok
        self.continue_btn.setEnabled(can_continue)

        # —— 按钮文案 ——
        if can_continue:
            self.continue_btn.setText("继续使用（我已阅读并同意上述条款）")
        else:
            if not countdown_ok and not scroll_ok:
                self.continue_btn.setText(
                    f"请阅读 {self._countdown_remain} 秒后滚动至底部"
                )
            elif not countdown_ok:
                self.continue_btn.setText(f"请阅读 {self._countdown_remain} 秒后再继续")
            else:
                self.continue_btn.setText("请滚动协议文本到底部")

        # —— 顶部提示条 ——
        if not countdown_ok and not scroll_ok:
            self.hint_label.setText(
                f"⏱  阅读倒计时还需 {self._countdown_remain} 秒，同时请将文本滚动至最底部"
            )
        elif not countdown_ok:
            self.hint_label.setText(f"⏱  阅读倒计时：还需 {self._countdown_remain} 秒")
        elif not scroll_ok:
            self.hint_label.setText("⤵  请将协议文本滚动至最底部")
        else:
            self.hint_label.setText("✅ 条件全部满足，点击最下方绿色按钮即表示同意并启动程序")


# ============================== 入口函数 ==============================

def check_consent_or_quit() -> bool:
    """启动时检查同意状态，未同意则弹窗。"""
    if is_consent_valid():
        return True
    dialog = ConsentDialog()
    result = dialog.exec()
    if result == QDialog.Accepted:
        save_consent_record()
        return True
    return False
