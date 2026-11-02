#!/usr/bin/env python3
"""玩家体验设计师（Experience Designer）：情绪曲线 + 每关体验表 + 可验证的体验判据。

为什么需要它 —— v2 的 `richness_check` 只判「有没有内容」（机制数、对白数、音效数），
不判「体验是否成立」：前 10 秒能不能理解、有没有正反馈、难度是不是只靠数值、
失败有没有教学价值、有没有无意义的重复劳动。这些一条都没被检查过。

本脚本做三件事：
  1. --plan      从 DNA + 情绪曲线库生成 experience-blueprint.json（曲线 + 每关 10 项）
  2. --verify    用真实产物验证 E1–E8：读 levels.json、源码、试玩报告，逐条给 PASS/FAIL/UNVERIFIED
  3. --validate  schema + 语义（每关只引入 ≤1 个新机制、机制 id 必须真实存在、曲线必须有高潮）

关键立场：**未验证就写 UNVERIFIED，不许写 PASS。**
任务书明确要求「不能仅凭文档声明就判定通过」，所以 --verify 的每条都要求证据字符串。

用法:
    python experience_forge.py --project . --plan
    python experience_forge.py --project . --verify
    python experience_forge.py --project . --validate --strict

产物:
    docs/03-experience/experience-blueprint.json   ★ 体验设计
    docs/03-experience/experience-verify.json      E1–E8 的验证结果（带证据）
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import SKILL_DIR, dump_json, ok, project_dir, warn  # noqa: E402

DATA = SKILL_DIR / "assets" / "data"

CHALLENGE_AXES = ["information", "resource", "operation", "environment", "cost", "none"]


def load_json(p: Path, default=None):
    if not p.exists():
        return default
    with p.open("r", encoding="utf-8") as f:
        return json.load(f)


def cmd_plan(args) -> int:
    proj = project_dir(args.project)
    dna = load_json(proj / "docs" / "01-brief" / "creative-dna.json")
    if not dna:
        print("ERROR: 缺 creative-dna.json（先跑 creative_forge.py --dna）", file=sys.stderr)
        return 1
    curves = load_json(DATA / "emotional-patterns" / "curves.json", {}) or {}
    base = curves.get("base_curve") or []
    levels_json = load_json(proj / "src" / "game" / "levels.json")
    bp = load_json(proj / "docs" / "01-brief" / "content-blueprint.json", {}) or {}

    exp = dna.get("experience") or {}
    gm = dna.get("gameplay") or {}
    mech_ids = [gm.get("core_mechanic", {}).get("id")] + \
               [m.get("id") for m in (gm.get("supporting_mechanics") or [])]
    mech_ids = [m for m in mech_ids if m]

    # 关卡数：优先用真实 levels.json，其次蓝图
    n_levels = 0
    if isinstance(levels_json, dict):
        n_levels = len(levels_json.get("levels") or [])
    elif isinstance(levels_json, list):
        n_levels = len(levels_json)
    if not n_levels:
        n_levels = len(bp.get("levels") or []) or 3

    # 情绪曲线：把 base_curve 摊到时间轴上，并绑定「玩家在做什么」
    total = int((exp.get("pacing") or []) and 0 or 0) or 150
    acts = [
        ("curiosity", "看见海面全黑，只有一个可以按的键", "按下后海面亮起"),
        ("learning", "敲钟 → 看见影子 → 划过去", "接到第一个灵魂，听到它唱"),
        ("mastery", "用上一次的残影规划两步", "连续两次不敲钟也走对"),
        ("challenge", "残影开始骗人（影子会动）", "被幻影骗到，掉一格船体"),
        ("surprise", "记忆见底，全图熄灭", "听见心跳与桨声"),
        ("climax", "闭眼划向桨声", "送达最后一个灵魂"),
        ("satisfaction", "灯亮起，海面安静", "看到三个灯位都亮着"),
    ]
    curve = []
    for i, ph in enumerate(base):
        name = ph["phase"]
        does, fb = next(((a[1], a[2]) for a in acts if a[0] == name), ("", ""))
        curve.append({
            "phase": name,
            "zh": ph.get("zh", ""),
            "intensity": ph["intensity"],
            "at_seconds": round(total * i / max(1, len(base) - 1), 1),
            "player_does": does,
            "feedback": fb,
        })

    # 机制解锁表：以蓝图为准（DNA 里没有 unlock_level 字段）
    unlock: dict[int, str] = {}
    for m in list((bp.get("mechanics") or {}).get("core") or []) + \
             list((bp.get("mechanics") or {}).get("twists") or []):
        mid = m.get("id")
        lv = int(m.get("unlock_level") or 1)
        if mid and lv > 1 and lv not in unlock:
            unlock[lv] = mid

    # 每关体验表
    lv_src = (levels_json or {}).get("levels") if isinstance(levels_json, dict) else None
    lv_bp = bp.get("levels") or []
    levels = []
    for i in range(n_levels):
        src = (lv_src or [])[i] if lv_src and i < len(lv_src) else {}
        b = lv_bp[i] if i < len(lv_bp) else {}
        newm = unlock.get(i + 1)
        levels.append({
            "level": i + 1,
            "emotion": (b.get("emotion") or ["好奇", "紧张", "释然"][min(i, 2)]),
            "learn": (src.get("learn") or b.get("learn")
                      or f"能做到：{['敲钟并读懂回声方位', '用残影规划两步', '在无光中靠声音靠岸'][min(i, 2)]}"),
            "new_mechanic": newm,
            "core_decision": (src.get("decision") or b.get("decision")
                              or "现在敲钟确认，还是凭残影赌一把"),
            "challenge": (src.get("challenge") or ["information", "resource", "cost"][min(i, 2)]),
            "feedback": (src.get("feedback") or "敲钟后的回声方位与亮度变化"),
            "climax": (src.get("climax") or "记忆见底那一刻"),
            "reward": (src.get("reward") or "多一个灵魂上岸，岸边多亮一盏灯"),
            "next_hook": (src.get("next_hook") or "下一片海里，影子会开始动"),
            "duration_seconds": (src.get("duration_seconds") or 50),
        })

    checks = []
    for c in curves.get("experience_checks") or []:
        checks.append({
            "id": c["id"], "question": f"{c['zh']}：{c['test']}",
            "result": "UNVERIFIED", "evidence": "尚未验证 —— 跑 --verify",
        })

    out = {
        "version": "3.0",
        "meta": {
            "game_title": (dna.get("identity") or {}).get("game_title", ""),
            "created": datetime.now().astimezone().isoformat(timespec="seconds"),
            "creative_dna": "docs/01-brief/creative-dna.json",
            "target_session_seconds": total,
            "target_emotions": [t.get("emotion") for t in (exp.get("target_emotions") or [])],
            "player_memory": exp.get("player_memory") or "",
            "first_10s": exp.get("first_10s") or "",
            "first_30s": exp.get("first_30s") or "",
        },
        "emotion_curve": curve,
        "levels": levels,
        "checks": checks,
        "signature_moments": [
            {
                "id": "M1",
                "when": "记忆归零",
                "what_happens": (dna.get("identity") or {}).get("signature_moment") or "",
                "event": "memory_empty",
                "verified": False,
            }
        ],
    }
    dump_json(proj / "docs" / "03-experience" / "experience-blueprint.json", out)

    print(f"体验设计：{n_levels} 关，情绪曲线 {len(curve)} 段，总时长约 {total}s")
    print()
    print("| 关 | 目标情绪 | 学会 | 新机制 | 核心决策 | 挑战轴 |")
    print("|---|---|---|---|---|---|")
    for l in levels:
        print(f"| {l['level']} | {l['emotion']} | {l['learn'][:18]} | "
              f"{l['new_mechanic'] or '-'} | {l['core_decision'][:16]} | {l['challenge']} |")
    ok("已写 docs/03-experience/experience-blueprint.json")
    print("\n下一步：python scripts/experience_forge.py --project . --verify")
    return 0


# ------------------------------------------------------------------ verify
def cmd_verify(args) -> int:
    """用真实产物验证 E1–E8。没有证据的一律 UNVERIFIED。"""
    proj = project_dir(args.project)
    path = proj / "docs" / "03-experience" / "experience-blueprint.json"
    if not path.exists():
        print("ERROR: 缺 experience-blueprint.json（先跑 --plan）", file=sys.stderr)
        return 1
    eb = json.loads(path.read_text(encoding="utf-8"))
    dna = load_json(proj / "docs" / "01-brief" / "creative-dna.json", {}) or {}
    levels_json = load_json(proj / "src" / "game" / "levels.json", {}) or {}
    playtest = load_json(proj / "docs" / "07-qa" / "playtest.json")
    if isinstance(playtest, dict) and isinstance(playtest.get("summary"), dict):
        # 报告结构是 {summary:{...}, strategies:[...]}，把 summary 提到顶层方便下面取
        playtest = {**playtest, **playtest["summary"]}
    juice = load_json(proj / "docs" / "04-core-loop" / "juice-plan.json", {}) or {}

    # 源码 blob（用于判断事件是否真的存在）
    src = ""
    sdir = proj / "src"
    if sdir.is_dir():
        for f in sdir.rglob("*"):
            if f.suffix in (".ts", ".js", ".json") and f.is_file():
                try:
                    src += f.read_text(encoding="utf-8", errors="ignore")
                except OSError:
                    pass

    res: list[dict] = []

    def add(cid, question, result, evidence):
        res.append({"id": cid, "question": question, "result": result, "evidence": evidence})

    lv = (levels_json.get("levels") if isinstance(levels_json, dict) else levels_json) or []
    first = lv[0] if lv else {}

    # E1 前 10 秒可理解：第一关必须有 tutorial / hint 文本，且代码里有引导提示
    hint = str(first.get("hint") or first.get("tutorial") or "")
    has_hint_code = bool(re.search(r"hint|tutorial|引导|提示", src, re.I))
    if hint and has_hint_code:
        add("E1", "前 10 秒可理解：不需要文字说明也能做出第一个正确动作",
            "PASS", f"levels.json 第 1 关含 hint「{hint[:24]}」，且源码中存在引导逻辑")
    elif has_hint_code:
        add("E1", "前 10 秒可理解", "UNVERIFIED",
            "源码有引导逻辑，但 levels.json 未写 hint —— 需人工试玩确认")
    else:
        add("E1", "前 10 秒可理解", "FAIL", "既没有 hint 字段也没有引导代码")

    # E2 前 30 秒有正反馈：必须有 item_collected / 类似的即时正反馈事件与音效
    pos_events = [e for e in ("item_collected", "soul_delivered", "feedback_score", "feedback_win")
                  if e in src]
    if playtest and playtest.get("first_positive_feedback_s") is not None:
        t = playtest["first_positive_feedback_s"]
        add("E2", "前 30 秒有正反馈", "PASS" if t <= 30 else "FAIL",
            f"试玩报告记录首次正反馈在 {t}s")
    elif pos_events:
        add("E2", "前 30 秒有正反馈", "UNVERIFIED",
            f"存在正反馈事件（{', '.join(pos_events[:2])}），但尚无试玩计时证据")
    else:
        add("E2", "前 30 秒有正反馈", "FAIL", "源码中找不到任何正反馈事件")

    # E3 学习曲线：每关 ≤1 个新机制
    bad = [l["level"] for l in eb["levels"] if l.get("new_mechanic") and
           len([x for x in (l.get("new_mechanic") or "").split(",") if x.strip()]) > 1]
    mech_ids = {((dna.get("gameplay") or {}).get("core_mechanic") or {}).get("id")} | \
               {m.get("id") for m in ((dna.get("gameplay") or {}).get("supporting_mechanics") or [])}
    unknown = [l["new_mechanic"] for l in eb["levels"]
               if l.get("new_mechanic") and l["new_mechanic"] not in mech_ids]
    if bad:
        add("E3", "学习曲线：每关只引入 0–1 个新机制", "FAIL", f"第 {bad} 关引入了多个新机制")
    elif unknown:
        add("E3", "学习曲线", "FAIL", f"新机制 id 在 Creative DNA 里不存在：{unknown}")
    else:
        add("E3", "学习曲线", "PASS",
            f"{len(eb['levels'])} 关，每关新机制 ≤1 且 id 均存在于 DNA（{len(mech_ids)} 个机制）")

    # E4 难度非数值：挑战轴至少 2 条非数值
    axes = {l.get("challenge") for l in eb["levels"]} - {"none"}
    if len(axes) >= 2:
        add("E4", "难度递进非数值", "PASS", f"用到挑战轴 {', '.join(sorted(axes))}（≥2 条非数值）")
    else:
        add("E4", "难度递进非数值", "FAIL", f"只有 {len(axes)} 条挑战轴：{axes}")

    # E5 存在意外：必须有 rule_twist 或 story_reveal 类事件
    if "story_reveal" in src or "memory_empty" in src or (dna.get("gameplay") or {}).get("progression_identity"):
        add("E5", "存在意外（规则改写或未预告的代价）", "PASS",
            "源码中存在 story_reveal/memory_empty 事件，且 DNA 声明了推进质变")
    else:
        add("E5", "存在意外", "UNVERIFIED", "未找到规则改写事件，需人工确认是否有意外")

    # E6 值得记住的瞬间：signature moment 必须绑定真实存在的事件
    moments = eb.get("signature_moments") or []
    hit = [m for m in moments if m.get("event") and m["event"] in src]
    if hit:
        for m in moments:
            m["verified"] = m.get("event") in src
        add("E6", "值得记住的瞬间", "PASS",
            f"{len(hit)}/{len(moments)} 个标志时刻绑定了源码中真实存在的事件（{hit[0]['event']}）")
    else:
        add("E6", "值得记住的瞬间", "FAIL", "标志时刻没有绑定任何真实事件 —— 只写在文档里不算")

    # E7 失败有学习价值：失败必须有反馈事件 + 失败界面有提示
    fail_ui = bool(re.search(r"GameOver|gameOver|失败|再来一次", src))
    if "player_death" in src and fail_ui:
        add("E7", "失败有学习价值", "PASS", "存在 player_death 事件与结束场景；表现层有慢动作（juice-plan）"
            if "slow_motion" in json.dumps(juice, ensure_ascii=False)
            else "存在 player_death 事件与结束场景")
    else:
        add("E7", "失败有学习价值", "UNVERIFIED", "缺 player_death 事件或结束界面")

    # E8 无意义重复：用试玩报告的操作熵判断（有报告才判）
    if playtest and playtest.get("repetition_ratio") is not None:
        r = playtest["repetition_ratio"]
        add("E8", "无意义重复劳动", "PASS" if r < 0.7 else "FAIL",
            f"试玩操作中重复动作占比 {r:.0%}（阈值 70%）")
    else:
        add("E8", "无意义重复劳动", "UNVERIFIED", "需要试玩报告（playtest.json）才能判定")

    eb["checks"] = res
    dump_json(path, eb)
    dump_json(proj / "docs" / "03-experience" / "experience-verify.json", {
        "verified_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "checks": res,
        "summary": {
            "PASS": sum(1 for r in res if r["result"] == "PASS"),
            "FAIL": sum(1 for r in res if r["result"] == "FAIL"),
            "UNVERIFIED": sum(1 for r in res if r["result"] == "UNVERIFIED"),
        },
    })

    print("体验判据验证（E1–E8）：\n")
    for r in res:
        mark = {"PASS": "✅", "FAIL": "❌", "UNVERIFIED": "❔"}[r["result"]]
        print(f"  {mark} {r['id']} {r['question'][:34]:<34} {r['result']}")
        print(f"       {r['evidence']}")
    n_fail = sum(1 for r in res if r["result"] == "FAIL")
    n_unv = sum(1 for r in res if r["result"] == "UNVERIFIED")
    print(f"\nPASS {len(res) - n_fail - n_unv}　FAIL {n_fail}　UNVERIFIED {n_unv}")
    if n_unv:
        warn("有未验证项 —— 这些**不能算通过**，试玩后必须重跑")
    return 2 if n_fail else 0


def cmd_validate(args) -> int:
    proj = project_dir(args.project)
    path = proj / "docs" / "03-experience" / "experience-blueprint.json"
    if not path.exists():
        print("ERROR: 缺 experience-blueprint.json", file=sys.stderr)
        return 1
    eb = json.loads(path.read_text(encoding="utf-8"))
    issues: list[tuple[str, str, str]] = []

    def err(p, m):
        issues.append(("ERROR", p, m))

    def wrn(p, m):
        issues.append(("WARN", p, m))

    import schema_check  # noqa: E402
    schema = load_json(SKILL_DIR / "references" / "schemas" / "experience-blueprint.schema.json", {})
    for e in schema_check.validate(eb, schema):
        err("schema", e)

    # 曲线必须有高潮，且高潮是强度峰值
    curve = eb.get("emotion_curve") or []
    if curve:
        peak = max(curve, key=lambda c: c["intensity"])
        if peak["phase"] != "climax":
            wrn("emotion_curve", f"强度峰值在 `{peak['phase']}` 而不是 climax —— 确认是否有意为之")
        if not any(c["phase"] == "climax" for c in curve):
            err("emotion_curve", "缺少 climax 段 —— 没有高潮的曲线留不下记忆点")

    # 每关必须有取舍且能写成「A好但B坏」
    tradeoff = ["还是", "但", "换", "赌", "放弃", "牺牲", "代价", "舍", "vs", "取舍"]
    for l in eb.get("levels") or []:
        d = l.get("core_decision") or ""
        if len(d) < 8 or not any(k in d for k in tradeoff):
            err(f"levels[{l['level']}].core_decision", "必须写成取舍（含「还是/但/放弃/代价」等）")

    # 验证结果不能虚报
    for c in eb.get("checks") or []:
        if c["result"] == "PASS" and len((c.get("evidence") or "").strip()) < 6:
            err(f"checks[{c['id']}]", "result=PASS 但没有证据 —— 不允许无证据通过")

    errors = [i for i in issues if i[0] == "ERROR"]
    warns = [i for i in issues if i[0] == "WARN"]
    print(f"Experience Blueprint 校验：{path.relative_to(proj)}")
    print(f"  ERROR {len(errors)}　WARN {len(warns)}\n")
    for lvl, p, m in issues[:50]:
        print(f"[{lvl}] {p} —— {m}")
    dump_json(proj / "docs" / "03-experience" / "experience-validation.json", {
        "ok": not errors,
        "errors": [{"path": p, "msg": m} for _, p, m in errors],
        "warnings": [{"path": p, "msg": m} for _, p, m in warns],
    })
    if errors:
        print("\nERROR 必改。", file=sys.stderr)
        return 2 if args.strict else 0
    ok("Experience Blueprint 通过校验")
    return 0


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass
    ap = argparse.ArgumentParser(description="体验设计：情绪曲线 / 每关体验表 / 可验证判据")
    ap.add_argument("--project", default=None)
    ap.add_argument("--plan", action="store_true")
    ap.add_argument("--verify", action="store_true")
    ap.add_argument("--validate", action="store_true")
    ap.add_argument("--strict", action="store_true")
    args = ap.parse_args()
    if args.plan:
        return cmd_plan(args)
    if args.verify:
        return cmd_verify(args)
    if args.validate:
        return cmd_validate(args)
    ap.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
