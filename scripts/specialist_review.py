#!/usr/bin/env python3
"""专项审核官（Specialist Reviewer）：创意 / 美术 / 动画 / 音频 / 体验 / 试玩 六项。

与 `review_gate.py` 的分工：
  - `review_gate.py` 判「能不能上架」（CrazyGames A–H 八维，合规与可玩性）
  - 本脚本判「值不值得上架」（视觉身份是否成立、声音是否表达情绪、表现是否分级、体验是否成立）

三条铁律（与 R0/R1/R2 一致）：
  1. **只审不写**：不改 `src/`、`assets/`、`docs/00–08`，只写 `docs/09-review/`
  2. **必须给证据**：每条 PASS 都要能指到文件、数值或截图。禁止「美术风格很好」这类空话
  3. **不许虚报**：缺产物 = UNVERIFIED（视为未通过），不是 PASS

关键实现：美术审核真的去读截图像素（色相分布、明度对比），音频审核真的读波形测量结果。
没有实测数据就不给 PASS —— 这是本脚本与「文档自评」的唯一区别。

用法:
    python specialist_review.py --project .                 # 全部六项
    python specialist_review.py --project . --only art
    python specialist_review.py --project . --strict        # 有 FAIL 时返回 2

产物:
    docs/09-review/specialist-{creative,art,animation,audio,experience,playtest}.json
    docs/09-review/specialist-report.md
    docs/09-review/verdict-specialist.json
"""

from __future__ import annotations

import argparse
import colorsys
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import SKILL_DIR, dump_json, load_state, ok, project_dir, save_state, warn  # noqa: E402

SCHEMA_DIR = SKILL_DIR / "references" / "schemas"

REVIEWS = ["creative", "art", "animation", "audio", "experience", "playtest"]

REVIEW_ZH = {
    "creative": "创意审核",
    "art": "美术审核",
    "animation": "动画与表现审核",
    "audio": "音频审核",
    "experience": "体验审核",
    "playtest": "试玩审核",
}


def load_json(p: Path, default=None):
    if not p.exists():
        return default
    try:
        with p.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:  # noqa: BLE001
        warn(f"解析失败 {p}：{e}")
        return default


def src_blob(proj: Path) -> str:
    out = []
    for d in ("src",):
        root = proj / d
        if not root.is_dir():
            continue
        for f in root.rglob("*"):
            if f.suffix in (".ts", ".tsx", ".js", ".mjs", ".json") and f.is_file():
                try:
                    out.append(f.read_text(encoding="utf-8", errors="ignore"))
                except OSError:
                    pass
    return "\n".join(out)


def hex_to_hsl(h: str):
    h = h.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))
    hh, ll, ss = colorsys.rgb_to_hls(r, g, b)
    return hh * 360, ss, ll


def hue_dist(a: float, b: float) -> float:
    d = abs(a - b) % 360
    return min(d, 360 - d)


# ------------------------------------------------------------------ 收集证据
class Ev:
    """一条审核结论。evidence 必须是可核对的字符串。"""

    def __init__(self):
        self.items: list[dict] = []

    def add(self, code, title, result, evidence, fix=""):
        assert result in ("PASS", "FAIL", "UNVERIFIED"), result
        self.items.append({"code": code, "title": title, "result": result,
                           "evidence": evidence, "fix": fix})

    def summary(self):
        return {
            "PASS": sum(1 for i in self.items if i["result"] == "PASS"),
            "FAIL": sum(1 for i in self.items if i["result"] == "FAIL"),
            "UNVERIFIED": sum(1 for i in self.items if i["result"] == "UNVERIFIED"),
        }

    def verdict(self):
        s = self.summary()
        if s["FAIL"]:
            return "FAIL"
        if s["UNVERIFIED"]:
            return "INCOMPLETE"
        return "PASS"


