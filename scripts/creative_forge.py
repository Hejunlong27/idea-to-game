#!/usr/bin/env python3
"""创意总监（Creative Director）：把一句话想法变成「有差异的多个方向」，再收敛成一份创意身份。

为什么需要它 —— v2 的结构性缺陷：
  `content_forge.infer_genre()` 用关键词选出**唯一**品类，`build_skeleton()` 直接产出**唯一**蓝图。
  系统从第一步就只有一条路，后面所有环节都在为这条路服务 —— 这就是「换皮」的机制性原因。

本脚本补的是「发散 → 评估 → 收敛」这三步：
  1. --diverge   生成 N 个**结构上真正不同**的方向（用交互动词的结构指纹做最远点采样，
                 保证任意两个方案在 spatial/time/info/resource/risk 上至少 3 项不同）
  2. --twist     对某个方向做创意反转（9 个维度，每个维度都有「代价」）
  3. --evaluate  7 维评分 + **启发式相似度分析**（与 16 个玩法原型比对，识别换皮风险）
  4. --dna       把选中的方向收敛成 docs/01-brief/creative-dna.json（唯一创意身份）

重要立场（任务书 §3.4）：
  **不宣称「完全原创」。** 本脚本只做启发式相似度分析 —— 识别常见玩法套路、结构相似、潜在换皮。
  结论写成「与 X 原型的结构重合度 0.82，需重新设计核心机制」，而不是「原创度 95 分」。

用法:
    python creative_forge.py --project . --diverge --idea "守一座会失去光的灯塔" --n 5
    python creative_forge.py --project . --twist --concept C2 --dim sound_as_mechanic
    python creative_forge.py --project . --evaluate
    python creative_forge.py --project . --dna --pick C3
    python creative_forge.py --project . --validate

产物:
    docs/01-brief/creative-concepts.json    N 个方向 + 评分 + 相似度分析
    docs/01-brief/creative-review.md        人读的创意评审报告
    docs/01-brief/creative-dna.json         ★ 唯一创意身份（schema: references/schemas/creative-dna.schema.json）
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import SKILL_DIR, dump_json, load_state, ok, project_dir, warn  # noqa: E402

DATA = SKILL_DIR / "assets" / "data"
FP_KEYS = ["spatial", "time", "info", "resource", "risk"]

# 动词 → 品类亲和（用于给 idea 做初步匹配；不是硬分类）
VERB_GENRE = {
    "tap_timing": ["whack", "arcade"],
    "drag_place": ["tower_defense", "management"],
    "paint_area": ["puzzle", "tower_defense"],
    "aim_light": ["tower_defense", "survival", "stealth"],
    "listen_locate": ["puzzle", "rhythm", "survival"],
    "merge_combine": ["merge"],
    "cut_split": ["puzzle", "physics"],
    "push_pull": ["puzzle"],
    "stack_balance": ["physics", "arcade"],
    "swap_switch": ["puzzle", "match3"],
    "path_route": ["puzzle", "runner"],
    "sacrifice_resource": ["tower_defense", "survival", "management"],
    "remember_recall": ["puzzle", "card"],
    "build_grow": ["management", "tower_defense", "idle"],
    "lure_bait": ["stealth", "survival"],
    "disguise_hide": ["stealth"],
    "conduct_chain": ["puzzle", "physics"],
    "rhythm_sync": ["rhythm"],
    "aim_precision": ["shooter"],
    "sweep_clear": ["arcade", "whack"],
    "trade_exchange": ["management", "card"],
    "time_rewind": ["puzzle", "physics"],
    "signal_transmit": ["stealth", "puzzle"],
    "survive_hold": ["survival", "tower_defense"],
}

# 品类 → 中文名（与 content_forge.GENRE_INFO 对齐，但不 import 它，避免耦合）
GENRE_ZH = {
    "whack": "敲击/反应", "arcade": "街机刷分", "tower_defense": "塔防/防守", "merge": "合成",
    "puzzle": "解谜", "runner": "跑酷", "card": "卡牌构筑", "management": "经营",
    "rhythm": "节奏", "shooter": "射击", "survival": "生存", "idle": "放置",
    "physics": "物理", "stealth": "潜行", "match3": "消除",
}

# 情绪词 → 建议的视觉/音频气质
EMOTION_TONE = {
    "孤独": ("melancholy", "candle_warm", "felt_piano"),
    "紧张": ("tense", "single_side", "sub_pulse"),
    "好奇": ("mystery", "backlit", "glass_bell"),
    "温柔": ("warm", "flat_even", "music_box"),
    "荒诞": ("funny", "top_down", "paper_rustle"),
    "敬畏": ("epic", "volumetric", "bowed_strings"),
    "不安": ("uneasy", "single_side", "wood_creak"),
    "释然": ("calm", "flat_even", "sea_waves"),
}

DIFFICULTY_SCORE = {
    "spatial": {"none": 0, "lane": 1, "grid": 2, "radial": 2, "free": 3},
    "time": {"turn": 1, "rhythm": 3, "realtime": 3},
    "info": {"full": 0, "partial": 2, "hidden": 3},
    "resource": {"renewable": 0, "converted": 2, "finite": 2},
    "risk": {"reversible": 0, "irreversible": 2},
}

SENSE_WORDS = ["看见", "听到", "听见", "触摸", "感到", "闻到", "光", "声音", "震动",
               "暗", "亮", "冷", "热", "心跳", "呼吸", "安静", "响", "影子", "味道"]

NUMERIC_MARKERS = ["更快", "更多", "更强", "更高", "加量", "倍率", "加血", "加攻", "提速"]
NEGATIONS = ["不是", "而非", "不再", "禁止", "不能", "避免", "不靠", "别用", "拒绝"]
# 出现任一「质变」词，说明推进方式不是纯数值 —— 允许句中夹带「更快」这类修饰
QUALITATIVE = ["质变", "改写", "失去", "变少", "减少", "代价", "不可信", "反转", "换成",
               "消失", "被夺", "退化", "变质", "变慢", "变难", "变陌生"]


def numeric_only(text: str) -> list[str]:
    """返回**真正在宣称数值加强**的片段。

    「推进不是变快，而是……」这类否定句不算 —— 它恰恰是在反对数值推进。
    做法：按标点切句，含否定词的句子整句跳过。
    """
    if not text:
        return []
    import re
    clauses = re.split(r"[，。；、,.;：:（）()\n]", text)
    hits = []
    for cl in clauses:
        if any(n in cl for n in NEGATIONS):
            continue
        if any(w in cl for w in NUMERIC_MARKERS):
            hits.append(cl.strip())
    return [h for h in hits if h]


def load_json(p: Path, default=None):
    if not p.exists():
        warn(f"缺少数据文件：{p}")
        return default
    with p.open("r", encoding="utf-8") as f:
        return json.load(f)


def load_libs() -> dict:
    return {
        "verbs": load_json(DATA / "creative-patterns" / "interaction-verbs.json", {}).get("verbs", []),
        "twists": load_json(DATA / "creative-patterns" / "twist-dimensions.json", {}).get("dimensions", []),
        "archetypes": load_json(DATA / "gameplay-patterns" / "archetypes.json", {}).get("archetypes", []),
        "styles": load_json(DATA / "visual-styles" / "styles.json", {}).get("styles", []),
        "blend_axes": load_json(DATA / "visual-styles" / "styles.json", {}).get("blend_axes", {}),
        "audio": load_json(DATA / "audio-styles" / "palettes.json", {}),
        "curves": load_json(DATA / "emotional-patterns" / "curves.json", {}),
        "character": load_json(DATA / "creative-patterns" / "character-patterns.json", {}),
    }


def stable_seed(*parts) -> int:
    """确定性种子：同一 idea 永远得到同一组方案（可复现是测试的前提）。"""
    h = hashlib.sha256("|".join(str(p) for p in parts).encode("utf-8")).hexdigest()
    return int(h[:8], 16)


# ------------------------------------------------------------------ 结构距离
def fp_of(verb: dict) -> dict:
    return dict(verb.get("fingerprint") or {})


def hamming(a: dict, b: dict) -> int:
    return sum(1 for k in FP_KEYS if (a or {}).get(k) != (b or {}).get(k))


def min_pairwise_distance(verbs: list[dict]) -> int:
    best = 99
    for i in range(len(verbs)):
        for j in range(i + 1, len(verbs)):
            best = min(best, hamming(fp_of(verbs[i]), fp_of(verbs[j])))
    return 0 if best == 99 else best


# ------------------------------------------------------------------ 匹配
def score_verb(verb: dict, idea: str, genre: str) -> int:
    s = 0
    if genre and genre in VERB_GENRE.get(verb["id"], []):
        s += 6
    for kw in (verb.get("zh") or ""):
        if kw in idea:
            s += 1
    if verb["id"].split("_")[0] in idea.lower():
        s += 4
    if verb["id"] in idea:
        s += 6
    return s


def pick_verbs(verbs: list[dict], idea: str, genre: str, n: int) -> list[dict]:
    """最远点采样：先取与 idea 最匹配的，再逐个取「与已选集合最小距离最大」的。

    这样能保证 5 个方向不是同一交互的 5 个皮肤。
    """
    if not verbs:
        return []
    scored = sorted(verbs, key=lambda v: (-score_verb(v, idea, genre), v["id"]))
    chosen = [scored[0]]
    pool = [v for v in scored[1:]]
    while len(chosen) < n and pool:
        def far(v):
            return min(hamming(fp_of(v), fp_of(c)) for c in chosen)
        pool.sort(key=lambda v: (-far(v), -score_verb(v, idea, genre), v["id"]))
        chosen.append(pool.pop(0))
    return chosen[:n]


def blend_style(styles: list[dict], seed: int, idx: int) -> dict:
    """混血视觉提案：取 2 个风格，按轴各取一半，产出一个不在库里的组合。

    任务书 §5.1 明确反对「固定模板选择器」，所以这里必须混合而不是选一个。
    """
    if not styles:
        return {}
    a = styles[(seed + idx * 3) % len(styles)]
    b = styles[(seed + idx * 3 + 5) % len(styles)]
    if a["id"] == b["id"]:
        b = styles[(idx + 1) % len(styles)]
    # 主轴取自 a，材质/光/纹理取自 b，形成真正的混血
    return {
        "id": f"blend_{a['id']}_{b['id']}",
        "zh": f"{a['zh']} × {b['zh']}",
        "primary_style": a["id"],
        "secondary_style": b["id"],
        "axes": {
            "shape": a.get("shape"),
            "material": b.get("material"),
            "light": b.get("light"),
            "texture": b.get("texture"),
            "edge": a.get("edge"),
        },
        "tokens": f"{a.get('tokens', '')}, {b.get('material', '')} materials, {b.get('light', '')} lighting",
        "negative": ", ".join(x for x in [a.get("negative", ""), b.get("negative", "")] if x),
        "risks": list(dict.fromkeys((a.get("risks") or []) + (b.get("risks") or []))),
        "why_this_blend": f"用{a['zh']}的轮廓与收边保持可读性，用{b['zh']}的材质与光照制造记忆点",
    }


def difficulty_of(fp: dict) -> tuple[str, int]:
    score = sum(DIFFICULTY_SCORE[k].get((fp or {}).get(k, ""), 1) for k in FP_KEYS)
    if score <= 4:
        return "低", score
    if score <= 8:
        return "中", score
    return "高", score


# ------------------------------------------------------------------ diverge
def cmd_diverge(args) -> int:
    proj = project_dir(args.project)
    libs = load_libs()
    idea = args.idea or (load_state(proj).get("project") or {}).get("idea") or ""
    if not idea:
        print("ERROR: 需要 --idea（或项目 state.yaml 里已有 idea）", file=sys.stderr)
        return 1
    genre = args.genre or (load_state(proj).get("project") or {}).get("genre") or ""
    n = max(3, min(6, args.n))

    verbs = pick_verbs(libs["verbs"], idea, genre, n)
    if len(verbs) < n:
        warn(f"动词库只选出 {len(verbs)} 个（需要 {n}）")
    seed = stable_seed(idea, genre)
    twists = libs["twists"]
    emotions = list(EMOTION_TONE.keys())
    audio_moods = libs["audio"].get("mood_map", {})
    instruments = libs["audio"].get("instrument_families", [])

    # 反转维度必须互不重复：取一个与库长互质的步长（9 维时用 4 → 0,4,8,3,7）
    stride = 1
    if twists:
        for cand in (4, 3, 2, 5, 7):
            if len(twists) % cand != 0:
                stride = cand
                break
    concepts = []
    for i, verb in enumerate(verbs):
        fp = fp_of(verb)
        diff_label, diff_score = difficulty_of(fp)
        # 每个方案换一个反转维度：这是「结构性差异」的第二重保证
        tw = twists[(seed + i * stride) % len(twists)] if twists else {}
        emo = emotions[(seed + i) % len(emotions)]
        tone, light, inst = EMOTION_TONE[emo]
        style = blend_style(libs["styles"], seed, i)
        mood = "exploration" if i % 2 == 0 else "danger"
        mood_cfg = audio_moods.get(mood) or {}
        cid = f"C{i + 1}"

        concepts.append({
            "id": cid,
            "game_title": "",                 # Agent 填（≤40 字，必须含一个具体名词）
            "genre": [GENRE_ZH.get(genre, genre or "待定")],
            "one_liner": "",
            "core_fantasy": "",
            "core_gameplay": f"{verb['zh']} + {tw.get('zh', '待定反转')}：{tw.get('rewrite', '')}",
            "unique_mechanic": {
                "id": f"{verb['id']}_{tw.get('mechanic_hint', 'twist')}",
                "name": f"{verb['zh']}·{tw.get('zh', '')}",
                "one_sentence": "",
                "why_unique": "",
                "non_numeric": True,
                "interacts": [],
                "changes_decision": "",
                "signature_moment": "",
            },
            "player_decisions": [],
            "world": "",
            "main_emotion": emo,
            "signature_scene": "",
            "visual_style": style,
            "audio_style": {
                "mood": mood,
                "identity": "",
                "instrumentation": [inst],
                "bpm": mood_cfg.get("bpm"),
                "mode": mood_cfg.get("mode"),
            },
            "platforms": ["crazygames"],
            "difficulty": {"label": diff_label, "score": diff_score},
            "innovation": f"{tw.get('zh', '')}：{tw.get('cost', '')}",
            "structure": fp,
            "twist_dimension": tw.get("id", ""),
            "twist_cost": tw.get("cost", ""),
            "tone": tone,
            "lighting_hint": light,
            "_todo": "必填：game_title / one_liner / core_fantasy / unique_mechanic 的 one_sentence+why_unique+changes_decision+signature_moment / player_decisions(≥2) / world / signature_scene / audio_style.identity",
        })

    if len(concepts) >= 2:
        md = min_pairwise_distance(verbs)
        distinct = md >= 3
    else:
        md, distinct = 0, False

    out = {
        "version": "3.0",
        "idea": idea,
        "genre_hint": genre,
        "seed": seed,
        "created": datetime.now().astimezone().isoformat(timespec="seconds"),
        "n": len(concepts),
        "structural_distance": {"min_pairwise": md, "required": 3, "pass": distinct},
        "concepts": concepts,
        "how_to_choose": "先看 structural_distance 是否 pass；再看 --evaluate 的相似度；最后由人（G1）拍板",
    }
    path = proj / "docs" / "01-brief" / "creative-concepts.json"
    dump_json(path, out)

    print(f"创意发散：{len(concepts)} 个方向（seed={seed}）")
    print(f"结构差异：最小两两距离 {md}/5（要求 ≥3）→ {'通过' if distinct else '不通过，需换动词'}")
    print()
    print("| id | 交互动词 | 结构指纹 | 反转维度 | 主情绪 | 难度 | 视觉混血 |")
    print("|---|---|---|---|---|---|---|")
    for c in concepts:
        fp = c["structure"]
        fptxt = f"{fp.get('spatial')}/{fp.get('time')}/{fp.get('info')}"
        print(f"| {c['id']} | {c['unique_mechanic']['name']} | {fptxt} | "
              f"{c['twist_dimension']} | {c['main_emotion']} | {c['difficulty']['label']} | "
              f"{c['visual_style'].get('zh', '-')} |")
    print()
    print(f"已写：{path.relative_to(proj)}")
    print("下一步：逐条填 _todo → 再跑 --evaluate")
    if not distinct:
        return 2
    return 0


# ------------------------------------------------------------------ twist
def cmd_twist(args) -> int:
    proj = project_dir(args.project)
    path = proj / "docs" / "01-brief" / "creative-concepts.json"
    if not path.exists():
        print("ERROR: 缺 creative-concepts.json（先跑 --diverge）", file=sys.stderr)
        return 1
    data = json.loads(path.read_text(encoding="utf-8"))
    libs = load_libs()
    target = None
    if args.concept:
        target = next((c for c in data["concepts"] if c["id"] == args.concept), None)
        if not target:
            print(f"ERROR: 找不到 {args.concept}", file=sys.stderr)
            return 1
        targets = [target]
    else:
        targets = data["concepts"]

    dims = libs["twists"]
    if args.dim:
        dims = [d for d in dims if d["id"] == args.dim]
        if not dims:
            print(f"ERROR: 未知反转维度 {args.dim}", file=sys.stderr)
            return 1

    print("创意反转候选（每个维度都必须付出代价，不能白拿）：\n")
    for c in targets:
        print(f"### {c['id']} {c.get('game_title') or '（未命名）'}　当前反转：{c.get('twist_dimension')}")
        for d in dims:
            print(f"- **{d['zh']}**（`{d['id']}`）")
            print(f"    假设：{d['assumption']}")
            print(f"    改写：{d['rewrite']}")
            print(f"    代价：{d['cost']}")
        print()
    print("选定后把 twist_dimension / twist_cost 写回 creative-concepts.json，再跑 --evaluate")
    return 0


# ------------------------------------------------------------------ 相似度
def similarity(concept: dict, arch: dict) -> tuple[float, list[str]]:
    """启发式结构相似度。0–1，越高越像换皮。"""
    fp = concept.get("structure") or {}
    afp = arch.get("fingerprint") or {}
    hits = [k for k in FP_KEYS if fp.get(k) == afp.get(k)]
    base = len(hits) / len(FP_KEYS) * 0.6
    extra_keys = ["win", "fail", "progression"]
    extra_hits = [k for k in extra_keys if fp.get(k) == afp.get(k)]
    # concept 的 structure 只含 5 维时，额外维度按「未知」处理，不给分也不扣分
    extra = len(extra_hits) / len(extra_keys) * 0.25 if any(k in fp for k in extra_keys) else 0.0

    # 机制名 / 一句话里的关键词与原型 signature 的重合
    text = " ".join([
        str((concept.get("unique_mechanic") or {}).get("name", "")),
        str((concept.get("unique_mechanic") or {}).get("one_sentence", "")),
        str(concept.get("core_gameplay", "")),
    ])
    sig_hit = sum(1 for s in arch.get("signature", []) if s and s in text)
    sig = min(0.15, sig_hit * 0.05)
    return round(min(1.0, base + extra + sig), 3), hits


def reskin_verdict(sim: float) -> str:
    if sim >= 0.85:
        return "HIGH"      # 换皮风险高，必须重设计核心机制
    if sim >= 0.7:
        return "MEDIUM"    # 需要一条结构性差异
    return "LOW"


# ------------------------------------------------------------------ evaluate
def evaluate_concept(c: dict, libs: dict) -> dict:
    items = []

    def add(code, dim, got, max_, note, fix=""):
        items.append({"code": code, "dim": dim, "got": round(float(got), 2),
                      "max": max_, "note": note, "fix": fix})

    # --- 1 新颖度 20：来自相似度（1-max_sim）+ 反转维度使用
    sims = []
    for a in libs["archetypes"]:
        s, hits = similarity(c, a)
        sims.append((s, a, hits))
    sims.sort(key=lambda x: -x[0])
    top_s, top_a, top_hits = sims[0] if sims else (0.0, {"id": "-", "zh": "-"}, [])
    verdict = reskin_verdict(top_s)
    novelty_got = round((1 - top_s) * 16, 2)
    if c.get("twist_dimension"):
        novelty_got += 4
    add("C1", "novelty", min(20, novelty_got), 20,
        f"最相似原型 `{top_a['id']}`（{top_a['zh']}）结构重合 {top_s:.2f} → 换皮风险 {verdict}；"
        f"重合维度 {','.join(top_hits) or '无'}；反转维度 {c.get('twist_dimension') or '未设'}",
        (f"与 {top_a['zh']} 重合度过高，按「{top_a.get('how_to_differentiate', '换一条结构维度')}」重设计核心机制"
         if verdict != "LOW"
         else "已低于换皮阈值，不必改动；若想再拉开差距，可换一条结构维度（信息可见度或失败代价）"))

    # --- 2 核心机制独特性 20：6 条硬条件
    m = c.get("unique_mechanic") or {}
    conds = {
        "一句话可解释": 8 <= len((m.get("one_sentence") or "").strip()) <= 80,
        "非数值变化": bool(m.get("non_numeric")),
        "与≥2机制互动": len(m.get("interacts") or []) >= 2,
        "改变策略选择": len((m.get("changes_decision") or "").strip()) >= 12,
        "能形成标志时刻": len((m.get("signature_moment") or "").strip()) >= 16,
        "有独特性论证": len((m.get("why_unique") or "").strip()) >= 12,
    }
    got = 20 * sum(conds.values()) / len(conds)
    add("C2", "uniqueness", got, 20,
        "6 条条件达成 " + f"{sum(conds.values())}/6：" +
        "、".join(k for k, v in conds.items() if v) +
        ("；缺：" + "、".join(k for k, v in conds.items() if not v) if not all(conds.values()) else ""),
        "逐条补齐 unique_mechanic 的缺失条件（一句话/非数值/互动/策略/时刻/论证）" if got < 20 else "")

    # --- 3 可理解性 15：动词在库 + 决策数 + 品类明确
    dec = c.get("player_decisions") or []
    verb_known = any(v["id"] in (m.get("id") or "") for v in libs["verbs"])
    parts = [verb_known, 2 <= len(dec) <= 4, bool(c.get("genre")), bool(c.get("one_liner"))]
    got = 15 * sum(parts) / 4
    add("C3", "comprehensible", got, 15,
        f"动词可识别={verb_known}；决策 {len(dec)} 个（2–4 为佳）；品类={'有' if c.get('genre') else '无'}；"
        f"一句话={'有' if c.get('one_liner') else '无'}",
        "补 one_liner（玩家看完就知道要做什么）并把决策收敛到 2–4 个" if got < 15 else "")

    # --- 4 互动深度 15：机制图边数 + 是否有环
    ids = {m.get("id")} | {x.get("id") for x in (c.get("supporting_mechanics") or [])}
    ids.discard(None)
    edges = len([r for r in (m.get("interacts") or []) if r in ids and r != m.get("id")])
    for s in c.get("supporting_mechanics") or []:
        edges += len([r for r in (s.get("interacts") or []) if r in ids and r != s.get("id")])
    has_cycle = edges >= len(ids)  # 边数 ≥ 节点数 → 必然有环（简单判据）
    got = min(15, edges * 3.5) + (2 if has_cycle else 0)
    add("C4", "interaction_depth", min(15, got), 15,
        f"机制节点 {len(ids)} 个，引用边 {edges} 条，{'存在' if has_cycle else '不存在'}环（互相增强）",
        "至少补 3 条互动边，并让两个机制互相增强（形成环）" if got < 15 else "")

    # --- 5 玩法与叙事一致性 10：主题词是否出现在机制/决策里
    theme = ""
    world = c.get("world") or ""
    theme_words = [w for w in ("记忆", "遗忘", "守护", "代价", "孤独", "光", "声音", "失去", "留下", "真相")
                   if w in world]
    body = json.dumps({"m": m, "d": dec}, ensure_ascii=False)
    linked = [w for w in theme_words if w in body]
    got = (10 * len(linked) / len(theme_words)) if theme_words else (5 if body.strip("{}") else 0)
    add("C5", "narrative_link", got, 10,
        f"世界观关键词 {theme_words or '无'}，其中 {linked or '无'} 出现在机制/决策描述里",
        "把世界观里的核心词写进机制命名与决策代价（否则叙事只是贴皮）" if got < 10 else "")

    # --- 6 可实现性 10
    diff = (c.get("difficulty") or {}).get("score", 99)
    n_mech = 1 + len(c.get("supporting_mechanics") or [])
    parts = [diff <= 9, n_mech <= 6, bool(c.get("platforms")), bool(c.get("visual_style"))]
    got = 10 * sum(parts) / 4
    add("C6", "feasibility", got, 10,
        f"结构复杂度 {diff}/13；机制 {n_mech} 个（≤6）；平台 {len(c.get('platforms') or [])} 个；"
        f"视觉提案={'有' if c.get('visual_style') else '无'}",
        "降低结构复杂度（去掉 free 空间或 hidden 信息）或减少机制数" if got < 10 else "")

    # --- 7 记忆点 10：signature_scene 的感官密度
    scene = c.get("signature_scene") or ""
    senses = [w for w in SENSE_WORDS if w in scene]
    got = 0.0
    if len(scene) >= 20:
        got = 4.0 + min(6.0, len(senses) * 1.5)
    add("C7", "memorability", min(10, got), 10,
        f"标志场景 {len(scene)} 字，感官词 {len(senses)} 个：{','.join(senses) or '无'}",
        "signature_scene 要写清「发生条件 + 玩家动作 + 至少两种感官反馈」" if got < 10 else "")

    total = round(sum(i["got"] for i in items), 2)
    dims = {}
    for i in items:
        dims[i["dim"]] = round(dims.get(i["dim"], 0) + i["got"], 2)
    return {
        "concept_id": c["id"],
        "title": c.get("game_title") or "",
        "total": total,
        "dims": dims,
        "items": items,
        "similarity": {
            "top_archetype": top_a["id"],
            "top_archetype_zh": top_a["zh"],
            "score": top_s,
            "matched_dims": top_hits,
            "reskin_risk": verdict,
            "top3": [{"archetype": a["id"], "zh": a["zh"], "score": s} for s, a, _h in sims[:3]],
        },
        "verdict": "ACCEPT" if total >= 70 and verdict != "HIGH" else ("REVISE" if total >= 55 else "REJECT"),
        "fixes": [i for i in sorted(items, key=lambda x: x["got"] - x["max"])
                  if i["got"] < i["max"] and (i.get("fix") or "").strip()][:4],
    }


def cmd_evaluate(args) -> int:
    proj = project_dir(args.project)
    path = proj / "docs" / "01-brief" / "creative-concepts.json"
    if not path.exists():
        print("ERROR: 缺 creative-concepts.json（先跑 --diverge）", file=sys.stderr)
        return 1
    data = json.loads(path.read_text(encoding="utf-8"))
    libs = load_libs()
    results = [evaluate_concept(c, libs) for c in data["concepts"]]
    results.sort(key=lambda r: -r["total"])
    data["evaluation"] = results
    data["evaluated_at"] = datetime.now().astimezone().isoformat(timespec="seconds")
    data["best"] = results[0]["concept_id"] if results else ""
    dump_json(path, data)

    print(f"创意评估：{len(results)} 个方向\n")
    print("| id | 名称 | 总分 | 新颖 | 独特 | 理解 | 深度 | 叙事 | 可行 | 记忆 | 相似原型 | 风险 | 结论 |")
    print("|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    for r in results:
        d = r["dims"]
        print(f"| {r['concept_id']} | {r['title'] or '（未命名）'} | **{r['total']:.1f}** | "
              f"{d.get('novelty', 0):.1f} | {d.get('uniqueness', 0):.1f} | {d.get('comprehensible', 0):.1f} | "
              f"{d.get('interaction_depth', 0):.1f} | {d.get('narrative_link', 0):.1f} | "
              f"{d.get('feasibility', 0):.1f} | {d.get('memorability', 0):.1f} | "
              f"{r['similarity']['top_archetype_zh']} {r['similarity']['score']:.2f} | "
              f"{r['similarity']['reskin_risk']} | {r['verdict']} |")
    print()
    for r in results[:3]:
        if r["fixes"]:
            print(f"{r['concept_id']} 最小改动：")
            for f in r["fixes"]:
                print(f"  - [{f['code']}] {f['fix']}（当前 {f['got']:.1f}/{f['max']}）")
    write_review_md(proj, data, results)
    print()
    print("注意：新颖度是**启发式相似度分析**，不是原创性证明。它只能告诉你「像哪个原型」。")
    print(f"已写：docs/01-brief/creative-review.md　最佳候选：{data['best']}")
    return 0


def write_review_md(proj: Path, data: dict, results: list[dict]) -> None:
    L = [
        "# 创意评审报告（Creative Review）",
        "",
        f"> 想法：{data['idea']}　seed：{data['seed']}",
        f"> 判据：`references/creative-identity.md`　方案数：{data['n']}",
        f"> 结构差异：最小两两距离 {data['structural_distance']['min_pairwise']}/5"
        f"（要求 ≥3，{'通过' if data['structural_distance']['pass'] else '不通过'}）",
        "",
        "## 方法说明",
        "",
        "本报告的新颖度**不是**原创性证明，而是启发式相似度分析：把方案的结构指纹",
        "（spatial / time / info / resource / risk）与 16 个公开玩法原型比对，",
        "重合度越高说明越可能只是换皮。结论只说明「像哪个原型、哪里需要改」。",
        "",
        "## 排名",
        "",
        "| 排名 | id | 名称 | 总分 | 换皮风险 | 最相似原型 | 结论 |",
        "|---|---|---|---|---|---|---|",
    ]
    for i, r in enumerate(results, 1):
        L.append(f"| {i} | {r['concept_id']} | {r['title'] or '（未命名）'} | {r['total']:.1f} | "
                 f"{r['similarity']['reskin_risk']} | {r['similarity']['top_archetype_zh']}"
                 f"（{r['similarity']['score']:.2f}） | {r['verdict']} |")
    L += ["", "## 逐方案明细", ""]
    for r in results:
        L += [f"### {r['concept_id']} {r['title'] or '（未命名）'}　{r['total']:.1f}/100　{r['verdict']}", "",
              "| 项 | 得分 | 满分 | 证据 |", "|---|---|---|---|"]
        for it in r["items"]:
            L.append(f"| {it['code']} {it['dim']} | {it['got']:.1f} | {it['max']} | {it['note']} |")
        if r["similarity"]["top3"]:
            L += ["", "相似原型 Top3：" + "；".join(
                f"{x['zh']} {x['score']:.2f}" for x in r["similarity"]["top3"]), ""]
        if r["fixes"]:
            L += ["最小改动：", ""]
            for f in r["fixes"]:
                L.append(f"- **{f['code']}** {f['fix']}")
            L.append("")
    L += ["---", "",
          "选定方向后：`python scripts/creative_forge.py --project . --dna --pick C1`",
          "然后由人确认（门禁 G1）。**不得跳过人工确认直接进入 P1。**", ""]
    (proj / "docs" / "01-brief" / "creative-review.md").write_text("\n".join(L), encoding="utf-8")


# ------------------------------------------------------------------ dna
def cmd_dna(args) -> int:
    proj = project_dir(args.project)
    path = proj / "docs" / "01-brief" / "creative-concepts.json"
    if not path.exists():
        print("ERROR: 缺 creative-concepts.json（先跑 --diverge）", file=sys.stderr)
        return 1
    data = json.loads(path.read_text(encoding="utf-8"))
    pick = args.pick or data.get("best")
    c = next((x for x in data["concepts"] if x["id"] == pick), None)
    if not c:
        print(f"ERROR: 找不到方案 {pick}", file=sys.stderr)
        return 1
    if args.force is False and (proj / "docs/01-brief/creative-dna.json").exists():
        warn("creative-dna.json 已存在，未覆盖（--force 重写）")
        return 0

    libs = load_libs()
    m = c.get("unique_mechanic") or {}
    vs = c.get("visual_style") or {}
    aud = c.get("audio_style") or {}
    ev = next((r for r in (data.get("evaluation") or []) if r["concept_id"] == pick), {})

    dna = {
        "version": "3.0",
        "meta": {
            "idea": data["idea"],
            "concept_id": pick,
            "created": datetime.now().astimezone().isoformat(timespec="seconds"),
            "judged_by": "references/creative-identity.md",
            "creative_score": ev.get("total"),
            "novelty_note": (f"启发式相似度：与 `{ev['similarity']['top_archetype']}` 重合 "
                             f"{ev['similarity']['score']:.2f}（风险 {ev['similarity']['reskin_risk']}）"
                             if ev else ""),
            "seed": data["seed"],
        },
        "identity": {
            "game_title": c.get("game_title") or "",
            "core_fantasy": c.get("core_fantasy") or "",
            "unique_hook": (m.get("one_sentence") or ""),
            "creative_promise": "",
            "signature_moment": m.get("signature_moment") or c.get("signature_scene") or "",
            "one_line_pitch": c.get("one_liner") or "",
        },
        "gameplay": {
            "genre": c.get("genre") or [],
            "core_verb": (m.get("id") or "").split("_")[0] if m.get("id") else "",
            "core_mechanic": {
                "id": m.get("id") or "",
                "name": m.get("name") or "",
                "one_sentence": m.get("one_sentence") or "",
                "why_unique": m.get("why_unique") or "",
                "non_numeric": True,
                "interacts": m.get("interacts") or [],
                "changes_decision": m.get("changes_decision") or "",
                "signature_moment": m.get("signature_moment") or "",
            },
            "supporting_mechanics": c.get("supporting_mechanics") or [],
            "player_decisions": c.get("player_decisions") or [],
            "progression_identity": "",
            "fail_state": "",
            "win_condition": "",
        },
        "narrative": {
            "world_rules": [],
            "theme": "",
            "emotional_arc": [
                {"beat": p["phase"], "emotion": p["zh"], "intensity": p["intensity"]}
                for p in (libs["curves"].get("base_curve") or [])
            ],
            "story_frame": "",
            "narrative_mechanic_link": "",
        },
        "visual": {
            "style_identity": f"{vs.get('zh', '')}（{vs.get('why_this_blend', '')}）" if vs else "",
            "visual_keywords": [],
            "palette": {"primary": [], "accent": [], "danger": "#000000"},
            "materials": [vs.get("axes", {}).get("material")] if vs else [],
            "lighting": (vs.get("axes", {}).get("light") or c.get("lighting_hint") or ""),
            "camera": "",
            "shape_language": (vs.get("axes", {}).get("shape") or ""),
            "texture_rules": [vs.get("axes", {}).get("texture")] if vs else [],
            "shadow_rules": "",
            "depth_of_field": "",
            "ui_language": "",
            "typography": "",
            "character_ratio": "",
            "animation_style": "",
            "fx_style": "",
        },
        "audio": {
            "audio_identity": aud.get("identity") or "",
            "music_mood": [aud.get("mood")] if aud.get("mood") else [],
            "instrumentation": aud.get("instrumentation") or [],
            "sound_signature": [],
            "dynamic_audio_rules": [],
            "sound_as_gameplay": {"enabled": False, "mechanic": "", "why": ""},
        },
        "experience": {
            "target_emotions": [{"emotion": c.get("main_emotion") or "", "weight": 0.6}],
            "pacing": [{"phase": p["phase"], "intensity": p["intensity"]}
                       for p in (libs["curves"].get("base_curve") or [])],
            "player_memory": "",
            "first_10s": "",
            "first_30s": "",
        },
        "references": [],
        "_todo": [
            "identity.creative_promise（≥16 字，写玩家会体验到什么别处没有的东西）",
            "gameplay.progression_identity（禁止「更快/更多」，必须质变）",
            "gameplay.fail_state / win_condition",
            "narrative.world_rules（≥3 条约束句式）/ theme / narrative_mechanic_link",
            "visual.palette（primary ≥3 / accent ≥1 / danger）/ visual_keywords（≥5）/ camera / shadow_rules / ui_language / typography / character_ratio / animation_style / fx_style",
            "audio.sound_signature（≥2）/ dynamic_audio_rules（≥2）",
            "experience.player_memory / first_10s / first_30s",
        ],
    }
    out = proj / "docs" / "01-brief" / "creative-dna.json"
    dump_json(out, dna)
    ok(f"已生成 Creative DNA：{out.relative_to(proj)}（方案 {pick}）")
    print("\n这是骨架。逐项填完后跑：")
    print("  python scripts/schema_check.py --data docs/01-brief/creative-dna.json \\")
    print("         --schema references/schemas/creative-dna.schema.json")
    print("  python scripts/creative_forge.py --project . --validate")
    return 0


# ------------------------------------------------------------------ validate
def cmd_validate(args) -> int:
    proj = project_dir(args.project)
    dna_path = proj / "docs" / "01-brief" / "creative-dna.json"
    if not dna_path.exists():
        print("ERROR: 缺 creative-dna.json（先跑 --dna）", file=sys.stderr)
        return 1
    dna = json.loads(dna_path.read_text(encoding="utf-8"))
    issues: list[tuple[str, str, str]] = []

    def err(p, m):
        issues.append(("ERROR", p, m))

    def wrn(p, m):
        issues.append(("WARN", p, m))

    # 1 schema
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import schema_check  # noqa: E402
    schema_path = SKILL_DIR / "references" / "schemas" / "creative-dna.schema.json"
    for e in schema_check.validate(dna, json.loads(schema_path.read_text(encoding="utf-8"))):
        err("schema", e)

    # 2 语义：独特机制必须真独特
    gm = dna.get("gameplay") or {}
    cm = gm.get("core_mechanic") or {}
    libs = load_libs()
    lib_names = {v["zh"] for v in libs["verbs"]}
    if cm.get("name") in lib_names:
        wrn("gameplay.core_mechanic.name", f"`{cm.get('name')}` 与动词库条目同名，说明还没做反转")
    txt = (cm.get("one_sentence") or "") + "。" + (cm.get("why_unique") or "")
    bad = numeric_only(txt)
    if bad:
        err("gameplay.core_mechanic", f"独特机制的描述里出现数值加强词（{bad[0]}）—— 只改数值的机制不算独特机制")

    # 3 机制咬合
    ids = {cm.get("id")} | {x.get("id") for x in (gm.get("supporting_mechanics") or [])}
    ids.discard(None)
    for ref in cm.get("interacts") or []:
        if ref not in ids:
            err("gameplay.core_mechanic.interacts", f"引用了不存在的机制 `{ref}`")

    # 4 推进身份不能是数值
    prog = gm.get("progression_identity") or ""
    bad = numeric_only(prog)
    # 只要整体表达了「质变」，句中夹带的「更快」只是修饰，不算违规
    qualitative = any(w in prog for w in QUALITATIVE)
    if bad and not qualitative:
        err("gameplay.progression_identity",
            f"推进方式只写了数值加强（{bad[0]}）—— 任务书 §4 要求质变，请写成「X 被改写/失去/变陌生」")

    # 5 叙事必须影响规则
    nar = dna.get("narrative") or {}
    if not (nar.get("narrative_mechanic_link") or "").strip():
        err("narrative.narrative_mechanic_link", "必填：哪条世界规则被写进了机制（否则叙事是贴皮）")

    # 6 视觉身份必须是混血而不是单一流派名
    vis = dna.get("visual") or {}
    si = vis.get("style_identity") or ""
    if si and "×" not in si and "x" not in si and "+" not in si:
        wrn("visual.style_identity", "视觉身份只写了一个流派 —— 建议写成混血（A × B），否则容易撞脸")

    # 7 音频必须有动态规则
    aud = dna.get("audio") or {}
    if len(aud.get("dynamic_audio_rules") or []) < 2:
        err("audio.dynamic_audio_rules", "需要 ≥2 条状态驱动规则（何时变、怎么变）")

    # 8 引用必须带来源与许可
    for i, r in enumerate(dna.get("references") or []):
        for k in ("pattern_id", "source", "license"):
            if not (r.get(k) or "").strip():
                err(f"references[{i}].{k}", "引用模式必须记录来源与许可（任务书 §12.5）")

    # 9 模式库自检
    for name in ("creative-patterns/interaction-verbs.json", "creative-patterns/twist-dimensions.json",
                 "gameplay-patterns/archetypes.json", "visual-styles/styles.json",
                 "audio-styles/palettes.json", "emotional-patterns/curves.json"):
        p = DATA / name
        if not p.exists():
            err("assets/data", f"缺少模式库 {name}")
            continue
        d = json.loads(p.read_text(encoding="utf-8"))
        for k in ("source", "license"):
            if not (d.get(k) or "").strip():
                err(f"assets/data/{name}", f"模式库缺 `{k}` 字段")

    errors = [i for i in issues if i[0] == "ERROR"]
    warns = [i for i in issues if i[0] == "WARN"]
    print(f"Creative DNA 校验：{dna_path.relative_to(proj)}")
    print(f"  ERROR {len(errors)}　WARN {len(warns)}　待填 _todo {len(dna.get('_todo') or [])}\n")
    for lvl, p, m in issues[:60]:
        print(f"[{lvl}] {p} —— {m}")
    dump_json(proj / "docs" / "01-brief" / "creative-validation.json", {
        "ok": not errors,
        "errors": [{"path": p, "msg": m} for _, p, m in errors],
        "warnings": [{"path": p, "msg": m} for _, p, m in warns],
    })
    if errors:
        print("\nERROR 必改。改完重跑本命令。", file=sys.stderr)
        return 2 if args.strict else 0
    ok("Creative DNA 通过校验")
    return 0


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass
    ap = argparse.ArgumentParser(description="创意总监：发散 / 反转 / 评估 / DNA")
    ap.add_argument("--project", default=None)
    ap.add_argument("--idea", default="")
    ap.add_argument("--genre", default="")
    ap.add_argument("--n", type=int, default=5, help="方案数（3–6）")
    ap.add_argument("--diverge", action="store_true")
    ap.add_argument("--twist", action="store_true")
    ap.add_argument("--concept", default="", help="--twist 的目标方案 id")
    ap.add_argument("--dim", default="", help="--twist 的维度 id")
    ap.add_argument("--evaluate", action="store_true")
    ap.add_argument("--dna", action="store_true")
    ap.add_argument("--pick", default="", help="--dna 选哪个方案（默认 best）")
    ap.add_argument("--validate", action="store_true")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--strict", action="store_true")
    args = ap.parse_args()

    if args.diverge:
        return cmd_diverge(args)
    if args.twist:
        return cmd_twist(args)
    if args.evaluate:
        return cmd_evaluate(args)
    if args.dna:
        return cmd_dna(args)
    if args.validate:
        return cmd_validate(args)
    ap.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
