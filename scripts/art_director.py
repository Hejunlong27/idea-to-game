#!/usr/bin/env python3
"""美术总监（Art Director）：从 Creative DNA 生成三套视觉提案，收敛成 Visual DNA。

为什么需要它 —— v2 的美术环节只有 `palette.json`（style_tokens + 几个颜色），
`asset_forge.ROLES` 的 9 个模板全是**出图参数**，没有一条描述「这套视觉的语言」。
颜色不是视觉身份：轮廓怎么走、材质是什么、光从哪来、阴影硬还是软、镜头是俯视还是平视、
UI 圆角多少、角色几头身 —— 这些才是。

本脚本做四件事：
  1. --propose      读 Creative DNA → 三套**可区分**的风格提案（每套混合 2 个风格轴，不是选模板）
  2. --dna --pick   收敛成 docs/02-art/visual-dna.json，并**同步写出 palette.json**（向后兼容旧脚本）
  3. --consistency  角色一致性计划（基准图 + 三视图 + seed），并按通道能力如实标注降级状态
  4. --validate     schema + 对比度 + 色相距离 + 参考图存在性

用法:
    python art_director.py --project . --propose
    python art_director.py --project . --dna --pick S2
    python art_director.py --project . --consistency
    python art_director.py --project . --validate --strict

产物:
    docs/02-art/style-proposals.json      三套提案（含正负提示词）
    docs/02-art/visual-dna.json           ★ 视觉设计系统（schema 见 references/schemas/）
    docs/02-art/palette.json              兼容旧脚本的色板（从 Visual DNA 同步）
    docs/02-art/consistency-plan.json     角色一致性计划与降级状态
"""

from __future__ import annotations

import argparse
import colorsys
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import SKILL_DIR, dump_json, ok, project_dir, warn  # noqa: E402

DATA = SKILL_DIR / "assets" / "data"

LIGHT_DIR_MAP = {
    "top_left": "光从左上方来",
    "top_right": "光从右上方来",
    "top_down": "顶光",
    "left": "侧光从左来",
    "right": "侧光从右来",
    "backlit": "逆光，主体压成剪影",
    "flat": "平光，无方向",
}
QUALITY_MAP = {"hard": "硬光，阴影边缘锐利", "soft": "柔光，阴影边缘晕开",
               "volumetric": "体积光，可见光束", "flat": "无方向光，靠固有色区分"}

# style_tokens 会原样进英文提示词 —— 这里必须是英文，中文只能出现在给人看的字段里
LIGHT_EN = {
    "top_left": "light from upper left", "top_right": "light from upper right",
    "top_down": "top-down light", "left": "side light from left",
    "right": "side light from right", "backlit": "strong backlight, subject in silhouette",
    "flat": "flat even lighting, no directional shadow",
}
QUALITY_EN = {
    "hard": "hard-edged shadows", "soft": "soft diffused shadows",
    "volumetric": "volumetric god rays", "flat": "no cast shadow",
}

# style_tokens 会原样进英文提示词 —— 这里必须是英文，中文只能出现在给人看的字段里
LIGHT_EN = {
    "top_left": "light from upper left", "top_right": "light from upper right",
    "top_down": "top-down light", "left": "side light from left",
    "right": "side light from right", "backlit": "strong backlight, subject in silhouette",
    "flat": "flat even lighting, no directional shadow",
}
QUALITY_EN = {
    "hard": "hard-edged shadows", "soft": "soft diffused shadows",
    "volumetric": "volumetric god rays", "flat": "no cast shadow",
}


def load_json(p: Path, default=None):
    if not p.exists():
        return default
    with p.open("r", encoding="utf-8") as f:
        return json.load(f)


# ------------------------------------------------------------------ 颜色工具
def hex_to_rgb(h: str) -> tuple[int, int, int]:
    h = h.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def rgb_to_hex(r, g, b) -> str:
    return "#{:02X}{:02X}{:02X}".format(
        max(0, min(255, int(round(r)))), max(0, min(255, int(round(g)))), max(0, min(255, int(round(b)))))


