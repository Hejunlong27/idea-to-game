#!/usr/bin/env python3
"""动画与表现力总监（Animation Director）：事件 → 表现的映射矩阵。

为什么需要它 —— v2 把 `cameras.main.shake()` 写死在 `PlayScene.hitTarget()` 里：
换玩法要重写一遍手感，且所有事件共用同一组 shake 参数，玩家分不清轻重。
任务书要求的 14 类效果里，v2 实际只有 shake 一种。

本脚本产出「矩阵」而不是「代码」：每个事件该触发哪几种效果、强度多少、为什么。
运行时由模板 `src/game/juice.ts` 执行（`--emit-ts` 生成配置）。

设计约束（都来自 animation-patterns.json 的 intensity_tiers 与 anti_patterns）：
  micro  1–2 个效果，无镜头无闪屏
  light  2–3 个效果，可轻微震动
  medium 3–4 个效果，可 hit stop 或 zoom
  heavy  5–6 个效果，可闪屏 + 慢动作
  —— 闪屏 ≤1 次/秒、震动 ≤300ms 是硬上限，不是建议

用法:
    python juice_forge.py --project . --plan
    python juice_forge.py --project . --emit-ts
    python juice_forge.py --project . --validate --strict

产物:
    docs/04-core-loop/juice-plan.json     ★ 表现矩阵
    src/game/juice-config.ts              运行时配置（由 --emit-ts 生成）
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import SKILL_DIR, dump_json, ok, project_dir, warn  # noqa: E402

DATA = SKILL_DIR / "assets" / "data"

# 事件严重度（与 src/game/events.ts 的 DEFAULT_INTENSITY 保持一致）
SEVERITY = {
    "game_start": 0.5, "game_over": 0.9, "player_move": 0.1, "player_action": 0.35,
    "player_hit": 0.7, "player_death": 1.0, "enemy_spawn": 0.3, "enemy_defeated": 0.6,
    "item_collected": 0.25, "level_started": 0.5, "level_completed": 0.9,
    "boss_appeared": 0.85, "boss_defeated": 1.0, "story_reveal": 0.6,
    "secret_found": 0.55, "resource_changed": 0.2, "state_changed": 0.3,
}

# 每个 tier 的「该有哪些效果」。顺序即执行顺序。
TIER_EFFECTS = {
    "micro": [("squash_stretch", 0.4), ("ui_motion", 0.3)],
    "light": [("squash_stretch", 0.8), ("particles", 8), ("ui_motion", 0.5)],
    "medium": [("squash_stretch", 1.0), ("particles", 14), ("camera_shake", 0.6), ("hit_stop", 60)],
    "heavy": [("squash_stretch", 1.0), ("particles", 32), ("camera_shake", 1.0),
              ("hit_stop", 90), ("camera_zoom", 1.0), ("screen_flash", 0.5)],
}

# 特殊事件覆盖（有明确设计意图的，不走通用分档）
OVERRIDES = {
    "player_death": {
        "tier": "heavy",
        "effects": [("slow_motion", 420), ("screen_flash", 0.7), ("camera_shake", 1.0),
                    ("particles", 24), ("hit_stop", 120)],
        "why": "死亡是唯一允许慢动作的时刻 —— 慢动作给玩家「看清自己怎么输的」的时间，这是失败的教学价值",
    },
    "level_completed": {
        "tier": "heavy",
        "effects": [("camera_zoom", 1.0), ("particles", 40), ("hit_stop", 90),
                    ("ui_motion", 1.0), ("screen_flash", 0.35)],
        "why": "完成用推近 + 粒子爆发 + UI 弹入，不用震动 —— 震动是「受击」的语义，混用会让玩家误判",
    },
    "player_move": {
        "tier": "micro",
        "effects": [("squash_stretch", 0.35), ("environmental", 0.5)],
        "why": "移动是最频繁的事件（每秒可能 2 次），任何镜头效果都会变成噪声；只做形变与水纹",
    },
    "story_reveal": {
        "tier": "medium",
        "effects": [("hit_stop", 220), ("particles", 12), ("ui_motion", 0.8), ("environmental", 0.9)],
        "why": "叙事揭示用「时间停顿 + 环境变化」而不是震动或闪屏 —— 停顿让人安静下来听，"
               "这是听觉优先的设计；闪屏会把注意力抢回画面",
    },
    "enemy_spawn": {
        "tier": "light",
        "effects": [("particles", 6), ("squash_stretch", 0.5), ("environmental", 0.6)],
        "why": "生成只是信息，不是威胁；威胁感由音频的低频负责，画面不抢",
    },
    # ---- 本作特有事件（回声摆渡）
    "echo_ping": {
        "tier": "medium",
        "effects": [("environmental", 1.0), ("particles", 10), ("hit_stop", 60)],
        "why": "敲钟是全局最重要的动作，但它必须「安静」：只做水纹扩散 + 极短停顿，"
               "不能震动（震动=受击语义），否则玩家会把主动发声当成被攻击",
    },
    "memory_spent": {
        "tier": "micro",
        "effects": [("ui_motion", 0.9), ("squash_stretch", 0.25)],
        "why": "记忆消耗每几秒就发生一次，只能做 UI 层面的轻微反馈；任何镜头效果都会疲劳",
    },
    "memory_empty": {
        "tier": "heavy",
        "effects": [("slow_motion", 500), ("hit_stop", 180), ("camera_zoom", 0.6),
                    ("particles", 20), ("environmental", 1.0)],
        "why": "这是本作的标志性时刻（全图熄灭）。用慢动作 + 长停顿让玩家意识到「地图没了」，"
               "不用闪屏 —— 闪屏是亮，这里需要的是暗",
    },
    "soul_delivered": {
        "tier": "medium",
        "effects": [("camera_zoom", 0.8), ("particles", 18), ("ui_motion", 1.0), ("environmental", 0.7)],
        "why": "正向事件不用震动：推近 + 粒子 + UI 弹入，与受击的语义严格区分",
    },
}


def tier_of(sev: float) -> str:
    if sev < 0.3:
        return "micro"
    if sev < 0.55:
        return "light"
    if sev < 0.8:
        return "medium"
    return "heavy"


def load_json(p: Path, default=None):
    if not p.exists():
        return default
    with p.open("r", encoding="utf-8") as f:
        return json.load(f)


def cmd_plan(args) -> int:
    proj = project_dir(args.project)
    dna = load_json(proj / "docs" / "01-brief" / "creative-dna.json", {}) or {}
    vd = load_json(proj / "docs" / "02-art" / "visual-dna.json", {}) or {}
    patterns = load_json(DATA / "creative-patterns" / "animation-patterns.json", {}) or {}
    valid_types = {e["id"] for e in (patterns.get("effects") or [])}

    accent = ((vd.get("color") or {}).get("accent") or ["#F2B04A"])[0]
    danger = (vd.get("color") or {}).get("danger") or "#C6463C"

    # 本作实际用到的事件：优先取 DNA 里出现过的机制/状态关键词，否则用标准集
    events = list(SEVERITY.keys())
    extra = []
    blob = json.dumps(dna, ensure_ascii=False)
    if "记忆" in blob:
        extra += ["memory_spent", "echo_ping", "memory_empty"]
    if "送达" in blob or "摆渡" in blob:
        extra += ["soul_delivered"]
    for e in extra:
        if e not in events:
            events.append(e)
            SEVERITY.setdefault(e, 0.55)

    rules = []
    for ev in events:
        sev = SEVERITY[ev]
        ov = OVERRIDES.get(ev)
        tier = ov["tier"] if ov else tier_of(sev)
        spec = ov["effects"] if ov else TIER_EFFECTS[tier]
        why = ov["why"] if ov else (
            f"严重度 {sev:.2f} → {tier} 档，按档位预算给 {len(spec)} 个效果；"
            f"不加大于本档的效果，否则会和更重要的事件抢注意力")
        effects = []
        for t, amount in spec:
            if t not in valid_types:
                warn(f"效果 `{t}` 不在 animation-patterns.json 里，已跳过")
                continue
            fx = {"type": t}
            if t in ("particles",):
                fx["amount"] = int(amount)
                fx["color"] = danger if sev >= 0.85 else accent
            elif t in ("camera_shake", "camera_zoom", "screen_flash", "squash_stretch",
                       "ui_motion", "environmental"):
                fx["scale"] = float(amount)
                if t == "screen_flash":
                    fx["color"] = danger if sev >= 0.85 else accent
            elif t in ("hit_stop", "slow_motion"):
                fx["durationMs"] = int(amount)
            effects.append(fx)
        rules.append({
            "event": ev,
            "severity": sev,
            "tier": tier,
            "minIntensity": 0.0 if sev >= 0.5 else 0.15,
            "effects": effects,
            "why": why,
        })

    distinct = {f["type"] for r in rules for f in r["effects"]}
    plan = {
        "version": "3.0",
        "meta": {
            "game_title": (dna.get("identity") or {}).get("game_title", ""),
            "created": datetime.now().astimezone().isoformat(timespec="seconds"),
            "judged_by": "assets/data/creative-patterns/animation-patterns.json",
            "creative_dna": "docs/01-brief/creative-dna.json",
            "visual_dna": "docs/02-art/visual-dna.json",
        },
        "settings": {
            "maxParticles": 120,
            "shakeCap": 0.012,
            "flashMaxPerSecond": 1,
            "shakeMaxMs": 300,
            "accentColor": accent,
            "dangerColor": danger,
            "qualityLevels": ["high", "medium", "low"],
        },
        "rules": rules,
        "coverage": {
            "distinct_effects": len(distinct),
            "events": len(rules),
            "tiers_used": sorted({r["tier"] for r in rules}),
            "effects_used": sorted(distinct),
            "unused_effects": sorted(valid_types - distinct),
        },
    }
    dump_json(proj / "docs" / "04-core-loop" / "juice-plan.json", plan)

    print(f"表现矩阵：{len(rules)} 个事件，{len(distinct)} 类效果")
    print(f"  覆盖档位：{', '.join(plan['coverage']['tiers_used'])}")
    print(f"  未使用效果：{', '.join(plan['coverage']['unused_effects']) or '无'}")
    print()
    print("| 事件 | 严重度 | 档位 | 效果 |")
    print("|---|---|---|---|")
    for r in rules:
        print(f"| {r['event']} | {r['severity']:.2f} | {r['tier']} | "
              f"{', '.join(f['type'] for f in r['effects'])} |")
    ok("已写 docs/04-core-loop/juice-plan.json")
    print("\n下一步：python scripts/juice_forge.py --project . --emit-ts")
    return 0


def cmd_emit_ts(args) -> int:
    proj = project_dir(args.project)
    plan = load_json(proj / "docs" / "04-core-loop" / "juice-plan.json")
    if not plan:
        print("ERROR: 缺 juice-plan.json（先跑 --plan）", file=sys.stderr)
        return 1
    s = plan["settings"]

    def fx_ts(f: dict) -> str:
        parts = [f"type: '{f['type']}'"]
        if "scale" in f:
            parts.append(f"scale: {f['scale']}")
        if "durationMs" in f:
            parts.append(f"durationMs: {f['durationMs']}")
        if "amount" in f:
            parts.append(f"amount: {f['amount']}")
        if "color" in f:
            parts.append(f"color: '{f['color']}'")
        return "{ " + ", ".join(parts) + " }"

    rules = ",\n  ".join(
        "{\n    event: '%s',\n    minIntensity: %s,\n    effects: [%s],\n  }" % (
            r["event"], r.get("minIntensity", 0),
            ", ".join(fx_ts(f) for f in r["effects"]))
        for r in plan["rules"])

    ts = f"""/* eslint-disable */
