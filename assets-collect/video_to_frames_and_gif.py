"""从本地剧情视频里抽 PNG 帧，或直接合成 GIF（适合桌宠素材制作）。

前提：
    - support/ffmpeg.exe 已经放好（抖音爬虫用的那个），脚本会自动找
    - 视频文件随便放哪，用 --video 指过来就行

典型用法：
    # 1. 只抽 PNG 帧，每秒 6 张（不卡，够用），保存到 output/frames_ch01/
    python assets-collect/video_to_frames_and_gif.py \\
        --video "C:/Users/xxx/Video/捕获/第1章初遇.mp4" \\
        --frames-fps 6 --outdir assets-collect/output/frames_ch01

    # 2. 抽帧 + 同时合成 GIF（按 8fps 播放，循环 0 = 无限循环）
    python assets-collect/video_to_frames_and_gif.py \\
        --video "C:/Users/xxx/Video/捕获/王涵眨眼.mp4" \\
        --gif --gif-fps 8

    # 3. 裁切画面：只留中间主体（去掉顶部黑边 + 底部对话条）
    #    --crop x:y:w:h   x,y 是左上角坐标，w,h 是裁切后宽高
    #    1920x1080 → 比如裁成 x=540,y=200,w=840,h=880 → 中间 4:3 主体人像区
    python assets-collect/video_to_frames_and_gif.py \\
        --video "xxx.mp4" --crop 540:200:840:880 --gif

    # 4. 只取 00:01:20 ~ 00:01:45 这 25 秒（眨眼的动作区间）
    python assets-collect/video_to_frames_and_gif.py \\
        --video "xxx.mp4" --ss 00:01:20 --to 00:01:45 --frames-fps 10 --gif

    # 5. GIF 太大（默认 240 宽？）时，设 --gif-width 缩放
    python assets-collect/video_to_frames_and_gif.py \\
        --video "xxx.mp4" --gif --gif-width 240

抽好的帧 / GIF 都会落在 output/ 下（gitignore 已经锁死，不会进仓库，也不会随桌宠发布）。
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_OUT = _HERE / "output"


def find_ffmpeg() -> Path:
    """按桌宠项目约定找 support/ffmpeg.exe；找不到退回 PATH。"""
    project_root = _HERE.parent
    candidates = [
        project_root / "support" / "ffmpeg.exe",
        project_root / "support" / "bin" / "ffmpeg.exe",
        project_root / "support" / "tools" / "ffmpeg.exe",
    ]
    for c in candidates:
        if c.is_file():
            return c
    # 退回 PATH
    which = shutil.which("ffmpeg")
    if which:
        return Path(which)
    raise SystemExit(
        "× 找不到 ffmpeg.exe。\n"
        "    ① 把它复制到项目 support/ffmpeg.exe（抖音爬虫也要求它在那）；\n"
        "    ② 或确保 ffmpeg 已经加到系统 PATH 里。"
    )


def _parse_wxh(s: str) -> tuple[int, int]:
    s = (s or "").strip().lower()
    if not s:
        return (0, 0)
    s = s.replace("*", "x").replace("×", "x")
    if "x" not in s:
        raise ValueError("尺寸格式应为 WxH，如 240x320")
    w, h = s.split("x", 1)
    return (int(w.strip()), int(h.strip()))


def _fmt_size(n: int) -> str:
    if n < 1024:
        return f"{n} B"
    for u in ("KB", "MB", "GB"):
        n /= 1024.0
        if n < 1024:
            return f"{n:.1f} {u}"
    return f"{n:.1f} TB"


def _build_scale_pad(w: int, h: int) -> str | None:
    """把裁切后的画面等比缩放 + 居中白底留白，强制成 WxH。保证所有素材尺寸一致。"""
    if w <= 0 or h <= 0:
        return None
    # lanczos 降采样，再 color=white（RGB24）做画布，overlay 居中
    return (
        f"scale={w}:{h}:force_original_aspect_ratio=decrease:flags=lanczos,"
        f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:color=white"
    )


def main() -> None:
    ap = argparse.ArgumentParser(
        description="抽剧情视频成 PNG 帧 / 或直接合成桌宠用的 GIF",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    ap.add_argument("--video", required=True, help="剧情视频文件（mp4/mkv/mov/avi 都认）")
    ap.add_argument("--outdir", default=str(_OUT / "frames"),
                    help="PNG 帧保存目录（默认 output/frames，可自定义）")
    ap.add_argument("--frames-fps", type=float, default=6,
                    help="每秒抽多少张 PNG（默认 6，桌宠够用；写 0 = 用原视频帧率不抽，动作快就 8~10）")
    ap.add_argument("--frames-max", type=int, default=0,
                    help="最多抽 N 张（0 = 不限制，适合长视频不想全抽）")

    # 裁切（先裁后抽，省内存+省时间，还能顺便去掉对话条）
    ap.add_argument("--crop", type=str, default="",
                    help="裁切区域：x:y:w:h，如 1920x1080 裁中间人像 540:200:840:880")

    # 时间范围
    ap.add_argument("--ss", default="", help="起始时间，00:01:20 或 80（秒）都支持")
    ap.add_argument("--to", default="", help="结束时间")

    # GIF
    ap.add_argument("--gif", action="store_true", help="顺便合成 GIF（放在同目录）")
    ap.add_argument("--gif-fps", type=float, default=6,
                    help="GIF 每秒多少帧（默认 6 = 每张 167ms；写 0 = 用视频原帧率不抽）")
    ap.add_argument("--gif-loop", type=int, default=0, help="0=无限循环，1=放一次")
    ap.add_argument("--gif-width", type=int, default=0,
                    help="GIF 宽（0 = 和视频同宽；桌宠一般 240 足够）")
    ap.add_argument("--gif-size", type=str, default="",
                    help="GIF 统一输出尺寸 WxH，如 240x320（等比缩放+居中白底留白，保证素材尺寸一致）。"
                         "优先级高于 --gif-width。")
    ap.add_argument("--frames-size", type=str, default="",
                    help="PNG 帧也统一输出尺寸 WxH（和 --gif-size 同语法），保证你挑帧时不用手动调大小。")
    ap.add_argument("--gif-palette", action="store_true", default=True,
                    help="（默认打开）2 次编码生成调色板，GIF 画质更好；想省时间就 --no-gif-palette")
    ap.add_argument("--no-gif-palette", dest="gif_palette", action="store_false")

    args = ap.parse_args()

    # 1) 校验
    video = Path(args.video).expanduser().resolve()
    if not video.is_file():
        print(f"× 视频不存在：{video}")
        sys.exit(1)
    ffmpeg = find_ffmpeg()
    print(f"  ffmpeg: {ffmpeg}")
    print(f"  视频:   {video}   ({_fmt_size(video.stat().st_size)})")

    try:
        frames_w, frames_h = _parse_wxh(args.frames_size)
        gif_w, gif_h = _parse_wxh(args.gif_size)
    except ValueError as e:
        print(f"× {e}")
        sys.exit(1)

    outdir = Path(args.outdir).expanduser().resolve()
    outdir.mkdir(parents=True, exist_ok=True)
    prefix = video.stem or "video"

    # 2) 基础 crop filter（任何输出都先裁，避免对话条/黑边进后续流程）
    crop_filter: str | None = None
    if args.crop:
        items = args.crop.split(":")
        if len(items) != 4 or not all(x.isdigit() for x in items):
            print("× --crop 格式应为 x:y:w:h，如 540:200:840:880")
            sys.exit(1)
        crop_filter = f"crop={items[2]}:{items[3]}:{items[0]}:{items[1]}"

    # 3) 抽帧 vf：crop → fps（非 0 才抽）→ 统一尺寸（可选）
    vf_parts: list[str] = []
    if crop_filter:
        vf_parts.append(crop_filter)
    if args.frames_fps > 0:
        vf_parts.append(f"fps={args.frames_fps}")
    frames_scale = _build_scale_pad(frames_w, frames_h)
    if frames_scale:
        vf_parts.append(frames_scale)
    frames_vf = ",".join(vf_parts) if vf_parts else None

    # 4) GIF 专用的尺寸/缩放 filter（和 frames 分开，因为二者尺寸可以不同）
    def _build_gif_resize_filter() -> str | None:
        """决定 GIF 的最终 resize 策略：--gif-size 优先，否则 --gif-width。"""
        if gif_w > 0 and gif_h > 0:
            return _build_scale_pad(gif_w, gif_h)
        if args.gif_width > 0:
            return f"scale={args.gif_width}:-1:flags=lanczos"
        return None

    def _build_gif_vf_chains() -> tuple[str, str]:
        """返回 (palettegen 用的 vf, paletteuse 用的 filter chain 字符串不含 paletteuse 本身)。
        paletteuse 阶段是 -lavfi [0:v]crop..fps..resize[x];[x][1:v]paletteuse...
        """
        head: list[str] = []
        if crop_filter:
            head.append(crop_filter)
        if args.gif_fps > 0:
            head.append(f"fps={args.gif_fps}")
        # gif_fps == 0 → 不加 fps filter，保留原视频 29.97fps
        resizer = _build_gif_resize_filter()
        if resizer:
            head.append(resizer)
        chain = ",".join(head)
        return (chain, chain)

    def _build_gif_simple_vf() -> str:
        """1 次编码兜底的 -vf。"""
        head: list[str] = []
        if crop_filter:
            head.append(crop_filter)
        if args.gif_fps > 0:
            head.append(f"fps={args.gif_fps}")
        resizer = _build_gif_resize_filter()
        if resizer:
            head.append(resizer)
        return ",".join(head)

    # 3) 抽帧命令
    frame_pattern = outdir / f"{prefix}_%05d.png"
    cmd = [str(ffmpeg), "-hide_banner", "-loglevel", "error", "-stats"]
    if args.ss:
        cmd += ["-ss", args.ss]
    if args.to:
        cmd += ["-to", args.to]
    cmd += ["-i", str(video)]
    if frames_vf:
        cmd += ["-vf", frames_vf]
    if args.frames_max:
        cmd += ["-frames:v", str(args.frames_max)]
    cmd += ["-y", str(frame_pattern)]

    frames_fps_hint = (
        "原视频帧率（不抽）" if args.frames_fps == 0 else f"{args.frames_fps}"
    )
    frames_size_hint = ""
    if frames_w > 0 and frames_h > 0:
        frames_size_hint = f"   →统一 {frames_w}x{frames_h}"

    print()
    print("  [1/2] 抽帧…")
    print(f"        输出: {outdir}/{prefix}_*.png")
    print(f"        fps= {frames_fps_hint}" + (f"   crop= {args.crop}" if args.crop else "") +
          frames_size_hint + (f"   max= {args.frames_max}" if args.frames_max else ""))
    t0 = time.time()
    rc = subprocess.run(cmd).returncode
    if rc != 0:
        print(f"× ffmpeg 抽帧失败 exit={rc}")
        sys.exit(rc)
    frames = sorted(outdir.glob(f"{prefix}_*.png"))
    # 过滤 ffmpeg 只在这次运行写的（其实就是 glob 通配就行）
    dt = time.time() - t0
    total_sz = sum(p.stat().st_size for p in frames)
    print(f"        ✅ 抽了 {len(frames)} 张 PNG，占用 {_fmt_size(total_sz)}，耗时 {dt:.1f}s")
    if not frames:
        print("  × 没抽出任何帧，检查时间范围 --ss/--to 或 fps。")
        sys.exit(1)

    # 4) 可选合成 GIF
    if not args.gif:
        print()
        print("  —— 不合成 GIF，结束。需要的话下次在同一命令末尾加 --gif 或再补：")
        print(f"       python assets-collect/video_to_frames_and_gif.py --video \"{args.video}\" "
              f"--frames-fps {args.frames_fps} --gif --gif-fps {args.gif_fps}")
        return

    gif_fps_hint = "原视频帧率（不抽，约29.97fps）" if args.gif_fps == 0 else f"{args.gif_fps}"
    gif_size_hint = ""
    if gif_w > 0 and gif_h > 0:
        gif_size_hint = f" →统一 {gif_w}x{gif_h}"
    elif args.gif_width > 0:
        gif_size_hint = f" →宽 {args.gif_width}px"

    print()
    print("  [2/2] 合成 GIF…")
    print(f"        fps= {gif_fps_hint}" + gif_size_hint +
          (f"   crop= {args.crop}" if args.crop else ""))
    gif_path = outdir / f"{prefix}.gif"

    if args.gif_palette:
        # 2-pass 调色板（官方推荐，画质好很多）
        palette = outdir / f".{prefix}_palette.png"
        vf1_gen, head_chain = _build_gif_vf_chains()
        cmd_a = [str(ffmpeg), "-hide_banner", "-loglevel", "error"]
        if args.ss:
            cmd_a += ["-ss", args.ss]
        if args.to:
            cmd_a += ["-to", args.to]
        cmd_a += [
            "-i", str(video),
            "-vf", (vf1_gen + "," if vf1_gen else "") + "palettegen=stats_mode=diff",
            "-y", str(palette),
        ]
        print(f"        第 1/2 步：生成调色板 palette.png…")
        rc = subprocess.run(cmd_a).returncode
        if rc != 0:
            print(f"  × 生成调色板失败 exit={rc}，退回 1 次编码。")
            args.gif_palette = False
        else:
            # paletteuse 阶段：[0:v] head_chain [x]; [x][1:v] paletteuse ...
            paletteuse_cfg = "paletteuse=dither=bayer:bayer_scale=3:diff_mode=rectangle"
            if head_chain:
                lavfi = f"[0:v]{head_chain}[x];[x][1:v]{paletteuse_cfg}"
            else:
                lavfi = f"[0:v][1:v]{paletteuse_cfg}"
            cmd_b = [str(ffmpeg), "-hide_banner", "-loglevel", "error", "-stats"]
            if args.ss:
                cmd_b += ["-ss", args.ss]
            if args.to:
                cmd_b += ["-to", args.to]
            cmd_b += [
                "-i", str(video),
                "-i", str(palette),
                "-lavfi", lavfi,
                "-loop", str(args.gif_loop),
                "-y", str(gif_path),
            ]
            print(f"        第 2/2 步：2-pass 合成 GIF（画质更好）…")
            rc = subprocess.run(cmd_b).returncode
            try:
                if palette.is_file():
                    os.unlink(palette)
            except Exception:
                pass
            if rc != 0:
                print(f"  × 2-pass GIF 合成失败 exit={rc}，退回 1 次编码。")
                args.gif_palette = False

    if not args.gif_palette:
        # 1 次编码兜底（简单但色带多）
        vf = _build_gif_simple_vf()
        cmd = [str(ffmpeg), "-hide_banner", "-loglevel", "error", "-stats"]
        if args.ss:
            cmd += ["-ss", args.ss]
        if args.to:
            cmd += ["-to", args.to]
        cmd += [
            "-i", str(video),
        ]
        if vf:
            cmd += ["-vf", vf]
        cmd += [
            "-loop", str(args.gif_loop),
            "-y", str(gif_path),
        ]
        rc = subprocess.run(cmd).returncode
        if rc != 0:
            print(f"  × GIF 合成失败 exit={rc}")
            sys.exit(rc)

    sz = gif_path.stat().st_size if gif_path.is_file() else 0
    print(f"        ✅ GIF 已生成：{gif_path}   ({_fmt_size(sz)})")
    if sz > 10 * 1024 * 1024:
        print(f"        ⚠ 文件 > 10MB，建议再调：--gif-size 240x320 或 --gif-width 240，"
              f"或 --gif-fps 降到 6，或缩小 --ss/--to 时间范围。")
    if args.gif_fps == 0 and sz > 3 * 1024 * 1024:
        print(f"        提示：当前是原视频帧率（约29.97fps）。如果你不需要这么流畅，"
              f"加 --gif-fps 6 体积可以小 80%。")

    print()
    print("  下一步：")
    print(f"    · 手动挑 {len(frames)} 张 PNG 里你喜欢的，给 idle/walking 这些动画目录用")
    print(f"    · GIF 可以直接拖进图像工具（PS/画图 3D/格式工厂）再裁一下人物区域，")
    print("      或用 --crop + --gif-size 重新跑脚本得到"
          "等比缩放并居中的精简 GIF（白底留白，保证尺寸一致）。")


if __name__ == "__main__":
    main()