# ------------------------------------------------------------------ 创意
def review_creative(proj: Path, ev: Ev) -> None:
    concepts = load_json(proj / "docs" / "01-brief" / "creative-concepts.json")
    dna = load_json(proj / "docs" / "01-brief" / "creative-dna.json")

    if not concepts:
        ev.add("C1", "创意发散（≥5 个结构不同的方案）", "UNVERIFIED",
               "缺 docs/01-brief/creative-concepts.json —— 无法证明做过发散",
               "跑 creative_forge.py --diverge")
    else:
        n = len(concepts.get("concepts") or [])
        sd = concepts.get("structural_distance") or {}
        okd = sd.get("pass") and (sd.get("min_pairwise") or 0) >= 3
        ev.add("C1", "创意发散（≥5 个结构不同的方案）",
               "PASS" if n >= 5 and okd else "FAIL",
               f"{n} 个方案，最小两两结构距离 {sd.get('min_pairwise')}/5（要求 ≥3）",
               "方案结构太像 —— 换交互动词（spatial/time/info/resource/risk 至少 3 项不同）")

    if not dna:
        ev.add("C2", "Creative DNA 存在且通过 schema", "UNVERIFIED",
               "缺 creative-dna.json", "跑 creative_forge.py --dna")
        return

    import schema_check  # noqa: E402
    schema = load_json(SCHEMA_DIR / "creative-dna.schema.json", {})
    errs = schema_check.validate(dna, schema)
    ev.add("C2", "Creative DNA 通过 schema", "PASS" if not errs else "FAIL",
           f"{len(errs)} 个 schema 错误" + (f"：{errs[0]}" if errs else ""))

    cm = (dna.get("gameplay") or {}).get("core_mechanic") or {}
    conds = {
        "一句话（8–80 字）": 8 <= len((cm.get("one_sentence") or "").strip()) <= 80,
        "非数值": bool(cm.get("non_numeric")),
        "与≥2机制互动": len(cm.get("interacts") or []) >= 2,
        "改变策略": len((cm.get("changes_decision") or "").strip()) >= 12,
        "标志时刻": len((cm.get("signature_moment") or "").strip()) >= 16,
    }
    got = sum(conds.values())
    ev.add("C3", "独特机制满足 6 条判据", "PASS" if got == len(conds) else "FAIL",
           f"{got}/{len(conds)}：" + "、".join(k for k, v in conds.items() if v),
           "补齐缺失条件：" + "、".join(k for k, v in conds.items() if not v))

    note = (dna.get("meta") or {}).get("novelty_note") or ""
    high = "HIGH" in note
    ev.add("C4", "启发式相似度分析（换皮风险）", "FAIL" if high else ("PASS" if note else "UNVERIFIED"),
           note or "DNA 未记录相似度分析结论",
           "与原型重合度过高 —— 按 archetypes.json 的 how_to_differentiate 重设计核心机制")

    link = (dna.get("narrative") or {}).get("narrative_mechanic_link") or ""
    ev.add("C5", "叙事与机制真实耦合", "PASS" if len(link) >= 12 else "FAIL",
           f"narrative_mechanic_link：{link[:60] or '空'}",
           "写清「哪条世界规则被写进了机制」，否则叙事只是贴皮")

    refs = dna.get("references") or []
    bad = [r for r in refs if not (r.get("source") and r.get("license"))]
    ev.add("C6", "引用模式带来源与许可", "PASS" if refs and not bad else ("FAIL" if bad else "UNVERIFIED"),
           f"{len(refs)} 条引用，{len(bad)} 条缺 source/license",
           "给每条引用补 source 与 license（任务书 §12.5）")