def hex_to_hsl(h: str) -> tuple[float, float, float]:
    r, g, b = [x / 255 for x in hex_to_rgb(h)]
    hh, ll, ss = colorsys.rgb_to_hls(r, g, b)
    return hh * 360, ss, ll


def hsl_to_hex(h: float, s: float, l: float) -> str:
    r, g, b = colorsys.hls_to_rgb((h % 360) / 360, max(0, min(1, l)), max(0, min(1, s)))
    return rgb_to_hex(r * 255, g * 255, b * 255)


def shift(h: str, dh: float = 0, ds: float = 0, dl: float = 0) -> str:
    hh, ss, ll = hex_to_hsl(h)
    return hsl_to_hex(hh + dh, ss + ds, ll + dl)


def luminance(h: str) -> float:
    def chan(c):
        c = c / 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = hex_to_rgb(h)
    return 0.2126 * chan(r) + 0.7152 * chan(g) + 0.0722 * chan(b)


def contrast(a: str, b: str) -> float:
    la, lb = luminance(a), luminance(b)
    hi, lo = max(la, lb), min(la, lb)
    return round((hi + 0.05) / (lo + 0.05), 2)


def hue_distance(a: str, b: str) -> float:
    ha = hex_to_hsl(a)[0]
    hb = hex_to_hsl(b)[0]
    d = abs(ha - hb) % 360
    return min(d, 360 - d)


