#!/usr/bin/env python3
"""阶段产物校验（门禁检查）。阶段完成前必须跑一次。

用法:
    python gate_check.py --project <proj> --stage brief
    python gate_check.py --project <proj> --stage all
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import STAGES, iter_files, project_dir  # noqa: E402

REQUIRED_FILES = {
    "brief": [
        "docs/00-platforms/platform-plan.md",
        "docs/01-brief/gdd.md",
        "docs/01-brief/scope.json",
    ],
    "scaffold": [
        "package.json",
        "index.html",
        "vite.config.ts",
        "src/main.ts",
        "src/types.ts",
        "src/platform/index.ts",
        "src/platform/mock.ts",
        "src/platform/crazygames.ts",
        "src/platform/poki.ts",
        "src/platform/playgama.ts",
        "src/platform/gamedistribution.ts",
        "src/platform/taptap.ts",
    ],
    "creative": [
        "docs/01-brief/creative-concepts.json",
        "docs/01-brief/creative-review.md",
    ],
    "creative_dna": [
        "docs/01-brief/creative-dna.json",
        "docs/01-brief/creative-validation.json",
    ],
    "content": [
        "docs/01-brief/content-blueprint.json",
        "docs/01-brief/story.md",
    ],
    "review_richness": ["docs/09-review/richness.json", "docs/09-review/richness-report.md"],
    "art_bible": ["docs/02-art/art-bible.md", "docs/02-art/palette.json"],
    "visual_dna": [
        "docs/02-art/visual-dna.json",
        "docs/02-art/style-proposals.json",
        "docs/02-art/consistency-plan.json",
    ],
    "core_loop": ["docs/04-core-loop/notes.md", "src/game"],
    "art_forge": ["assets/raw"],
    "sprite_tools": ["assets/processed", "assets/atlas"],
    "audio_forge": ["assets/audio/bgm", "assets/audio/sfx"],
    "audio_director": [
        "docs/05-audio/audio-dna.json",
        "docs/05-audio/audio-qc.json",
        "docs/05-audio/stem-render-plan.json",
    ],
    "juice": ["docs/04-core-loop/juice-plan.json"],
    "experience": ["docs/03-experience/experience-blueprint.json"],
    "playtest": ["docs/07-qa/playtest.json", "docs/07-qa/playtest-report.html"],
    "review_specialist": ["docs/09-review/verdict-specialist.json"],
    "polish": ["docs/05-polish/juice-log.md"],
    "perf_audit": ["docs/06-perf/report.md"],
    "qa": ["docs/07-qa/report.html"],
    "review_plan": ["docs/09-review/r0-plan-review.md", "docs/09-review/verdict-r0.json"],
    "review_graybox": ["docs/09-review/r1-graybox-review.md", "docs/09-review/verdict-r1.json"],
    "review_final": [
        "docs/09-review/r2-final-review.md",
        "docs/09-review/verdict-r2.json",
        "docs/09-review/checklist.md",
        "docs/09-review/issues.json",
    ],
    "ship": ["docs/08-ship/submit-checklist.md", "docs/08-ship/store-copy.md"],
}


def nonempty_dir(p: Path) -> bool:
    return p.is_dir() and any(p.iterdir())


def check_brief(proj: Path, errs: list, warns: list):
    # 先校验平台确认（门禁 G0）—— 未确认平台不得进入立项
    state_file = proj / ".gamedev" / "state.yaml"
    if state_file.exists():
        from _common import load_state

        try:
            st = load_state(proj)
        except SystemExit:
            st = {}
        d = (st or {}).get("delivery", {}) or {}
        plats = d.get("platforms") or []
        if not plats:
            errs.append(
                "尚未确认目标平台（delivery.platforms 为空）—— 必须先执行 modules/00-platforms.md 的 G0 门禁"
            )
        elif not d.get("platform_confirmed"):
            errs.append(
                f"目标平台 {plats} 已设置但未经用户确认（platform_confirmed=false）—— "
                "确认后执行 state.py set-platforms --confirm"
            )

    sp = proj / "docs/01-brief/scope.json"
    if not sp.exists():
        return
    try:
        data = json.loads(sp.read_text(encoding="utf-8"))
    except Exception as e:
        errs.append(f"scope.json 解析失败：{e}")
        return
    for key in ("genre", "core_loop", "controls", "mvp_features", "out_of_scope", "assets"):
        if key not in data:
            errs.append(f"scope.json 缺少字段：{key}")
    mvp = data.get("mvp_features") or []
    if len(mvp) > 6:
        errs.append(f"MVP 功能 {len(mvp)} 项，超出上限 6 项（v2：每个功能应对应一个机制，机制合计 ≥5）")
    if not data.get("out_of_scope"):
        warns.append("out_of_scope 为空，说明没有做取舍，范围可能失控")
    assets = data.get("assets") or {}
    total = sum(len(v) for v in assets.values() if isinstance(v, list))
    if total > 40:
        warns.append(f"素材总数 {total} 个，超出建议上限 40 个（v2 需要覆盖 6 类 role）")


def check_content(proj: Path, errs: list, warns: list):
    """内容蓝图完整性：必填槽位填满 + 机制 id 真实咬合。"""
    bp_file = proj / "docs" / "01-brief" / "content-blueprint.json"
    if not bp_file.exists():
        errs.append("缺 content-blueprint.json（跑 content_forge.py --scaffold）")
        return
    try:
        bp = json.loads(bp_file.read_text(encoding="utf-8"))
    except Exception as e:  # noqa: BLE001
        errs.append(f"content-blueprint.json 解析失败：{e}")
        return

    def todo_count(o) -> int:
        if isinstance(o, dict):
            return sum(todo_count(v) for k, v in o.items() if k != "_todo") + (1 if "_todo" in o else 0)
        if isinstance(o, list):
            return sum(todo_count(v) for v in o)
        return 0

    left = todo_count(bp)
    if left:
        warns.append(f"蓝图仍有 {left} 处 _todo 标记（说明性注释，可保留但需确认内容已填）")

    w = bp.get("world") or {}
    if len((w.get("logline") or "").strip()) < 16:
        errs.append("world.logline 不足 16 字")
    if len(w.get("rules") or []) < 3:
        errs.append(f"world.rules 需 ≥3 条（当前 {len(w.get('rules') or [])}）")

    s = bp.get("story") or {}
    pr = s.get("protagonist") or {}
    if not all((pr.get(k) or "").strip() for k in ("want", "need", "flaw", "arc")):
        errs.append("story.protagonist 的 want/need/flaw/arc 未填全")
    if (pr.get("want") or "").strip() and pr.get("want") == pr.get("need"):
        errs.append("story.protagonist 的 want 与 need 相同（弧光不成立）")
    if len(s.get("acts") or []) != 3:
        errs.append("story.acts 必须是 3 幕")
    if len(s.get("dialogue") or []) < 12:
        errs.append(f"story.dialogue 需 ≥12 条（当前 {len(s.get('dialogue') or [])}）")

    m = bp.get("mechanics") or {}
    mechs = list(m.get("core") or []) + list(m.get("twists") or [])
    if len(mechs) < 5:
        errs.append(f"机制合计需 ≥5 个（当前 {len(mechs)}）")
    ids = {x.get("id") for x in mechs if x.get("id")}
    orphans = [x.get("id") for x in mechs
               if not [r for r in (x.get("interacts") or []) if r in ids and r != x.get("id")]]
    if orphans:
        errs.append(f"机制咬合缺失（interacts 为空或引用无效）：{', '.join(str(o) for o in orphans)}")

    lv = bp.get("levels") or []
    bad = [x.get("level") for x in lv if not (x.get("decision") or "").strip()]
    if bad:
        errs.append(f"关卡缺 decision（取舍）：第 {bad} 关")


def check_richness(proj: Path, errs: list, warns: list):
    """丰富度门禁：读 richness.json，非 RICH 即阻断。"""
    f = proj / "docs" / "09-review" / "richness.json"
    if not f.exists():
        errs.append("缺 richness.json（跑 richness_check.py）")
        return
    try:
        d = json.loads(f.read_text(encoding="utf-8"))
    except Exception as e:  # noqa: BLE001
        errs.append(f"richness.json 解析失败：{e}")
        return
    v = d.get("verdict")
    total = d.get("total", 0)
    if v != "RICH":
        errs.append(f"丰富度未达标：{v}（{total:.1f}/100）——见 docs/09-review/richness-report.md")
    else:
        warns.append(f"丰富度 {total:.1f}/100 RICH")
    for c in d.get("cross_checks") or []:
        if not c.get("ok"):
            errs.append(f"交叉校验 {c.get('code')} 失败：{c.get('detail')}")


def _schema_errs(proj: Path, rel: str, schema_name: str) -> list[str]:
    """用 schema_check 校验一份产物。缺文件返回空（由 REQUIRED_FILES 报）。"""
    p = proj / rel
    if not p.exists():
        return []
    from _common import SKILL_DIR
    import schema_check

    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        schema = json.loads((SKILL_DIR / "references" / "schemas" / schema_name).read_text(encoding="utf-8"))
    except Exception as e:  # noqa: BLE001
        return [f"{rel} 解析失败：{e}"]
    return [f"{rel}：{x}" for x in schema_check.validate(data, schema)]


def check_creative(proj: Path, errs: list, warns: list):
    """创意门禁：必须真的发散过，且结构差异达标。"""
    f = proj / "docs/01-brief/creative-concepts.json"
    if not f.exists():
        errs.append("缺 creative-concepts.json（跑 creative_forge.py --diverge）")
        return
    try:
        d = json.loads(f.read_text(encoding="utf-8"))
    except Exception as e:  # noqa: BLE001
        errs.append(f"creative-concepts.json 解析失败：{e}")
        return
    n = len(d.get("concepts") or [])
    if n < 5:
        errs.append(f"创意方案只有 {n} 个（要求 ≥5，且必须在核心交互上实质不同）")
    sd = d.get("structural_distance") or {}
    if not sd.get("pass"):
        errs.append(
            f"方案结构差异不足：最小两两距离 {sd.get('min_pairwise')}/5（要求 ≥3）—— 这是换皮的判据"
        )
    ev = d.get("evaluation") or []
    if not ev:
        warns.append("尚未跑 creative_forge.py --evaluate（没有相似度分析）")
    else:
        best = d.get("best") or ""
        top = next((x for x in ev if x.get("concept_id") == best), None)
        if top and top.get("verdict") == "REJECT":
            errs.append(f"最佳方案 {best} 仍判 REJECT（{top.get('total')} 分）")


def check_creative_dna(proj: Path, errs: list, warns: list):
    errs += _schema_errs(proj, "docs/01-brief/creative-dna.json", "creative-dna.schema.json")
    v = proj / "docs/01-brief/creative-validation.json"
    if v.exists():
        try:
            d = json.loads(v.read_text(encoding="utf-8"))
            if not d.get("ok"):
                for e in (d.get("errors") or [])[:5]:
                    errs.append(f"DNA 语义校验失败 {e.get('path')}：{e.get('msg')}")
        except Exception:  # noqa: BLE001
            warns.append("creative-validation.json 解析失败")
    else:
        warns.append("未跑 creative_forge.py --validate")


def check_visual_dna(proj: Path, errs: list, warns: list):
    errs += _schema_errs(proj, "docs/02-art/visual-dna.json", "visual-dna.schema.json")
    v = proj / "docs/02-art/visual-dna.json"
    if v.exists():
        try:
            d = json.loads(v.read_text(encoding="utf-8"))
            bad = [c for c in (d.get("color") or {}).get("contrast_checks") or [] if not c.get("pass")]
            if bad:
                errs.append(f"色彩对比度不达标 {len(bad)} 组：{bad[0].get('pair')} {bad[0].get('ratio')}")
            con = (d.get("character") or {}).get("consistency") or {}
            if con.get("status") == "full_ref_chain":
                refs = con.get("refs") or []
                if not any((proj / r.get("file", "")).exists() for r in refs):
                    errs.append("一致性状态声明 full_ref_chain 但参考图不存在（虚报）")
            elif con.get("status") in ("degraded_no_ref", "prompt_only", "seed_only"):
                warns.append(f"角色一致性为降级状态 `{con.get('status')}` —— 交付报告须如实列出")
        except Exception:  # noqa: BLE001
            pass
    p = proj / "docs/02-art/palette.json"
    if p.exists():
        try:
            pal = json.loads(p.read_text(encoding="utf-8"))
            if not pal.get("style_tokens"):
                errs.append("palette.json 缺 style_tokens")
        except Exception:  # noqa: BLE001
            pass


def check_audio_director(proj: Path, errs: list, warns: list):
    errs += _schema_errs(proj, "docs/05-audio/audio-dna.json", "audio-dna.schema.json")
    q = proj / "docs/05-audio/audio-qc.json"
    if q.exists():
        try:
            d = json.loads(q.read_text(encoding="utf-8"))
            v = d.get("verdict")
            if v == "FAIL":
                s = d.get("summary") or {}
                errs.append(
                    f"音频质检 FAIL：缺失 {s.get('missing')}、削波 {s.get('clipped')}、静音 {s.get('silent')}"
                )
            elif v == "WARN":
                warns.append(f"音频质检 WARN（接缝或体积）：{d.get('total_kb')}KB")
        except Exception:  # noqa: BLE001
            errs.append("audio-qc.json 解析失败")
    else:
        warns.append("未跑 audio_director.py --qc（音频审核会因缺实测判 UNVERIFIED）")
    ad = proj / "docs/05-audio/audio-dna.json"
    if ad.exists():
        try:
            d = json.loads(ad.read_text(encoding="utf-8"))
            states = (d.get("music") or {}).get("states") or []
            sigs = {json.dumps(st.get("stem_gains") or {}, sort_keys=True) for st in states}
            if len(states) >= 2 and len(sigs) < len(states):
                errs.append("有两个音乐状态的分轨配比完全相同 —— 状态切换听不出区别")
        except Exception:  # noqa: BLE001
            pass


def check_juice(proj: Path, errs: list, warns: list):
    errs += _schema_errs(proj, "docs/04-core-loop/juice-plan.json", "juice-plan.schema.json")
    f = proj / "docs/04-core-loop/juice-plan.json"
    if not f.exists():
        return
    try:
        d = json.loads(f.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return
    used = {fx["type"] for r in d.get("rules") or [] for fx in r.get("effects") or []}
    if len(used) < 8:
        warns.append(f"表现只用了 {len(used)} 类效果（建议 ≥8）")
    s = d.get("settings") or {}
    if (s.get("flashMaxPerSecond") or 0) > 1:
        errs.append("闪屏频率上限 >1 次/秒（光敏性风险，硬上限）")
    if (s.get("shakeMaxMs") or 0) > 300:
        errs.append("震动时长上限 >300ms（晕动风险，硬上限）")


def check_experience(proj: Path, errs: list, warns: list):
    errs += _schema_errs(proj, "docs/03-experience/experience-blueprint.json",
                         "experience-blueprint.schema.json")
    f = proj / "docs/03-experience/experience-blueprint.json"
    if not f.exists():
        return
    try:
        d = json.loads(f.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return
    checks = d.get("checks") or []
    fails = [c for c in checks if c.get("result") == "FAIL"]
    unv = [c for c in checks if c.get("result") == "UNVERIFIED"]
    if fails:
        errs.append(f"体验判据有 {len(fails)} 条 FAIL：{', '.join(c['id'] for c in fails)}")
    if unv:
        warns.append(f"体验判据有 {len(unv)} 条未验证（未验证不算通过）：{', '.join(c['id'] for c in unv)}")


def check_playtest(proj: Path, errs: list, warns: list):
    f = proj / "docs/07-qa/playtest.json"
    if not f.exists():
        errs.append("缺 playtest.json（跑 playtest.py 或 node scripts/playtest.mjs）")
        return
    try:
        d = json.loads(f.read_text(encoding="utf-8"))
    except Exception as e:  # noqa: BLE001
        errs.append(f"playtest.json 解析失败：{e}")
        return
    s = d.get("summary") or {}
    if s.get("errors"):
        errs.append(f"试玩期间有 {len(s['errors'])} 条运行时错误：{str(s['errors'][0])[:80]}")
    if s.get("any_stuck"):
        errs.append("试玩检测到卡死（连续 6 秒状态不变）")
    fp = s.get("first_positive_feedback_s")
    if fp is not None and fp < 999 and fp > 30:
        warns.append(f"首次正反馈在 {fp}s（要求 ≤30s）")
    if len(d.get("strategies") or []) < 3:
        warns.append("试玩策略少于 3 种，覆盖不足")


def check_specialist(proj: Path, errs: list, warns: list):
    f = proj / "docs/09-review/verdict-specialist.json"
    if not f.exists():
        errs.append("缺 verdict-specialist.json（跑 specialist_review.py）")
        return
    try:
        d = json.loads(f.read_text(encoding="utf-8"))
    except Exception as e:  # noqa: BLE001
        errs.append(f"verdict-specialist.json 解析失败：{e}")
        return
    v = d.get("verdict")
    if v == "FAIL":
        bl = [b for b in d.get("blocking") or [] if b.get("result") == "FAIL"]
        detail = "；".join(f"{b['code']} {b['title']}" for b in bl[:4])
        errs.append(f"专项审核 FAIL，不得通过 —— 阻塞项：{detail}")
    elif v == "INCOMPLETE":
        bl = [b for b in d.get("blocking") or [] if b.get("result") == "UNVERIFIED"]
        errs.append(
            "专项审核 INCOMPLETE（有未验证项，未验证不算通过）："
            + "；".join(f"{b['code']} {b['title']}" for b in bl[:4])
        )
    else:
        warns.append(f"专项审核 PASS（{d.get('summary', {}).get('PASS')} 条证据）")


def check_scaffold(proj: Path, errs: list, warns: list):
    gd = proj / "src/game"
    if gd.is_dir():
        pat = re.compile(r"""from\s+['"][^'"]*platform|require\(['"][^'"]*platform""")
        for f in iter_files(gd):
            if f.suffix in (".ts", ".tsx", ".js", ".mjs"):
                if pat.search(f.read_text(encoding="utf-8", errors="ignore")):
                    errs.append(f"src/game 内出现平台适配层引用（违反契约）：{f.relative_to(proj).as_posix()}")
    html = proj / "index.html"
    if html.exists():
        t = html.read_text(encoding="utf-8", errors="ignore")
        if "user-select" not in t:
            errs.append("index.html 缺少 user-select: none（CrazyGames 移动端要求）")
        if "viewport" not in t:
            warns.append("index.html 缺少 viewport meta")


def check_art_bible(proj: Path, errs: list, warns: list):
    pj = proj / "docs/02-art/palette.json"
    if not pj.exists():
        return
    try:
        data = json.loads(pj.read_text(encoding="utf-8"))
    except Exception as e:
        errs.append(f"palette.json 解析失败：{e}")
        return
    if not data.get("style_tokens"):
        errs.append("palette.json 缺少 style_tokens（风格一致性锚点，必须提供）")
    prim = data.get("primary") or []
    if not (5 <= len(prim) <= 8):
        warns.append(f"主色板 {len(prim)} 色，建议 5–8 色")
    prompts = proj / "docs/02-art/prompts"
    if not nonempty_dir(prompts):
        errs.append("docs/02-art/prompts/ 为空，未产出素材提示词")
    else:
        missing = []
        for f in prompts.iterdir():
            if f.is_file() and f.suffix == ".txt":
                if data.get("style_tokens") and data["style_tokens"] not in f.read_text(encoding="utf-8", errors="ignore"):
                    missing.append(f.name)
        if missing:
            errs.append(f"以下提示词未包含 style_tokens：{', '.join(missing)}")


def check_audio(proj: Path, errs: list, warns: list):
    total = 0
    for sub in ("assets/audio/bgm", "assets/audio/sfx"):
        d = proj / sub
        if not nonempty_dir(d):
            errs.append(f"{sub}/ 为空")
            continue
        for f in d.iterdir():
            if f.is_file():
                total += f.stat().st_size
                if f.suffix.lower() == ".wav":
                    errs.append(f"音频使用 wav（体积过大）：{f.relative_to(proj).as_posix()}")
    if total > 2 * 1024 * 1024:
        errs.append(f"音频总体积 {total / 1048576:.1f}MB，超出 2MB 预算")
    sfx = proj / "assets/audio/sfx"
    if sfx.is_dir():
        n_sfx = len([f for f in sfx.iterdir() if f.is_file()])
        # v2：音效不再是"越少越好"，四层结构要求 ≥16（content-depth.md U1）
        if n_sfx < 16:
            warns.append(f"音效 {n_sfx} 个，低于丰富度要求的 16 个（见 content-depth.md U1）")
        elif n_sfx > 32:
            warns.append(f"音效 {n_sfx} 个，超过 32 个可能超出 400KB 预算")


def check_sprite_tools(proj: Path, errs: list, warns: list):
    atlas = proj / "assets/atlas"
    if not atlas.is_dir():
        return
    jsons = [f for f in atlas.iterdir() if f.suffix == ".json"]
    pngs = [f for f in atlas.iterdir() if f.suffix == ".png"]
    if not jsons:
        errs.append("assets/atlas/ 中无图集 json")
    if not pngs:
        errs.append("assets/atlas/ 中无图集 png")
    for j in jsons:
        try:
            d = json.loads(j.read_text(encoding="utf-8"))
        except Exception as e:
            errs.append(f"{j.name} 解析失败：{e}")
            continue
        if "frames" not in d or not d["frames"]:
            errs.append(f"{j.name} 缺少 frames")
        meta_img = (d.get("meta") or {}).get("image")
        if meta_img and not (atlas / meta_img).exists():
            errs.append(f"{j.name} 引用的图集图不存在：{meta_img}")


def check_art_forge(proj: Path, errs: list, warns: list):
    """校验生图台账：提示词是否都出了图、有没有降级项。"""
    raw = proj / "assets" / "raw"
    mf = raw / "manifest.json"
    prompts = []
    pdir = proj / "docs" / "02-art" / "prompts"
    if pdir.is_dir():
        prompts = sorted(p.stem for p in pdir.glob("*.txt"))
    if not mf.exists():
        has_png = raw.is_dir() and any(raw.glob("*.png"))
        if has_png:
            warns.append(
                "assets/raw/ 有图片但缺少 manifest.json —— 无法追溯 provider / seed / 降级项"
                "（用 gen_assets.py 生成会自动写台账）"
            )
        return
    try:
        data = json.loads(mf.read_text(encoding="utf-8"))
    except Exception as e:  # noqa: BLE001
        errs.append(f"manifest.json 解析失败：{e}")
        return
    assets = data.get("assets") or {}
    degraded = [k for k, v in assets.items() if (v or {}).get("status") == "degraded"]
    if degraded:
        warns.append(
            f"{len(degraded)} 个素材为降级产物（占位兜底）：{', '.join(degraded[:6])}"
            " —— 最终交付报告必须列出，不得当成品交付"
        )
    ph = [k for k, v in assets.items() if (v or {}).get("provider") == "placeholder"]
    if ph and len(ph) == len(assets):
        warns.append("全部素材都是程序化占位 —— 只有 L1 可玩档位，不能作为 L2/L3 交付")
    # 网格模式（kind=sheet/frames）的提示词文件名（如 slimes）不会出现在 manifest 里，
    # 要按 sidecar 声明的格子名核对，否则永远误报「有提示词没出图」。
    expected: list[str] = []
    for stem in prompts:
        side = pdir / f"{stem}.json"
        kind = ""
        if side.exists():
            try:
                kind = str((json.loads(side.read_text(encoding="utf-8")) or {}).get("kind") or "")
            except Exception:  # noqa: BLE001
                kind = ""
        if kind in ("sheet", "frames"):
            try:
                spec = json.loads(side.read_text(encoding="utf-8"))
                grid = str(spec.get("grid") or "1x1").lower()
                rows, cols = (int(x) for x in grid.split("x"))
                items = [str(x) for x in (spec.get("items") or [])]
                if kind == "sheet" and items:
                    expected += items[: rows * cols]
                else:
                    n = int(spec.get("frames") or rows * cols)
                    expected += [f"{stem}_{i}" for i in range(n)]
            except Exception:  # noqa: BLE001
                expected.append(stem)
        else:
            expected.append(stem)
    missing = [n for n in expected if n not in assets]
    if missing:
        errs.append(
            f"以下素材有提示词但没有出图：{', '.join(missing[:8])}"
            + (" …" if len(missing) > 8 else "")
            + " —— 跑 gen_assets.py 补齐（--only 可单类补）"
        )


def check_qa(proj: Path, errs: list, warns: list):
    shot_dir = proj / "docs" / "07-qa" / "screenshots"
    shots = []
    if shot_dir.is_dir():
        shots = [p for p in shot_dir.iterdir() if p.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}]
    if len(shots) < 3:
        errs.append(
            f"实机截图不足（{len(shots)}/3）—— 商店提交必须有 3 张实机截图，跑 `npm run shots` 生成"
        )
    sj = shot_dir / "shots.json"
    if sj.exists():
        try:
            d = json.loads(sj.read_text(encoding="utf-8"))
            errs_list = d.get("errors") or []
            if errs_list:
                warns.append(f"截图时控制台有 {len(errs_list)} 条错误：{str(errs_list[0])[:120]}")
        except Exception:  # noqa: BLE001
            warns.append("shots.json 解析失败")


