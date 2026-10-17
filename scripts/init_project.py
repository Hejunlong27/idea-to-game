#!/usr/bin/env python3
"""初始化 IdeaToGame 项目：建目录、复制模板、写 state.yaml。

用法:
    python init_project.py --name merge-fruit --idea "做一个合成水果的游戏" \
        [--style-ref /path/style.png] [--genre merge] [--out /path/workspace]

若 --out 省略，则在当前目录下创建 <name>/。
"""

from __future__ import annotations

import argparse
import shutil
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import PLATFORM_KEYS, STAGES, TEMPLATE_DIR, dump_json, ok, save_state, warn  # noqa: E402

DOC_DIRS = [
    "00-platforms",
    "01-brief",
    "02-art/prompts",
    "03-scaffold",
    "04-core-loop",
    "05-polish",
    "06-perf",
    "07-qa/screenshots",
    "08-ship",
    "09-review/evidence",
]
ASSET_DIRS = ["raw", "processed", "atlas", "audio/bgm", "audio/sfx", "ref"]


def main() -> int:
    ap = argparse.ArgumentParser(description="初始化 IdeaToGame 项目")
    ap.add_argument("--name", required=True, help="项目名（kebab-case）")
    ap.add_argument("--idea", required=True, help="游戏想法描述，或同款游戏名")
    ap.add_argument("--style-ref", default="", help="风格参考图路径（会被复制到 assets/ref/）")
    ap.add_argument("--genre", default="", help="品类，如 merge / idle / runner")
    ap.add_argument(
        "--platforms",
        default="",
        help=f"目标平台，逗号分隔。可选：{', '.join(PLATFORM_KEYS)}。"
             "留空表示尚未与用户确认（后续必须用 state.py set-platforms 补上）",
    )
    ap.add_argument("--out", default=".", help="输出父目录，默认当前目录")
    args = ap.parse_args()

    # 平台校验
    platforms = [p.strip().lower() for p in args.platforms.split(",") if p.strip()]
    unknown = [p for p in platforms if p not in PLATFORM_KEYS]
    if unknown:
        print(
            f"ERROR: 未知平台 {unknown}；可选：{', '.join(PLATFORM_KEYS)}",
            file=sys.stderr,
        )
        return 1
    if not platforms:
        warn("未指定 --platforms —— 上线前必须按 modules/00-platforms.md 与用户确认后再补上")

    # 项目名只接受安全字符集，避免路径穿越
    import re

    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", args.name) or args.name in (".", ".."):
        print(
            f"ERROR: --name 只允许字母/数字/点/下划线/连字符，且不能以点开头（收到 {args.name!r}）",
            file=sys.stderr,
        )
        return 1

    parent = Path(args.out).expanduser().resolve()
    parent.mkdir(parents=True, exist_ok=True)
    proj = parent / args.name
    if proj.exists() and any(proj.iterdir()):
        print(f"ERROR: 目标目录已存在且非空：{proj}", file=sys.stderr)
        return 1
    proj.mkdir(parents=True, exist_ok=True)

    for d in DOC_DIRS:
        (proj / "docs" / d).mkdir(parents=True, exist_ok=True)
    for d in ASSET_DIRS:
        (proj / "assets" / d).mkdir(parents=True, exist_ok=True)
    (proj / ".gamedev" / "logs").mkdir(parents=True, exist_ok=True)

    if not TEMPLATE_DIR.is_dir():
        warn(f"模板目录不存在，跳过模板复制：{TEMPLATE_DIR}")
    else:
        for item in TEMPLATE_DIR.iterdir():
            dst = proj / item.name
            if item.is_dir():
                shutil.copytree(item, dst, dirs_exist_ok=True)
            else:
                shutil.copy2(item, dst)
        ok(f"已复制项目模板 → {proj}")

    style_ref = ""
    if args.style_ref:
        src = Path(args.style_ref).expanduser().resolve()
        if src.is_file():
            dst = proj / "assets" / "ref" / src.name
            shutil.copy2(src, dst)
            style_ref = dst.relative_to(proj).as_posix()
            ok(f"已复制风格参考图 → {style_ref}")
        else:
            warn(f"风格参考图不存在，已跳过：{src}")

    state = {
        "project": {
            "name": args.name,
            "idea": args.idea,
            "style_ref": style_ref,
            "genre": args.genre,
            "created": datetime.now().astimezone().isoformat(timespec="seconds"),
        },
        "stages": {s: {"status": "pending"} for s in STAGES},
        "delivery": {
            "tier": None,
            "platform_confirmed": bool(platforms),
            "platforms": platforms,
            "platform_notes": {},
        },
    }
    save_state(proj, state)
    dump_json(proj / "docs" / "00-platforms" / ".keep.json", {"note": "占位，可删除"})

    ok(f"项目已初始化：{proj}")
    if platforms:
        ok(f"目标平台：{', '.join(platforms)}")
    print("\n下一步：")
    if not platforms:
        print("  0. 读 modules/00-platforms.md，先向用户确认目标平台（门禁 G0）")
    print("  1. 读 modules/01-brief.md，产出 docs/01-brief/gdd.md 与 scope.json")
    print("  2. 运行 gate_check.py --stage brief 校验")
    print("  3. 向用户确认方向（门禁 G1）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
