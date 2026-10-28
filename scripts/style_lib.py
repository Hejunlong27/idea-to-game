#!/usr/bin/env python3
"""画风预设库（assets/styles/）：列出、查看、应用到项目。

来源：RHSTORY 画风库（服务端全量，306 条）里筛出的、**适合 HTML5 小游戏素材**的 5 档。
每条都做了三件事，不是照搬：
  1. 把冗长的「视频向」提示词**蒸馏成游戏资产向的短 style_tokens**
  2. 配好可直接用的主色板（palette.json 格式）
  3. 标注后处理要求与已知风险（像素风的半像素、吉卜力的抠图成本等）

用法:
    python style_lib.py list
    python style_lib.py show pixel-game
    python style_lib.py apply pixel-game --project .          # 写入 docs/02-art/palette.json
    python style_lib.py apply chibi-2d --project . --force    # 覆盖已有风格
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import SKILL_DIR, dump_json, ok, project_dir, warn  # noqa: E402

STYLE_DIR = SKILL_DIR / "assets" / "styles"


def load_presets() -> dict[str, dict]:
    out: dict[str, dict] = {}
    if not STYLE_DIR.is_dir():
        return out
    for f in sorted(STYLE_DIR.glob("*.json")):
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
        except Exception as e:  # noqa: BLE001
            warn(f"{f.name} 解析失败，已跳过：{e}")
            continue
        key = d.get("key") or f.stem
        d["_file"] = f.name
        out[key] = d
    return out


def cmd_list(presets: dict[str, dict]) -> int:
    if not presets:
        print(f"ERROR: 预设目录为空：{STYLE_DIR}", file=sys.stderr)
        return 1
    print(f"画风预设（{len(presets)} 档）  目录：{STYLE_DIR}")
    print("=" * 78)
    for k, d in presets.items():
        print(f"{k:<14} {d.get('name', '')}  /  {d.get('name_en', '')}")
        print(f"{'':<14} 适用：{', '.join(d.get('best_for') or [])}")
        print(f"{'':<14} 来源：{d.get('source', {}).get('original_name', '-')}"
              f"（{d.get('source', {}).get('group')} #{d.get('source', {}).get('index')}）")
        print(f"{'':<14} 风险：{d.get('risk', '-')}")
        print()
    print("应用：python style_lib.py apply <key> --project <proj>")
    return 0


def cmd_show(presets: dict[str, dict], key: str) -> int:
    d = presets.get(key)
    if not d:
        print(f"ERROR: 未知画风 {key}；可选：{', '.join(presets)}", file=sys.stderr)
        return 1
    body = {k: v for k, v in d.items() if k != "_file"}
    print(json.dumps(body, ensure_ascii=False, indent=2))
    print("\n可直接粘进 palette.json 的 style_tokens：")
    print(f'  "style_tokens": "{d["style_tokens"]}"')
    return 0


def apply_preset(proj: Path, key: str, force: bool = False) -> int:
    presets = load_presets()
    d = presets.get(key)
    if not d:
        print(f"ERROR: 未知画风 {key}；可选：{', '.join(presets)}", file=sys.stderr)
        return 1

    art_dir = proj / "docs" / "02-art"
    art_dir.mkdir(parents=True, exist_ok=True)
    pal_p = art_dir / "palette.json"

    pal: dict = {}
    if pal_p.exists():
        try:
            pal = json.loads(pal_p.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            pal = {}
        if pal.get("style_tokens") and not force:
            print(
                f"ERROR: {pal_p} 已有 style_tokens（当前风格已定）。"
                "确认要换成预设再跑一次并加 --force",
                file=sys.stderr,
            )
            return 1

    p = d.get("palette") or {}
    pal.update(
        {
            "style_key": key,
            "style_tokens": d["style_tokens"],
            "primary": p.get("primary") or pal.get("primary") or [],
            "accent": p.get("accent") or pal.get("accent") or [],
            "background": p.get("background") or pal.get("background") or "#FFFFFF",
            "negative": ", ".join(
                x for x in [pal.get("negative", ""), d.get("negative_extra", "")] if x
            ),
            "source": d.get("source", {}),
        }
    )
    dump_json(pal_p, pal)

    dump_json(
        art_dir / "style.json",
        {
            "key": key,
            "name": d.get("name"),
            "name_en": d.get("name_en"),
            "source": d.get("source"),
            "sprite_hint": d.get("sprite_hint"),
            "risk": d.get("risk"),
            "best_for": d.get("best_for"),
            "gen": d.get("gen"),
            "applied_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        },
    )

    ok(f"已应用画风预设「{d.get('name')}」→ {pal_p.relative_to(proj).as_posix()}")
    print(f"  style_tokens: {d['style_tokens']}")
    if d.get("sprite_hint"):
        print(f"  后处理要求：{d['sprite_hint']}")
    if d.get("risk"):
        print(f"  已知风险：{d['risk']}")
    print("\n下一步：")
    print("  1. 写 docs/02-art/art-bible.md（色板 + 尺寸规范 + 命名规范），门禁 G2 要用户确认")
    print("  2. python gen_prompts.py        # 提示词会自动带上这套 style_tokens")
    print("  3. python gen_assets.py --dry-run")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="画风预设库")
    sub = ap.add_subparsers(dest="cmd")

    sub.add_parser("list", help="列出全部预设")

    sp = sub.add_parser("show", help="查看单个预设")
    sp.add_argument("key")

    sa = sub.add_parser("apply", help="把预设写入项目 docs/02-art/")
    sa.add_argument("key")
    sa.add_argument("--project", default=None)
    sa.add_argument("--force", action="store_true", help="覆盖项目里已有的 style_tokens")

    args = ap.parse_args()
    presets = load_presets()

    if args.cmd in (None, "list"):
        return cmd_list(presets)
    if args.cmd == "show":
        return cmd_show(presets, args.key)
    if args.cmd == "apply":
        return apply_preset(project_dir(args.project), args.key, args.force)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