def check_review(proj: Path, errs: list, warns: list, phase: str):
    """校验审核结论（R0/R1/R2）。REJECTED / INCOMPLETE 一律视为未通过。"""
    from _common import PASSING_VERDICTS

    # 按阶段分文件存放（单文件会被后一轮覆盖）
    candidates = [proj / f"docs/09-review/verdict-{phase}.json", proj / "docs/09-review/verdict.json"]
    vj = next((c for c in candidates if c.exists()), None)
    if vj is None:
        errs.append(
            f"缺少 docs/09-review/verdict-{phase}.json —— 本阶段必须先跑 "
            f"`review_gate.py --phase {phase}` 并由审核官给出结论"
        )
        return
    try:
        v = json.loads(vj.read_text(encoding="utf-8"))
    except Exception as e:
        errs.append(f"{vj.name} 解析失败：{e}")
        return

    if v.get("phase") != phase and vj.name == "verdict.json":
        errs.append(
            f"verdict.json 记录的是 {v.get('phase')} 轮结论，本阶段需要 {phase} 轮的结论 —— "
            f"请重跑 review_gate.py --phase {phase}"
        )
    verdict = v.get("verdict")
    if verdict not in PASSING_VERDICTS:
        blockers = v.get("blockers") or []
        detail = "; ".join(f"{b.get('item')} {b.get('desc')}" for b in blockers[:4])
        errs.append(
            f"审核结论为 {verdict}，不得通过 —— "
            + (f"阻塞项：{detail}" if detail else "人工条目未判定完（INCOMPLETE）")
        )
    if verdict == "PASS_WITH_DEVIATIONS":
        devs = v.get("deviations") or []
        warns.append(
            f"存在 {len(devs)} 条建议项偏离，交付报告只能写「达到必需标准」，"
            f"并须列出偏离清单：{', '.join(d.get('item', '') for d in devs)}"
        )

    mj = proj / "docs/09-review/manual-checks.json"
    if mj.exists():
        try:
            m = json.loads(mj.read_text(encoding="utf-8"))
            unfilled = [k for k, v2 in m.items() if not (v2 or {}).get("result")]
            if unfilled:
                warns.append(f"manual-checks.json 尚有 {len(unfilled)} 条未判定：{', '.join(unfilled[:8])}")
        except Exception:
            warns.append("manual-checks.json 解析失败")


