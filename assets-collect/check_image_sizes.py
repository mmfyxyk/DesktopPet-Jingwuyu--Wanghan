"""查看 assets/ 或任意文件夹里所有图片/GIF 的像素尺寸。

用法：
    # 看项目默认 assets 文件夹（桌宠素材）
    python assets-collect/check_image_sizes.py

    # 看某个具体文件夹（比如你刚导出的 PNG 序列）
    python assets-collect/check_image_sizes.py --folder "D:/素材/王涵眨眼序列"

    # 看单个文件
    python assets-collect/check_image_sizes.py --folder "C:/xxx/试.gif"
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

try:
    from PIL import Image
except ImportError:
    # 没装 Pillow 时退回 PySide6（桌宠项目里一定装了）
    try:
        from PySide6.QtGui import QImageReader
    except ImportError:
        raise SystemExit(
            "× 需要 Pillow 或 PySide6 来读图片尺寸。\n"
            "    激活 venv 后再跑：.venv\\Scripts\\activate"
        )
    Image = None
    QImageReader = QImageReader


def _read_size(p: Path) -> tuple[int, int] | None:
    try:
        if Image is not None:
            with Image.open(p) as im:
                return im.size  # (w, h)
        else:
            r = QImageReader(str(p))
            s = r.size()
            if s.isValid():
                return (s.width(), s.height())
    except Exception:
        return None
    return None


def _fmt(n: int) -> str:
    return f"{n:,}"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--folder", default="",
                    help="要查看的文件夹 / 单个文件。不填 = 项目的 assets/")
    args = ap.parse_args()

    project_root = Path(__file__).resolve().parent.parent
    target = Path(args.folder).expanduser().resolve() if args.folder else project_root / "assets"

    suffixes = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".tif", ".tiff"}

    files: list[Path] = []
    if target.is_file():
        files = [target]
    elif target.is_dir():
        files = sorted(p for p in target.rglob("*") if p.suffix.lower() in suffixes)
    else:
        print(f"× 路径不存在：{target}")
        sys.exit(1)

    if not files:
        print(f"在 {target} 里没找到图片。")
        return

    # 对齐宽度
    w_w = max((len(str(p.name)) for p in files), default=10) + 2
    header = f"{'文件名':<{w_w}}  {'尺寸(W×H)':>14}  {'类型':<6}"
    print(header)
    print("-" * len(header))
    for p in files:
        size = _read_size(p)
        size_str = f"{_fmt(size[0])}×{_fmt(size[1])}" if size else "× 读失败"
        print(f"{p.name:<{w_w}}  {size_str:>14}  {p.suffix.lower():<6}")


if __name__ == "__main__":
    main()