# ------------------------------------------------------------------ 提案
def build_proposals(dna: dict, styles: list[dict], n: int = 3) -> list[dict]:
    """生成 n 套可区分的提案。

    区分度来自三条轴的不同组合：轮廓来源 / 材质来源 / 光照方案。
    不是「换一个风格名」，而是换掉视觉语言的一半。
    """
    if not styles:
        return []
    base_pal = ((dna.get("visual") or {}).get("palette") or {})
    primary = list(base_pal.get("primary") or ["#1B3A4B", "#2E5D6B", "#4A8A8C"])
    accent_in = list(base_pal.get("accent") or ["#F2B04A"])
    danger = base_pal.get("danger") or "#C6463C"
    bg = base_pal.get("background") or "#08121C"

    # 三套提案各自换一个「主轮廓来源」。优先用 DNA 里已经声明的风格，
    # 否则提案会与 Creative DNA 脱节 —— 那正是「四块各做各的」的老毛病。
    si = ((dna.get("visual") or {}).get("style_identity") or "") + " " + \
         " ".join((dna.get("visual") or {}).get("visual_keywords") or [])
    preferred = [s for s in styles if s["zh"] in si or s["id"] in si]
    rest = [s for s in styles if s not in preferred]
    ordered = preferred + rest
    picks = [0, 3, 6] if len(ordered) >= 7 else list(range(min(n, len(ordered))))
    out = []
    for i in range(n):
        a = ordered[picks[i % len(picks)]]
        b = ordered[(picks[i % len(picks)] + 4) % len(ordered)]
        if a["id"] == b["id"]:
            b = ordered[(ordered.index(a) + 1) % len(ordered)]
        # 每套提案的色温/饱和度偏移不同，保证三套在画面上一眼可分
        hue_shift = [0, 18, -14][i % 3]
        sat_shift = [0, -0.12, 0.1][i % 3]
        pal_primary = [shift(c, hue_shift, sat_shift) for c in primary]
        pal_accent = [shift(c, hue_shift + 6, sat_shift) for c in accent_in]
        danger_h = shift(danger, hue_shift)
        # 锚定色（=强调色）必须与危险色可区分。
        # 做法有讲究：**先挑**最远的候选，再**最小幅度**转色相 ——
        # 一上来就大角度旋转会把琥珀色转成荧光绿，画面身份就毁了。
        if pal_accent:
            def dist(c):
                return hue_distance(c, danger_h)
            need = 30.0
            # 尊重设计者给的顺序（第一个就是「灯的暖色」），只在不合格时才换/微调
            pick = next((c for c in pal_accent if dist(c) >= need), None)
            if pick is not None:
                pal_accent = [pick] + [c for c in pal_accent if c != pick]
            else:
                h0 = hex_to_hsl(pal_accent[0])
                dh = hex_to_hsl(danger_h)[0]
                # 朝远离危险色的方向转，幅度刚好够
                away = 1 if ((h0[0] - dh) % 360) <= 180 else -1
                pal_accent[0] = hsl_to_hex(h0[0] + away * (need - dist(pal_accent[0]) + 2),
                                           min(1.0, h0[1] + 0.05), h0[2])
        text = "#F2EBDD" if hex_to_hsl(bg)[2] < 0.4 else "#101820"

        light = a.get("light", "single_side")
        light_dir = {"single_side": "top_left", "flat_even": "flat", "top_down": "top_down",
                     "backlit": "backlit", "volumetric": "top_left", "candle_warm": "top_right"}.get(light, "top_left")
        quality = {"single_side": "hard", "flat_even": "flat", "top_down": "soft",
                   "backlit": "volumetric", "volumetric": "volumetric", "candle_warm": "soft"}.get(light, "soft")

        tokens = (f"{a.get('tokens', '')}, {b.get('material', '')} materials, "
                  f"{b.get('texture', '')} texture, {LIGHT_EN[light_dir]}, "
                  f"{QUALITY_EN[quality]}, "
                  f"palette {' '.join(pal_primary[:3])} with accent {pal_accent[0]}")
        negative = ", ".join(x for x in [a.get("negative", ""), b.get("negative", ""),
                                        "text, letters, watermark, extra limbs"] if x)

        out.append({
            "id": f"S{i + 1}",
            "name": f"{a['zh']} × {b['zh']}",
            "primary_style": a["id"],
            "secondary_style": b["id"],
            "reference_direction": f"{a['zh']}的轮廓与收边 + {b['zh']}的材质与纹理",
            "color_system": {
                "primary": pal_primary,
                "accent": pal_accent,
                "danger": danger_h,
                "background": shift(bg, hue_shift * 0.4),
                "text": text,
                "ratio": {"background": 0.55, "primary": 0.25, "accent": 0.12, "danger": 0.08},
            },
            "outline": f"{a.get('edge', 'crisp_ink')}，线宽随物件尺寸线性变化",
            "shape_language": a.get("shape", ""),
            "materials": [a.get("material", ""), b.get("material", "")],
            "lighting": f"{LIGHT_DIR_MAP[light_dir]}；{QUALITY_MAP[quality]}",
            "camera": "俯视 45° 斜角，相机固定，关键事件 1.06 倍推近",
            "camera_en": "top-down 45 degree angle, fixed camera, slight zoom-in on key events",
            "camera_en": "top-down 45 degree angle, fixed camera, slight zoom-in on key events",
            "atmosphere": f"{b.get('texture', '')} 质感 + {a.get('zh', '')} 的空间感",
            "ui_language": f"线框 + 单一强调色（{pal_accent[0]}），圆角 0，描边 2px",
            "character_design": "横向剪影，不做五官；每个角色只带一个高辨识度道具",
            "positive_prompt": tokens,
            "negative_prompt": negative,
            "risks": list(dict.fromkeys((a.get("risks") or []) + (b.get("risks") or []))),
            "differentiation": f"与 S{1 if i else 2} 的区别：轮廓来自 {a['zh']}，色相偏移 {hue_shift:+d}°，饱和度 {sat_shift:+.2f}",
        })

    # 对比度检查（可读性硬指标）。主色取**最亮的一档**做检查 ——
    # 深色主色是给浅底上的形体用的，拿去和深背景比没有意义。
    for p in out:
        cs = p["color_system"]
        lightest_primary = max(cs["primary"], key=luminance)
        checks = []
        for pair_name, fg, bgn, need in [
            ("正文/背景", cs["text"], cs["background"], 4.5),
            ("强调/背景", cs["accent"][0], cs["background"], 3.0),
            ("主色(最亮)/背景", lightest_primary, cs["background"], 3.0),
            ("危险色/背景", cs["danger"], cs["background"], 3.0),
        ]:
            r = contrast(fg, bgn)
            checks.append({"pair": pair_name, "fg": fg, "bg": bgn, "ratio": r,
                           "need": need, "pass": r >= need})
        p["contrast_checks"] = checks
    return out