def check_ship(proj: Path, errs: list, warns: list):
    from _common import PLATFORM_KEYS, load_state

    # ★ 审核官一票否决：R2 终审未通过则不得交付
    check_review(proj, errs, warns, "r2")
    # ★ v3：六项专项审核同样一票否决（创意/美术/动画/音频/体验/试玩）
    check_specialist(proj, errs, warns)

    state_file = proj / ".gamedev" / "state.yaml"
    platforms = []
    stages = {}
    if state_file.exists():
        try:
            st = load_state(proj)
            platforms = ((st or {}).get("delivery", {}) or {}).get("platforms") or []
            stages = (st or {}).get("stages", {}) or {}
        except SystemExit:
            pass

    # R0 / R1 也必须已完成（审核环节不可跳过）
    for key, rnd in (("review_plan", "R0"), ("review_graybox", "R1")):
        node = stages.get(key) or {}
        if node.get("status") != "done":
            errs.append(f"{rnd} 审核阶段未完成（{key}.status={node.get('status', 'pending')}）—— 审核环节不可跳过")

    dist = proj / "dist"
    if not platforms:
        errs.append("未记录目标平台，无法校验交付包与平台是否一致（请先完成 G0）")
        return

    # 交付包必须与用户选定的平台完全一致（不多不少）
    missing, extra = [], []
    for p in platforms:
        if p not in PLATFORM_KEYS:
            errs.append(f"delivery.platforms 含未知平台：{p}")
            continue
        d = dist / p
        z = dist / f"{p}.zip"
        if not d.is_dir() and not z.exists():
            missing.append(p)
    if dist.is_dir():
        for item in dist.iterdir():
            name = item.name[:-4] if item.name.endswith(".zip") else item.name
            if item.is_dir() or item.name.endswith(".zip"):
                if name in PLATFORM_KEYS and name not in platforms:
                    extra.append(name)
            elif item.is_file():
                continue
    if missing:
        errs.append(f"缺少选定平台的交付产物：{', '.join(missing)}")
    if extra:
        errs.append(
            f"存在未在用户选定范围内的平台产物：{', '.join(sorted(set(extra)))} "
            "—— 交付包必须与用户回复的平台一致"
        )

    for p in platforms:
        z = dist / f"{p}.zip"
        if z.exists() and z.stat().st_size == 0:
            errs.append(f"{p}.zip 为空文件")

    sc = proj / "docs/08-ship/submit-checklist.md"
    if sc.exists():
        t = sc.read_text(encoding="utf-8", errors="ignore")
        if "MB" not in t:
            warns.append("submit-checklist.md 中未见实测体积数值（应附实测值）")
        for p in platforms:
            if p not in t:
                warns.append(f"submit-checklist.md 未提及选定平台 {p}")


