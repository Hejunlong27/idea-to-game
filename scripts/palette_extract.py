#!/usr/bin/env python3
"""从风格参考图提取主色板，产出 palette.json（模块 03 用）。

用法:
    python palette_extract.py --input style.png --out docs/02-art/palette.json [--colors 8]

依赖: Pillow, numpy
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

try:
    import numpy as np
    from PIL import Image
except ImportError:
    print("ERROR: 需要 Pillow 与 numpy。请安装：pip install pillow numpy", file=sys.stderr)
    raise SystemExit(1)


def hex_of(rgb) -> str:
    return "#{:02X}{:02X}{:02X}".format(int(rgb[0]), int(rgb[1]), int(rgb[2]))


def load_pixels(path: Path, max_side: int = 320):
    im = Image.open(path).convert("RGBA")
    im.thumbnail((max_side, max_side))
    arr = np.asarray(im).astype(np.float32)
    alpha = arr[:, :, 3]
    rgb = arr[:, :, :3]
    mask = alpha > 32
    if mask.sum() < 100:
        mask = np.ones(alpha.shape, dtype=bool)
    return rgb[mask]


def kmeans(pixels: np.ndarray, k: int, iters: int = 24, seed: int = 7):
    rng = np.random.default_rng(seed)
    if len(pixels) > 60000:
        idx = rng.choice(len(pixels), 60000, replace=False)
        pixels = pixels[idx]
    # k-means++ 初始化
    centers = [pixels[rng.integers(len(pixels))]]
    for _ in range(k - 1):
        d = np.min(((pixels[:, None, :] - np.array(centers)[None, :, :]) ** 2).sum(-1), axis=1)
        s = float(d.sum())
        if not np.isfinite(s) or s <= 0:
            centers.append(pixels[rng.integers(len(pixels))])
            continue
        probs = d / s
        probs = probs / probs.sum()
        probs = np.nan_to_num(probs, nan=0.0, posinf=0.0, neginf=0.0)
        if probs.sum() <= 0:
            centers.append(pixels[rng.integers(len(pixels))])
            continue
        centers.append(pixels[rng.choice(len(pixels), p=probs)])
    C = np.array(centers, dtype=np.float32)
    labels = np.zeros(len(pixels), dtype=np.int32)
    for _ in range(iters):
        dist = ((pixels[:, None, :] - C[None, :, :]) ** 2).sum(-1)
        labels = dist.argmin(axis=1)
        for i in range(k):
            sel = pixels[labels == i]
            if len(sel):
                C[i] = sel.mean(axis=0)
    counts = Counter(labels.tolist())
    order = [i for i, _ in counts.most_common()]
    return C[order], [counts[i] for i in order], len(pixels)


def relative_luminance(rgb) -> float:
    r, g, b = [c / 255.0 for c in rgb[:3]]
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def main() -> int:
    ap = argparse.ArgumentParser(description="提取参考图主色板")
    ap.add_argument("--input", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--colors", type=int, default=8, help="主色数量，建议 5–8")
    ap.add_argument("--name", default="", help="素材名（可选，仅记录）")
    args = ap.parse_args()

    src = Path(args.input).expanduser().resolve()
    if not src.is_file():
        print(f"ERROR: 参考图不存在：{src}", file=sys.stderr)
        return 1

    pixels = load_pixels(src)
    k = max(2, min(args.colors, 12))
    centers, counts, total = kmeans(pixels, k)

    ordered = sorted(range(len(centers)), key=lambda i: relative_luminance(centers[i]))
    by_light = [centers[i] for i in ordered]

    background = hex_of(by_light[-1])
    accent = hex_of(by_light[0])
    primary = [hex_of(c) for c in by_light]

    data = {
        "source_image": src.name,
        "primary": primary,
        "accent": [accent],
        "background": background,
        "coverage": {hex_of(centers[i]): round(counts[i] / total, 4) for i in range(len(centers))},
        "line_style": "",
        "shading": "",
        "texture": "",
        "mood": [],
        "style_tokens": "",
        "_todo": "人工补全 line_style / shading / texture / mood，并合成 style_tokens（见 modules/03-art-bible.md）",
    }

    out = Path(args.out).expanduser().resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"已提取 {len(primary)} 个主色 → {out}")
    for h in primary:
        print(f"  {h}")
    print("\n下一步：人工判读线条/着色/质感/氛围，并合成一行 style_tokens。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
