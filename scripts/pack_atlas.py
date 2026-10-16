#!/usr/bin/env python3
"""把切好的精灵打包成 Phaser 可用的纹理图集（模块 06 用）。

用法:
    python pack_atlas.py --input assets/processed/ --out assets/atlas/atlas \
        [--padding 2] [--max-size 2048] [--name game]

产出: <out>.png + <out>.json（TexturePacker JSON Hash 格式，Phaser 可直接加载）

依赖: Pillow
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

try:
    from PIL import Image
except ImportError:
    print("ERROR: 需要 Pillow。请安装：pip install pillow", file=sys.stderr)
    raise SystemExit(1)

IMG_EXT = {".png", ".webp", ".bmp"}


def next_pow2(n: int) -> int:
    p = 1
    while p < n:
        p *= 2
    return p


def pack_shelf(items, max_w: int, max_h: int, padding: int):
    """货架式装箱：同一页内先横向排，排满换行，行满换页。

    items: [(name, w, h)]，已按高度降序排列。
    返回 pages: [{"rects": [...], "w": 已用宽, "h": 已用高}]
    """
    pages = []
    page = {"rects": [], "w": 0, "h": 0}
    shelf_y = 0
    shelf_h = 0
    row_x = 0

    for name, w, h in items:
        need_w = w + padding * 2
        need_h = h + padding * 2

        if row_x + need_w > max_w:
            shelf_y += shelf_h
            shelf_h = 0
            row_x = 0

        if shelf_y + need_h > max_h:
            page["h"] = shelf_y + shelf_h
            pages.append(page)
            page = {"rects": [], "w": 0, "h": 0}
            shelf_y = 0
            shelf_h = 0
            row_x = 0

        page["rects"].append({"name": name, "x": row_x + padding, "y": shelf_y + padding, "w": w, "h": h})
        row_x += need_w
        shelf_h = max(shelf_h, need_h)
        page["w"] = max(page["w"], row_x)

    if page["rects"]:
        page["h"] = shelf_y + shelf_h
        pages.append(page)
    return pages


def main() -> int:
    ap = argparse.ArgumentParser(description="打包纹理图集")
    ap.add_argument("--input", required=True, help="精灵目录")
    ap.add_argument("--out", required=True, help="输出前缀，如 assets/atlas/atlas")
    ap.add_argument("--padding", type=int, default=2)
    ap.add_argument("--max-size", type=int, default=2048, help="单张图集最大边长，默认 2048")
    ap.add_argument("--name", default="atlas", help="meta.image 引用的文件名前缀")
    args = ap.parse_args()

    srcdir = Path(args.input).expanduser().resolve()
    if not srcdir.is_dir():
        print(f"ERROR: 输入目录不存在：{srcdir}", file=sys.stderr)
        return 1
    files = sorted([f for f in srcdir.iterdir() if f.suffix.lower() in IMG_EXT])
    if not files:
        print(f"ERROR: 目录内无图片：{srcdir}", file=sys.stderr)
        return 1

    imgs = {}
    items = []
    for f in files:
        im = Image.open(f).convert("RGBA")
        imgs[f.stem] = im
        items.append((f.stem, im.width, im.height))

    items.sort(key=lambda t: (-t[2], -t[1]))

    # 目标宽度：让图集尽量接近正方形，避免出现又宽又扁的图集
    area = sum((w + args.padding * 2) * (h + args.padding * 2) for _, w, h in items)
    import math

    target_w = next_pow2(max(64, int(math.sqrt(area * 1.25))))
    target_w = min(max(target_w, 128), args.max_size)
    widest = max(w + args.padding * 2 for _, w, h in items)
    if target_w < widest:
        target_w = min(next_pow2(widest), args.max_size)

    pages = pack_shelf(items, target_w, args.max_size, args.padding)

    outp = Path(args.out).expanduser().resolve()
    outp.parent.mkdir(parents=True, exist_ok=True)

    if len(pages) > 1:
        print(f"WARN: 素材超出单张 {args.max_size}px 图集，已拆为 {len(pages)} 张。"
              f"建议减少素材数量或缩小尺寸。")

    manifest = {}
    for pi, page in enumerate(pages):
        W = next_pow2(max(page["w"], 1))
        H = next_pow2(max(page["h"], 1))
        W = min(W, args.max_size) if W > args.max_size else W
        H = min(H, args.max_size) if H > args.max_size else H
        canvas = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        frames = {}
        for r in page["rects"]:
            src = imgs[r["name"]]
            canvas.paste(src, (r["x"], r["y"]), src)
            frames[r["name"]] = {
                "frame": {"x": r["x"], "y": r["y"], "w": r["w"], "h": r["h"]},
                "rotated": False,
                "trimmed": False,
                "spriteSourceSize": {"x": 0, "y": 0, "w": r["w"], "h": r["h"]},
                "sourceSize": {"w": r["w"], "h": r["h"]},
            }
        suffix = "" if len(pages) == 1 else f"_{pi + 1}"
        img_name = f"{args.name}{suffix}.png"
        json_name = f"{args.name}{suffix}.json"
        canvas.save(outp.parent / img_name, "PNG")
        data = {
            "frames": frames,
            "meta": {
                "app": "idea-to-game",
                "version": "1.0",
                "image": img_name,
                "format": "RGBA8888",
                "size": {"w": W, "h": H},
                "scale": "1",
            },
        }
        (outp.parent / json_name).write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        manifest[img_name] = len(frames)
        print(f"  页 {pi + 1}: {img_name} ({W}x{H})，{len(frames)} 帧")

    print(f"完成。图集输出至 {outp.parent}")
    print("\nPhaser 加载方式：")
    for img_name in manifest:
        key = Path(img_name).stem
        print(f"  this.load.atlas('{key}', 'assets/atlas/{img_name}', 'assets/atlas/{key}.json');")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