def cmd_propose(args) -> int:
    proj = project_dir(args.project)
    dna = load_json(proj / "docs" / "01-brief" / "creative-dna.json")
    if not dna:
        print("ERROR: 缺 creative-dna.json（先跑 creative_forge.py --dna）", file=sys.stderr)
        return 1
    styles = (load_json(DATA / "visual-styles" / "styles.json", {}) or {}).get("styles", [])
    proposals = build_proposals(dna, styles, args.n)

    out = {
        "version": "3.0",
        "game_title": (dna.get("identity") or {}).get("game_title", ""),
        "concept_id": (dna.get("meta") or {}).get("concept_id", ""),
        "created": datetime.now().astimezone().isoformat(timespec="seconds"),
        "how_to_choose": "看三套在「轮廓来源 / 材质 / 色温」上是否真的一眼可分；再由人确认（门禁 G2）",
        "proposals": proposals,
    }
    dump_json(proj / "docs" / "02-art" / "style-proposals.json", out)

    print(f"视觉提案：{len(proposals)} 套（来自 Creative DNA 的 palette + 12 个风格库）\n")
    for p in proposals:
        bad = [c for c in p["contrast_checks"] if not c["pass"]]
        print(f"[{p['id']}] {p['name']}")
        print(f"     参考方向：{p['reference_direction']}")
        print(f"     光照：{p['lighting']}")
        print(f"     主色：{' '.join(p['color_system']['primary'][:4])}　强调：{p['color_system']['accent'][0]}")
        print(f"     对比度：{'全部达标' if not bad else '不达标 ' + ', '.join(c['pair'] for c in bad)}")
        if p["risks"]:
            print(f"     风险：{'；'.join(p['risks'][:2])}")
        print()
    print("选定后：python scripts/art_director.py --project . --dna --pick S1")
    return 0