// 由 scripts/juice_forge.py --emit-ts 生成，**不要手改**。
// 真相源：docs/04-core-loop/juice-plan.json

export interface EffectSpec {{
  type:
    | 'squash_stretch'
    | 'anticipation'
    | 'follow_through'
    | 'secondary_motion'
    | 'parallax'
    | 'particles'
    | 'environmental'
    | 'ui_motion'
    | 'camera_shake'
    | 'camera_zoom'
    | 'hit_stop'
    | 'slow_motion'
    | 'screen_flash'
    | 'transition';
  scale?: number;
  durationMs?: number;
  amount?: number;
  color?: string;
}}

export interface JuiceRule {{
  event: string;
  minIntensity?: number;
  effects: EffectSpec[];
}}

export const JUICE_RULES: JuiceRule[] = [
  {rules},
];

export const JUICE_SETTINGS = {{
  maxParticles: {s['maxParticles']},
  shakeCap: {s['shakeCap']},
  flashMaxPerSecond: {s['flashMaxPerSecond']},
  shakeMaxMs: {s['shakeMaxMs']},
  accentColor: '{s['accentColor']}',
  dangerColor: '{s['dangerColor']}',
}};
"""
    out = proj / "src" / "game" / "juice-config.ts"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(ts, encoding="utf-8")
    ok(f"已生成运行时配置：{out.relative_to(proj)}（{len(plan['rules'])} 条规则）")
    return 0


def cmd_validate(args) -> int:
    proj = project_dir(args.project)
    path = proj / "docs" / "04-core-loop" / "juice-plan.json"
    if not path.exists():
        print("ERROR: 缺 juice-plan.json", file=sys.stderr)
        return 1
    plan = json.loads(path.read_text(encoding="utf-8"))
    issues: list[tuple[str, str, str]] = []

    def err(p, m):
        issues.append(("ERROR", p, m))

    def wrn(p, m):
        issues.append(("WARN", p, m))

    import schema_check  # noqa: E402
    schema = load_json(SKILL_DIR / "references" / "schemas" / "juice-plan.schema.json", {})
    for e in schema_check.validate(plan, schema):
        err("schema", e)

    patterns = load_json(DATA / "creative-patterns" / "animation-patterns.json", {}) or {}
    valid = {e["id"] for e in (patterns.get("effects") or [])}
    rules = plan.get("rules") or []

    # 反模式：所有事件同一强度
    sigs = {json.dumps([f["type"] for f in r["effects"]]) for r in rules}
    if len(sigs) < min(3, len(rules)):
        err("rules", "超过一半事件的表现在结构上相同 —— 玩家会分不清轻重（反模式 1）")

    # 反模式：闪屏用于低严重度事件
    for r in rules:
        for f in r["effects"]:
            if f["type"] == "screen_flash" and r["severity"] < 0.7:
                err(f"rules[{r['event']}]",
                    f"严重度 {r['severity']:.2f} 却用了闪屏 —— 闪屏只允许用于 ≥0.7 的事件")
            if f["type"] not in valid:
                err(f"rules[{r['event']}]", f"未知效果 `{f['type']}`")
            if f["type"] == "hit_stop" and (f.get("durationMs") or 0) > 200:
                wrn(f"rules[{r['event']}]", f"hit stop {f.get('durationMs')}ms 偏长（>200ms 会打断节奏）")

    # 关键事件必须被覆盖
    must = {"player_hit", "level_completed", "player_death", "item_collected"}
    covered = {r["event"] for r in rules}
    missing = must - covered
    if missing:
        err("rules", f"缺少关键事件的表现设计：{', '.join(sorted(missing))}")

    # 覆盖度：不能只靠 shake
    used = {f["type"] for r in rules for f in r["effects"]}
    if len(used) < 8:
        wrn("coverage", f"只用了 {len(used)} 类效果（建议 ≥8）—— 表现手段偏单一")
    if "camera_shake" in used and used <= {"camera_shake", "particles", "squash_stretch"}:
        err("coverage", "表现只有震动/粒子/形变三种 —— 等于把 v2 的做法包了一层")

    # 硬上限
    s = plan.get("settings") or {}
    if (s.get("flashMaxPerSecond") or 0) > 1:
        err("settings.flashMaxPerSecond", "闪屏频率上限不得 > 1 次/秒（光敏性癫痫）")
    if (s.get("shakeMaxMs") or 0) > 300:
        err("settings.shakeMaxMs", "震动时长上限不得 > 300ms（晕动）")

    errors = [i for i in issues if i[0] == "ERROR"]
    warns = [i for i in issues if i[0] == "WARN"]
    print(f"Juice Plan 校验：{path.relative_to(proj)}")
    print(f"  ERROR {len(errors)}　WARN {len(warns)}　效果覆盖 {len(used)} 类\n")
    for lvl, p, m in issues[:50]:
        print(f"[{lvl}] {p} —— {m}")
    dump_json(proj / "docs" / "04-core-loop" / "juice-validation.json", {
        "ok": not errors,
        "errors": [{"path": p, "msg": m} for _, p, m in errors],
        "warnings": [{"path": p, "msg": m} for _, p, m in warns],
        "distinct_effects": len(used),
    })
    if errors:
        print("\nERROR 必改。", file=sys.stderr)
        return 2 if args.strict else 0
    ok("Juice Plan 通过校验")
    return 0


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass
    ap = argparse.ArgumentParser(description="表现矩阵：事件 → 效果组合")
    ap.add_argument("--project", default=None)
    ap.add_argument("--plan", action="store_true")
    ap.add_argument("--emit-ts", action="store_true")
    ap.add_argument("--validate", action="store_true")
    ap.add_argument("--strict", action="store_true")
    args = ap.parse_args()
    if args.plan:
        return cmd_plan(args)
    if getattr(args, "emit_ts"):
        return cmd_emit_ts(args)
    if args.validate:
        return cmd_validate(args)
    ap.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