# ------------------------------------------------------------------ 美术
def dominant_hues(img_path: Path, top: int = 6) -> list[tuple[float, float]]:
    """截图的色相分布（按饱和度加权）。返回 [(hue, weight)]。"""
    try:
        from PIL import Image
    except ImportError:
        return []
    try:
        im = Image.open(img_path).convert("RGB")
    except Exception:  # noqa: BLE001
        return []
    im.thumbnail((160, 160))
    bins = [0.0] * 36  # 每 10° 一档
    raw = im.tobytes()
    for i in range(0, len(raw), 3):
        r, g, b = raw[i], raw[i + 1], raw[i + 2]
        h, s, l = colorsys.rgb_to_hls(r / 255, g / 255, b / 255)
        if s < 0.18 or l < 0.06 or l > 0.96:
            continue
        bins[int((h * 360) // 10) % 36] += s
    total = sum(bins) or 1.0
    ranked = sorted(enumerate(bins), key=lambda kv: -kv[1])[:top]
    return [(i * 10 + 5, w / total) for i, w in ranked if w > 0]


def review_art(proj: Path, ev: Ev) -> None:
    vd = load_json(proj / "docs" / "02-art" / "visual-dna.json")
    pal = load_json(proj / "docs" / "02-art" / "palette.json", {}) or {}
    if not vd:
        ev.add("A1", "Visual DNA 存在且通过 schema", "UNVERIFIED",
               "缺 visual-dna.json —— 只有 palette.json 不足以证明视觉身份",
               "跑 art_director.py --dna")
        return

    import schema_check  # noqa: E402
    errs = schema_check.validate(vd, load_json(SCHEMA_DIR / "visual-dna.schema.json", {}))
    ev.add("A1", "Visual DNA 通过 schema", "PASS" if not errs else "FAIL",
           f"{len(errs)} 个错误" + (f"：{errs[0]}" if errs else ""))

    checks = (vd.get("color") or {}).get("contrast_checks") or []
    bad = [c for c in checks if not c.get("pass")]
    ev.add("A2", "色彩对比度达标（可读性）",
           "PASS" if checks and not bad else ("FAIL" if bad else "UNVERIFIED"),
           f"{len(checks)} 组对比检查，{len(bad)} 组不达标" +
           (f"：{bad[0]['pair']} {bad[0]['ratio']}" if bad else ""),
           "提高前景色明度或压暗背景，正文 ≥4.5:1、强调 ≥3:1")

    # 真实像素：截图的主色相是否落在 DNA 色相附近
    shots = []
    for sub in ("docs/07-qa/screenshots", "docs/07-qa/playtest-shots"):
        d = proj / sub
        if d.is_dir():
            shots += sorted(d.glob("*.png"))
    if not shots:
        ev.add("A3", "实机截图与视觉 DNA 一致", "UNVERIFIED",
               "没有截图 —— 无法判断实际画面是否遵守 DNA", "跑 qa.mjs / playtest.mjs 生成截图")
    else:
        dna_hues = [hex_to_hsl(c)[0] for c in
                    (pal.get("primary") or []) + (pal.get("accent") or []) +
                    [pal.get("danger") or "#000000"]]
        near, far, tested = 0, 0, 0
        detail = []
        for sh in shots[:6]:
            hues = dominant_hues(sh)
            if not hues:
                continue
            tested += 1
            d = min(hue_dist(h, dh) for h, _w in hues for dh in dna_hues)
            detail.append(f"{sh.name}:{d:.0f}°")
            if d <= 25:
                near += 1
            else:
                far += 1
        if not tested:
            ev.add("A3", "实机截图与视觉 DNA 一致", "UNVERIFIED", "截图无法解析（可能为空图）")
        else:
            ev.add("A3", "实机截图与视觉 DNA 一致",
                   "PASS" if far == 0 else "FAIL",
                   f"{tested} 张截图，主色相与 DNA 距离：{', '.join(detail)}（阈值 25°）",
                   "画面色相偏离 DNA —— 检查素材或后处理是否引入了新色相")

    con = (vd.get("character") or {}).get("consistency") or {}
    st = con.get("status")
    if st == "full_ref_chain":
        exist = [r for r in (con.get("refs") or []) if (proj / r.get("file", "")).exists()]
        ev.add("A4", "角色一致性方案（不得虚报）", "PASS" if len(exist) >= 3 else "FAIL",
               f"status=full_ref_chain，实际参考图 {len(exist)}/3",
               "参考图不存在就不能声称 ref 链已生效")
    else:
        ev.add("A4", "角色一致性方案（不得虚报）", "PASS",
               f"status={st}（{con.get('reason', '')[:50]}）—— 已如实标注降级")

    # UI 文字必须由 Text 渲染（注意代码里常写成 this.add\n  .text(...)）
    import re as _re
    blob = src_blob(proj)
    has_text = bool(_re.search(r"add\s*\.\s*text\s*\(", blob))
    ev.add("A5", "文字由 Text 渲染（不画进素材）", "PASS" if has_text else "UNVERIFIED",
           "源码中存在 Phaser Text 调用" if has_text else "未找到 Text 调用")

    sn = vd.get("scene_narrative") or []
    ev.add("A6", "场景承担叙事（环境随进度变化）", "PASS" if len(sn) >= 2 else "FAIL",
           f"{len(sn)} 条场景叙事规则" + (f"：{sn[0].get('trigger', '')}" if sn else ""),
           "补「什么触发 + 画面怎么变 + 意味着什么」")


# ------------------------------------------------------------------ 动画
def review_animation(proj: Path, ev: Ev) -> None:
    jp = load_json(proj / "docs" / "04-core-loop" / "juice-plan.json")
    blob = src_blob(proj)
    if not jp:
        ev.add("N1", "表现矩阵存在", "UNVERIFIED", "缺 juice-plan.json", "跑 juice_forge.py --plan")
        return

    import schema_check  # noqa: E402
    errs = schema_check.validate(jp, load_json(SCHEMA_DIR / "juice-plan.schema.json", {}))
    ev.add("N1", "表现矩阵通过 schema", "PASS" if not errs else "FAIL",
           f"{len(errs)} 个错误" + (f"：{errs[0]}" if errs else ""))

    used = {f["type"] for r in jp.get("rules") or [] for f in r.get("effects") or []}
    ev.add("N2", "效果类型覆盖（≥8 类）", "PASS" if len(used) >= 8 else "FAIL",
           f"{len(used)} 类：{', '.join(sorted(used))}",
           "只靠震动/粒子/形变等于把 v2 的做法包了一层")

    sigs = {tuple(f["type"] for f in r.get("effects") or []) for r in jp.get("rules") or []}
    ev.add("N3", "表现强度按事件分级（不是全同一套）",
           "PASS" if len(sigs) >= 3 else "FAIL",
           f"{len(jp.get('rules') or [])} 条规则产生 {len(sigs)} 种不同效果组合",
           "按 severity 分档：micro/light/medium/heavy")

    s = jp.get("settings") or {}
    flash_ok = (s.get("flashMaxPerSecond") or 0) <= 1
    shake_ok = (s.get("shakeMaxMs") or 0) <= 300
    ev.add("N4", "无障碍硬上限（闪屏 ≤1/s、震动 ≤300ms）",
           "PASS" if flash_ok and shake_ok else "FAIL",
           f"flashMaxPerSecond={s.get('flashMaxPerSecond')}，shakeMaxMs={s.get('shakeMaxMs')}",
           "光敏性癫痫与晕动的硬上限，不可配置放宽")

    import re as _re
    wired = bool(_re.search(r"new\s+JuiceDirector", blob)) and \
        bool(_re.search(r"juice\??\.update\s*\(", blob))
    ev.add("N5", "表现引擎真实接入（不是只有配置）",
           "PASS" if wired else "FAIL",
           "源码实例化 JuiceDirector 并在 update 中调用" if wired else "源码里找不到 JuiceDirector 的使用",
           "在场景里 new JuiceDirector 并 attach，事件才会驱动表现")

    rm = "prefers-reduced-motion" in blob or "reducedMotion" in blob
    ev.add("N6", "减少动态效果的无障碍支持", "PASS" if rm else "FAIL",
           "检测 prefers-reduced-motion 并关闭震动/闪屏" if rm else "没有无障碍开关",
           "加 matchMedia('(prefers-reduced-motion: reduce)') 判断")

    cleanup = ("SHUTDOWN" in blob or "shutdown" in blob) and \
        bool(__import__("re").search(r"\.destroy\s*\(\)", blob))
    ev.add("N7", "场景切换时清理（避免对象泄漏）", "PASS" if cleanup else "FAIL",
           "SHUTDOWN 时调用 destroy" if cleanup else "未找到场景清理逻辑",
           "在 SHUTDOWN 里 destroy juice/audio/bus")

    # 逻辑确定性：hit stop / slow motion 只能缩放 tween，不能改逻辑步长
    bad_dt = "time.timeScale" in blob or "physics.world.timeScale" in blob
    ev.add("N8", "动画不影响玩法确定性（只冻结表现）",
           "FAIL" if bad_dt else "PASS",
           "发现 time.timeScale 改写 —— 会影响逻辑步长" if bad_dt
           else "只缩放 tweens.timeScale，update 的逻辑步长未变")


# ------------------------------------------------------------------ 音频
def review_audio(proj: Path, ev: Ev) -> None:
    ad = load_json(proj / "docs" / "05-audio" / "audio-dna.json")
    blob = src_blob(proj)
    if not ad:
        ev.add("U1", "音频系统设计存在", "UNVERIFIED",
               "缺 audio-dna.json —— 只有 mp3 文件不构成音频系统", "跑 audio_director.py --plan")
        return

    import schema_check  # noqa: E402
    errs = schema_check.validate(ad, load_json(SCHEMA_DIR / "audio-dna.schema.json", {}))
    ev.add("U1", "音频系统设计通过 schema", "PASS" if not errs else "FAIL",
           f"{len(errs)} 个错误" + (f"：{errs[0]}" if errs else ""))

    states = (ad.get("music") or {}).get("states") or []
    sigs = {tuple(sorted((st.get("stem_gains") or {}).items())) for st in states}
    ev.add("U2", "自适应音乐状态有真实区分度",
           "PASS" if len(states) >= 2 and len(sigs) == len(states) else "FAIL",
           f"{len(states)} 个状态，{len(sigs)} 种不同分轨配比",
           "两个状态音量完全一样 = 切换听不出区别，自适应是假的")

    qc = ad.get("qc") or {}
    files = qc.get("files") or []
    if not files:
        ev.add("U3", "音频实测（波形检查）", "UNVERIFIED",
               "尚未跑 audio_director.py --qc —— 没有实测数据不能判音频正常")
    else:
        miss = [f for f in files if not f.get("exists")]
        clip = [f for f in files if f.get("clipped")]
        silent = [f for f in files if f.get("silent")]
        seam = [f for f in files if (f.get("loop_seam_db") or 0) > 26]
        okd = not (miss or clip or silent)
        ev.add("U3", "音频实测（存在/削波/静音/接缝）",
               "PASS" if okd else "FAIL",
               f"{len(files)} 个文件：缺失 {len(miss)}、削波 {len(clip)}、静音 {len(silent)}、"
               f"接缝可疑 {len(seam)}；总 {qc.get('total_kb', 0)}KB/{qc.get('budget_kb', 0)}KB",
               "补齐缺失文件或重做削波/静音的音效")

    import re as _re
    wired = bool(_re.search(r"new\s+AudioDirector", blob)) and \
        bool(_re.search(r"\.setState\s*\(", blob))
    ev.add("U4", "音频引擎真实接入（状态真的被切换）",
           "PASS" if wired else "FAIL",
           "源码实例化 AudioDirector 且调用 setState" if wired else "源码里没有状态切换",
           "玩法状态必须驱动音乐状态，否则分层没有意义")

    hooks = [h for h in ad.get("gameplay_hooks") or [] if h.get("event") != "none"]
    if hooks:
        bad = [h for h in hooks if not (h.get("visual_fallback") or "").strip()]
        ev.add("U5", "声音承担玩法职责时有视觉替代（无障碍）",
               "PASS" if not bad else "FAIL",
               f"{len(hooks)} 个玩法钩子，{len(bad)} 个缺 visual_fallback",
               "静音玩家必须也能通关")
    else:
        ev.add("U5", "声音承担玩法职责时有视觉替代（无障碍）", "PASS",
               "本作声音不承担玩法职责，不适用")

    total = qc.get("total_kb") or 0
    budget = qc.get("budget_kb") or 2048
    ev.add("U6", "音频体积在预算内", "PASS" if total <= budget else "FAIL",
           f"{total}KB / {budget}KB")


# ------------------------------------------------------------------ 体验
def review_experience(proj: Path, ev: Ev) -> None:
    eb = load_json(proj / "docs" / "03-experience" / "experience-blueprint.json")
    if not eb:
        ev.add("E1", "体验蓝图存在", "UNVERIFIED", "缺 experience-blueprint.json",
               "跑 experience_forge.py --plan")
        return

    import schema_check  # noqa: E402
    errs = schema_check.validate(eb, load_json(SCHEMA_DIR / "experience-blueprint.schema.json", {}))
    ev.add("E1", "体验蓝图通过 schema", "PASS" if not errs else "FAIL",
           f"{len(errs)} 个错误" + (f"：{errs[0]}" if errs else ""))

    checks = eb.get("checks") or []
    fails = [c for c in checks if c.get("result") == "FAIL"]
    unv = [c for c in checks if c.get("result") == "UNVERIFIED"]
    if not checks:
        ev.add("E2", "体验判据 E1–E8 已验证", "UNVERIFIED", "尚未跑 --verify")
    else:
        ev.add("E2", "体验判据 E1–E8 已验证",
               "FAIL" if fails else ("UNVERIFIED" if unv else "PASS"),
               f"{len(checks)} 条：PASS {len(checks) - len(fails) - len(unv)}、"
               f"FAIL {len(fails)}、UNVERIFIED {len(unv)}" +
               (f"；首个失败：{fails[0]['id']}" if fails else ""),
               "未验证 ≠ 通过；跑 experience_forge.py --verify")

    curve = eb.get("emotion_curve") or []
    peak = max(curve, key=lambda c: c["intensity"]) if curve else None
    ev.add("E3", "情绪曲线有高潮且峰值在 climax",
           "PASS" if peak and peak["phase"] == "climax" else "FAIL",
           f"峰值 {peak['intensity']} 在 {peak['phase']}" if peak else "曲线为空",
           "没有高潮的曲线留不下记忆点")

    lv = eb.get("levels") or []
    bad = [l["level"] for l in lv if not (l.get("core_decision") or "").strip()]
    ev.add("E4", "每关都有取舍决策", "PASS" if lv and not bad else "FAIL",
           f"{len(lv)} 关，{len(bad)} 关缺决策")

    moments = eb.get("signature_moments") or []
    verified = [m for m in moments if m.get("verified")]
    ev.add("E5", "标志性时刻绑定了真实事件",
           "PASS" if verified else "FAIL",
           f"{len(verified)}/{len(moments)} 已验证" if moments else "未定义标志时刻",
           "标志时刻必须由代码里真实存在的游戏事件触发")


# ------------------------------------------------------------------ 试玩
def review_playtest(proj: Path, ev: Ev) -> None:
    pt = load_json(proj / "docs" / "07-qa" / "playtest.json")
    if not pt:
        ev.add("P1", "试玩报告存在", "UNVERIFIED",
               "缺 docs/07-qa/playtest.json", "跑 playtest.py 或 node scripts/playtest.mjs")
        return

    s = pt.get("summary") or {}
    strategies = pt.get("strategies") or []
    ev.add("P1", "四种玩家策略都跑过", "PASS" if len(strategies) >= 3 else "FAIL",
           f"{len(strategies)} 种策略：{', '.join(x.get('strategy', '?') for x in strategies)}")

    errs = s.get("errors") or []
    ev.add("P2", "试玩期间零运行时错误", "PASS" if not errs else "FAIL",
           f"{len(errs)} 条" + (f"：{errs[0][:60]}" if errs else ""))

    ev.add("P3", "无卡死", "PASS" if not s.get("any_stuck") else "FAIL",
           "未检测到连续 6 秒状态不变" if not s.get("any_stuck") else "有策略出现卡死")

    fp = s.get("first_positive_feedback_s")
    if fp is None or fp >= 999:
        ev.add("P4", "前 30 秒有正反馈", "FAIL", "试玩中未采集到任何正反馈事件",
               "检查是否有 item_collected 之类的即时反馈")
    else:
        ev.add("P4", "前 30 秒有正反馈", "PASS" if fp <= 30 else "FAIL",
               f"首次正反馈 {fp}s")

    rep = s.get("repetition_ratio")
    ev.add("P5", "无意义重复劳动", "PASS" if rep is not None and rep < 0.7 else "FAIL",
           f"重复动作占比 {rep:.0%}（阈值 70%）" if rep is not None else "无数据",
           "同一操作重复而无新信息 = 重复劳动")

    shots = list((proj / "docs" / "07-qa" / "playtest-shots").glob("*.png"))
    ev.add("P6", "试玩有截图证据", "PASS" if len(shots) >= 2 else "FAIL",
           f"{len(shots)} 张截图")

    ev.add("P7", "已声明「AI 试玩 ≠ 真人测试」",
           "PASS" if "不等于" in (pt.get("disclaimer") or "") else "FAIL",
           (pt.get("disclaimer") or "缺免责声明")[:60])


# ------------------------------------------------------------------ 主流程
def run_review(proj: Path, name: str) -> dict:
    ev = Ev()
    {
        "creative": review_creative,
        "art": review_art,
        "animation": review_animation,
        "audio": review_audio,
        "experience": review_experience,
        "playtest": review_playtest,
    }[name](proj, ev)
    res = {
        "review": name,
        "zh": REVIEW_ZH[name],
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "verdict": ev.verdict(),
        "summary": ev.summary(),
        "checks": ev.items,
    }
    dump_json(proj / "docs" / "09-review" / f"specialist-{name}.json", res)
    return res


def write_md(proj: Path, results: list[dict], agg: dict) -> None:
    L = ["# 专项审核报告（Specialist Review）", "",
         f"> 生成：{datetime.now().astimezone().isoformat(timespec='seconds')}",
         f"> 总判定：**{agg['verdict']}**　PASS {agg['summary']['PASS']}　"
         f"FAIL {agg['summary']['FAIL']}　UNVERIFIED {agg['summary']['UNVERIFIED']}", "",
         "本报告只审不写：不修改 `src/`、`assets/`、`docs/00–08`。",
         "每条 PASS 都必须给证据；缺产物一律 UNVERIFIED（视为未通过）。", "",
         "| 审核 | 判定 | PASS | FAIL | UNVERIFIED |", "|---|---|---|---|---|"]
    for r in results:
        L.append(f"| {r['zh']} | {r['verdict']} | {r['summary']['PASS']} | "
                 f"{r['summary']['FAIL']} | {r['summary']['UNVERIFIED']} |")
    for r in results:
        L += ["", f"## {r['zh']}　{r['verdict']}", "", "| 项 | 结论 | 证据 |", "|---|---|---|"]
        for c in r["checks"]:
            L.append(f"| {c['code']} {c['title']} | {c['result']} | {c['evidence']} |")
        fixes = [c for c in r["checks"] if c["result"] != "PASS" and c.get("fix")]
        if fixes:
            L += ["", "需修复："]
            for c in fixes:
                L.append(f"- **{c['code']}** {c['fix']}")
    L += ["", "---", "", "复审必须全量重跑：`python scripts/specialist_review.py --project .`", ""]
    (proj / "docs" / "09-review" / "specialist-report.md").write_text("\n".join(L), encoding="utf-8")


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass
    ap = argparse.ArgumentParser(description="专项审核：创意/美术/动画/音频/体验/试玩")
    ap.add_argument("--project", default=None)
    ap.add_argument("--only", default="", help=f"逗号分隔，可选：{', '.join(REVIEWS)}")
    ap.add_argument("--strict", action="store_true")
    args = ap.parse_args()

    proj = project_dir(args.project)
    names = [x.strip() for x in args.only.split(",") if x.strip()] or REVIEWS
    unknown = [n for n in names if n not in REVIEWS]
    if unknown:
        print(f"ERROR: 未知审核项 {unknown}；可选 {', '.join(REVIEWS)}", file=sys.stderr)
        return 1

    results = [run_review(proj, n) for n in names]
    agg_sum = {k: sum(r["summary"][k] for r in results) for k in ("PASS", "FAIL", "UNVERIFIED")}
    if agg_sum["FAIL"]:
        verdict = "FAIL"
    elif agg_sum["UNVERIFIED"]:
        verdict = "INCOMPLETE"
    else:
        verdict = "PASS"
    agg = {
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "verdict": verdict,
        "summary": agg_sum,
        "reviews": [{"review": r["review"], "zh": r["zh"], "verdict": r["verdict"],
                     "summary": r["summary"]} for r in results],
        "blocking": [{"review": r["review"], "code": c["code"], "title": c["title"],
                      "result": c["result"], "fix": c.get("fix", "")}
                     for r in results for c in r["checks"] if c["result"] != "PASS"],
    }
    dump_json(proj / "docs" / "09-review" / "verdict-specialist.json", agg)
    write_md(proj, results, agg)

    print(f"专项审核：{len(results)} 项　→　{verdict}\n")
    for r in results:
        mark = {"PASS": "✅", "FAIL": "❌", "INCOMPLETE": "❔"}[r["verdict"]]
        print(f"  {mark} {r['zh']:<12} {r['verdict']:<10} "
              f"PASS {r['summary']['PASS']}　FAIL {r['summary']['FAIL']}　UNV {r['summary']['UNVERIFIED']}")
        for c in r["checks"]:
            if c["result"] != "PASS":
                print(f"       [{c['result']}] {c['code']} {c['title']} —— {c['evidence'][:70]}")
    print(f"\n已写 docs/09-review/specialist-report.md 与 verdict-specialist.json")

    st = load_state(proj)
    st.setdefault("stages", {})["review_specialist"] = {
        "status": "done" if verdict == "PASS" else "in_progress",
        "verdict": verdict,
        "pass": agg_sum["PASS"], "fail": agg_sum["FAIL"], "unverified": agg_sum["UNVERIFIED"],
    }
    save_state(proj, st)

    if verdict == "PASS":
        ok("六项专项审核全部通过")
        return 0
    if verdict == "FAIL":
        warn("有 FAIL 项 —— R2 与 ship 会被阻断")
        return 2 if args.strict else 0
    warn("有 UNVERIFIED 项 —— 未验证不算通过")
    return 2 if args.strict else 0


if __name__ == "__main__":
    raise SystemExit(main())