# ------------------------------------------------------------------ visual dna
def cmd_dna(args) -> int:
    proj = project_dir(args.project)
    sp = load_json(proj / "docs" / "02-art" / "style-proposals.json")
    dna = load_json(proj / "docs" / "01-brief" / "creative-dna.json")
    if not sp:
        print("ERROR: 缺 style-proposals.json（先跑 --propose）", file=sys.stderr)
        return 1
    if not dna:
        print("ERROR: 缺 creative-dna.json", file=sys.stderr)
        return 1
    pick = args.pick or "S1"
    p = next((x for x in sp["proposals"] if x["id"] == pick), None)
    if not p:
        print(f"ERROR: 找不到提案 {pick}", file=sys.stderr)
        return 1
    dv = dna.get("visual") or {}
    cs = p["color_system"]
    aud = dna.get("audio") or {}

    light_dir = "flat"
    for k, v in LIGHT_DIR_MAP.items():
        if v in p["lighting"]:
            light_dir = k
            break
    quality = "soft"
    for k, v in QUALITY_MAP.items():
        if v.split("，")[0] in p["lighting"]:
            quality = k
            break

    vdna = {
        "version": "3.0",
        "meta": {
            "game_title": (dna.get("identity") or {}).get("game_title", ""),
            "concept_id": (dna.get("meta") or {}).get("concept_id", ""),
            "created": datetime.now().astimezone().isoformat(timespec="seconds"),
            "chosen_proposal": pick,
            "creative_dna": "docs/01-brief/creative-dna.json",
        },
        "style": {
            "identity": dv.get("style_identity") or p["name"],
            "primary_style": p["primary_style"],
            "secondary_style": p["secondary_style"],
            "keywords": dv.get("visual_keywords") or [p["primary_style"], p["secondary_style"]],
            "style_tokens": p["positive_prompt"],
            "negative": p["negative_prompt"],
            "reference_direction": p["reference_direction"],
            "risks": p["risks"],
        },
        "color": {
            "primary": cs["primary"],
            "accent": cs["accent"],
            "danger": cs["danger"],
            "background": cs["background"],
            "text": cs["text"],
            "ratio": cs["ratio"],
            "usage_rules": [
                "背景永远占 55% 以上面积，保证「空」的感觉",
                f"强调色（{cs['accent'][0]}）只用于玩家需要注意的东西，全场同时出现不超过 2 处",
                f"危险色（{cs['danger']}）不得用于装饰，只用于威胁与不可逆操作",
                "文字永远不用纯白，用 text 色，避免在暗背景上发光刺眼",
            ],
            "contrast_checks": p["contrast_checks"],
        },
        "form": {
            "outline": p["outline"],
            "outline_width_px": 2,
            "shape_language": p["shape_language"],
            "materials": p["materials"],
            "texture_rules": dv.get("texture_rules") or ["纸纤维噪点 6%", "边缘晕开 2–3px"],
            "detail_density": "low",
        },
        "light": {
            "direction": light_dir,
            "quality": quality,
            "temperature": "2700K 偏暖（灯）对 7000K 偏冷（雾）",
            "shadow_rules": dv.get("shadow_rules") or "单层软投影，方向与主光一致",
            "contrast_target": "主体与背景明度差 ≥ 25%",
            "vignette": "四角压暗 12%，不遮玩法区域",
        },
        "camera": {
            "view": "俯视",
            "angle": dv.get("camera") or p["camera"],
            "angle_en": p.get("camera_en") or "top-down 45 degree angle, fixed camera",
            "angle_en": p.get("camera_en") or "top-down 45 degree angle, fixed camera",
            "depth_of_field": dv.get("depth_of_field") or "只有焦点区清晰，其余按距离渐隐",
            "framing": "设计分辨率 720×1280，安全区 8%",
            "parallax_layers": 2,
        },
        "ui": {
            "language": p["ui_language"],
            "corner_radius_px": 0,
            "stroke_px": 2,
            "typography": dv.get("typography") or "系统无衬线，28/18/14 三档",
            "font_sizes": [28, 18, 14],
            "text_render": "全部文字用 Phaser Text 渲染，绝不画进素材（多语言与清晰度）",
            "focus_ring": "选中态用 2px 强调色外描边，不用发光",
        },
        "character": {
            "ratio": dv.get("character_ratio") or "1:1.2 横向剪影",
            "silhouette_rules": ["纯黑填充后仍可与场上其他单位区分", "每个角色只带一个高辨识度道具",
                                 "同一游戏内全部角色同一头身比"],
            "anchor_color": cs["accent"][0],
            "face_detail": "不做五官，靠轮廓与光点识别",
            "consistency": {
                "key": f"{(dna.get('meta') or {}).get('concept_id', 'C1')}-hero-{(dna.get('identity') or {}).get('game_title', 'game')}",
                "seed": int((dna.get("meta") or {}).get("seed") or 20261101),
                "status": "prompt_only",
                "reason": "尚未出图；--consistency 会探测通道后更新为 full_ref_chain / seed_only / degraded_no_ref",
                "refs": [
                    {"view": "front", "file": "assets/raw/hero_front.png", "exists": False},
                    {"view": "side", "file": "assets/raw/hero_side.png", "exists": False},
                    {"view": "back", "file": "assets/raw/hero_back.png", "exists": False},
                ],
            },
        },
        "motion": {
            "style": dv.get("animation_style") or "慢入快出，循环带呼吸停顿",
            "easing": "ease-out 为主，强调用 Back.easeOut，不用线性",
            "looping": "循环动画首尾帧必须可对接，且带 0.3 秒停顿",
            "feedback_rules": [
                "玩家动作的反馈必须在 80ms 内出现（否则感觉不到是自己的操作）",
                "同一事件的表现强度按 severity 分级，不得所有事件同一强度",
                "残影/衰减类效果用 alpha 线性变化，不用闪烁（闪烁会读成 bug）",
            ],
        },
        "fx": {
            "style": dv.get("fx_style") or "水纹扩散 + 墨点，不用发光粒子",
            "palette": [cs["accent"][0], cs["text"], cs["danger"]],
            "rules": [
                "特效颜色只能来自 fx.palette，不得引入新色相",
                "特效峰值亮度不超过强调色，避免盖过玩法元素",
                "同屏粒子数上限 120（低端设备 60）",
            ],
        },
        "scene_narrative": [
            {"trigger": "记忆 ≤1 格", "visual_change": "背景明度整体下降 40%，水纹消失",
             "meaning": "世界正在失去细节 —— 这是玩家的认知状态，不是天气"},
            {"trigger": "送达灵魂", "visual_change": "岸边亮起一盏灯，之后永久保留",
             "meaning": "进度可视化，同时暗示「你救的人还在」"},
            {"trigger": "被威胁靠近 3 格内", "visual_change": "画面边缘开始向内挤压，暗角加深",
             "meaning": "危险不需要敌人可见也能被感知"},
        ],
        "audio_link": {
            "note": "视觉与音频必须共用同一套语义色/情绪映射",
            "danger_color": cs["danger"],
            "accent_color": cs["accent"][0],
            "mood": aud.get("music_mood") or [],
        },
    }
    dump_json(proj / "docs" / "02-art" / "visual-dna.json", vdna)

    # 同步 palette.json —— 向后兼容：asset_forge / style_lib / richness_check 仍读它
    palette = {
        "style_key": f"vdna:{p['primary_style']}+{p['secondary_style']}",
        "style_tokens": vdna["style"]["style_tokens"],
        "negative": vdna["style"]["negative"],
        "primary": cs["primary"],
        "accent": cs["accent"],
        "background": cs["background"],
        "danger": cs["danger"],
        "text": cs["text"],
        "source": "docs/02-art/visual-dna.json（由 art_director.py 同步，不要手改）",
    }
    dump_json(proj / "docs" / "02-art" / "palette.json", palette)

    ok(f"已生成 Visual DNA：docs/02-art/visual-dna.json（提案 {pick}）")
    ok("已同步 palette.json（旧脚本继续可用）")
    print("\n下一步：")
    print("  python scripts/art_director.py --project . --consistency")
    print("  python scripts/art_director.py --project . --validate --strict")
    return 0


