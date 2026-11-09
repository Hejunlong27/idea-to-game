#!/usr/bin/env python3
"""Consistency Check —— 生成素材的一致性度量。

## 为什么需要它

AI 美术落地最大的坑不是「画得好不好看」，是**同一个角色生成 10 次有 10 个样**。
铺开全套素材前必须先回答：这个差异能不能接受？

靠肉眼比 10 张图不可靠（人眼对「感觉像不像」判断很主观）。所以要量化。

## 三个指标

| 指标 | 测什么 | 判读 |
|---|---|---|
| **pHash 汉明距离** | 整体感知相似度 | <10 几乎相同 / 10–20 同角色有差异 / >20 像不同角色 |
| **剪影 IoU** | 轮廓重合度 | >0.75 好 / 0.55–0.75 可接受 / <0.55 形状漂移 |
| **主色距离** | 配色一致性 | ΔRGB <30 一致 / 30–60 有偏差 / >60 配色漂移 |

pHash 用 aHash + dHash 双哈希（不需要 DCT 依赖），对缩放和压缩鲁棒。

## 用法

  python consistency_check.py --dir docs/02-art/consistency
  python consistency_check.py --dir ... --json out.json
"""

from __future__ import annotations

import argparse
import itertools
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image

# 判定阈值（写在这里，不散落在代码里）
THRESHOLDS = {
    "phash_good": 10,
    "phash_ok": 20,
    "iou_good": 0.75,
    "iou_ok": 0.55,
    "color_good": 30,
    "color_ok": 60,
}


def ahash(img: Image.Image, size: int = 8) -> int:
    """均值哈希：缩到 size²，与均值比较得 bit。"""
    g = img.convert("L").resize((size, size), Image.LANCZOS)
    a = np.asarray(g, dtype=np.float32)
    bits = (a > a.mean()).flatten()
    v = 0
    for b in bits:
        v = (v << 1) | int(b)
    return v


def dhash(img: Image.Image, size: int = 8) -> int:
    """差分哈希：相邻像素比较，对亮度变化更敏感。"""
    g = img.convert("L").resize((size + 1, size), Image.LANCZOS)
    a = np.asarray(g, dtype=np.float32)
    bits = (a[:, 1:] > a[:, :-1]).flatten()
    v = 0
    for b in bits:
        v = (v << 1) | int(b)
    return v


def hamming(a: int, b: int) -> int:
    return bin(a ^ b).count("1")


def silhouette(img: Image.Image) -> np.ndarray:
    """抠掉浅灰背景得到二值掩码。素材约定用浅色纯背景。"""
    rgb = np.asarray(img.convert("RGB"), dtype=np.int16)
    # 背景判定：三通道都接近白/浅灰
    bg = (rgb[:, :, 0] > 200) & (rgb[:, :, 1] > 200) & (rgb[:, :, 2] > 200)
    return ~bg


def color_mean(img: Image.Image, mask: np.ndarray) -> np.ndarray:
    """主体区域的平均 RGB。"""
    rgb = np.asarray(img.convert("RGB"), dtype=np.float32)
    if mask.sum() == 0:
        return np.array([0.0, 0.0, 0.0])
    return rgb[mask].mean(axis=0)


def compare(a_path: Path, b_path: Path) -> dict:
    a_img, b_img = Image.open(a_path), Image.open(b_path)
    ha, hb = ahash(a_img), ahash(b_img)
    da, db = dhash(a_img), dhash(b_img)

    ma, mb = silhouette(a_img), silhouette(b_img)
    if ma.shape != mb.shape:
        mb = np.asarray(
            Image.fromarray((mb * 255).astype(np.uint8)).resize(
                (ma.shape[1], ma.shape[0]), Image.NEAREST
            )
        ) > 127
    inter = np.logical_and(ma, mb).sum()
    union = np.logical_or(ma, mb).sum()
    iou = float(inter / union) if union else 0.0

    ca, cb = color_mean(a_img, ma), color_mean(b_img, mb)
    color_dist = float(np.linalg.norm(ca - cb))

    return {
        "phash": hamming(ha, hb) + hamming(da, db),  # 双哈希合并，满分 128
        "iou": round(iou, 3),
        "color": round(color_dist, 1),
    }