CHECKERS = {
    "brief": check_brief,
    "creative": check_creative,
    "creative_dna": check_creative_dna,
    "visual_dna": check_visual_dna,
    "audio_director": check_audio_director,
    "juice": check_juice,
    "experience": check_experience,
    "playtest": check_playtest,
    "review_specialist": check_specialist,
    "content": check_content,
    "review_richness": check_richness,
    "scaffold": check_scaffold,
    "art_bible": check_art_bible,
    "art_forge": check_art_forge,
    "qa": check_qa,
    "sprite_tools": check_sprite_tools,
    "audio_forge": check_audio,
    "review_plan": lambda p, e, w: check_review(p, e, w, "r0"),
    "review_graybox": lambda p, e, w: check_review(p, e, w, "r1"),
    "review_final": lambda p, e, w: check_review(p, e, w, "r2"),
    "ship": check_ship,
}


def check_stage(proj: Path, stage: str) -> tuple[list, list]:
    errs, warns = [], []
    for rel in REQUIRED_FILES.get(stage, []):
        p = proj / rel
        if rel.endswith("/") or rel in ("src/game", "assets/raw", "assets/processed", "assets/atlas", "assets/audio/bgm", "assets/audio/sfx"):
            if not nonempty_dir(p):
                errs.append(f"缺少或为空：{rel}/")
        elif not p.exists():
            errs.append(f"缺少：{rel}")
    fn = CHECKERS.get(stage)
    if fn:
        fn(proj, errs, warns)
    return errs, warns


def main() -> int:
    ap = argparse.ArgumentParser(description="IdeaToGame 阶段产物校验")
    ap.add_argument("--project", default=None)
    ap.add_argument("--stage", required=True, help=f"阶段名或 all（{'/'.join(STAGES)}）")
    args = ap.parse_args()
    proj = project_dir(args.project)

    stages = STAGES if args.stage == "all" else [args.stage]
    if args.stage != "all" and args.stage not in STAGES:
        print(f"ERROR: 未知阶段 {args.stage}", file=sys.stderr)
        return 1

    failed = 0
    for s in stages:
        errs, warns = check_stage(proj, s)
        label = f"{s:<14}"
        if errs:
            failed += 1
            print(f"[FAIL] {label}")
            for e in errs:
                print(f"       - {e}")
        else:
            print(f"[PASS] {label}")
        for w in warns:
            print(f"       WARN: {w}")

    print("-" * 56)
    if failed:
        print(f"{failed} 个阶段未通过校验。修复后再标记 done。")
        return 1
    print("全部通过。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
