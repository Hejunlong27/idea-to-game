#!/usr/bin/env python3
"""内容蓝图生成器（模块 01b 用）：把一句话想法变成「可判定深度」的结构化规格。

分工原则：**脚本给约束和骨架，Agent 写真正的内容。**
本脚本不试图自动编故事 —— 它负责三件事：
  1. --analyze   从 idea 推断品类 / 推荐叙事框架与机制候选 / 列素材角色需求
  2. --scaffold  生成 content-blueprint.json 骨架（带 TODO 与数量要求，堵死漏项）
  3. --validate  校验每个必填槽位是否填满、数量是否达标、机制 id 是否真实咬合

用法:
    python content_forge.py --idea "守护一座会下沉的灯塔" --analyze
    python content_forge.py --project . --scaffold
    python content_forge.py --project . --validate [--strict]

产物:
    docs/01-brief/analysis.json            分析结果（可复现）
    docs/01-brief/content-blueprint.json   ★ 内容单一真相源
    docs/01-brief/story.md                 故事草稿模板（Agent 填）

判据: references/content-depth.md（四维）+ assets/data/{mechanic-vocab,story-frames}.json
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import SKILL_DIR, dump_json, load_state, ok, project_dir, warn  # noqa: E402

DATA_DIR = SKILL_DIR / "assets" / "data"

# ---------------------------------------------------------------- 品类推断
GENRE_KEYWORDS = {
    "whack": ["敲", "打地鼠", "拍", "锤", "戳"],
    "arcade": ["街机", "刷分", "无尽", "挑战高分", "连打", "得分"],
    "tower_defense": ["塔防", "防守", "守塔", "守夜", "守灯", "守", "建塔", "入侵", "基地"],
    "merge": ["合成", "合并", "升级物品"],
    "puzzle": ["解谜", "推箱", "拼图", "消除", "逻辑", "关卡"],
    "runner": ["跑酷", "跑", "飞", "躲避障碍", "前进"],
    "card": ["卡牌", "牌组", "出牌", "回合"],
    "management": ["经营", "农场", "餐厅", "店铺", "管理", "养成"],
    "rhythm": ["节奏", "音游", "节拍", "音乐"],
    "shooter": ["射击", "弹幕", "飞机", "枪"],
    "survival": ["生存", "荒野", "饥饿", "夜袭"],
    "idle": ["放置", "挂机", "自动"],
    "physics": ["物理", "弹球", "重力", "碰撞"],
}

GENRE_INFO = {
    "whack": ("敲击/反应类", 9, ["character", "prop", "ui", "fx", "bg", "keyart"], "tap_target"),
    "arcade": ("街机刷分类", 8, ["character", "prop", "ui", "fx", "bg", "keyart"], "tap_target"),
    "tower_defense": ("塔防/防守类", 8, ["character", "prop", "tile", "ui", "fx", "bg", "keyart"], "drag_place"),
    "merge": ("合成类", 6, ["prop", "tile", "ui", "fx", "bg", "keyart"], "merge_combine"),
    "puzzle": ("解谜类", 12, ["prop", "tile", "ui", "fx", "bg", "keyart"], "space_grid"),
    "runner": ("跑酷类", 8, ["character", "prop", "bg", "ui", "fx", "keyart"], "lane_switch"),
    "card": ("卡牌/构筑类", 8, ["character", "prop", "ui", "fx", "bg", "keyart"], "card_combo"),
    "management": ("经营类", 8, ["prop", "character", "ui", "bg", "fx", "keyart"], "resource_econ"),
    "rhythm": ("节奏类", 8, ["character", "prop", "ui", "fx", "bg", "keyart"], "rhythm_sync"),
    "shooter": ("射击类", 8, ["character", "prop", "bg", "ui", "fx", "keyart"], "precision_aim"),
    "survival": ("生存类", 8, ["character", "prop", "tile", "ui", "fx", "bg", "keyart"], "survival_need"),
    "idle": ("放置类", 6, ["prop", "ui", "bg", "fx", "keyart", "character"], "exchange_market"),
    "physics": ("物理类", 8, ["prop", "tile", "ui", "fx", "bg", "keyart"], "physics_bounce"),
}

TONE_WORDS = {
    "warm": ["温暖", "治愈", "温柔", "怀旧", "童年", "家"],
    "dark": ["恐怖", "黑暗", "诡异", "死亡", "诅咒", "深渊", "爬上来", "怪物", "夜袭", "海怪"],
    "funny": ["搞笑", "荒诞", "傻", "胡闹", "幽默", "滑稽"],
    "epic": ["史诗", "英雄", "战争", "传说", "王"],
    "melancholy": ["孤独", "失去", "告别", "遗忘", "沉没", "废弃"],
    "tense": ["紧张", "极限", "追赶", "逃生", "倒计时"],
}

# 非数值难度轴的候选池（对应 content-depth M3）
AXIS_POOL = [
    ("信息可见度", "全显示 → 部分隐藏"),
    ("资源充裕度", "够用 → 枯竭"),
    ("操作复杂度", "单步 → 组合"),
    ("环境稳定性", "静态 → 会变"),
    ("失败代价", "可重试 → 不可逆"),
]


def load_json(path: Path):
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def load_vocab() -> list[dict]:
    p = DATA_DIR / "mechanic-vocab.json"
    if not p.exists():
        warn(f"机制词库缺失：{p}")
        return []
    return load_json(p)["mechanics"]


def load_frames() -> list[dict]:
    p = DATA_DIR / "story-frames.json"
    if not p.exists():
        warn(f"叙事框架库缺失：{p}")
        return []
    return load_json(p)["frames"]


def infer_genre(idea: str) -> tuple[str, dict]:
    """关键词命中计分；平手时用 '小游戏' 兜底到 arcade。"""
    score: dict[str, int] = {}
    for g, words in GENRE_KEYWORDS.items():
        for w in words:
            if w in idea:
                score[g] = score.get(g, 0) + (3 if len(w) >= 3 else 1)
    if not score:
        return "arcade", {}
    ranked = sorted(score.items(), key=lambda kv: (-kv[1], kv[0]))
    return ranked[0][0], dict(ranked)


def infer_tones(idea: str) -> list[str]:
    hits = [t for t, words in TONE_WORDS.items() if any(w in idea for w in words)]
    return hits or ["neutral"]


def match_mechanics(idea: str, genre: str, vocab: list[dict]) -> list[dict]:
    """按品类匹配 + idea 关键词加分，返回排序后的候选（含匹配理由）。"""
    out = []
    for m in vocab:
        s = 0
        reasons = []
        if genre in m.get("genres", []):
            s += 5
            reasons.append(f"品类命中 {genre}")
        # 中文名做 2-gram 重叠匹配（无分词器，2 字足够区分「合成」「防守」「节奏」等）
        nm = m["name_zh"]
        grams = {nm[i:i + 2] for i in range(max(1, len(nm) - 1))}
        hit_grams = [g for g in grams if len(g) == 2 and g in idea]
        if hit_grams:
            s += 4 * min(2, len(hit_grams))
            reasons.append(f"想法含「{'/'.join(hit_grams[:2])}」")
        if m["name_en"].split()[0] in idea.lower():
            s += 4
            reasons.append("英文动词命中")
        cost = m.get("cost", "M")
        s += {"S": 2, "M": 1, "L": 0}.get(cost, 0)   # 低成本优先（小游戏体量）
        if s > 0:
            out.append({**m, "_score": s, "_why": "；".join(reasons) or "品类匹配"})
    out.sort(key=lambda m: (-m["_score"], m["cat"], m["id"]))
    return out


def recommend_frames(genre: str, tones: list[str], frames: list[dict]) -> list[dict]:
    scored = []
    for f in frames:
        s = 0
        if genre in f.get("genres", []):
            s += 5
        for t in tones:
            if t == "dark" and f["id"] in ("descend_layers", "cycle_curse", "bargain_debt"):
                s += 3
            if t in ("warm", "melancholy") and f["id"] in ("anthropomorph_daily", "guard_lose", "collect_truth"):
                s += 3
            if t == "funny" and f["id"] in ("absurd_work", "reverse_story"):
                s += 3
            if t == "epic" and f["id"] in ("descend_layers", "guard_lose", "bargain_debt"):
                s += 2
            if t == "tense" and f["id"] in ("cycle_curse", "guard_lose", "descend_layers"):
                s += 2
        scored.append({**f, "_score": s})
    scored.sort(key=lambda f: -f["_score"])
    return scored[:2]


# ---------------------------------------------------------------- 骨架
def build_skeleton(idea: str, genre: str, tones: list[str],
                   mech_cands: list[dict], frames: list[dict], levels_n: int) -> dict:
    label, lv, roles, main_hint = GENRE_INFO.get(genre, GENRE_INFO["arcade"])
    main = next((m for m in mech_cands if m["id"] == main_hint), None) or (mech_cands[0] if mech_cands else None)
    subs = [m for m in mech_cands if main and m["id"] != main["id"]][:2]

    def mech_stub(m: dict) -> dict:
        return {
            "id": m["id"],
            "name_zh": m["name_zh"],
            "role": "core" if main and m["id"] == main["id"] else "support",
            "why_fun": "",
            "interacts": [],
            "unlock_level": 1,
            "_todo": f"填 why_fun（一句话：它凭什么好玩）；interacts 必须引用真实机制 id（候选池：{', '.join(x['id'] for x in mech_cands[:8])}）",
        }

    core = [mech_stub(m) for m in ([main] if main else []) + subs]
    # 补足到 3 个占位，供继续扩展
    while len(core) < 3:
        core.append({"id": f"TODO_mech_{len(core)+1}", "name_zh": "", "role": "core",
                     "why_fun": "", "interacts": [], "unlock_level": 1,
                     "_todo": "必须从 mechanic-vocab.json 选真实 id 并改写"})

    twists = [
        {"id": "TODO_twist_1", "name_zh": "", "why_fun": "", "changes_decision": "",
         "interacts": [], "unlock_level": max(2, levels_n // 3),
         "_todo": "第二个机制层：必须改变玩家的最优策略，不是数值加强"},
        {"id": "TODO_twist_2", "name_zh": "", "why_fun": "", "changes_decision": "",
         "interacts": [], "unlock_level": max(3, levels_n // 2),
         "_todo": "第三个机制层"},
    ]

    frame = frames[0] if frames else None
    bp = {
        "_meta": {
            "version": "2.0",
            "idea": idea,
            "genre": genre,
            "genre_label": label,
            "tones": tones,
            "created": datetime.now().astimezone().isoformat(timespec="seconds"),
            "judged_by": "references/content-depth.md",
            "filled_by": "Agent（本文件由 content_forge.py 生成骨架，内容必须人/模型精修）",
        },
        "world": {
            "logline": "",
            "setting": "",
            "theme": "",
            "rules": [],
            "visual_motifs": [],
            "palette_hint": [],
            "_todo": "logline ≥20 字；rules 至少 3 条且必须是约束（「这个世界的X不能Y」）",
        },
        "story": {
            "frame": frame["id"] if frame else "",
            "frame_name": frame["name_zh"] if frame else "",
            "frame_why": frame["why"] if frame else "",
            "protagonist": {"name": "", "role": "", "want": "", "need": "", "flaw": "", "arc": ""},
            "antagonist": {"name": "", "role": "", "pressure": ""},
            "acts": [
                {"act": i + 1, "name": "", "goal": "", "turn": "", "levels": []}
                for i in range(3)
            ],
            "ending_beats": [],
            "dialogue": [],
            "_todo": "want≠need；三幕每幕都要 turn；dialogue ≥12 条，每条含 speaker/line/cue/emotion；对白 ≤20 条",
        },
        "mechanics": {
            "core_verb": "",
            "core": core,
            "twists": twists,
            "progression_axis": [],
            "rule_twist": {"level": 0, "what": "", "_todo": "规则在哪一关被改写"},
            "_todo": "progression_axis 至少 2 条非「更快/更多」；核心机制合计 ≥5 个",
        },
        "levels": [
            {
                "level": i + 1,
                "new": [],
                "logline": "",
                "decision": "",
                "target": "",
                "_todo": "decision 必须能写成「A好但B坏」",
            }
            for i in range(levels_n)
        ],
        "art": {
            "style_key": "",
            "perspective": "",
            "lighting": "",
            "ui_language": "",
            "roles_required": roles,
            "hero_consistency_key": "",
            "_todo": "style_key 取自 assets/styles/；hero_consistency_key 用于 i2i ref 链",
        },
        "audio": {
            "mood_arc": [],
            "sfx_events": [],
            "music_cues": [],
            "voice": {"enabled": True, "reason": "", "voices": {}},
            "_todo": "mood_arc ≥2；sfx_events ≥16 且覆盖 ui/gameplay/feedback/ambience 四层；music_cues ≥2",
        },
        "exceptions": [],
    }
    return bp


STORY_MD_TEMPLATE = """# 故事与设定 · {name}