def judge(m: dict) -> str:
    if m["phash"] <= THRESHOLDS["phash_good"] and m["iou"] >= THRESHOLDS["iou_good"]:
        return "几乎相同"
    if m["phash"] <= THRESHOLDS["phash_ok"] and m["iou"] >= THRESHOLDS["iou_ok"]:
        return "同角色有差异"
    return "像不同角色"


def main() -> int:
    ap = argparse.ArgumentParser(description="生成素材一致性度量")
    ap.add_argument("--dir", required=True)
    ap.add_argument("--json", default="")
    ap.add_argument("--prefix", default="", help="只算指定前缀（t2i / i2i），空表示全部")
    args = ap.parse_args()

    d = Path(args.dir)
    if not d.is_dir():
        print(f"目录不存在：{d}", file=sys.stderr)
        return 2
    prefixes = (args.prefix + "_",) if args.prefix else ("t2i_", "i2i_")
    files = sorted(p for p in d.glob("*.png") if p.name.startswith(prefixes))
    if len(files) < 2:
        print(f"至少需要 2 张样本，当前 {len(files)} 张", file=sys.stderr)
        return 2

    print(f"样本 {len(files)} 张：{', '.join(p.stem for p in files)}\n")

    pairs = []
    for a, b in itertools.combinations(files, 2):
        m = compare(a, b)
        m["a"], m["b"] = a.stem, b.stem
        pairs.append(m)

    ph = [p["phash"] for p in pairs]
    io_ = [p["iou"] for p in pairs]
    co = [p["color"] for p in pairs]

    def stat(name, vals, unit="", higher_better=False):
        # IoU 越大越好，其余越小越好 —— 不能一律按 min 当「最好」
        best = max(vals) if higher_better else min(vals)
        worst = min(vals) if higher_better else max(vals)
        return f"{name}  平均 {np.mean(vals):.1f}{unit}  最好 {best:.1f}  最差 {worst:.1f}"

    print("两两对比（共 %d 对）" % len(pairs))
    print("─" * 62)
    print(stat("pHash 距离 ", ph, " / 128"))
    print(stat("剪影 IoU   ", io_, higher_better=True))
    print(stat("主色距离   ", co, " / 441"))
    print()

    # 分布
    tags = {"几乎相同": 0, "同角色有差异": 0, "像不同角色": 0}
    for p in pairs:
        tags[judge(p)] += 1
    print("判定分布")
    print("─" * 62)
    for k, v in tags.items():
        print(f"  {k:<12} {v:>3} 对（{v / len(pairs) * 100:.0f}%）")
    print()

    # 最差的一对
    worst = max(pairs, key=lambda p: p["phash"])
    print(f"差异最大的一对：{worst['a']} vs {worst['b']}")
    print(f"  pHash {worst['phash']}  IoU {worst['iou']}  主色 {worst['color']}")
    print()

    # 结论
    same = tags["几乎相同"]
    drift = tags["像不同角色"]
    print("结论")
    print("─" * 62)
    if drift == 0 and same >= len(pairs) * 0.5:
        print("一致性可接受：全部是「同角色有差异」以内，多数几乎相同。可以铺开。")
        verdict = "PASS"
    elif drift <= len(pairs) * 0.15:
        print("基本可用：绝大多数同角色，少数漂移。建议用 i2i ref 锁定后再铺开。")
        verdict = "WARN"
    else:
        print("一致性不足：大量样本像不同角色。纯 t2i 不可用于量产，必须上 ref / ControlNet。")
        verdict = "FAIL"
    print(f"\n判定：{verdict}")

    if args.json:
        out = Path(args.json)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(
            json.dumps(
                {
                    "samples": [p.stem for p in files],
                    "pairs": pairs,
                    "summary": {
                        "phash_mean": round(float(np.mean(ph)), 1),
                        "phash_worst": max(ph),
                        "iou_mean": round(float(np.mean(io_)), 3),
                        "iou_worst": round(min(io_), 3),
                        "color_mean": round(float(np.mean(co)), 1),
                        "distribution": tags,
                    },
                    "verdict": verdict,
                    "thresholds": THRESHOLDS,
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        print(f"报告：{out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
