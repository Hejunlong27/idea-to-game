#!/usr/bin/env python3
"""素材生成器：把「美术需求」变成「可直接喂 ComfyUI 的素材规格 + 提示词」。

为什么需要它 —— v1 的三个真实痛点：
  ① 素材类型单一（只有 sprites），没有角色/背景/UI/特效/过场/封面的结构化需求
  ② 同一角色多姿态独立生成，必然漂移（玩家认不出是同一个角色）
  ③ 提示词靠手写，常漏 style_tokens，或把素材 id（keeper_idle）写进提示词被模型画出来

本脚本的解法：
  ① 9 种 role 模板，每种有自己的槽位结构/尺寸/负向词/后处理规范
  ② 一致性锚：主角类固定 seed + 首图为基准，后续姿态走 i2i ref 链
  ③ 槽位化拼装 + lint（缺槽位/含中文/含 id 名/与 negative 冲突都会报）

用法:
    python asset_forge.py --project . --spec        # 蓝图 → asset-spec.json（带 TODO 骨架）
    python asset_forge.py --project . --prompts     # asset-spec → docs/02-art/prompts/*.txt(+json)
    python asset_forge.py --project . --lint        # 检查已生成的提示词
    python asset_forge.py --project . --all         # spec + prompts + lint

产物:
    docs/02-art/asset-spec.json                 ★ 素材规格单一真相源
    docs/02-art/prompts/<id>.txt                单行提示词（gen_assets.py 直接消费）
    docs/02-art/prompts/<id>.json               sidecar：size/seed/ref/trim/kind
    docs/02-art/asset-lint.json                 lint 结果
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import dump_json, ok, project_dir, warn  # noqa: E402

CJK = re.compile(r"[\u4e00-\u9fff\u3000-\u303f\uff00-\uffef]")

# ------------------------------------------------------------------ role 模板
# view    —— 必含视角描述（lint 校验）
# extra   —— 该 role 的补充约束
# bg      —— 背景策略：solid=纯色便于抠图；scene=场景化不抠
# trim    —— 1024 方图约 70% 是空白，精灵类必开
# budget  —— 单张预算（KB，processed 后）
ROLES = {
    "character": {
        "label": "角色",
        "view": "full body standing upright, complete single figure from head to boots, front view, centered composition",
        "extra": "one connected figure, clear readable silhouette, no floating parts",
        "bg": "solid", "trim": True, "budget_kb": 120, "count": 3,
        "neg_extra": "multiple characters, cropped body, cut off limbs, back view, disconnected body parts, floating head, floating hands, exploded view, character sheet with separated elements",
        "note": "首张为基准图（base=true），后续姿态共用 seed 并 ref 指向基准，保证同一角色",
    },
    "prop": {
        "label": "道具/单位",
        "view": "single object, three-quarter view, isolated",
        "extra": "clear outline, readable at small size",
        "bg": "solid", "trim": True, "budget_kb": 60, "count": 8,
        "neg_extra": "multiple objects, scattered items, hands",
        "note": "同类道具可合并成网格图（--sheet）省算力",
    },
    "tile": {
        "label": "地块",
        "view": "top-down flat view, filling the frame edge to edge",
        "extra": "seamless tileable texture, no perspective, uniform lighting",
        "bg": "none", "trim": False, "budget_kb": 40, "count": 6,
        "neg_extra": "perspective, vanishing point, vignette, border, frame",
        "note": "必须满幅无缝，不能抠图不能裁边",
    },
    "bg": {
        "label": "背景",
        "view": "wide establishing shot, no characters",
        "extra": "clear foreground midground background separation, room for UI at edges",
        "bg": "scene", "trim": False, "budget_kb": 300, "count": 3,
        "neg_extra": "characters, people, text, ui elements, watermark",
        "note": "全屏背景：sidecar 里 trim=false，尺寸按 16:9 或 9:16 出",
    },
    "ui": {
        "label": "UI 元件",
        "view": "flat single UI element, centered, no text",
        "extra": "consistent corner radius, even stroke weight, no gradient banding",
        "bg": "solid", "trim": True, "budget_kb": 30, "count": 6,
        "neg_extra": "text, letters, numbers, labels, screenshot, mockup",
        "note": "UI 禁止出现文字（文字由游戏内 Text 对象渲染，多语言与清晰度都需要）",
    },
    "fx": {
        "label": "特效",
        "view": "centered effect burst, symmetrical, empty background",
        "extra": "additive-friendly, bright core, soft falloff to transparent edges",
        "bg": "solid", "trim": True, "budget_kb": 50, "count": 4,
        "neg_extra": "characters, objects, text, hard rectangular edges",
        "note": "特效帧用 2x2 网格（frames），4 帧是动画一致性上限",
    },
    "cutscene": {
        "label": "过场插画",
        "view": "cinematic composition, character in environment",
        "extra": "story moment, strong mood, letterbox-friendly framing",
        "bg": "scene", "trim": False, "budget_kb": 400, "count": 2,
        "neg_extra": "text, speech bubble, watermark, ui overlay",
        "note": "全游戏最多 3 张，多了就不是小游戏了（content-depth.md §3 硬上限）",
    },
    "keyart": {
        "label": "主视觉",
        "view": "poster composition, hero in center, title space at top",
        "extra": "high impact, store-page thumbnail legible, dramatic lighting",
        "bg": "scene", "trim": False, "budget_kb": 500, "count": 1,
        "neg_extra": "text, logo, watermark, frame",
        "note": "商店页与分享卡必需；留出标题区（文字后期用排版工具加）",
    },
    "icon": {
        "label": "应用图标",
        "view": "centered emblem, square composition, no background detail",
        "extra": "readable at 64px, bold shapes, single focal point",
        "bg": "solid", "trim": False, "budget_kb": 25, "count": 1,
        "neg_extra": "text, letters, fine detail, thin lines",
        "note": "64px 下必须可辨认；出图后统一裁成正方形",
    },
}

QUALITY = "high quality, crisp clean edges, game-ready asset, consistent art direction"
SOLID_BG = "on a plain solid light mint background, no shadow, no ground plane, no scenery"
SCENE_BG = ""

# 一致性锚：主角所有姿态共用同一段描述前缀，防止"同一个角色越画越不像"
HERO_ANCHOR = "same character design as reference, identical costume and color scheme, identical face"


def load_json(p: Path, default=None):
    if not p.exists():
        return default
    try:
        with p.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:  # noqa: BLE001
        warn(f"解析失败 {p}：{e}")
        return default


def read_style(proj: Path) -> dict:
    pal = load_json(proj / "docs" / "02-art" / "palette.json", {}) or {}
    return {
        "style_key": pal.get("style_key", ""),
        "style_tokens": (pal.get("style_tokens") or "").strip(),
        "negative": (pal.get("negative") or "").strip(),
        "colors": (pal.get("primary") or []) + (pal.get("accent") or []),
    }


# ------------------------------------------------------------------ spec
def cmd_spec(args) -> int:
    proj = project_dir(args.project)
    bp = load_json(proj / "docs" / "01-brief" / "content-blueprint.json")
    if not bp:
        print("ERROR: 缺 content-blueprint.json（先跑 content_forge.py --scaffold）", file=sys.stderr)
        return 1
    out = proj / "docs" / "02-art" / "asset-spec.json"
    if out.exists() and not args.force:
        warn(f"asset-spec.json 已存在，未覆盖（--force 重写）")
        return 0

    style = read_style(proj)
    art = bp.get("art") or {}
    roles = art.get("roles_required") or ["character", "prop", "ui", "fx", "bg", "keyart"]
    hero_key = art.get("hero_consistency_key") or ""
    base_seed = int(art.get("seed") or 20261029)

    # 从蓝图里能自动提取的具名实体
    named = []
    p = (bp.get("story") or {}).get("protagonist") or {}
    if p.get("name"):
        named.append((p["name"], "character", f"the protagonist {p['name']}", True))
    a = (bp.get("story") or {}).get("antagonist") or {}
    if a.get("name"):
        named.append((a["name"], "character", f"the antagonist {a['name']}", False))
    for m in (bp.get("world") or {}).get("visual_motifs") or []:
        named.append((slug(m), "prop", m, False))

    items = []
    for role in roles:
        tpl = ROLES.get(role)
        if not tpl:
            warn(f"未知 role `{role}`，已跳过（可用：{', '.join(ROLES)}）")
            continue
        n = int(args.per_role or tpl["count"])
        # 具名实体优先占用该 role 的名额
        mine = [x for x in named if x[1] == role]
        for name, _r, desc, is_base in mine:
            items.append(mk_item(name, role, desc, tpl, base_seed, is_base, hero_key))
        for i in range(max(0, n - len(mine))):
            items.append(mk_item(f"{role}_{i+1}", role, "", tpl, base_seed, False, hero_key))

    spec = {
        "version": "2.0",
        "style_key": style["style_key"],
        "base_seed": base_seed,
        "hero_consistency_key": hero_key,
        "ui_language": art.get("ui_language") or "",
        "perspective": art.get("perspective") or "",
        "lighting": art.get("lighting") or "",
        "sheet_enabled": bool(args.sheet),
        "total_budget_kb": int(args.budget_kb),
        "items": items,
        "_todo": "逐条填 subject（英文，描述这个素材长什么样）。subject 为空时 --prompts 会用 id 兜底，质量差",
    }
    dump_json(out, spec)
    ok(f"已生成素材规格：{out}（{len(items)} 条，待填 subject）")
    empty = [i["id"] for i in items if not i.get("subject")]
    if empty:
        print(f"待填 subject 的条目 {len(empty)} 个：{', '.join(empty[:12])}{' …' if len(empty) > 12 else ''}")
    est = sum(i.get("budget_kb", 50) for i in items) / 1024
    print(f"体积预算合计约 {est:.2f}MB（processed 后），首包红线内请自行核算")
    return 0


def slug(s: str) -> str:
    s = re.sub(r"[^0-9a-zA-Z]+", "_", s).strip("_").lower()
    return s or "item"


def mk_item(item_id: str, role: str, subject: str, tpl: dict, seed: int, is_base: bool,
            hero_key: str) -> dict:
    return {
        "id": item_id,
        "role": role,
        "subject": subject,
        "view": tpl["view"],
        "extra": tpl["extra"],
        "negative_extra": tpl["neg_extra"],
        "size": [1024, 1024] if role not in ("bg", "keyart", "cutscene") else [1344, 1024],
        "seed": seed if (role in ("character", "prop") and hero_key) else "",
        "ref": "",
        "base": bool(is_base),
        "required": role in ("character", "prop", "ui", "fx"),
        "trim": bool(tpl["trim"]),
        "bg_mode": tpl["bg"],
        "budget_kb": tpl["budget_kb"],
        "sheet_group": "",
        "note": tpl["note"],
    }


# ------------------------------------------------------------------ prompts
def build_prompt(item: dict, style: dict) -> tuple[str, str]:
    """返回 (正向, 负向)。七槽位：style / subject / view / extra / lighting / bg / quality。"""
    tpl = ROLES.get(item.get("role"), ROLES["prop"])
    subject = (item.get("subject") or "").strip()
    if not subject:
        # 兜底：把 id 转成描述（去掉下划线数字），绝不把原始 id 写进提示词
        subject = re.sub(r"[_\-]\d+$", "", item.get("id", "")).replace("_", " ").replace("-", " ").strip()
        subject = f"a {subject}" if subject else "a game object"

    parts = [style["style_tokens"], subject, item.get("view") or tpl["view"]]
    if item.get("role") == "character" and item.get("ref"):
        parts.insert(1, HERO_ANCHOR)
    parts.append(item.get("extra") or tpl["extra"])
    lighting = style.get("lighting") or ""
    if lighting:
        parts.append(lighting)
    if (item.get("bg_mode") or tpl["bg"]) == "solid":
        parts.append(SOLID_BG)
    elif (item.get("bg_mode") or tpl["bg"]) == "scene":
        parts.append("detailed environment background, atmospheric depth")
    if style["colors"]:
        parts.append("palette: " + ", ".join(style["colors"][:6]))
    parts.append(QUALITY)

    pos = ", ".join(p for p in parts if p and p.strip())
    return pos, build_negative(item, style, tpl)


def build_negative(item: dict, style: dict, tpl: dict) -> str:
    seen, out = set(), []
    for chunk in (style.get("negative", ""), tpl.get("neg_extra", ""), item.get("negative_extra", "")):
        for w in [x.strip() for x in str(chunk).split(",") if x.strip()]:
            if w.lower() not in seen:
                seen.add(w.lower())
                out.append(w)
    return ", ".join(out)


def cmd_prompts(args) -> int:
    proj = project_dir(args.project)
    spec_path = proj / "docs" / "02-art" / "asset-spec.json"
    spec = load_json(spec_path)
    if not spec:
        print(f"ERROR: 缺 {spec_path}（先跑 --spec）", file=sys.stderr)
        return 1
    style = read_style(proj)
    if not style["style_tokens"]:
        print("ERROR: palette.json 缺 style_tokens（先跑 style_lib.py apply）", file=sys.stderr)
        return 1
    pdir = proj / "docs" / "02-art" / "prompts"
    pdir.mkdir(parents=True, exist_ok=True)

    items = spec.get("items") or []
    # 一致性锚：主角基准图的 raw 路径
    base = next((i for i in items if i.get("role") == "character" and i.get("base")), None)
    base_raw = f"assets/raw/{base['id']}.png" if base else ""
    for i in items:
        if (i.get("role") == "character" and not i.get("base") and base_raw
                and not i.get("ref") and i.get("use_hero_ref")):
            i["ref"] = base_raw
            i["seed"] = base.get("seed") or ""

    # 网格合并
    groups: dict[str, list[dict]] = {}
    singles: list[dict] = []
    for i in items:
        g = (i.get("sheet_group") or "").strip()
        if g:
            groups.setdefault(g, []).append(i)
        else:
            singles.append(i)

    written = 0
    for i in singles:
        pos, neg = build_prompt(i, style)
        (pdir / f"{i['id']}.txt").write_text(pos + "\n", encoding="utf-8")
        side = {
            "size": {"width": int(i["size"][0]), "height": int(i["size"][1])},
            "trim": bool(i.get("trim", True)),
            "negative": neg,
        }
        if str(i.get("seed") or "").strip():
            side["seed"] = int(i["seed"])
        if i.get("ref"):
            side["ref"] = i["ref"]
        dump_json(pdir / f"{i['id']}.json", side)
        i["prompt_file"] = f"docs/02-art/prompts/{i['id']}.txt"
        written += 1

    for g, members in groups.items():
        # 网格必须尽量贴合 item 数：3x3 放 4 个 → 模型会把同一物品画三遍（实测）
        n = len(members)
        rows = 2 if n <= 4 else 3
        cols = 2 if n <= 4 else 3
        while rows * cols < n:
            cols += 1
        subjects = " | ".join(f"{i + 1}. {(m.get('subject') or m['id']).strip()}"
                              for i, m in enumerate(members))
        pos = ", ".join(x for x in [
            style["style_tokens"],
            f"a {rows}x{cols} grid sheet containing exactly {n} DIFFERENT objects, one per cell, no duplicates, no repeated items",
            subjects,
            "each object appears only once, centered in its own cell, separated by clear margins",
            ROLES["prop"]["view"],
            SOLID_BG,
            QUALITY,
        ] if x)
        fname = f"_sheet_{g}"
        (pdir / f"{fname}.txt").write_text(pos + "\n", encoding="utf-8")
        dump_json(pdir / f"{fname}.json", {
            "kind": "sheet", "grid": f"{rows}x{cols}",
            "items": [m["id"] for m in members],
            "trim": True, "negative": build_negative({}, style, ROLES["prop"]),
        })
        for m in members:
            m["prompt_file"] = f"docs/02-art/prompts/{fname}.txt"
            m["in_sheet"] = fname
        written += 1

    dump_json(spec_path, spec)
    ok(f"已生成 {written} 个提示词 → docs/02-art/prompts/")
    missing = [i["id"] for i in items if not (i.get("subject") or "").strip()]
    if missing:
        warn(f"{len(missing)} 条缺 subject，已用 id 兜底（质量不佳）：{', '.join(missing[:8])}")
    print("\n下一步：")
    print("  python scripts/asset_forge.py --project . --lint")
    print("  python scripts/gen_assets.py --project . --dry-run")
    print("  python scripts/gen_assets.py --project . --max 2     # 先验风格")
    return 0


# ------------------------------------------------------------------ lint
def cmd_lint(args) -> int:
    proj = project_dir(args.project)
    spec = load_json(proj / "docs" / "02-art" / "asset-spec.json", {}) or {}
    style = read_style(proj)
    pdir = proj / "docs" / "02-art" / "prompts"
    if not pdir.is_dir():
        print(f"ERROR: 提示词目录不存在：{pdir}", file=sys.stderr)
        return 1
    ids = {i.get("id") for i in spec.get("items") or []}
    subj_map = {i.get("id"): (i.get("subject") or "").strip() for i in spec.get("items") or []}
    anchor_words = [w for w in (style.get("style_tokens") or "").split(",")[:3] if len(w.strip()) > 3]

    problems = []
    files = sorted(f for f in pdir.glob("*.txt"))
    if not files:
        print("ERROR: 没有提示词文件", file=sys.stderr)
        return 1

    for f in files:
        name = f.stem
        txt = f.read_text(encoding="utf-8", errors="ignore").strip()
        role = next((i.get("role") for i in spec.get("items") or [] if i.get("id") == name), None)
        tpl = ROLES.get(role or "prop")

        def err(code, msg):
            problems.append({"file": f.name, "level": "ERROR", "code": code, "msg": msg})

        def wrn(code, msg):
            problems.append({"file": f.name, "level": "WARN", "code": code, "msg": msg})

        if CJK.search(txt):
            err("CJK", "提示词含中文/中文标点，模型会画错或忽略")
        # id 型素材名绝不能出现在提示词里（模型会把名字画出来）
        # 但要排除 style_tokens 本来就含的常用词（如 "icon-like readability" 里的 icon）
        style_words = {w.strip().lower() for w in (style.get("style_tokens") or "").replace("-", " ").split()}
        low = txt.lower()
        is_sheet = name.startswith("_sheet_")
        for iid in ids:
            key = str(iid or "").lower()
            if len(key) <= 3:
                continue
            if key in style_words:
                continue
            if re.search(r"(?<![a-z0-9_])" + re.escape(key) + r"(?![a-z0-9_])", low):
                err("ID_LEAK", f"提示词含素材 id `{iid}`，模型可能把它当文字画出来")
                break
        words = len(txt.split())
        if words < 15:
            err("TOO_SHORT", f"仅 {words} 词，槽位不全（style/subject/view/extra/bg/quality）")
        elif words > (220 if is_sheet else 140):
            wrn("TOO_LONG", f"{words} 词，过长会稀释主体")
        if anchor_words and not any(a.strip().lower() in txt.lower() for a in anchor_words):
            err("NO_STYLE_ANCHOR", f"缺风格锚词（应有 style_tokens 前几段，如「{anchor_words[0].strip()}」）")
        if tpl and tpl["view"].split(",")[0].strip().lower() not in txt.lower():
            wrn("NO_VIEW", f"缺视角槽位（建议含「{tpl['view'].split(',')[0]}」）")
        if not is_sheet and not subj_map.get(name):
            wrn("GENERIC_SUBJECT", "asset-spec 的 subject 为空，提示词只是 id 兜底 → 出图内容不可控，必须填写")
        side = f.with_suffix(".json")
        if not side.exists():
            wrn("NO_SIDECAR", "缺 sidecar json（尺寸/seed/ref/trim 会走默认值）")
        else:
            o = load_json(side, {}) or {}
            if o.get("ref") and path_missing(proj, o["ref"]):
                wrn("REF_MISSING", f"ref 指向的基准图不存在：{o['ref']}（i2i 会失败退回 t2i）")

    errs = [p for p in problems if p["level"] == "ERROR"]
    wrns = [p for p in problems if p["level"] == "WARN"]
    print(f"提示词 lint：{len(files)} 个文件　ERROR {len(errs)}　WARN {len(wrns)}")
    for p in problems:
        print(f"  [{p['level']}] {p['file']} {p['code']} —— {p['msg']}")
    dump_json(proj / "docs" / "02-art" / "asset-lint.json", {
        "files": len(files), "errors": errs, "warnings": wrns, "ok": not errs,
    })
    if errs:
        print("\nERROR 必改，否则出图会走偏。改 asset-spec.json 后重跑 --prompts。", file=sys.stderr)
        return 2
    ok("lint 通过")
    return 0


def path_missing(proj: Path, ref: str) -> bool:
    p = Path(ref)
    return not (p if p.is_absolute() else proj / p).exists()


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    ap = argparse.ArgumentParser(description="素材生成器：asset-spec → 提示词 → lint")
    ap.add_argument("--project", default=None)
    ap.add_argument("--spec", action="store_true")
    ap.add_argument("--prompts", action="store_true")
    ap.add_argument("--lint", action="store_true")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--sheet", action="store_true", help="把同类道具合并成网格图省算力")
    ap.add_argument("--per-role", type=int, default=0, help="每个 role 生成几条（覆盖默认）")
    ap.add_argument("--budget-kb", type=int, default=2000, help="素材总体积预算（KB）")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    if args.all:
        args.spec = args.prompts = args.lint = True
    if args.spec and cmd_spec(args) != 0:
        return 1
    if args.prompts and cmd_prompts(args) != 0:
        return 1
    if args.lint:
        return cmd_lint(args)
    if not any((args.spec, args.prompts, args.lint)):
        ap.print_help()
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
