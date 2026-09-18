"""桌面电子宠物 - 入口文件

启动透明窗口，显示桌面宠物。
"""

import sys
import signal

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from src.consent import check_consent_or_quit
from src.main_window import PetWindow


def main():
    # 允许 Ctrl+C 终止程序（Qt 事件循环默认捕获 SIGINT）
    signal.signal(signal.SIGINT, signal.SIG_DFL)

    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(True)

    # —— 首次启动免责声明检查 ——
    # 必须在 QApplication 创建后、PetWindow 创建前调用
    # 用户不同意则直接退出
    if not check_consent_or_quit():
        sys.exit(0)

    # 定时器让 Python 有机会处理 SIGINT 信号
    timer = QTimer()
    timer.start(500)
    timer.timeout.connect(lambda: None)

    pet = PetWindow()
    pet.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
