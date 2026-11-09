#!/usr/bin/env python3
"""Asset Registry —— 素材的统一台账与一致性检查。

## 为什么需要

素材散在四个地方，各说各话：
  assets/raw/manifest.json   生图台账（provider / prompt / seed）
  docs/02-art/asset-spec.json 规格（要什么、多大、什么角色）
  assets/img/*.png            实际文件
  src/**.ts                   谁在用

出问题时（「这张图哪来的」「改了 prompt 要不要重出」「这个文件还有人用吗」）
要翻四个地方。Registry 把它们合并成一张表，并自动检查不一致。

## 三个子命令

  scan    扫描项目，生成 assets/registry.json（合并来源 + 文件 + 引用）
  check   一致性检查，输出 docs/02-art/asset-registry-report.json，有问题退出码 1
  report  打印汇总（人读）

## 检查项

| 级别 | 检查 | 说明 |
|---|---|---|
| FAIL | 断链 | registry 记了但文件不存在 |
| FAIL | 超预算 | 图片总体积超过 asset-spec 的 total_budget_kb |
| FAIL | 空文件 / 尺寸为 0 | 生成失败留下的残骸 |
| WARN | 孤儿素材 | 文件在但没有任何源码引用 |
| WARN | 缺来源 | AI 图在 manifest 里找不到记录 |
| WARN | 缺 prompt | source=ai 但没有 prompt，无法复现 |

## 用法

  python asset_registry.py scan
  python asset_registry.py check
  python asset_registry.py report
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

IMG_EXT = {".png", ".jpg", ".jpeg", ".webp"}
AUDIO_EXT = {".mp3", ".ogg", ".wav", ".m4a"}
SKIP_DIRS = {"node_modules", ".git", "dist", "__pycache__", ".gamedev", "assets/raw"}

REGISTRY = Path("assets/registry.json")
SPEC = Path("docs/02-art/asset-spec.json")
MANIFEST = Path("assets/raw/manifest.json")
REPORT = Path("docs/02-art/asset-registry-report.json")


def find_project(start: Path) -> Path:
    cur = start.resolve()
    for _ in range(6):
        if (cur / ".gamedev" / "state.yaml").exists():
            return cur
        if cur.parent == cur:
            break
        cur = cur.parent
    return start.resolve()


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return "sha256:" + h.hexdigest()[:16]


def image_size(p: Path) -> tuple[int, int] | None:
    """用 Pillow 读尺寸；没装 Pillow 时退回读 PNG 头。"""
    try:
        from PIL import Image  # type: ignore

        with Image.open(p) as im:
            return im.size
    except Exception:
        pass
    try:
        with p.open("rb") as f:
            head = f.read(24)
        if head[:8] == b"\x89PNG\r\n\x1a\n":
            return int.from_bytes(head[16:20], "big"), int.from_bytes(head[20:24], "big")
    except Exception:
        pass
    return None


def collect_sources(root: Path) -> dict[str, list[str]]:
    """扫描 src/，建立「素材 stem → 引用它的文件」映射。"""
    index: dict[str, list[str]] = {}
    src = root / "src"
    if not src.is_dir():
        return index
    for p in src.rglob("*"):
        if not p.is_file() or p.suffix not in {".ts", ".js", ".mjs", ".tsx"}:
            continue
        if any(part in SKIP_DIRS for part in p.parts):
            continue
        try:
            text = p.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        rel = p.relative_to(root).as_posix()
        for m in re.finditer(r"[A-Za-z0-9_\-]+", text):
            index.setdefault(m.group(0), []).append(rel)
    return index


def load_json(p: Path, fallback=None):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return fallback


def scan(root: Path) -> dict:
    spec = load_json(root / SPEC, {}) or {}
    manifest = (load_json(root / MANIFEST, {}) or {}).get("assets", {}) or {}
    refs = collect_sources(root)

    # manifest 的键是生成用的 asset id（hero / bg_1），落盘文件名往往被改过。
    # 三级关联：人工 links > 文件名精确匹配 > prompt 关键词唯一命中。
    # 都不中就是 unknown —— 这本身就是有价值的发现（素材与生成记录脱钩了）。
    by_stem: dict[str, dict] = {str(k): v for k, v in manifest.items()}
    links = load_json(root / "assets" / "registry-links.json", {}) or {}
    # 音频的生成记录（music_gen.py 写）。比 grep 可靠：直接记了谁生成的。
    provenance = load_json(root / "docs" / "05-audio" / "bgm-provenance.json", {}) or {}

    def match_manifest(stem: str) -> tuple[dict | None, str]:
        if stem in links:
            key = str(links[stem])
            if key in by_stem:
                return by_stem[key], "link"
        if stem in by_stem:
            return by_stem[stem], "exact"
        # 关键词：stem 出现在 prompt 里，且只命中一条
        word = stem.replace("_", " ").lower()
        hits = [(k, v) for k, v in by_stem.items() if word in str(v.get("prompt", "")).lower()]
        if len(hits) == 1:
            return hits[0][1], "prompt"
        return None, "none"

    assets: list[dict] = []

    def add_file(p: Path, kind: str) -> None:
        rel = p.relative_to(root).as_posix()
        stem = p.stem
        rec, matched_by = match_manifest(stem)
        entry: dict = {
            "id": stem,
            "type": kind,
            "path": rel,
            "bytes": p.stat().st_size,
            "hash": sha256_file(p),
        }
        if kind == "image":
            size = image_size(p)
            entry["width"], entry["height"] = (size if size else (0, 0))
        if rec:
            entry.update(
                {
                    "source": "ai",
                    "provider": rec.get("provider"),
                    "seed": rec.get("seed"),
                    "prompt_sha": hashlib.sha256(str(rec.get("prompt", "")).encode()).hexdigest()[:12],
                    "prompt_preview": str(rec.get("prompt", ""))[:160],
                    "generated_at": rec.get("generated_at"),
                    "status": rec.get("status", "ok"),
                    "linked_by": matched_by,
                }
            )
        elif rel in provenance:
            pv = provenance[rel]
            entry.update({
                "source": pv.get("source", "ai"),
                "provider": pv.get("provider"),
                "prompt_preview": str(pv.get("prompt", ""))[:160],
                "generated_at": pv.get("generated_at"),
                "linked_by": "provenance",
            })
        else:
            # 图片没有生成记录 = 来源不明（可能是手工放的）；
            # 音频没有 provenance 时视为程序化合成（gen_audio.py 生成）
            entry["source"] = "procedural" if kind == "audio" else "unknown"
            entry["linked_by"] = "none"
        # 引用反查：文件 stem 或去掉前缀后的名字
        used = sorted(set(refs.get(stem, [])))
        entry["used_by"] = used
        entry["used"] = bool(used)
        assets.append(entry)

    img_dir = root / "assets" / "img"
    if img_dir.is_dir():
        for p in sorted(img_dir.iterdir()):
            if p.is_file() and p.suffix.lower() in IMG_EXT:
                add_file(p, "image")

    for sub in ("sfx", "bgm"):
        d = root / "assets" / "audio" / sub
        if d.is_dir():
            for p in sorted(d.iterdir()):
                if p.is_file() and p.suffix.lower() in AUDIO_EXT:
                    add_file(p, "audio")

    budget_kb = spec.get("total_budget_kb")
    img_kb = sum(a["bytes"] for a in assets if a["type"] == "image") / 1024
    au_kb = sum(a["bytes"] for a in assets if a["type"] == "audio") / 1024

    return {
        "version": 1,
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "budget_kb": budget_kb,
        "summary": {
            "images": sum(1 for a in assets if a["type"] == "image"),
            "audio": sum(1 for a in assets if a["type"] == "audio"),
            "ai": sum(1 for a in assets if a.get("source") == "ai"),
            "unknown": sum(1 for a in assets if a.get("source") == "unknown"),
            "procedural": sum(1 for a in assets if a.get("source") == "procedural"),
            "image_kb": round(img_kb, 1),
            "audio_kb": round(au_kb, 1),
        },
        "assets": assets,
    }


def check(root: Path, reg: dict) -> dict:
    issues: list[dict] = []

    def add(level: str, code: str, msg: str, asset: str = "") -> None:
        issues.append({"level": level, "code": code, "asset": asset, "message": msg})

    for a in reg["assets"]:
        p = root / a["path"]
        if not p.exists():
            add("FAIL", "broken_link", f"registry 记了但文件不存在：{a['path']}", a["id"])
            continue
        if a["bytes"] == 0:
            add("FAIL", "empty_file", f"文件是空的：{a['path']}", a["id"])
        if a["type"] == "image" and (a.get("width", 0) == 0 or a.get("height", 0) == 0):
            add("FAIL", "bad_image", f"读不出图片尺寸：{a['path']}", a["id"])
        if not a.get("used"):
            # 图片是直接引用，孤儿判定可靠；音频常通过 `key + '_b'` 拼接或配置表引用，
            # grep 不到不代表没用，所以只做提示不做警告
            lvl = "WARN" if a["type"] == "image" else "INFO"
            add(lvl, "orphan", f"没有直接的源码引用：{a['path']}", a["id"])
        if a.get("source") == "unknown":
            add("WARN", "no_source", f"来源不明（生成记录里没有）：{a['path']}", a["id"])
        if a.get("source") == "ai" and not a.get("prompt_preview"):
            add("WARN", "no_prompt", f"AI 图但没有 prompt，无法复现：{a['path']}", a["id"])

    budget = reg.get("budget_kb")
    if budget and reg["summary"]["image_kb"] > budget:
        add(
            "FAIL",
            "over_budget",
            f"图片总体积 {reg['summary']['image_kb']}KB 超过预算 {budget}KB",
        )

    fails = sum(1 for i in issues if i["level"] == "FAIL")
    warns = sum(1 for i in issues if i["level"] == "WARN")
    infos = sum(1 for i in issues if i["level"] == "INFO")
    return {
        "checked_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "verdict": "FAIL" if fails else "PASS",
        "fail_count": fails,
        "warn_count": warns,
        "info_count": infos,
        "issues": issues,
        "summary": reg["summary"],
        "budget_kb": budget,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="素材台账与一致性检查")
    ap.add_argument("cmd", choices=["scan", "check", "report"], help="子命令")
    ap.add_argument("--project", default="", help="项目根目录，默认自动查找")
    args = ap.parse_args()

    root = Path(args.project).resolve() if args.project else find_project(Path.cwd())
    # 纯程序化美术的项目可以没有 assets/：scan 生成空台账，check 直接 PASS。
    # 这不是错误状态，是「这个项目不依赖外部素材」。
    if not (root / "assets").is_dir() and args.cmd != "scan":
        print(f"提示: {root.name} 没有 assets/ 目录（纯程序化美术）", file=sys.stderr)
        return 0

    if args.cmd == "scan":
        reg = scan(root)
        out = root / REGISTRY
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(reg, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        s = reg["summary"]
        print(f"已扫描 {root.name}")
        print(f"  图片 {s['images']} 张（{s['image_kb']}KB）· 音频 {s['audio']} 个（{s['audio_kb']}KB）")
        print(f"  AI 生成 {s['ai']} · 程序化 {s.get('procedural', 0)} · 来源不明 {s['unknown']}")
        if reg["budget_kb"]:
            pct = s["image_kb"] / reg["budget_kb"] * 100
            print(f"  图片预算 {reg['budget_kb']}KB，已用 {pct:.0f}%")
        if not reg["assets"]:
            print("  没有任何外部素材 —— 该项目全部使用程序化美术")
        print(f"→ {REGISTRY}")
        return 0

    reg = load_json(root / REGISTRY)
    if not reg:
        print("ERROR: 还没有 assets/registry.json，先跑 scan", file=sys.stderr)
        return 2

    result = check(root, reg)

    if args.cmd == "check":
        out = root / REPORT
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(
            f"素材一致性检查：{result['verdict']}"
            f"（FAIL {result['fail_count']} / WARN {result['warn_count']} / INFO {result.get('info_count', 0)}）"
        )
        for i in result["issues"]:
            print(f"  [{i['level']}] {i['message']}")
        if not result["issues"]:
            print("  没有问题。")
        print(f"→ {REPORT}")
        return 1 if result["fail_count"] else 0

    # report：人读汇总
    s = result["summary"]
    print(f"{root.name} 素材台账")
    print("─" * 60)
    print(f"图片 {s['images']} 张 / {s['image_kb']}KB" + (f"（预算 {result['budget_kb']}KB）" if result["budget_kb"] else ""))
    print(f"音频 {s['audio']} 个 / {s['audio_kb']}KB")
    print(f"AI 生成 {s['ai']} · 程序化 {s.get('procedural', 0)} · 来源不明 {s['unknown']}")
    print()
    if reg["assets"]:
        print(f"{'素材':<22}{'类型':<8}{'来源':<10}{'体积':<10}{'引用'}")
        print("─" * 60)
        for a in reg["assets"]:
            kb = f"{a['bytes'] / 1024:.0f}KB"
            used = f"{len(a['used_by'])} 处" if a["used"] else "未被引用"
            print(f"{a['id'][:20]:<22}{a['type']:<8}{a.get('source', '?'):<10}{kb:<10}{used}")
    else:
        print("（没有外部素材文件 —— 该项目全部使用程序化美术）")
    print()
    print(f"检查结论：{result['verdict']}（FAIL {result['fail_count']} / WARN {result['warn_count']}）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