# ------------------------------------------------------------------ consistency
def probe_art_channel(proj: Path) -> dict:
    """探测生图通道能力。返回 {channel, i2i, note}。

    不做网络请求（避免在离线环境卡住），只看配置与可达性由 gen_assets 负责。
    这里只判断「配置里是否声明了 i2i 工作流」。
    """
    import yaml  # noqa: PLC0415

    p = proj / ".gamedev" / "artgen.yaml"
    if not p.exists():
        return {"channel": "unknown", "i2i": False, "note": "缺 .gamedev/artgen.yaml"}
    try:
        cfg = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    except Exception as e:  # noqa: BLE001
        return {"channel": "unknown", "i2i": False, "note": f"artgen.yaml 解析失败：{e}"}
    provider = str(cfg.get("provider") or "auto")
    cq = cfg.get("comfyui") or {}
    i2i = bool(cq.get("workflow_i2i"))
    if provider in ("placeholder",):
        return {"channel": "placeholder", "i2i": False, "note": "配置为占位通道，无 i2i 能力"}
    if provider in ("comfyui", "auto") and i2i:
        return {"channel": provider, "i2i": True, "note": "声明了 i2i 工作流"}
    return {"channel": provider, "i2i": False, "note": "未声明 i2i 工作流，只能靠固定 seed"}