> 由 `content_forge.py --scaffold` 生成骨架。**每一节都必须填满**，`--validate` 会逐项检查。
> 铁律：故事服务于循环，不取代循环。对白 ≤20 条、单条 ≤40 字、必须挂 cue。

## 1. 一句话世界观

（≥20 字。要包含：谁、在哪、被什么限制）

## 2. 世界规则（≥3 条，必须是约束）

1. 这个世界的 ______ 不能 ______
2. 任何人 ______ 都会 ______
3. ______ 只有在 ______ 时才成立

## 3. 主题

（一句话。玩家通关后应该带走的一个想法）

## 4. 主角

| 项 | 内容 |
|---|---|
| 名字 | |
| 身份 | |
| want（表层想要） | |
| need（真正需要） | |
| flaw（缺陷） | |
| arc（从 → 到） | |

`want` 与 `need` 必须不同，弧光来自这个差。

## 5. 对手 / 压力源

（不一定是有形反派。可以是环境、规则、时间、自己的记忆）

## 6. 三幕

| 幕 | 关卡 | 目标 | 转折（turn） |
|---|---|---|---|
| 一 | 1–{a} | | |
| 二 | {b}–{c} | | |
| 三 | {d}–{e} | | |

## 7. 关卡叙事钩子（每关一句 logline）

