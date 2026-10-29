#!/usr/bin/env python3
"""内容丰富度门禁（RC）：四维打分 + 与真实产物交叉校验。

判据唯一来源：references/content-depth.md。改判据先改那份文档。

用法:
    python richness_check.py --project .                 # 自动判断设计期/生产期
    python richness_check.py --project . --stage design  # 只查设计产物（不要求素材/音频已出）
    python richness_check.py --project . --stage build   # 全量（含 X1–X4 交叉校验）
    python richness_check.py --project . --quiet         # 只输出结论行

产物:
    docs/09-review/richness.json          机读结论（含逐条得分与证据）
    docs/09-review/richness-report.md     人读报告 + 最小改动清单

退出码: 0=RICH　2=THIN　3=INCOMPLETE
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import dump_json, load_state, ok, project_dir, save_state, warn  # noqa: E402

DIMS = [("gameplay", "玩法深度", 30), ("story", "叙事完整", 25),
        ("art", "美学体系", 25), ("audio", "音频设计", 20)]

NUMERIC_MARKERS = ["更快", "更多", "更高", "加量", "加速", "提速", "数值", "加血",
                   "加攻", "加防", "上限", "变快", "变多", "倍率"]
TRADEOFF_MARKERS = ["还是", "但", "换", "赌", "放弃", "牺牲", "代价", "风险",
                    "舍", "优先", "换来", "vs", "取舍", "保留"]
HIGH_CUES = {"victory", "defeat", "boss", "reveal", "levelup", "win", "lose"}
LAYERS = ["ui", "gameplay", "feedback", "ambience"]


def has(v, n: int = 1) -> bool:
    return isinstance(v, str) and len(v.strip()) >= n


def load_json(p: Path, default=None):
    if not p.exists():
        return default
    try:
        with p.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:  # noqa: BLE001
        warn(f"解析失败 {p}：{e}")
        return default


class Item:
    """一条评分项。"""

    def __init__(self, dim: str, code: str, got: float, max_: float, note: str, fix: str = ""):
        self.dim, self.code, self.got, self.max = dim, code, round(got, 2), max_
        self.note, self.fix = note, fix

    @property
    def lost(self) -> float:
        return round(self.max - self.got, 2)

    def as_dict(self) -> dict:
        return {"dim": self.dim, "code": self.code, "got": self.got,
                "max": self.max, "note": self.note, "fix": self.fix}


# ------------------------------------------------------------------ 读产物
def gather(proj: Path) -> dict:
    bp = load_json(proj / "docs" / "01-brief" / "content-blueprint.json")
    palette = load_json(proj / "docs" / "02-art" / "palette.json", {}) or {}
    art_bible = ""
    for cand in (proj / "docs" / "02-art" / "art-bible.md",):
        if cand.exists():
            art_bible = cand.read_text(encoding="utf-8", errors="ignore")
    spec = load_json(proj / "docs" / "02-art" / "asset-spec.json")
    sfx = load_json(proj / "docs" / "05-audio" / "sfx-plan.json")
    music = load_json(proj / "docs" / "05-audio" / "music-plan.json")
    voice = load_json(proj / "docs" / "05-audio" / "voice-plan.json")
    levels = load_json(proj / "src" / "game" / "levels.json")
    scope = load_json(proj / "docs" / "01-brief" / "scope.json", {}) or {}
    audio_dir = proj / "assets" / "audio"
    sfx_files = sorted(p.stem for p in (audio_dir / "sfx").glob("*.mp3")) if (audio_dir / "sfx").is_dir() else []
    bgm_files = sorted(p.stem for p in (audio_dir / "bgm").glob("*.mp3")) if (audio_dir / "bgm").is_dir() else []
    voice_files = sorted(p.name for p in (audio_dir / "voice").glob("*.mp3")) if (audio_dir / "voice").is_dir() else []
    # processed 与 live 都算「已处理素材」：大图（背景/主视觉）不进图集，单独放 live/
    processed: list[str] = []
    for sub in ("processed", "live"):
        d = proj / "assets" / sub
        if d.is_dir():
            processed += sorted(p.stem for p in d.glob("*.png"))
    return dict(blueprint=bp, palette=palette, art_bible=art_bible, spec=spec, sfx=sfx,
                music=music, voice=voice, levels=levels, scope=scope,
                sfx_files=sfx_files, bgm_files=bgm_files, voice_files=voice_files,
                processed=processed, proj=proj)


# ------------------------------------------------------------------ 玩法 30
def score_gameplay(g: dict, items: list[Item]) -> None:
    bp = g["blueprint"]
    if not bp:
        items.append(Item("gameplay", "M0", 0, 30,
                          "无 content-blueprint.json，玩法无法判定（只有关卡数值表不算设计）",
                          "跑 content_forge.py --scaffold 并填写机制/叙事/节奏"))
        return
    m = bp.get("mechanics") or {}
    mechs = list(m.get("core") or []) + list(m.get("twists") or [])
    n = len([x for x in mechs if has(x.get("id")) and not str(x["id"]).startswith("TODO")])

    # M1 机制数量（8）
    got = 8 if n >= 5 else max(0, 8 - 2 * (5 - n))
    items.append(Item("gameplay", "M1", got, 8, f"有效机制 {n} 个（需 ≥5）",
                      "从 mechanic-vocab.json 补足机制，优先选能互相咬合的" if got < 8 else ""))

    # M2 机制咬合（8）
    ids = {x.get("id") for x in mechs if has(x.get("id"))}
    linked, edges = 0, 0
    for x in mechs:
        refs = [r for r in (x.get("interacts") or []) if r in ids and r != x.get("id")]
        edges += len(refs)
        if refs:
            linked += 1
    if n == 0:
        got = 0.0
    elif linked == n and edges >= n - 1:
        got = 8.0
    else:
        orphans = n - linked
        got = max(0.0, 8.0 - 2.0 * orphans - (2.0 if edges < n - 1 else 0))
    items.append(Item("gameplay", "M2", got, 8,
                      f"{linked}/{n} 个机制有咬合引用，共 {edges} 条引用边（需全咬合且边数 ≥{max(0, n-1)}）",
                      "给孤立机制补 interacts，并确认同时存在时最优策略会变（乘法而非加法）" if got < 8 else ""))

    # M3 非数值难度轴（6）
    axes = m.get("progression_axis") or []
    non_numeric = []
    for a in axes:
        txt = a if isinstance(a, str) else json.dumps(a, ensure_ascii=False)
        if not any(k in txt for k in NUMERIC_MARKERS):
            non_numeric.append(txt)
    got = 6.0 if len(non_numeric) >= 2 else (3.0 if len(non_numeric) == 1 else 0.0)
    items.append(Item("gameplay", "M3", got, 6,
                      f"非数值难度轴 {len(non_numeric)} 条：{('; '.join(non_numeric[:3]) or '无')}",
                      "加至少 2 条非数值轴（信息可见度/资源充裕度/操作复杂度/环境稳定性/失败代价）" if got < 6 else ""))

    # M4 关卡决策点（8）
    lv = bp.get("levels") or []
    valid = 0
    for x in lv:
        d = (x.get("decision") or "").strip()
        if len(d) >= 8 and any(k in d for k in TRADEOFF_MARKERS):
            valid += 1
    ratio = valid / len(lv) if lv else 0
    got = 8.0 if ratio >= 0.9 else (5.0 if ratio >= 0.7 else (2.0 if ratio >= 0.5 else 0.0))
    items.append(Item("gameplay", "M4", got, 8,
                      f"{valid}/{len(lv)} 关有合格取舍（需写成「A好但B坏」）",
                      "给每关补 decision，必须包含取舍标记词（还是/但/放弃/代价…）" if got < 8 else ""))


# ------------------------------------------------------------------ 叙事 25
def score_story(g: dict, items: list[Item]) -> None:
    bp = g["blueprint"]
    if not bp:
        items.append(Item("story", "S0", 0, 25, "无蓝图，叙事维度无产物可判", "见 M0 修法"))
        return
    w = bp.get("world") or {}
    s = bp.get("story") or {}

    # S1 世界观（5）
    parts = [has(w.get("logline"), 16), has(w.get("setting")), has(w.get("theme"), 4),
             len(w.get("rules") or []) >= 3]
    got = 5.0 * sum(parts) / 4
    items.append(Item("story", "S1", got, 5,
                      f"logline/setting/theme/规则≥3 → {sum(parts)}/4 达成",
                      "补全世界观四件套；规则必须是约束句式「这个世界的X不能Y」" if got < 5 else ""))

    # S2 主角弧光（5）
    p = s.get("protagonist") or {}
    filled = sum(1 for k in ("want", "need", "flaw", "arc") if has(p.get(k)))
    got = 5.0 * filled / 4
    if filled == 4 and (p.get("want") or "").strip() == (p.get("need") or "").strip():
        got *= 0.6
        items.append(Item("story", "S2x", 0, 0, "want 与 need 相同，弧光不成立", "让「想要」和「真正需要」冲突"))
    items.append(Item("story", "S2", got, 5, f"主角 want/need/flaw/arc → {filled}/4 达成",
                      "补全主角四要素，want≠need" if got < 5 else ""))

    # S3 三幕（5）
    acts = s.get("acts") or []
    ok_acts = sum(1 for a in acts if has(a.get("goal")) and has(a.get("turn")))
    got = 5.0 if len(acts) == 3 and ok_acts == 3 else (5.0 * ok_acts / 3 if len(acts) == 3 else 5.0 * min(ok_acts, 3) / 3 * 0.8)
    items.append(Item("story", "S3", got, 5, f"{ok_acts}/{len(acts)} 幕完整（需恰好 3 幕且每幕有 goal+turn）",
                      "补足三幕的 goal 与 turn（turn 是转折点，不能为空）" if got < 5 else ""))

    # S4 关卡叙事钩子（4）
    lv = bp.get("levels") or []
    with_log = sum(1 for x in lv if has(x.get("logline"), 6))
    ratio = with_log / len(lv) if lv else 0
    got = 4.0 if ratio >= 0.8 else (2.0 if ratio >= 0.6 else 0.0)
    items.append(Item("story", "S4", got, 4, f"{with_log}/{len(lv)} 关有 logline",
                      "给每关写一句「本关发生什么」" if got < 4 else ""))

    # S5 对白（3）
    dlg = s.get("dialogue") or []
    good = sum(1 for d in dlg if all(has(d.get(k)) for k in ("speaker", "line", "cue", "emotion")))
    got = 3.0 if len(dlg) >= 12 and good == len(dlg) else (1.5 if len(dlg) >= 8 else 0.0)
    items.append(Item("story", "S5", got, 3, f"对白 {len(dlg)} 条，字段完整 {good} 条（需 ≥12 条全完整）",
                      "补对白，每条必须有 cue（触发点），无归属台词直接删" if got < 3 else ""))

    # S6 结局（3）
    eb = s.get("ending_beats") or []
    loop_end = any(k in json.dumps(eb, ensure_ascii=False) for k in ("循环继续", "继续循环", "无限重复"))
    got = 3.0 if len(eb) >= 2 and not loop_end else (1.0 if len(eb) >= 2 else 0.0)
    items.append(Item("story", "S6", got, 3, f"结局节拍 {len(eb)} 个{'（含开放式循环收尾）' if loop_end else ''}",
                      "补 2 个以上结局节拍，必须有明确代价或获得" if got < 3 else ""))


# ------------------------------------------------------------------ 美学 25
def score_art(g: dict, items: list[Item]) -> None:
    pal, spec, bible = g["palette"], g["spec"] or {}, g["art_bible"]
    tokens = (pal.get("style_tokens") or "").split()
    # A1 风格锚定（5）
    parts = [len(tokens) >= 15, bool((pal.get("negative") or "").strip()),
             ("perspective" in bible.lower() or "视角" in bible),
             ("lighting" in bible.lower() or "光照" in bible)]
    got = 5.0 * sum(parts) / 4
    items.append(Item("art", "A1", got, 5,
                      f"style_tokens {len(tokens)} 词 / negative {'有' if parts[1] else '无'} / 视角 {'有' if parts[2] else '无'} / 光照 {'有' if parts[3] else '无'}",
                      "补 art-bible 的 perspective 与 lighting 段，style_tokens ≥15 词" if got < 5 else ""))

    # A2 色板（4）
    colors = list(pal.get("primary") or []) + list(pal.get("accent") or [])
    parts = [len(colors) >= 6, bool(pal.get("background")), bool(pal.get("accent")),
             bool(pal.get("negative") or pal.get("danger"))]
    got = 4.0 * sum(parts) / 4
    items.append(Item("art", "A2", got, 4, f"色数 {len(colors)}，语义角色 {sum(parts)}/4 齐",
                      "色板 ≥6 色且覆盖 bg/primary/accent/danger(negative)" if got < 4 else ""))

    # A3 素材角色覆盖（6）
    roles = {i.get("role") for i in (spec.get("items") or [])} if spec else set()
    need = {"character", "prop", "ui", "fx"}
    need |= {"tile"} if "tile" in roles or "world" in roles else set()
    need |= {"bg"}
    covered = roles & need
    got = 6.0 * len(covered) / len(need) if need else 0.0
    items.append(Item("art", "A3", got, 6, f"覆盖 role {len(covered)}/{len(need)}：{', '.join(sorted(covered)) or '无'}",
                      "补缺失的素材角色（character/prop/tile/bg/ui/fx）" if got < 6 else ""))

    # A4 角色一致性（5）
    items_list = spec.get("items") or []
    hero_key = (spec.get("hero_consistency_key") or (g["blueprint"] or {}).get("art", {}).get("hero_consistency_key") or "")
    refs = [i for i in items_list if i.get("ref")]
    seeds = {i.get("seed") for i in items_list if i.get("seed") is not None}
    got = 0.0
    if hero_key and len(refs) >= 3 and seeds:
        got = 5.0
    elif hero_key and refs:
        got = 3.0
    elif hero_key:
        got = 1.5
    items.append(Item("art", "A4", got, 5,
                      f"一致性键 {'有' if hero_key else '无'}，ref 链 {len(refs)} 条，固定 seed {'有' if seeds else '无'}（需 ≥3 条 ref）",
                      "给主角类素材设 consistency_key + 固定 seed，后续姿态走 i2i ref 链" if got < 5 else ""))

    # A5 UI 语言（3）
    ui_items = [i for i in items_list if i.get("role") == "ui"]
    ui_lang = (spec.get("ui_language") or (g["blueprint"] or {}).get("art", {}).get("ui_language") or "")
    got = 3.0 if len(ui_items) >= 3 and has(ui_lang, 6) else (1.5 if len(ui_items) >= 3 or has(ui_lang, 6) else 0.0)
    items.append(Item("art", "A5", got, 3, f"UI 素材 {len(ui_items)} 个，UI 语言描述 {'有' if has(ui_lang, 6) else '无'}",
                      "补 ≥3 个 UI 素材并写清形状/圆角/描边/字重" if got < 3 else ""))

    # A6 封面（2）
    has_keyart = any(i.get("role") in ("keyart", "cover") for i in items_list) or "cover" in g["processed"]
    items.append(Item("art", "A6", 2.0 if has_keyart else 0.0, 2,
                      f"主视觉 {'有' if has_keyart else '无'}",
                      "补一张 keyart（商店页与分享卡必需）" if not has_keyart else ""))


# ------------------------------------------------------------------ 音频 20
def score_audio(g: dict, items: list[Item], stage: str) -> None:
    sfx = (g["sfx"] or {}).get("items") or []
    music = (g["music"] or {}).get("items") or []
    voice = g["voice"] or {}
    dlg = ((g["blueprint"] or {}).get("story") or {}).get("dialogue") or []

    # 生产期用真实文件数复核（防止只写 plan 不出音频）
    if stage == "build" and g["sfx_files"]:
        declared = [i.get("id") for i in sfx]
        if len(g["sfx_files"]) < len(declared):
            items.append(Item("audio", "U1x", 0, 0,
                              f"sfx-plan 声明 {len(declared)} 个，磁盘只有 {len(g['sfx_files'])} 个 mp3",
                              "跑 gen_audio.py --spec 补齐，或删掉多写的条目"))

    n = max(len(sfx), len(g["sfx_files"]) if stage == "build" else 0)
    got = 5.0 if n >= 16 else (3.0 if n >= 12 else (1.0 if n >= 8 else 0.0))
    items.append(Item("audio", "U1", got, 5, f"音效 {n} 个（需 ≥16）",
                      "补音效到 ≥16 个，优先覆盖四个 layer" if got < 5 else ""))

    layers = {i.get("layer") for i in sfx}
    covered = [l for l in LAYERS if l in layers]
    got = 5.0 * len(covered) / 4
    items.append(Item("audio", "U2", got, 5, f"覆盖 layer {len(covered)}/4：{', '.join(covered) or '无'}",
                      "补缺失层（ui/gameplay/feedback/ambience）" if got < 5 else ""))

    moods = {i.get("mood") for i in music if i.get("mood")}
    got = 4.0 if len(music) >= 2 and len(moods) >= 2 else (2.0 if len(music) >= 2 else (1.0 if music else 0.0))
    items.append(Item("audio", "U3", got, 4, f"音乐 {len(music)} 段，不同情绪 {len(moods)} 种",
                      "补到 ≥2 段且情绪不同（calm/tense/victory…）" if got < 4 else ""))

    stingers = [i for i in sfx + music if str(i.get("cue", "")).lower() in HIGH_CUES]
    hi = [i for i in stingers if i.get("priority") == "high"]
    got = 3.0 if len(hi) >= 2 else (1.5 if stingers else 0.0)
    items.append(Item("audio", "U4", got, 3, f"关键节点 stinger {len(stingers)} 个（high 优先级 {len(hi)}）",
                      "给胜利/失败/转折各配一个 high 优先级 stinger" if got < 3 else ""))

    enabled = voice.get("enabled")
    if enabled is False and has(voice.get("reason"), 6):
        got = 3.0
        note = f"无配音（已声明理由：{voice.get('reason')[:20]}）"
    elif enabled is False:
        got = 0.0
        note = "voice.enabled=false 但没写 reason"
    elif dlg:
        voiced = len(voice.get("items") or [])
        ratio = voiced / len(dlg)
        got = 3.0 if ratio >= 0.6 else (1.5 if ratio > 0 else 0.0)
        note = f"对白 {len(dlg)} 条，配音 {voiced} 条（{ratio:.0%}，需 ≥60%）"
    else:
        got = 0.0 if enabled else 3.0
        note = "有对白字段但无配音计划" if enabled else "未声明"
    items.append(Item("audio", "U5", got, 3, note,
                      "补 voice-plan，或置 enabled=false 并写明理由" if got < 3 else ""))


# ------------------------------------------------------------------ 交叉校验
def cross_check(g: dict, stage: str, exc: list[dict]) -> list[dict]:
    proj: Path = g["proj"]
    out = []

    def skip(code: str) -> bool:
        return any(e.get("code") == code for e in exc)

    # X1 关卡数一致
    bp_lv = len(((g["blueprint"] or {}).get("levels")) or [])
    real = g["levels"] or {}
    real_lv = len(real.get("levels") or []) if isinstance(real, dict) else len(real or [])
    if bp_lv and real_lv:
        out.append({"code": "X1", "ok": bp_lv == real_lv,
                    "detail": f"蓝图 {bp_lv} 关 vs levels.json {real_lv} 关"})
    elif bp_lv and not real_lv:
        out.append({"code": "X1", "ok": stage == "design",
                    "detail": f"蓝图声明 {bp_lv} 关，尚无 levels.json"})

    # X2 音效落地
    sfx = (g["sfx"] or {}).get("items") or []
    if sfx and not skip("X2"):
        if stage == "design":
            out.append({"code": "X2", "ok": True, "detail": "设计期跳过（音频尚未生产）"})
        else:
            declared = [str(i.get("id", "")) for i in sfx]
            has_files = [d for d in declared if d in g["sfx_files"]]
            ratio = len(has_files) / len(declared) if declared else 0
            out.append({"code": "X2", "ok": ratio >= 0.8,
                        "detail": f"声明的 {len(declared)} 个音效，磁盘命中 {len(has_files)}（{ratio:.0%}）"})

    # X3 素材落地
    spec_items = (g["spec"] or {}).get("items") or []
    if spec_items and not skip("X3"):
        if stage == "design":
            out.append({"code": "X3", "ok": True, "detail": "设计期跳过（素材尚未生产）"})
        else:
            need = [i.get("id") for i in spec_items if i.get("required", True)]
            hit = [i for i in need if i in g["processed"]]
            ratio = len(hit) / len(need) if need else 1
            out.append({"code": "X3", "ok": ratio >= 0.8,
                        "detail": f"必需素材 {len(need)} 个，已处理 {len(hit)}（{ratio:.0%}）"})

    # X4 对白落地
    dlg = ((g["blueprint"] or {}).get("story") or {}).get("dialogue") or []
    if dlg and not skip("X4"):
        if stage == "design":
            out.append({"code": "X4", "ok": True, "detail": f"设计期跳过（{len(dlg)} 条对白待接入代码）"})
            return out
        src = proj / "src"
        blob = ""
        if src.is_dir():
            for f in src.rglob("*"):
                if f.suffix in (".ts", ".js", ".json") and f.is_file():
                    try:
                        blob += f.read_text(encoding="utf-8", errors="ignore")
                    except OSError:
                        pass
        hit = sum(1 for d in dlg if (d.get("line") or "")[:12] in blob)
        ratio = hit / len(dlg) if dlg else 0
        out.append({"code": "X4", "ok": ratio >= 0.6,
                    "detail": f"对白 {len(dlg)} 条，源码中出现 {hit} 条（{ratio:.0%}）"})
    return out


# ------------------------------------------------------------------ 主流程
def run(args) -> int:
    proj = project_dir(args.project)
    g = gather(proj)
    st = load_state(proj)
    stages = st.get("stages") or {}
    if args.stage == "auto":
        stage = "build" if (stages.get("art_forge", {}).get("status") == "done") else "design"
    else:
        stage = args.stage
    exc = ((g["blueprint"] or {}).get("exceptions") or [])

    items: list[Item] = []
    score_gameplay(g, items)
    score_story(g, items)
    score_art(g, items)
    score_audio(g, items, stage)
    checks = cross_check(g, stage, exc)

    dims = {}
    for key, label, full in DIMS:
        got = round(sum(i.got for i in items if i.dim == key), 2)
        dims[key] = {"label": label, "got": got, "max": full,
                     "ratio": round(got / full, 3) if full else 0}

    total = round(sum(d["got"] for d in dims.values()), 2)
    low = [d for d in dims.values() if d["ratio"] < 0.6]
    x_fail = [c for c in checks if not c["ok"]]

    if not g["blueprint"]:
        verdict = "INCOMPLETE"
    elif x_fail:
        verdict = "THIN"
    elif total >= 70 and not low:
        verdict = "RICH"
    else:
        verdict = "THIN"

    fixes = sorted([i for i in items if i.lost > 0 and i.fix], key=lambda i: -i.lost)[:5]

    # 输出
    if not args.quiet:
        print(f"\n内容丰富度：{total:.1f} / 100　→　{verdict}　（阶段：{stage}）\n")
        for k, _l, full in DIMS:
            d = dims[k]
            mark = "✅" if d["ratio"] >= 0.8 else ("⚠️" if d["ratio"] >= 0.6 else "❌")
            print(f"  {mark} {d['label']:<6} {d['got']:>5.1f} / {full}")
        print()
        for i in items:
            if i.got < i.max:
                print(f"  [{-i.lost:+.1f}] {i.code} {i.note}")
        for c in checks:
            print(f"  {'✅' if c['ok'] else '❌'} {c['code']} {c['detail']}")
        if fixes:
            print("\n最小改动清单（按得分增量排序）：")
            for i, f in enumerate(fixes, 1):
                print(f"  {i}. {f.dim}/{f.code}　可拿 {f.lost:+.1f} 分　→ {f.fix}")
        print()

    result = {
        "verdict": verdict, "total": total, "stage": stage,
        "dims": dims,
        "items": [i.as_dict() for i in items],
        "cross_checks": checks,
        "min_fixes": [{"dim": f.dim, "code": f.code, "gain": f.lost, "fix": f.fix} for f in fixes],
        "judged_by": "references/content-depth.md",
        "has_blueprint": bool(g["blueprint"]),
    }
    dump_json(proj / "docs" / "09-review" / "richness.json", result)
    write_report(proj, result, dims, items, checks, fixes)

    st.setdefault("stages", {})["review_richness"] = {
        "status": "done" if verdict == "RICH" else "failed",
        "verdict": verdict, "score": total, "stage": stage,
    }
    save_state(proj, st)

    if verdict == "RICH":
        ok(f"丰富度达标：{total:.1f} 分")
        return 0
    if verdict == "INCOMPLETE":
        print(f"ERROR: 未完成——缺 content-blueprint.json（{total:.1f} 分）", file=sys.stderr)
        return 3
    print(f"ERROR: 丰富度不足（{total:.1f} 分，判定 {verdict}）——见 docs/09-review/richness-report.md", file=sys.stderr)
    return 2


def write_report(proj: Path, res: dict, dims: dict, items: list[Item], checks: list[dict], fixes: list[Item]) -> None:
    L = [f"# 内容丰富度报告\n",
         f"> 判据：`references/content-depth.md`　阶段：{res['stage']}",
         f"> 结论：**{res['verdict']}**　总分 **{res['total']:.1f} / 100**\n",
         "## 四维得分\n",
         "| 维度 | 得分 | 满分 | 占比 |", "|---|---|---|---|"]
    for k, _l, full in DIMS:
        d = dims[k]
        L.append(f"| {d['label']} | {d['got']:.1f} | {full} | {d['ratio']:.0%} |")
    L += ["", "## 逐条判定\n", "| 项 | 得分 | 满分 | 证据 |", "|---|---|---|---|"]
    for i in items:
        L.append(f"| {i.code} | {i.got:.1f} | {i.max} | {i.note} |")
    L += ["", "## 交叉校验（声明 vs 产物）\n", "| 项 | 结果 | 说明 |", "|---|---|---|"]
    for c in checks:
        L.append(f"| {c['code']} | {'PASS' if c['ok'] else 'FAIL'} | {c['detail']} |")
    if fixes:
        L += ["", "## 最小改动清单\n"]
        for n, f in enumerate(fixes, 1):
            L.append(f"{n}. **{f.dim}/{f.code}**（+{f.lost:.1f} 分）：{f.fix}")
    L += ["", "---", "", "复审必须全量重跑：`python scripts/richness_check.py --project .`"]
    (proj / "docs" / "09-review" / "richness-report.md").write_text("\n".join(L), encoding="utf-8")


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    ap = argparse.ArgumentParser(description="内容丰富度门禁")
    ap.add_argument("--project", default=None)
    ap.add_argument("--stage", default="auto", choices=["auto", "design", "build"])
    ap.add_argument("--quiet", action="store_true")
    return run(ap.parse_args())


if __name__ == "__main__":
    raise SystemExit(main())
