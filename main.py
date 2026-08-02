"""桌面电子宠物 - 程序入口.

运行方式（开发态）:
    python main.py

打包方式（见框架文档 6.3 节）:
    pyinstaller --onefile --windowed --icon=pet.ico \
        --add-data "assets;assets" \
        --hidden-import PySide6.QtGui \
        --hidden-import PySide6.QtWidgets \
        --hidden-import PySide6.QtCore \
        main.py
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

# 确保 src 包可被导入（开发态）
if __name__ == "__main__" and __package__ is None:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

from PySide6.QtWidgets import QApplication

from src.main_window import PetWindow
from src.resource_manager import ensure_runtime_dirs


def configure_logging() -> None:
    """配置日志：开发态输出到控制台，打包后输出到文件."""
    log_dir = Path("output/logs")
    log_dir.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(log_dir / "pet.log", encoding="utf-8"),
        ],
    )


def main() -> int:
    configure_logging()
    logger = logging.getLogger(__name__)
    logger.info("启动桌面电子宠物...")

    # 确保运行时目录存在
    ensure_runtime_dirs()

    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(True)

    window = PetWindow()
    window.show()

    logger.info("窗口已显示，进入事件循环")
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