（例：第 3 关「灯第一次灭掉，你听见有人在下面数数」）

## 8. 对白（≥12 条，≤20 条）

| id | cue（触发点） | 说话人 | 台词（≤40 字） | 情绪 |
|---|---|---|---|---|
| v01 | lv1_start | | | |

`cue` 规范：`lv<N>_start` / `lv<N>_end` / `lv<N>_twist` / `win` / `lose` / `menu_idle`

## 9. 结局（≥2 个节拍）

（必须有代价或获得，不能是「循环继续」）
"""


def cmd_analyze(args) -> int:
    idea = args.idea
    genre, scores = infer_genre(idea) if not args.genre else (args.genre, {})
    tones = infer_tones(idea)
    vocab = load_vocab()
    frames_lib = load_frames()
    cands = match_mechanics(idea, genre, vocab)
    frames = recommend_frames(genre, tones, frames_lib)
    label, levels_n, roles, main_hint = GENRE_INFO.get(genre, GENRE_INFO["arcade"])

    lines = [
        f"# 内容分析 · {idea}",
        "",
        f"- 推断品类：**{genre}**（{label}）" + (f"　命中：{scores}" if scores else "　（人工指定）"),
        f"- 情绪基调：{', '.join(tones)}",
        f"- 建议关卡数：{levels_n}（品类经验值，非硬性）",
        "",
        "## 推荐叙事框架",
        "",
    ]
    for f in frames:
        lines += [
            f"### {f['name_zh']}（`{f['id']}`）",
            f"- 前提：{f['premise']}",
            f"- 为什么适合小游戏：{f['why']}",
            f"- 三幕：" + " / ".join(f"①{a['goal']}→{a['turn']}" for a in f["acts"][:1]),
            f"- 需要配合的机制：{', '.join(f['requires'])}",
            f"- 转折点建议：{f['twist_hint']}",
            "",
        ]

    lines += ["## 机制候选（按匹配度排序，取「一主两副」）", ""]
    lines += ["| 机制 | id | 类 | 成本 | 为什么 |", "|---|---|---|---|---|"]
    for m in cands[:14]:
        lines.append(f"| {m['name_zh']} | `{m['id']}` | {m['cat']} | {m['cost']} | {m['_why']} |")

    main = next((m for m in cands if m["id"] == main_hint), cands[0] if cands else None)
    lines += ["", f"**建议主机制**：`{main['id']}`（{main['name_zh']}）" if main else "**建议主机制**：无匹配，人工指定"]
    if main and main.get("decision"):
        lines.append(f"- 它带来的取舍：{main['decision']}")
        lines.append(f"- 推荐搭配：{', '.join(main['interacts'])}")

    lines += ["", "## 难度轴候选（至少选 2 条非数值轴）", ""]
    for name, desc in AXIS_POOL:
        lines.append(f"- **{name}**：{desc}")

    lines += ["", "## 素材角色需求", "", f"必需 role：{', '.join(roles)}", ""]
    lines += ["| role | 数量建议 | 说明 |", "|---|---|---|"]
    role_n = {"character": 3, "prop": 8, "tile": 6, "bg": 3, "ui": 6, "fx": 4, "keyart": 1, "icon": 1, "cutscene": 2}
    for r in roles:
        lines.append(f"| {r} | {role_n.get(r, 2)} | {'主角三视图 + 对手 + NPC' if r=='character' else ''} |")

    lines += [
        "",
        "## 下一步",
        "",
        "```bash",
        "python scripts/content_forge.py --project . --scaffold",
        "# 然后按 story.md 与 blueprint 的 _todo 逐项填写（Agent 或人）",
        "python scripts/content_forge.py --project . --validate",
        "python scripts/richness_check.py --project .",
        "```",
    ]
    print("\n".join(lines))

    if args.project:
        proj = project_dir(args.project)
        dump_json(proj / "docs" / "01-brief" / "analysis.json", {
            "idea": idea, "genre": genre, "genre_scores": scores, "tones": tones,
            "levels_suggested": levels_n,
            "frames": [{k: v for k, v in f.items() if not k.startswith("_")} for f in frames],
            "mechanics": [{k: v for k, v in m.items()} for m in cands[:20]],
            "roles_required": roles,
            "axes": [{"name": n, "desc": d} for n, d in AXIS_POOL],
        })
        ok(f"已写 docs/01-brief/analysis.json")
    return 0


def cmd_scaffold(args) -> int:
    proj = project_dir(args.project)
    out = proj / "docs" / "01-brief" / "content-blueprint.json"
    if out.exists() and not args.force:
        warn(f"蓝图已存在，未覆盖：{out}（加 --force 重写）")
        return 0

    st = load_state(proj)
    idea = args.idea or st.get("project", {}).get("idea", "")
    if not idea:
        print("ERROR: 项目未记录 idea，请用 --idea 指定", file=sys.stderr)
        return 1
    genre = args.genre or st.get("project", {}).get("genre", "") or infer_genre(idea)[0]
    tones = infer_tones(idea)
    cands = match_mechanics(idea, genre, load_vocab())
    frames = recommend_frames(genre, tones, load_frames())
    levels_n = args.levels or GENRE_INFO.get(genre, GENRE_INFO["arcade"])[1]

    bp = build_skeleton(idea, genre, tones, cands, frames, levels_n)
    dump_json(out, bp)
    ok(f"已生成蓝图骨架：{out}")

    a = max(3, levels_n // 3)
    b, c = a + 1, max(a + 1, (levels_n * 2) // 3)
    d, e = c + 1, levels_n
    md = proj / "docs" / "01-brief" / "story.md"
    if not md.exists() or args.force:
        md.write_text(
            STORY_MD_TEMPLATE.format(name=st.get("project", {}).get("name", "game"),
                                     a=a, b=b, c=c, d=d, e=e),
            encoding="utf-8",
        )
        ok(f"已生成故事模板：{md}")

    todos = count_todos(bp)
    print(f"\n蓝图共 {todos} 处 _todo 待填。填完跑：")
    print("  python scripts/content_forge.py --project . --validate")
    return 0


def count_todos(obj) -> int:
    if isinstance(obj, dict):
        return sum(count_todos(v) for k, v in obj.items() if k != "_todo") + (1 if "_todo" in obj else 0)
    if isinstance(obj, list):
        return sum(count_todos(v) for v in obj)
    return 0


# ---------------------------------------------------------------- 校验
MIN_CHARS = {"logline": 12, "theme": 4}


def cmd_validate(args) -> int:
    proj = project_dir(args.project)
    bp_path = proj / "docs" / "01-brief" / "content-blueprint.json"
    if not bp_path.exists():
        print(f"ERROR: 蓝图不存在：{bp_path}（先跑 --scaffold）", file=sys.stderr)
        return 1
    bp = load_json(bp_path)
    issues: list[tuple[str, str, str]] = []   # (level, path, msg)

    def err(p, m):
        issues.append(("ERROR", p, m))

    def wrn(p, m):
        issues.append(("WARN", p, m))

    def need(d: dict, key: str, p: str, min_len: int = 1):
        v = (d or {}).get(key)
        if isinstance(v, str):
            if len(v.strip()) < min_len:
                err(f"{p}.{key}", f"必填，至少 {min_len} 字（当前 {len(v.strip())}）")
        elif not v:
            err(f"{p}.{key}", "必填但为空")

    w = bp.get("world", {})
    need(w, "logline", "world", MIN_CHARS["logline"])
    need(w, "setting", "world")
    need(w, "theme", "world", MIN_CHARS["theme"])
    if len(w.get("rules") or []) < 3:
        err("world.rules", f"需要 ≥3 条世界规则（当前 {len(w.get('rules') or [])}）")

    s = bp.get("story", {})
    p = s.get("protagonist") or {}
    for k in ("want", "need", "flaw", "arc"):
        need(p, k, "story.protagonist")
    if (p.get("want") or "").strip() and p.get("want") == p.get("need"):
        err("story.protagonist", "want 与 need 不能相同（弧光来自差异）")
    acts = s.get("acts") or []
    if len(acts) != 3:
        err("story.acts", f"必须是 3 幕（当前 {len(acts)}）")
    for i, a in enumerate(acts):
        for k in ("goal", "turn"):
            if not (a.get(k) or "").strip():
                err(f"story.acts[{i}].{k}", "必填")
    dlg = s.get("dialogue") or []
    if len(dlg) < 12:
        err("story.dialogue", f"需要 ≥12 条（当前 {len(dlg)}）")
    if len(dlg) > 20:
        wrn("story.dialogue", f"超过 20 条（{len(dlg)}），已越过小游戏叙事上限，见 content-depth.md §3")
    for i, d in enumerate(dlg):
        for k in ("speaker", "line", "cue", "emotion"):
            if not (d.get(k) or "").strip():
                err(f"story.dialogue[{i}].{k}", "必填")
        if len(d.get("line") or "") > 40:
            wrn(f"story.dialogue[{i}].line", f"{len(d['line'])} 字，建议 ≤40（TTS 约 3 秒）")
    if len(s.get("ending_beats") or []) < 2:
        err("story.ending_beats", f"需要 ≥2 个结局节拍（当前 {len(s.get('ending_beats') or [])}）")

    m = bp.get("mechanics", {})
    vocab_ids = {x["id"] for x in load_vocab()}
    allm = list(m.get("core") or []) + list(m.get("twists") or [])
    if len(allm) < 5:
        err("mechanics", f"核心机制合计需 ≥5（当前 {len(allm)}）")
    ids = [x.get("id", "") for x in allm]
    for i, x in enumerate(allm):
        mid = x.get("id", "")
        if mid.startswith("TODO"):
            err(f"mechanics[{i}].id", "占位未替换，必须用真实机制 id")
        elif vocab_ids and mid not in vocab_ids:
            wrn(f"mechanics[{i}].id", f"`{mid}` 不在词库内（允许自定义，但需在 blueprint 说明）")
        if not (x.get("why_fun") or "").strip():
            err(f"mechanics[{i}].why_fun", "必填：一句话说明它凭什么好玩")
        inter = x.get("interacts") or []
        if not inter:
            err(f"mechanics[{i}].interacts", "必填：至少引用 1 个其他机制 id（M2 咬合）")
        for ref in inter:
            if ref not in ids:
                err(f"mechanics[{i}].interacts", f"引用了不存在的机制 `{ref}`")
            elif ref == mid:
                err(f"mechanics[{i}].interacts", "不能引用自己")
    if len(m.get("progression_axis") or []) < 3:
        wrn("mechanics.progression_axis", f"建议 ≥3 条（当前 {len(m.get('progression_axis') or [])}）")
    rt = m.get("rule_twist") or {}
    if not rt.get("what"):
        wrn("mechanics.rule_twist", "建议填：规则在第几关被改写（M5 / 叙事反转）")

    lv = bp.get("levels") or []
    if not lv:
        err("levels", "关卡列表为空")
    for i, x in enumerate(lv):
        if not (x.get("decision") or "").strip():
            err(f"levels[{i}].decision", "必填：本关玩家要做的取舍（A好但B坏）")
        if not (x.get("logline") or "").strip():
            err(f"levels[{i}].logline", "必填：本关一句叙事钩子")
        if not x.get("new"):
            wrn(f"levels[{i}].new", "建议列本关新元素")

    au = bp.get("audio", {})
    if len(au.get("mood_arc") or []) < 2:
        err("audio.mood_arc", f"需要 ≥2 段情绪（当前 {len(au.get('mood_arc') or [])}）")
    sfx = au.get("sfx_events") or []
    if len(sfx) < 16:
        err("audio.sfx_events", f"需要 ≥16 个音效事件（当前 {len(sfx)}）")
    layers = {x.get("layer") for x in sfx}
    for need_layer in ("ui", "gameplay", "feedback", "ambience"):
        if need_layer not in layers:
            err("audio.sfx_events", f"缺少 layer=`{need_layer}` 的事件")
    if len(au.get("music_cues") or []) < 2:
        err("audio.music_cues", f"需要 ≥2 段音乐（当前 {len(au.get('music_cues') or [])}）")

    art = bp.get("art", {})
    if len(art.get("roles_required") or []) < 6:
        err("art.roles_required", "至少 6 类素材 role")

    # 输出
    errors = [i for i in issues if i[0] == "ERROR"]
    warns = [i for i in issues if i[0] == "WARN"]
    print(f"蓝图校验：{bp_path}")
    print(f"  ERROR {len(errors)}　WARN {len(warns)}　待填 _todo {count_todos(bp)}\n")
    for lvl, pth, msg in issues:
        print(f"[{lvl}] {pth} —— {msg}")
    if not issues:
        print("全部槽位已填满。下一步：python scripts/richness_check.py --project .")

    dump_json(proj / "docs" / "01-brief" / "blueprint-validation.json", {
        "ok": not errors,
        "errors": [{"path": p_, "msg": m_} for _, p_, m_ in errors],
        "warnings": [{"path": p_, "msg": m_} for _, p_, m_ in warns],
        "todo_left": count_todos(bp),
    })
    if errors:
        return 2 if args.strict else 0
    return 0


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    ap = argparse.ArgumentParser(description="内容蓝图生成器")
    ap.add_argument("--idea", default="", help="一句话想法（--analyze 必需；--scaffold 可省，从 state 读）")
    ap.add_argument("--genre", default="", help="强制指定品类（跳过推断）")
    ap.add_argument("--levels", type=int, default=0, help="建议关卡数（覆盖品类默认）")
    ap.add_argument("--project", default=None, help="项目目录")
    ap.add_argument("--analyze", action="store_true")
    ap.add_argument("--scaffold", action="store_true")
    ap.add_argument("--validate", action="store_true")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--strict", action="store_true", help="validate 有 ERROR 时返回非 0")
    args = ap.parse_args()

    if args.analyze:
        if not args.idea:
            print("ERROR: --analyze 需要 --idea", file=sys.stderr)
            return 1
        return cmd_analyze(args)
    if args.scaffold:
        return cmd_scaffold(args)
    if args.validate:
        return cmd_validate(args)
    ap.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
