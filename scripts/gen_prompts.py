#!/usr/bin/env python3
"""从 scope.json + palette.json 批量生成生图提示词（模块 03 收尾 / 05 前置）。

目的：把「写提示词」这件确定性的事自动化，保证
  ① 每个素材都有提示词（不漏）
  ② 每条都带 style_tokens（gate_check 的硬校验项）
  ③ 风格串只出现一次，避免风格漂移

用法:
    python gen_prompts.py                      # 补齐缺失的提示词，不动已有文件
    python gen_prompts.py --force              # 全部重写
    python gen_prompts.py --background none    # 不加纯色背景指令（工作流自带抠图时用）

    # 一张图出多个素材（九宫格）
    python gen_prompts.py --sheet items --grid 3x3 --items apple,pear,banana,grape,peach,lemon,plum,kiwi,cherry
    # 一张图出一套动画帧（2x2 四帧）
    python gen_prompts.py --frames slime_idle --grid 2x2 --frames 4 \
        --subject "a cute round slime monster" --action "idle breathing"

输入: docs/01-brief/scope.json 的 assets{}、docs/02-art/palette.json 的 style_tokens
可选: docs/02-art/subjects.json  —— 逐素材的主体描述（强烈建议手写/让 Agent 精修）
输出: docs/02-art/prompts/<asset>.txt（+ 缺失主体的 subjects.json 骨架）
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import dump_json, ok, project_dir, warn  # noqa: E402

# 分类 → (主体兜底描述后缀, 建议尺寸)
BUCKETS = {
    "sprites": ("game sprite, front view, single object, centered", 1024),
    "characters": ("game character, full body, front view, centered", 1024),
    "ui": ("game UI element, flat icon, centered, no text", 512),
    "props": ("game prop, front view, centered", 768),
    "bg": ("seamless game background, no characters", 1024),
    "backgrounds": ("seamless game background, no characters", 1024),
    "fx": ("game visual effect sprite, centered", 512),
}

NEGATIVE = (
    "low quality, blurry, jpeg artifacts, watermark, signature, text, caption, "
    "frame, border, cropped, extra limbs, deformed, photorealistic, 3d render"
)


def humanize(name: str) -> str:
    return name.replace("_", " ").replace("-", " ").strip()


def join_unique(*parts: str) -> str:
    """按逗号拼接并去重（大小写不敏感），避免 "front view" 之类的重复段。"""
    seen: set[str] = set()
    out: list[str] = []
    for part in parts:
        for seg in part.split(","):
            seg = seg.strip().strip(".")
            if not seg:
                continue
            key = seg.lower()
            if key in seen:
                continue
            seen.add(key)
            out.append(seg)
    return ", ".join(out)


def write_grid_prompt(
    proj: Path, pdir: Path, tokens: str, negative: str, bg_clause: str, args,
) -> int:
    """写「一张图出多个素材 / 一套动画帧」的提示词与 sidecar。"""
    grid = (args.grid or "").lower()
    if not grid or "x" not in grid:
        print("ERROR: --sheet / --frames 必须配 --grid RxC（如 3x3、2x2）", file=sys.stderr)
        return 1
    try:
        rows, cols = (int(x) for x in grid.split("x"))
    except Exception:
        print(f"ERROR: --grid 格式应为 RxC（收到 {args.grid}）", file=sys.stderr)
        return 1
    cells = rows * cols
    size = 1024
    width = height = size

    if args.sheet:
        names = [x.strip() for x in args.items.split(",") if x.strip()]
        if not names:
            print("ERROR: --sheet 需要 --items（逗号分隔的素材名）", file=sys.stderr)
            return 1
        if len(names) != cells:
            warn(f"items {len(names)} 个 vs 网格 {cells} 格 —— 建议改成 {len(names)} 格布局，否则会有空格/串格")
        subject = args.subject.strip() or "game items"
        prompt = join_unique(
            f"{subject}: {', '.join(names)}",
            f"sprite sheet in a {rows}x{cols} grid layout, {cells} separate items, one item per cell, "
            "evenly spaced, each item centered in its own cell, equal size, no overlap, no grid lines, no text",
            bg_clause,
        ) + f", {tokens}"
        sidecar = {
            "kind": "sheet",
            "grid": f"{rows}x{cols}",
            "items": names,
            "width": width,
            "height": height,
            "negative": negative,
        }
        name = args.sheet
    else:
        if not args.subject.strip():
            print("ERROR: --frames 需要 --subject（主体描述）", file=sys.stderr)
            return 1
        n = max(2, min(args.count, cells))
        if n != cells:
            warn(f"帧数 {n} < 网格 {cells} 格 —— 多余格子会被忽略")
        action = args.action.strip() or "animation"
        prompt = join_unique(
            f"{args.subject.strip()}, {action} animation",
            f"{n} sequential frames arranged in a {rows}x{cols} grid, consistent character design and size across frames, "
            "side view, evenly spaced, no overlap, no grid lines, no text",
            bg_clause,
        ) + f", {tokens}"
        sidecar = {
            "kind": "frames",
            "grid": f"{rows}x{cols}",
            "frames": n,
            "width": width,
            "height": height,
            "negative": negative,
        }
        name = args.frames_name

    if args.cell_size:
        sidecar["pad_to"] = int(args.cell_size)

    if args.dry_run:
        print(f"{name}.txt → {prompt}")
        print(f"{name}.json → {json.dumps(sidecar, ensure_ascii=False)}")
        return 0

    (pdir / f"{name}.txt").write_text(prompt + "\n", encoding="utf-8")
    dump_json(pdir / f"{name}.json", sidecar)
    ok(f"已写入 {name}.txt + {name}.json（{sidecar['kind']}，{rows}x{cols}）")
    print(f"  提示词：{prompt}")
    print("\n下一步：")
    print("  python gen_assets.py --only " + name + " --dry-run    # 复核")
    print("  python gen_assets.py --only " + name + "              # 出一张网格图并自动切分")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="批量生成生图提示词")
    ap.add_argument("--project", default=None)
    ap.add_argument("--force", action="store_true", help="覆盖已有提示词")
    ap.add_argument(
        "--background",
        default="magenta",
        choices=["magenta", "white", "none"],
        help="追加纯色背景指令，便于出图后泛洪抠图；工作流自带抠图节点时选 none",
    )
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--sheet", default="", help="生成一张网格图（多个素材）：输出 <name>.txt + <name>.json")
    ap.add_argument("--items", default="", help="--sheet 用：逗号分隔的素材名，数量应等于网格格数")
    ap.add_argument("--frames", dest="frames_name", default="", help="生成动画帧网格：输出 <name>.txt + <name>.json")
    ap.add_argument("--count", type=int, default=4, help="--frames 用：帧数（默认 4）")
    ap.add_argument("--grid", default="", help="网格布局 RxC，如 3x3 / 2x2；--sheet/--frames 时必填")
    ap.add_argument("--subject", default="", help="--sheet/--frames 用：主体描述")
    ap.add_argument("--action", default="", help="--frames 用：动作描述，如 run cycle / idle breathing")
    ap.add_argument("--cell-size", type=int, default=0, help="每格裁完后的统一画布边长（像素），0=自动")
    args = ap.parse_args()

    proj = project_dir(args.project)
    scope_p = proj / "docs" / "01-brief" / "scope.json"
    pal_p = proj / "docs" / "02-art" / "palette.json"
    if not scope_p.exists():
        print(f"ERROR: 缺少 {scope_p}（先做 modules/01-brief.md）", file=sys.stderr)
        return 1
    if not pal_p.exists():
        print(f"ERROR: 缺少 {pal_p}（先做 modules/03-art-bible.md）", file=sys.stderr)
        return 1

    scope = json.loads(scope_p.read_text(encoding="utf-8"))
    palette = json.loads(pal_p.read_text(encoding="utf-8"))
    tokens = (palette.get("style_tokens") or "").strip()
    if not tokens:
        print("ERROR: palette.json 缺少 style_tokens —— 它是风格一致性的唯一锚点", file=sys.stderr)
        return 1

    # 风格预设带来的 negative 优先（style_lib.py apply 会写入）
    negative = (palette.get("negative") or "").strip() or NEGATIVE

    subjects_p = proj / "docs" / "02-art" / "subjects.json"
    subjects = {}
    if subjects_p.exists():
        try:
            subjects = json.loads(subjects_p.read_text(encoding="utf-8"))
        except Exception as e:  # noqa: BLE001
            warn(f"subjects.json 解析失败，已忽略：{e}")

    if args.sheet or args.frames_name:
        gdir = proj / "docs" / "02-art" / "prompts"
        gdir.mkdir(parents=True, exist_ok=True)
        gb = {
            "magenta": "on a flat pure magenta background",
            "white": "on a flat pure white background",
            "none": "",
        }[args.background]
        return write_grid_prompt(proj, gdir, tokens, negative, gb, args)

    assets = scope.get("assets") or {}
    pdir = proj / "docs" / "02-art" / "prompts"
    pdir.mkdir(parents=True, exist_ok=True)

    bg_clause = {
        "magenta": "on a flat pure magenta background",
        "white": "on a flat pure white background",
        "none": "",
    }[args.background]

    written, skipped, missing_subject = 0, 0, []
    for bucket, names in assets.items():
        if not isinstance(names, list):
            continue
        suffix, size = BUCKETS.get(bucket, ("game asset, centered", 1024))
        for raw in names:
            name = str(raw).strip()
            if not name:
                continue
            dst = pdir / f"{name}.txt"
            if dst.exists() and not args.force:
                skipped += 1
                continue
            subject = subjects.get(name)
            if not subject:
                missing_subject.append(name)
                subject = humanize(name)
            # style_tokens 原样追加在最后，不参与去重（它是整体风格串）
            head = join_unique(subject, suffix, bg_clause)
            prompt = f"{head}, {tokens}" if head else tokens
            if args.dry_run:
                print(f"{name}.txt → {prompt}")
                continue
            dst.write_text(prompt + "\n", encoding="utf-8")
            side = pdir / f"{name}.json"
            if not side.exists():
                dump_json(side, {"width": size, "height": size, "negative": negative})
            written += 1

    if args.dry_run:
        return 0

    # 为缺失主体生成骨架，方便人工/Agent 精修
    if missing_subject:
        skeleton = dict(subjects)
        for n in missing_subject:
            skeleton.setdefault(n, humanize(n))
        if not subjects_p.exists():
            dump_json(subjects_p, skeleton)
            warn(f"已生成 subjects.json 骨架（{len(missing_subject)} 项用了文件名兜底描述）—— 建议精修后 --force 重跑")
        else:
            warn(f"{len(missing_subject)} 项缺少主体描述，已用文件名兜底：{', '.join(missing_subject[:8])}")

    ok(f"提示词已生成 {written} 条，跳过 {skipped} 条 → {pdir}")
    print("下一步：gen_assets.py --probe 确认 provider，再 gen_assets.py --dry-run 复核提示词")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
