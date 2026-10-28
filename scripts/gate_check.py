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
    "art_bible": ["docs/02-art/art-bible.md", "docs/02-art/palette.json"],
    "core_loop": ["docs/04-core-loop/notes.md", "src/game"],
    "art_forge": ["assets/raw"],
    "sprite_tools": ["assets/processed", "assets/atlas"],
    "audio_forge": ["assets/audio/bgm", "assets/audio/sfx"],
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
    if len(mvp) > 5:
        errs.append(f"MVP 功能 {len(mvp)} 项，超出上限 5 项（见 genre-playbook.md 范围控制规则）")
    if not data.get("out_of_scope"):
        warns.append("out_of_scope 为空，说明没有做取舍，范围可能失控")
    assets = data.get("assets") or {}
    total = sum(len(v) for v in assets.values() if isinstance(v, list))
    if total > 30:
        warns.append(f"素材总数 {total} 个，超出建议上限 30 个")


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
    if sfx.is_dir() and len([f for f in sfx.iterdir() if f.is_file()]) > 5:
        warns.append("音效数量超过建议上限 5 个")


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
