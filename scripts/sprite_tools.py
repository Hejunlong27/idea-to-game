#!/usr/bin/env python3
"""精灵图处理：网格切分 / 抠图 / 裁边 / 缩放（模块 06 用）。

用法:
    # 网格切分（3 行 3 列），并裁掉透明边距
    python sprite_tools.py --input sheet.png --grid 3x3 --trim --out assets/processed/

    # 抠图：把指定背景色转为透明
    python sprite_tools.py --input fruit.png --matte --bg-color "#FFFFFF" --out assets/processed/

    # 批量缩放
    python sprite_tools.py --input assets/processed/ --resize 64x64 --out assets/processed/

    # 抠图：把指定背景色转为透明（从四边泛洪，主体内同色区域不受影响）
    python sprite_tools.py --input fruit.png --remove-bg --bg-color "#FF00FF" --out assets/processed/

    # 抠图 + 裁边 + 统一成 256x256 透明画布（居中）
    python sprite_tools.py --input assets/raw/ --remove-bg --trim --pad-to 256x256 --out assets/processed/

    # 按 alpha 自动裁边（去透明留白）
    python sprite_tools.py --input assets/processed/ --trim --out assets/processed/

依赖: Pillow
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

try:
    from PIL import Image
except ImportError:
    print("ERROR: 需要 Pillow。请安装：pip install pillow", file=sys.stderr)
    raise SystemExit(1)

IMG_EXT = {".png", ".webp", ".jpg", ".jpeg", ".bmp"}


def parse_grid(s: str) -> tuple[int, int]:
    try:
        r, c = s.lower().split("x")
        return int(r), int(c)
    except Exception:
        print(f"ERROR: --grid 格式应为 RxC，例如 3x3（收到 {s}）", file=sys.stderr)
        raise SystemExit(1)


def parse_size(s: str) -> tuple[int, int]:
    try:
        w, h = s.lower().split("x")
        return int(w), int(h)
    except Exception:
        print(f"ERROR: --resize 格式应为 WxH，例如 64x64（收到 {s}）", file=sys.stderr)
        raise SystemExit(1)


def parse_color(s: str) -> tuple[int, int, int]:
    s = s.strip().lstrip("#")
    if len(s) == 3:
        s = "".join(ch * 2 for ch in s)
    if len(s) != 6:
        print(f"ERROR: --bg-color 格式应为 #RRGGBB（收到 {s}）", file=sys.stderr)
        raise SystemExit(1)
    return tuple(int(s[i : i + 2], 16) for i in (0, 2, 4))  # type: ignore


def do_grid(im: Image.Image, rows: int, cols: int) -> list[Image.Image]:
    W, H = im.size
    cw, ch = W // cols, H // rows
    out = []
    for r in range(rows):
        for c in range(cols):
            out.append(im.crop((c * cw, r * ch, (c + 1) * cw, (r + 1) * ch)))
    return out


def do_matte(im: Image.Image, bg: tuple[int, int, int], tol: int = 24) -> Image.Image:
    im = im.convert("RGBA")
    px = im.load()
    W, H = im.size
    br, bg_, bb = bg
    for y in range(H):
        for x in range(W):
            r, g, b, a = px[x, y]
            if abs(r - br) <= tol and abs(g - bg_) <= tol and abs(b - bb) <= tol:
                px[x, y] = (r, g, b, 0)
    return im


def do_trim(im: Image.Image) -> Image.Image:
    im = im.convert("RGBA")
    bbox = im.getchannel("A").getbbox()
    if not bbox:
        return im
    return im.crop(bbox)


def do_resize(im: Image.Image, size: tuple[int, int]) -> Image.Image:
    return im.convert("RGBA").resize(size, Image.LANCZOS)


def do_pad_to(im: Image.Image, size: tuple[int, int]) -> Image.Image:
    """把图等比缩放进 size 画布并居中，留透明边（统一精灵尺寸用）。"""
    im = im.convert("RGBA")
    w, h = size
    scale = min(w / im.width, h / im.height)
    nw, nh = max(1, int(im.width * scale)), max(1, int(im.height * scale))
    canvas = Image.new("RGBA", size, (0, 0, 0, 0))
    canvas.paste(im.resize((nw, nh), Image.LANCZOS), ((w - nw) // 2, (h - nh) // 2))
    return canvas


def detect_border_color(im: Image.Image) -> tuple[int, int, int]:
    """取四边像素逐通道中位数作为实际背景色（模型不会精确画出指定色）。"""
    im = im.convert("RGBA")
    w, h = im.size
    px = im.load()
    step = max(1, w // 64)
    samples = []
    for x in range(0, w, step):
        samples.append(px[x, 0][:3])
        samples.append(px[x, h - 1][:3])
    for y in range(0, h, step):
        samples.append(px[0, y][:3])
        samples.append(px[w - 1, y][:3])
    chans = list(zip(*samples)) if samples else [(255,), (255,), (255,)]
    return tuple(sorted(c)[len(c) // 2] for c in chans)  # type: ignore


def do_remove_bg(im: Image.Image, bg: "tuple[int, int, int] | None", tol: int = 40) -> Image.Image:
    """从四边泛洪抠背景色。比 --matte 的全局替换更安全（不会误伤主体内部同色像素）。

    bg 为 None 时自动从四边取样。
    """
    im = im.convert("RGBA")
    w, h = im.size
    px = im.load()
    if bg is None:
        bg = detect_border_color(im)

    def close(c) -> bool:
        return all(abs(c[i] - bg[i]) <= tol for i in range(3))

    stack = [(x, 0) for x in range(w)] + [(x, h - 1) for x in range(w)]
    stack += [(0, y) for y in range(h)] + [(w - 1, y) for y in range(h)]
    seen = bytearray(w * h)
    while stack:
        x, y = stack.pop()
        if x < 0 or y < 0 or x >= w or y >= h:
            continue
        idx = y * w + x
        if seen[idx]:
            continue
        seen[idx] = 1
        r, g, b, a = px[x, y]
        if not close((r, g, b)):
            continue
        px[x, y] = (r, g, b, 0)
        stack.extend([(x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)])
    return im


def process_one(im: Image.Image, args) -> list[Image.Image]:
    results = []
    if args.grid:
        rows, cols = parse_grid(args.grid)
        parts = do_grid(im, rows, cols)
    else:
        parts = [im]
    for p in parts:
        if args.remove_bg:
            auto = args.bg_color.strip().lower() in ("auto", "")
            p = do_remove_bg(p, None if auto else parse_color(args.bg_color), args.bg_tolerance)
        if args.matte:
            p = do_matte(p, parse_color(args.bg_color), args.tolerance)
        if args.trim:
            p = do_trim(p)
        if args.resize:
            p = do_resize(p, parse_size(args.resize))
        if args.pad_to:
            p = do_pad_to(p, parse_size(args.pad_to))
        results.append(p)
    return results


def main() -> int:
    ap = argparse.ArgumentParser(description="精灵图处理工具")
    ap.add_argument("--input", required=True, help="输入图片或目录")
    ap.add_argument("--out", required=True, help="输出目录")
    ap.add_argument("--grid", default="", help="网格切分，如 3x3")
    ap.add_argument("--matte", action="store_true", help="全局抠图（背景色转透明，可能误伤主体内同色像素）")
    ap.add_argument("--remove-bg", action="store_true", help="从四边泛洪抠背景色（AI 出图首选）")
    ap.add_argument("--bg-color", default="#FFFFFF", help="抠图背景色；--remove-bg 时可传 auto 自动取样")
    ap.add_argument("--tolerance", type=int, default=24, help="--matte 容差，默认 24")
    ap.add_argument("--bg-tolerance", type=int, default=40, help="--remove-bg 容差，默认 40")
    ap.add_argument("--trim", action="store_true", help="按 alpha 裁掉透明边距")
    ap.add_argument("--resize", default="", help="统一缩放，如 64x64（会拉伸）")
    ap.add_argument("--pad-to", default="", help="等比缩放进 WxH 透明画布并居中，如 256x256")
    ap.add_argument("--prefix", default="", help="输出文件名前缀")
    args = ap.parse_args()

    src = Path(args.input).expanduser().resolve()
    outdir = Path(args.out).expanduser().resolve()
    outdir.mkdir(parents=True, exist_ok=True)

    if src.is_dir():
        files = sorted([f for f in src.iterdir() if f.suffix.lower() in IMG_EXT])
        if not files:
            print(f"ERROR: 目录内无图片：{src}", file=sys.stderr)
            return 1
    elif src.is_file():
        files = [src]
    else:
        print(f"ERROR: 输入不存在：{src}", file=sys.stderr)
        return 1

    written = 0
    for f in files:
        im = Image.open(f)
        parts = process_one(im, args)
        for i, p in enumerate(parts):
            if len(parts) == 1:
                name = f"{args.prefix}{f.stem}.png"
            else:
                name = f"{args.prefix}{f.stem}_{i + 1:02d}.png"
            dst = outdir / name
            p.save(dst, "PNG")
            written += 1

    print(f"已输出 {written} 个文件 → {outdir}")
    if args.grid:
        rows, cols = parse_grid(args.grid)
        print(f"网格 {rows}x{cols}，建议命名顺序按行优先，请核对与代码引用一致。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