def cmd_consistency(args) -> int:
    proj = project_dir(args.project)
    vd = load_json(proj / "docs" / "02-art" / "visual-dna.json")
    if not vd:
        print("ERROR: 缺 visual-dna.json（先跑 --dna）", file=sys.stderr)
        return 1
    ch = probe_art_channel(proj)
    con = vd["character"]["consistency"]
    refs = con.get("refs") or []

    for r in refs:
        r["exists"] = (proj / r["file"]).exists()
    n_exist = sum(1 for r in refs if r["exists"])

    if ch["i2i"] and n_exist >= 1:
        status, reason = "full_ref_chain", f"{ch['channel']} 支持 i2i 且基准图存在，后续姿态走 ref 链"
    elif ch["i2i"]:
        status, reason = "seed_only", f"{ch['channel']} 支持 i2i，但基准图尚未产出；先出 front 再回填 ref"
    elif n_exist >= 1:
        status, reason = "seed_only", f"{ch['channel']} 无 i2i 能力，只能靠固定 seed + 提示词锚（已知会漂移）"
    else:
        status, reason = "degraded_no_ref", f"{ch['channel']} 无 i2i 能力且基准图不存在：{ch['note']}"

    con["status"] = status
    con["reason"] = reason
    dump_json(proj / "docs" / "02-art" / "visual-dna.json", vd)

    plan = {
        "version": "3.0",
        "channel": ch,
        "consistency_key": con["key"],
        "seed": con["seed"],
        "status": status,
        "reason": reason,
        "steps": [
            {"order": 1, "action": "出基准图 front", "prompt_file": "docs/02-art/prompts/hero_front.txt",
             "seed": con["seed"], "ref": "", "check": "纯黑填充后剪影可辨"},
            {"order": 2, "action": "出 side（ref=front）", "prompt_file": "docs/02-art/prompts/hero_side.txt",
             "seed": con["seed"], "ref": "assets/raw/hero_front.png", "check": "主色直方图距离 < 0.18"},
            {"order": 3, "action": "出 back（ref=front）", "prompt_file": "docs/02-art/prompts/hero_back.txt",
             "seed": con["seed"], "ref": "assets/raw/hero_front.png", "check": "剪影宽高比偏差 < 0.12"},
            {"order": 4, "action": "出表情/姿态（ref=front）", "prompt_file": "docs/02-art/prompts/hero_pose_*.txt",
             "seed": con["seed"], "ref": "assets/raw/hero_front.png", "check": "锚定色占比 8%–20%"},
        ],
        "drift_thresholds": (load_json(DATA / "creative-patterns" / "character-patterns.json", {})
                             .get("consistency_protocol", {}).get("drift_thresholds", {})),
        "note": "仅「多张图用同一 prompt」不构成一致性方案；status 必须是上述四态之一，不得虚报",
    }
    dump_json(proj / "docs" / "02-art" / "consistency-plan.json", plan)

    print(f"生图通道：{ch['channel']}　i2i：{'支持' if ch['i2i'] else '不支持'}（{ch['note']}）")
    print(f"一致性状态：{status}")
    print(f"原因：{reason}")
    print(f"参考图：{n_exist}/{len(refs)} 已存在")
    print("已写：docs/02-art/consistency-plan.json")
    if status.startswith("degraded"):
        warn("一致性为降级状态 —— 交付报告必须如实列出，不能声称「角色一致性已解决」")
        return 0
    return 0


