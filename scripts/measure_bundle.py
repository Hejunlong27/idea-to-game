#!/usr/bin/env python3
"""构建产物体积与文件数审计（模块 09 用）。

用法:
    python measure_bundle.py --dir dist/crazygames [--platform crazygames] [--json out.json]

对照 CrazyGames 红线：
    总文件大小 <= 250MB
    文件数       <= 1500
    首包         <= 50MB（移动端首页 <= 20MB）
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import human_size, iter_files, scan_absolute_paths, scan_external_urls  # noqa: E402

LIMITS = {
    "total_mb": 250,
    "file_count": 1500,
    "initial_mb": 50,
    "initial_mb_mobile": 20,
}

# 首屏关键文件：入口与它直接依赖的常见资源类型
ENTRY = {"index.html", "index.js", "index.css"}


def guess_initial(files: list[tuple[Path, int]], root: Path):
    """粗估首包：index.html + 根级 js/css + 全部图片/音频中位于根目录或 assets/ 顶层且被引用的部分。

    精确首包需在真机按 CrazyGames SDK 的 gameplayStart 测量；
    本函数给出保守上界（入口文件 + 根级静态资源 + 图集）。
    """
    total = 0
    picked = []
    for p, size in files:
        rel = p.relative_to(root).as_posix()
        name = p.name
        ext = p.suffix.lower()
        if name in ENTRY or rel in ENTRY:
            total += size
            picked.append(rel)
            continue
        if ext in {".js", ".mjs", ".css"} and "/" not in rel:
            total += size
            picked.append(rel)
            continue
        if ext in {".png", ".webp", ".jpg", ".jpeg", ".ogg", ".mp3"} and rel.startswith("assets/atlas"):
            total += size
            picked.append(rel)
    return total, picked


def main() -> int:
    ap = argparse.ArgumentParser(description="构建产物审计")
    ap.add_argument("--dir", required=True, help="构建产物目录")
    ap.add_argument("--platform", default="crazygames")
    ap.add_argument("--json", default="", help="同时输出 JSON 报告路径")
    ap.add_argument("--top", type=int, default=12, help="列出最大的 N 个文件")
    args = ap.parse_args()

    root = Path(args.dir).expanduser().resolve()
    if not root.is_dir():
        print(f"ERROR: 目录不存在：{root}", file=sys.stderr)
        return 1

    files = [(p, p.stat().st_size) for p in iter_files(root)]
    total = sum(s for _, s in files)
    count = len(files)

    by_ext = defaultdict(lambda: [0, 0])
    for p, s in files:
        e = p.suffix.lower() or "(无扩展名)"
        by_ext[e][0] += 1
        by_ext[e][1] += s

    initial, initial_list = guess_initial(files, root)

    print(f"目录: {root}")
    print(f"平台: {args.platform}")
    print("=" * 58)
    print(f"总大小    : {human_size(total):>10}   (红线 <= {LIMITS['total_mb']}MB)")
    print(f"文件数    : {count:>10}   (红线 <= {LIMITS['file_count']})")
    print(f"首包(估)  : {human_size(initial):>10}   "
          f"(红线 <= {LIMITS['initial_mb']}MB / 移动首页 <= {LIMITS['initial_mb_mobile']}MB)")

    fails = []
    warns = []
    if total > LIMITS["total_mb"] * 1024 * 1024:
        fails.append(f"总大小超出 {LIMITS['total_mb']}MB")
    if count > LIMITS["file_count"]:
        fails.append(f"文件数超出 {LIMITS['file_count']}")
    if initial > LIMITS["initial_mb_mobile"] * 1024 * 1024:
        if initial > LIMITS["initial_mb"] * 1024 * 1024:
            fails.append(f"首包超出 {LIMITS['initial_mb']}MB，无法发布")
        else:
            warns.append(f"首包超出 {LIMITS['initial_mb_mobile']}MB，将失去移动端首页资格")

    print("-" * 58)
    print("按类型:")
    for e, (c, s) in sorted(by_ext.items(), key=lambda kv: -kv[1][1])[:10]:
        print(f"  {e:<12} {c:>6} 个   {human_size(s):>10}")

    print("-" * 58)
    print(f"最大的 {args.top} 个文件:")
    for p, s in sorted(files, key=lambda t: -t[1])[: args.top]:
        print(f"  {human_size(s):>10}  {p.relative_to(root).as_posix()}")

    abs_hits = scan_absolute_paths(root)
    if abs_hits:
        print("-" * 58)
        print(f"根绝对路径引用 {len(abs_hits)} 处（CrazyGames 会因绝对路径拒审）：")
        for rel, frag in abs_hits[:10]:
            print(f"  {rel}: {frag}")
        fails.append("存在根绝对路径引用")
    else:
        print("-" * 58)
        print("绝对路径检查: 通过")

    ext_hits = scan_external_urls(root)
    if ext_hits:
        hosts = sorted({u.split("/")[2] for _, u in ext_hits if len(u.split("/")) > 2})
        print(f"外部 URL 引用 {len(ext_hits)} 处，涉及域名: {', '.join(hosts[:8])}")
        print("  （平台 SDK 的 CDN 属正常；其余域名需确认 iframe 内可访问）")

    print("=" * 58)
    for f in fails:
        print(f"[FAIL] {f}")
    for w in warns:
        print(f"[WARN] {w}")
    if not fails:
        print("[PASS] 体积与文件数审计通过")

    if args.json:
        out = Path(args.json).expanduser().resolve()
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(
            json.dumps(
                {
                    "dir": str(root),
                    "platform": args.platform,
                    "total_bytes": total,
                    "file_count": count,
                    "initial_bytes": initial,
                    "initial_files": initial_list,
                    "by_ext": {k: {"count": v[0], "bytes": v[1]} for k, v in by_ext.items()},
                    "absolute_path_hits": abs_hits,
                    "fails": fails,
                    "warns": warns,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        print(f"报告已写入：{out}")

    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
