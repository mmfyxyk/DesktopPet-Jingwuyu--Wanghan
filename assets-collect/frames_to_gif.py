"""把一文件夹的 PNG 序列（达芬奇导出的抠图序列）直接合成 GIF。

配合流程 B 用：
    录屏 → 达芬奇抠图、裁紧、导出 PNG 序列 → 用这个脚本合成 GIF。

典型用法：
    # 1. 最基础：文件夹里按文件名排序，直接按原尺寸合成
    python assets-collect/frames_to_gif.py \\
        --folder "D:/素材/王涵眨眼序列" --out assets-collect/output/眨眼.gif --fps 8

    # 2. 强制缩成统一尺寸 240x320（居中白底留白，保证跟之前的 GIF 一样大）
    python assets-collect/frames_to_gif.py \\
        --folder "D:/素材/王涵眨眼序列" --out 眨眼.gif --fps 6 --size 240x320

    # 3. 只取前 30 张（后面是重复动作不想保留），并让每帧播放 2 次 → 慢动作
    python assets-collect/frames_to_gif.py \\
        --folder xxx --out xxx.gif --fps 6 --max 30 --repeat-each 2

    # 4. 背景透明！（达芬奇抠图后带 alpha，--transparent 会保留透明通道生成 GIF）
    #    注意：GIF 的透明只能 0/1，半透明会有锯齿。真正桌面透明效果建议 --transparent。
    python assets-collect/frames_to_gif.py \\
        --folder xxx --out xxx.gif --fps 8 --transparent

产物建议直接丢 assets/ 替换「试.gif」，改 ASSET_MAP 里的路径即可。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

try:
    from PIL import Image
except ImportError:
    raise SystemExit("× 需要 Pillow。先激活 venv 后 pip install Pillow，或用 conda 装。")


def _parse_wxh(s: str) -> tuple[int, int]:
    s = (s or "").strip().lower().replace("*", "x").replace("×", "x")
    if not s:
        return (0, 0)
    if "x" not in s:
        raise ValueError("尺寸格式应为 WxH，如 240x320")
    w, h = s.split("x", 1)
    return int(w.strip()), int(h.strip())


def _paste_to_canvas(
    img: Image.Image,
    w: int,
    h: int,
    mode: str,
    bg_color,
) -> Image.Image:
    """把 img 等比缩放到能放进 (w,h) 内，居中贴在对应画布上。"""
    # 先算缩放比
    ratio = min(w / img.width, h / img.height)
    new_w = max(1, int(img.width * ratio))
    new_h = max(1, int(img.height * ratio))
    if (new_w, new_h) != (img.width, img.height):
        img = img.resize((new_w, new_h), Image.LANCZOS)
    # 决定画布模式/背景
    if mode == "RGBA":
        canvas = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    else:
        canvas = Image.new("RGB", (w, h), bg_color)
    x = (w - new_w) // 2
    y = (h - new_h) // 2
    if img.mode == "RGBA" and mode != "RGBA":
        # 把透明合成成白底（用 alpha 通道 blend）
        bg = Image.new("RGB", img.size, bg_color)
        bg.paste(img.convert("RGB"), mask=img.split()[-1])
        canvas.paste(bg, (x, y))
    elif img.mode != "RGBA" and mode == "RGBA":
        canvas.paste(img.convert("RGBA"), (x, y))
    else:
        canvas.paste(img, (x, y))
    return canvas


def main() -> None:
    ap = argparse.ArgumentParser(description="把 PNG 序列合成 GIF（配合达芬奇抠图导出用）")
    ap.add_argument("--folder", required=True, help="放 PNG 序列的文件夹")
    ap.add_argument("--out", required=True, help="输出的 .gif 路径")
    ap.add_argument("--fps", type=float, default=8, help="GIF 每秒帧数（默认 8，不跳）")
    ap.add_argument("--pattern", default="*.png", help="匹配文件名 glob（默认 *.png）")
    ap.add_argument("--max", type=int, default=0, help="最多用 N 张（0 不限）")
    ap.add_argument("--start", type=int, default=0, help="从第几张开始（0 开头）")
    ap.add_argument("--repeat-each", type=int, default=1,
                    help="每张帧在 GIF 里重复 N 次（实现慢动作，fps 不用动）")
    ap.add_argument("--size", default="", help="强制输出尺寸 WxH，如 240x320，等比缩放居中留白")
    ap.add_argument("--bg", default="white",
                    help="非透明模式下留白的背景色（white/black/#f0f0f0，默认 white）")
    ap.add_argument("--transparent", action="store_true",
                    help="保留透明背景（输出 alpha 透明 GIF，桌宠背景会是真正透明）")
    ap.add_argument("--loop", type=int, default=0, help="0=无限循环，1=播一次")
    args = ap.parse_args()

    folder = Path(args.folder).expanduser().resolve()
    out = Path(args.out).expanduser().resolve()
    if not folder.exists():
        print(f"× 文件夹不存在：{folder}")
        sys.exit(1)
    try:
        size_w, size_h = _parse_wxh(args.size)
    except ValueError as e:
        print(f"× {e}")
        sys.exit(1)

    # 解析背景色（只对不透明模式有用）
    bg = args.bg.strip()
    if bg.startswith("#"):
        bg_color = (int(bg[1:3], 16), int(bg[3:5], 16), int(bg[5:7], 16))
    elif bg.lower() in ("w", "white"):
        bg_color = (255, 255, 255)
    elif bg.lower() in ("b", "black"):
        bg_color = (0, 0, 0)
    else:
        bg_color = (255, 255, 255)

    files = sorted(folder.glob(args.pattern))
    if not files:
        files = sorted(folder.glob(args.pattern.upper()))
    if not files:
        print(f"× {folder} 里没找到 {args.pattern} 的文件")
        sys.exit(1)

    files = files[args.start:]
    if args.max > 0:
        files = files[: args.max]

    print(f"  共找到 {len(files)} 张：{files[0].name} …… {files[-1].name}")

    if args.fps <= 0:
        print("× --fps 必须 > 0")
        sys.exit(1)
    duration_ms = int(round(1000 / args.fps))

    force_size = size_w > 0 and size_h > 0
    out_mode = "RGBA" if args.transparent else "RGB"

    # 预读所有帧并处理（PIL 写 GIF 时需要一整个 list）
    frames: list[Image.Image] = []
    for i, p in enumerate(files):
        try:
            im = Image.open(p)
            im.load()
        except Exception as e:
            print(f"    ⚠ 跳过 {p.name}: {e}")
            continue

        # 处理模式
        if out_mode == "RGBA":
            if im.mode != "RGBA":
                im = im.convert("RGBA")
        else:
            if im.mode == "RGBA":
                # 合成到白底（保留图像再贴）
                bg_img = Image.new("RGB", im.size, bg_color)
                alpha = im.split()[-1]
                bg_img.paste(im.convert("RGB"), mask=alpha)
                im = bg_img
            elif im.mode != "RGB":
                im = im.convert("RGB")

        # 处理强制统一尺寸
        if force_size:
            im = _paste_to_canvas(im, size_w, size_h, out_mode, bg_color)

        # repeat each
        for _ in range(max(1, args.repeat_each)):
            frames.append(im.copy())

    if not frames:
        print("× 没可写的帧")
        sys.exit(1)

    out.parent.mkdir(parents=True, exist_ok=True)

    # 写 GIF
    save_kwargs = {
        "save_all": True,
        "append_images": frames[1:],
        "duration": duration_ms,
        "loop": args.loop,
        "optimize": True,
    }
    if args.transparent:
        # Pillow 的 GIF 透明需要 disposal=2（每帧清空重来），避免残影
        save_kwargs["transparency"] = 0
        save_kwargs["disposal"] = 2
    try:
        frames[0].save(out, format="GIF", **save_kwargs)
    except Exception as e:
        print(f"× 写 GIF 失败：{e}")
        sys.exit(1)

    sz = out.stat().st_size
    sz_str = (
        f"{sz/1024/1024:.2f} MB" if sz > 1024 * 1024 else f"{sz/1024:.1f} KB"
    )
    # 首帧尺寸用于打印
    fw, fh = frames[0].size
    print()
    print(f"  ✅ 完成：{out}")
    print(f"     尺寸：{fw}×{fh}   帧数：{len(frames)}   fps：{args.fps}   时长：{len(frames)/args.fps:.1f}s   体积：{sz_str}")
    if sz > 10 * 1024 * 1024:
        print("     ⚠ 体积过大，建议：--fps 6 或 --size 240x320 或 --max 30")


if __name__ == "__main__":
    main()