# ------------------------------------------------------------------ validate
def cmd_validate(args) -> int:
    proj = project_dir(args.project)
    path = proj / "docs" / "02-art" / "visual-dna.json"
    if not path.exists():
        print("ERROR: 缺 visual-dna.json", file=sys.stderr)
        return 1
    vd = json.loads(path.read_text(encoding="utf-8"))
    issues: list[tuple[str, str, str]] = []

    def err(p, m):
        issues.append(("ERROR", p, m))

    def wrn(p, m):
        issues.append(("WARN", p, m))

    import schema_check  # noqa: E402
    schema = load_json(SKILL_DIR / "references" / "schemas" / "visual-dna.schema.json", {})
    for e in schema_check.validate(vd, schema):
        err("schema", e)

    # 语义：对比度
    for c in (vd.get("color") or {}).get("contrast_checks") or []:
        if not c.get("pass"):
            err("color.contrast_checks",
                f"{c.get('pair')} 对比度 {c.get('ratio')} < 3.0 —— 可读性不达标")
    # 语义：锚定色不能与危险色撞色（30° 是「色相可分辨」的经验下限，
    # 再往上加会迫使琥珀色转成荧光绿，反而破坏视觉身份）
    ch = vd.get("character") or {}
    d = hue_distance(ch.get("anchor_color") or "#FFFFFF", (vd.get("color") or {}).get("danger") or "#000000")
    if d < 30:
        err("character.anchor_color",
            f"锚定色与危险色色相距离仅 {d:.0f}°（需 ≥30°）—— 玩家会分不清「这是我」和「这是危险」")
    # 语义：style_tokens 词数
    n_words = len((vd.get("style") or {}).get("style_tokens", "").split())
    if n_words < 15:
        err("style.style_tokens", f"风格锚点仅 {n_words} 词（需 ≥15），出图会跑偏")
    # 语义：文字不得画进素材
    if "Text" not in ((vd.get("ui") or {}).get("text_render") or "") and \
       "文字" not in ((vd.get("ui") or {}).get("text_render") or ""):
        wrn("ui.text_render", "未声明「文字必须由 Text 渲染」")
    # 语义：一致性状态与实际参考图必须自洽
    con = ch.get("consistency") or {}
    if con.get("status") == "full_ref_chain":
        refs = con.get("refs") or []
        if not any((proj / r.get("file", "")).exists() for r in refs):
            err("character.consistency.status",
                "status=full_ref_chain 但没有任何参考图存在 —— 不允许虚报一致性")
    # 语义：场景叙事
    if not (vd.get("scene_narrative") or []):
        wrn("scene_narrative", "未定义「环境随进度变化」—— 场景只是背景板")

    errors = [i for i in issues if i[0] == "ERROR"]
    warns = [i for i in issues if i[0] == "WARN"]
    print(f"Visual DNA 校验：{path.relative_to(proj)}")
    print(f"  ERROR {len(errors)}　WARN {len(warns)}\n")
    for lvl, p, m in issues[:50]:
        print(f"[{lvl}] {p} —— {m}")
    dump_json(proj / "docs" / "02-art" / "visual-validation.json", {
        "ok": not errors,
        "errors": [{"path": p, "msg": m} for _, p, m in errors],
        "warnings": [{"path": p, "msg": m} for _, p, m in warns],
    })
    if errors:
        print("\nERROR 必改。", file=sys.stderr)
        return 2 if args.strict else 0
    ok("Visual DNA 通过校验")
    return 0


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass
    ap = argparse.ArgumentParser(description="美术总监：风格提案 → Visual DNA → 一致性计划")
    ap.add_argument("--project", default=None)
    ap.add_argument("--propose", action="store_true")
    ap.add_argument("--dna", action="store_true")
    ap.add_argument("--pick", default="")
    ap.add_argument("--consistency", action="store_true")
    ap.add_argument("--validate", action="store_true")
    ap.add_argument("--n", type=int, default=3)
    ap.add_argument("--strict", action="store_true")
    args = ap.parse_args()
    if args.propose:
        return cmd_propose(args)
    if args.dna:
        return cmd_dna(args)
    if args.consistency:
        return cmd_consistency(args)
    if args.validate:
        return cmd_validate(args)
    ap.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
