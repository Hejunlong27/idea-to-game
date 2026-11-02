#!/usr/bin/env python3
"""音频总监（Audio Director）：从「有音频文件」升级为「有音频系统」。

v2 的问题：`audio_forge.py` 产出 plan，`gen_audio.py` 产出 mp3，然后**没有了** ——
模板里没有任何播放层。分层的意义（ui/gameplay/feedback/ambience）在运行时不存在，
四个层只是四个文件夹。所以自适应音乐、动态混音、并发控制、距离衰减全都无从谈起。

本脚本负责设计（运行时由模板 `src/game/audio.ts` 执行）：
  1. --plan      Creative DNA + 音频风格库 → audio-dna.json（stem 分层 / 状态机 / 动态音效规则 / 情绪规则）
  2. --emit      → stem-render-plan.json（交给 gen_stems.py 合成，或交给 YuE2 出分轨）
  3. --qc        真实波形检查：存在性 / 格式 / 采样率 / 削波 / 异常静音 / 循环接缝 / 体积
  4. --validate  schema + 语义（状态可达性、stem 完整性、无障碍替代方案）

用法:
    python audio_director.py --project . --plan
    python audio_director.py --project . --emit
    python audio_director.py --project . --qc
    python audio_director.py --project . --validate --strict

产物:
    docs/05-audio/audio-dna.json          ★ 音频系统设计
    docs/05-audio/stem-render-plan.json   分轨合成清单
    docs/05-audio/audio-qc.json           波形质检结果（真实测量，不是声明）
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
import wave
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import SKILL_DIR, dump_json, ok, project_dir, warn  # noqa: E402

DATA = SKILL_DIR / "assets" / "data"

# 状态 → 事件触发条件（模板 audio.ts 用同一套 id）
STATE_TRIGGERS = {
    "exploration": "游戏开始后默认状态；无敌人在 3 格内",
    "danger": "有威胁单位进入 5 格内，或玩家资源 < 50%",
    "combat": "同屏威胁 ≥2 个，或玩家主动攻击",
    "critical": "玩家资源 ≤20%，或 hull ≤1",
    "victory": "关卡完成 / 送达目标",
    "defeat": "玩家死亡 / 失败",
    "memory": "叙事揭示 / 回忆闪回",
}


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
    lib = load_json(DATA / "audio-styles" / "palettes.json", {}) or {}
    mood_map = lib.get("mood_map") or {}
    stem_defs = lib.get("stem_layers") or []
    variant_rules = lib.get("sfx_variant_rules") or {}
    emo_rules = lib.get("emotional_rules") or []
    aud = dna.get("audio") or {}

    moods = list(dict.fromkeys(aud.get("music_mood") or ["exploration", "danger", "victory"]))
    # 必备状态：exploration 必须在；critical / defeat 建议在
    for must in ("exploration",):
        if must not in moods:
            moods.insert(0, must)

    stems = []
    for s in stem_defs:
        stems.append({
            "id": s["id"],
            "file": f"assets/audio/bgm/stem_{s['id']}.mp3",
            "default_gain": s["default_gain"],
            "duck_under_sfx": s["duck_under_sfx"],
            "loop": True,
            "exists": (proj / "assets" / "audio" / "bgm" / f"stem_{s['id']}.mp3").exists(),
        })

    states = []
    for m in moods:
        cfg = mood_map.get(m) or mood_map.get("exploration") or {}
        gains = cfg.get("stems") or {s["id"]: s["default_gain"] for s in stem_defs}
        states.append({
            "id": m,
            "zh": cfg.get("zh") or m,
            "when": STATE_TRIGGERS.get(m, "由游戏逻辑判定"),
            "stem_gains": {k: round(float(v), 3) for k, v in gains.items()},
            "bpm": cfg.get("bpm"),
            "mode": cfg.get("mode") or "minor",
            "transition_ms": 1200 if m not in ("victory", "defeat") else 400,
            "note": cfg.get("change") or "",
        })

    sfx_plan = load_json(proj / "docs" / "05-audio" / "sfx-plan.json", {}) or {}
    n_sfx = len(sfx_plan.get("items") or [])

    out = {
        "version": "3.0",
        "meta": {
            "game_title": (dna.get("identity") or {}).get("game_title", ""),
            "concept_id": (dna.get("meta") or {}).get("concept_id", ""),
            "created": datetime.now().astimezone().isoformat(timespec="seconds"),
            "creative_dna": "docs/01-brief/creative-dna.json",
            "visual_dna": "docs/02-art/visual-dna.json",
            "degraded": False,
            "degraded_reason": "",
        },
        "identity": {
            "audio_identity": aud.get("audio_identity") or "",
            "instrumentation": aud.get("instrumentation") or [],
            "sound_signature": aud.get("sound_signature") or [],
            "mood_arc": moods,
        },
        "music": {
            "mode": "stems",
            "stems": stems,
            "states": states,
            "initial_state": "exploration",
            "victory_stinger": "assets/audio/sfx/feedback_win.mp3",
            "defeat_stinger": "assets/audio/sfx/feedback_defeat.mp3",
            "crossfade_note": "状态切换只改各 stem 的音量，不换曲 —— 这样切换点听不出接缝",
        },
        "sfx": {
            "variants": int(variant_rules.get("default_variants") or 3),
            "pitch_jitter_semitones": float(variant_rules.get("pitch_jitter_semitones") or 1.5),
            "gain_jitter_db": float(variant_rules.get("gain_jitter_db") or 2.5),
            "min_interval_ms": int(variant_rules.get("min_interval_ms") or 60),
            "same_sound_cooldown_ms": int(variant_rules.get("same_sound_cooldown_ms") or 90),
            "max_concurrent": int(variant_rules.get("max_concurrent") or 12),
            "max_concurrent_per_sound": int(variant_rules.get("max_concurrent_per_sound") or 3),
            "bus_gains": {"master": 0.85, "music": 0.55, "sfx": 0.9, "ui": 0.7, "ambience": 0.5},
            "distance": variant_rules.get("distance_attenuation") or {
                "enabled": True, "ref_distance": 400, "rolloff": 1.2, "max_distance": 1600},
            "priority_rules": [
                "feedback 层的胜利/失败/受击优先级最高，永不被挤掉",
                "同一事件 100ms 内重复触发只播一次（去重）",
                "并发超过上限时丢弃最旧的低优先级音",
                f"已登记音效 {n_sfx} 个（来自 sfx-plan.json）",
            ],
        },
        "emotional_rules": [
            {
                "id": r.get("id", f"rule_{i}"),
                "when": r.get("when", ""),
                "change": r.get("change", ""),
                "target_state": _guess_state(r.get("id", "")),
            }
            for i, r in enumerate(emo_rules)
        ],
        "gameplay_hooks": [],
        "qc": {},
    }

    # 声音即玩法：从 DNA 的声明落到事件钩子
    sg = aud.get("sound_as_gameplay") or {}
    if sg.get("enabled"):
        out["gameplay_hooks"] = [
            {
                "event": "echo_ping",
                "audio_role": "回声是唯一的信息来源：方位靠声像，距离靠延迟与音量衰减",
                "visual_fallback": "屏幕边缘的方向指示条（静音玩家必须也能通关）",
            },
            {
                "event": "threat_near",
                "audio_role": "低频脉冲的强度直接对应威胁距离，玩家闭眼也能判断",
                "visual_fallback": "画面边缘向内挤压的暗角",
            },
        ]
    else:
        out["gameplay_hooks"] = [{
            "event": "none",
            "audio_role": "本作声音不承担玩法职责（仅反馈与氛围）",
            "visual_fallback": "不适用",
        }]

    # 若 DNA 声明了动态规则，补充成 emotional_rules（DNA 优先，库兜底）
    for i, r in enumerate(aud.get("dynamic_audio_rules") or []):
        out["emotional_rules"].append({
            "id": f"dna_rule_{i + 1}",
            "when": r.get("when", ""),
            "change": r.get("change", ""),
            "target_state": "",
        })

    dump_json(proj / "docs" / "05-audio" / "audio-dna.json", out)
    print(f"音频系统设计：{len(states)} 个音乐状态 × {len(stems)} 条 stem")
    for s in states:
        g = s["stem_gains"]
        top = sorted(g.items(), key=lambda kv: -kv[1])[:3]
        print(f"  - {s['id']:<12} {s['zh']:<6} bpm={s['bpm']} 主层：{', '.join(f'{k}={v}' for k, v in top)}")
    print(f"情绪规则 {len(out['emotional_rules'])} 条　玩法钩子 {len(out['gameplay_hooks'])} 条")
    ok("已写 docs/05-audio/audio-dna.json")
    print("\n下一步：python scripts/audio_director.py --project . --emit")
    return 0


def _guess_state(rule_id: str) -> str:
    if "death" in rule_id or "near" in rule_id:
        return "critical"
    if "safe" in rule_id:
        return "exploration"
    if "reveal" in rule_id:
        return "memory"
    if "tension" in rule_id:
        return "danger"
    return ""


def cmd_emit(args) -> int:
    proj = project_dir(args.project)
    ad = load_json(proj / "docs" / "05-audio" / "audio-dna.json")
    if not ad:
        print("ERROR: 缺 audio-dna.json（先跑 --plan）", file=sys.stderr)
        return 1
    plan = {
        "version": "3.0",
        "note": "每一轨都是可独立循环的 20 秒片段，同一条 stem 在所有状态下共用 —— "
                "这样切换状态只改音量，不会出现接缝。",
        "targets": [],
        "provider_hint": {
            "yue2": "YuE2-Studio 逐轨生成时，style 里必须写明「solo <instrument>, no other instruments」",
            "procedural": "python scripts/gen_stems.py --project . 合成（无外部依赖，始终可用）",
        },
    }
    for s in ad["music"]["stems"]:
        plan["targets"].append({
            "stem": s["id"],
            "file": s["file"],
            "duration_seconds": 20,
            "loop": True,
            "gain": s["default_gain"],
            "prompt": _stem_prompt(s["id"], ad),
        })
    dump_json(proj / "docs" / "05-audio" / "stem-render-plan.json", plan)
    ok(f"已写 stem-render-plan.json（{len(plan['targets'])} 轨）")
    print("合成：python scripts/gen_stems.py --project .")
    return 0


def _stem_prompt(stem: str, ad: dict) -> str:
    inst = ", ".join((ad.get("identity") or {}).get("instrumentation") or [])
    base = {
        "melody": f"solo sparse melody on {inst}, long notes, wide silence between phrases, no drums",
        "rhythm": f"minimal rhythmic pulse, muted percussive ticks, steady tempo, no melody",
        "bass": f"deep sustained low drone, felt more than heard, slow swell, no melody",
        "percussion": f"sparse impacts, wooden and metallic hits, large gaps, no continuous rhythm",
        "atmosphere": f"ambient texture bed, {inst}, continuous noise-like wash, no rhythm, no melody",
    }
    return base.get(stem, f"solo {stem} layer")


# ------------------------------------------------------------------ QC
def ffmpeg_bin() -> str | None:
    for name in ("ffmpeg", "ffmpeg.exe"):
        p = shutil.which(name)
        if p:
            return p
    for cand in (r"C:\Users\15274\AppData\Local\Microsoft\WinGet\Links\ffmpeg.exe",
                 r"C:\Users\15274\AppData\Local\Microsoft\WinGet\Links\ffmpeg"):
        if Path(cand).exists():
            return cand
    return None


def analyze_audio(path: Path, expect_loop: bool = False) -> dict:
    """真实测量：解码成 wav 后算峰值 / RMS / 循环接缝。"""
    import numpy as np

    res = {"file": path.as_posix(), "exists": path.exists(), "size_kb": 0,
           "issues": [], "clipped": False, "silent": False}
    if not path.exists():
        res["issues"].append("文件不存在")
        return res
    res["size_kb"] = round(path.stat().st_size / 1024, 1)
    ff = ffmpeg_bin()
    if not ff:
        res["issues"].append("找不到 ffmpeg，无法解码做波形检查")
        return res
    with tempfile.TemporaryDirectory() as td:
        wav = Path(td) / "a.wav"
        cmd = [ff, "-y", "-v", "error", "-i", str(path), "-ac", "1", "-ar", "44100",
               "-f", "wav", str(wav)]
        r = subprocess.run(cmd, capture_output=True)
        if r.returncode != 0 or not wav.exists():
            res["issues"].append(f"ffmpeg 解码失败：{r.stderr.decode('utf-8', 'ignore')[:120]}")
            return res
        with wave.open(str(wav), "rb") as w:
            n = w.getnframes()
            sr = w.getframerate()
            ch = w.getnchannels()
            raw = w.readframes(n)
        data = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
        if data.size == 0:
            res["issues"].append("解码后为空")
            return res
        res["duration_s"] = round(n / sr, 3)
        res["sample_rate"] = sr
        res["channels"] = ch
        peak = float(np.max(np.abs(data)))
        rms = float(np.sqrt(np.mean(data ** 2)))
        res["peak_db"] = round(20 * np.log10(max(peak, 1e-9)), 2)
        res["rms_db"] = round(20 * np.log10(max(rms, 1e-9)), 2)
        res["clipped"] = peak >= 0.999
        res["silent"] = rms < 0.002
        if res["clipped"]:
            res["issues"].append(f"削波（峰值 {res['peak_db']}dBFS）")
        if res["silent"]:
            res["issues"].append(f"近似静音（RMS {res['rms_db']}dBFS）")
        if sr < 22050:
            res["issues"].append(f"采样率偏低（{sr}Hz）")
        if ch > 1:
            res["issues"].append(f"立体声（{ch} 声道）—— 平台体积预算下应为单声道")
        if expect_loop and data.size > sr // 10:
            head = data[: int(sr * 0.05)]
            tail = data[-int(sr * 0.05):]
            seam = float(abs(np.sqrt(np.mean(head ** 2)) - np.sqrt(np.mean(tail ** 2))))
            res["loop_seam_db"] = round(20 * np.log10(max(seam, 1e-9)), 2)
            if seam > 0.08:
                res["issues"].append(f"循环接缝明显（首尾 RMS 差 {res['loop_seam_db']}dB）")
    return res


def cmd_qc(args) -> int:
    proj = project_dir(args.project)
    ad = load_json(proj / "docs" / "05-audio" / "audio-dna.json")
    if not ad:
        print("ERROR: 缺 audio-dna.json（先跑 --plan）", file=sys.stderr)
        return 1
    targets: list[tuple[Path, bool]] = []
    for s in ad["music"]["stems"]:
        targets.append((proj / s["file"], True))
    sfx_plan = load_json(proj / "docs" / "05-audio" / "sfx-plan.json", {}) or {}
    for it in sfx_plan.get("items") or []:
        targets.append((proj / (it.get("file") or ""), False))

    rows = []
    for p, loop in targets:
        r = analyze_audio(p, expect_loop=loop)
        r["loop_expected"] = loop
        rows.append(r)

    total = round(sum(r.get("size_kb", 0) for r in rows), 1)
    budget = 2048.0
    missing = [r for r in rows if not r.get("exists")]
    clipped = [r for r in rows if r.get("clipped")]
    silent = [r for r in rows if r.get("silent")]
    seams = [r for r in rows if (r.get("loop_seam_db") or 0) > 26]
    verdict = "PASS"
    if missing or clipped or silent:
        verdict = "FAIL"
    elif seams or total > budget:
        verdict = "WARN"

    qc = {
        "checked_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "files": rows,
        "total_kb": total,
        "budget_kb": budget,
        "summary": {
            "declared": len(rows), "missing": len(missing), "clipped": len(clipped),
            "silent": len(silent), "loop_seam_suspect": len(seams),
        },
        "verdict": verdict,
    }
    ad["qc"] = qc
    # 分轨是否真实存在，直接反映到 music.stems[].exists
    have = {r["file"].replace("\\", "/") for r in rows if r.get("exists")}
    for s in ad["music"]["stems"]:
        s["exists"] = s["file"].replace("\\", "/") in have
    if missing:
        ad["meta"]["degraded"] = True
        ad["meta"]["degraded_reason"] = f"{len(missing)} 个音频文件缺失"
    dump_json(proj / "docs" / "05-audio" / "audio-dna.json", ad)
    dump_json(proj / "docs" / "05-audio" / "audio-qc.json", qc)

    print(f"音频质检：{len(rows)} 个文件，总计 {total:.1f}KB / {budget:.0f}KB → {verdict}")
    print(f"  缺失 {len(missing)}　削波 {len(clipped)}　静音 {len(silent)}　接缝可疑 {len(seams)}")
    for r in rows:
        if r.get("issues"):
            print(f"  [{r['file'].split('/')[-1]}] {'; '.join(r['issues'])}")
    if verdict == "FAIL":
        warn("音频质检未通过 —— 专项审核会据此判 FAIL，不允许声明「音频正常」")
        return 2
    ok("音频质检通过")
    return 0


# ------------------------------------------------------------------ validate
def cmd_validate(args) -> int:
    proj = project_dir(args.project)
    path = proj / "docs" / "05-audio" / "audio-dna.json"
    if not path.exists():
        print("ERROR: 缺 audio-dna.json", file=sys.stderr)
        return 1
    ad = json.loads(path.read_text(encoding="utf-8"))
    issues: list[tuple[str, str, str]] = []

    def err(p, m):
        issues.append(("ERROR", p, m))

    def wrn(p, m):
        issues.append(("WARN", p, m))

    import schema_check  # noqa: E402
    schema = load_json(SKILL_DIR / "references" / "schemas" / "audio-dna.schema.json", {})
    for e in schema_check.validate(ad, schema):
        err("schema", e)

    music = ad.get("music") or {}
    states = music.get("states") or []
    stems = {s["id"] for s in (music.get("stems") or [])}
    # 每个状态的 gain 必须覆盖全部 stem（否则切换时会残留上一状态音量）
    for st in states:
        missing = stems - set((st.get("stem_gains") or {}).keys())
        if missing:
            err(f"music.states[{st.get('id')}].stem_gains",
                f"缺少 {', '.join(sorted(missing))} 的音量 —— 切到该状态会残留上一状态音量")
    # 状态必须有区分度：不能所有状态音量一样
    sig = {st["id"]: tuple(sorted((st.get("stem_gains") or {}).items())) for st in states}
    if len(set(sig.values())) < len(sig):
        err("music.states", "存在两个状态的分轨音量完全相同 —— 状态切换听不出区别，自适应是假的")
    # 必须至少有一个 state 让某条 stem 为 0（真正的分层，而不是整体调音量）
    if not any(0.0 in (st.get("stem_gains") or {}).values() for st in states):
        wrn("music.states", "没有任何状态的某条 stem 为 0 —— 可能只是整体音量变化，不是分层")

    # 情绪规则必须可表达
    for r in ad.get("emotional_rules") or []:
        if not (r.get("when") or "").strip():
            err("emotional_rules", "规则缺 when（何时触发）")
        if len((r.get("change") or "").strip()) < 8:
            err("emotional_rules", f"规则 {r.get('id')} 的 change 太短，无法执行")

    # 声音即玩法必须有视觉替代方案
    for h in ad.get("gameplay_hooks") or []:
        if h.get("event") == "none":
            continue
        if not (h.get("visual_fallback") or "").strip():
            err("gameplay_hooks", f"{h.get('event')} 承担玩法职责但没有 visual_fallback（无障碍硬要求）")

    # 降级必须如实标注
    meta = ad.get("meta") or {}
    if meta.get("degraded") and not (meta.get("degraded_reason") or "").strip():
        err("meta.degraded_reason", "degraded=true 但没写原因")

    # QC 必须真的跑过
    qc = ad.get("qc") or {}
    if not qc.get("files"):
        wrn("qc", "尚未跑 --qc（音频审核会因为没有实测证据而判 FAIL）")

    errors = [i for i in issues if i[0] == "ERROR"]
    warns = [i for i in issues if i[0] == "WARN"]
    print(f"Audio DNA 校验：{path.relative_to(proj)}")
    print(f"  ERROR {len(errors)}　WARN {len(warns)}\n")
    for lvl, p, m in issues[:50]:
        print(f"[{lvl}] {p} —— {m}")
    dump_json(proj / "docs" / "05-audio" / "audio-validation.json", {
        "ok": not errors,
        "errors": [{"path": p, "msg": m} for _, p, m in errors],
        "warnings": [{"path": p, "msg": m} for _, p, m in warns],
    })
    if errors:
        print("\nERROR 必改。", file=sys.stderr)
        return 2 if args.strict else 0
    ok("Audio DNA 通过校验")
    return 0


def cmd_emit_ts(args) -> int:
    """把 audio-dna.json 编译成模板可直接 import 的 TS 配置。

    这一步是「DNA 真的接入运行时」的证据：改 audio-dna.json → 重跑本命令 →
    游戏里的音乐状态机就变了，不需要改代码。
    """
    proj = project_dir(args.project)
    ad = load_json(proj / "docs" / "05-audio" / "audio-dna.json")
    if not ad:
        print("ERROR: 缺 audio-dna.json（先跑 --plan）", file=sys.stderr)
        return 1
    music = ad["music"]
    sfx = ad["sfx"]

    stems = ",\n  ".join(
        f"{{ id: '{s['id']}', key: 'stem_{s['id']}', defaultGain: {s['default_gain']}, "
        f"duckUnderSfx: {'true' if s['duck_under_sfx'] else 'false'} }}"
        for s in music["stems"])
    states = ",\n  ".join(
        f"{{ id: '{st['id']}', zh: '{st.get('zh', st['id'])}', transitionMs: {st['transition_ms']}, "
        f"gains: {{ {', '.join(f'{k}: {v}' for k, v in st['stem_gains'].items())} }} }}"
        for st in music["states"])

    ts = f"""/* eslint-disable */
// 由 scripts/audio_director.py --emit-ts 生成，**不要手改**。
// 真相源：docs/05-audio/audio-dna.json
// 改设计 → 重跑脚本 → 运行时行为随之改变。

export interface StemCfg {{
  id: string;
  key: string;
  defaultGain: number;
  duckUnderSfx: boolean;
}}

export interface AudioStateCfg {{
  id: string;
  zh: string;
  transitionMs: number;
  gains: Record<string, number>;
}}

export const AUDIO_STEMS: StemCfg[] = [
  {stems},
];

export const AUDIO_STATES: AudioStateCfg[] = [
  {states},
];

export const AUDIO_INITIAL_STATE = '{music.get('initial_state', 'exploration')}';

export const AUDIO_BUS_GAINS = {json.dumps(sfx.get('bus_gains', {}), ensure_ascii=False)};

export const AUDIO_SFX_RULES = {{
  variants: {sfx.get('variants', 3)},
  pitchJitter: {sfx.get('pitch_jitter_semitones', 1.5)},
  gainJitterDb: {sfx.get('gain_jitter_db', 2.5)},
  minIntervalMs: {sfx.get('min_interval_ms', 60)},
  sameCooldownMs: {sfx.get('same_sound_cooldown_ms', 90)},
  maxConcurrent: {sfx.get('max_concurrent', 12)},
  maxPerSound: {sfx.get('max_concurrent_per_sound', 3)},
  distance: {{
    enabled: {'true' if (sfx.get('distance') or {}).get('enabled') else 'false'},
    refDistance: {(sfx.get('distance') or {}).get('ref_distance', 400)},
    rolloff: {(sfx.get('distance') or {}).get('rolloff', 1.2)},
    maxDistance: {(sfx.get('distance') or {}).get('max_distance', 1600)},
  }},
}};

/** 声音承担玩法职责的钩子（用于无障碍替代方案与自检） */
export const AUDIO_GAMEPLAY_HOOKS = {json.dumps(ad.get('gameplay_hooks', []), ensure_ascii=False, indent=2)};
"""
    out = proj / "src" / "game" / "audio-config.ts"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(ts, encoding="utf-8")
    ok(f"已生成运行时配置：{out.relative_to(proj)}（{len(music['stems'])} stem × {len(music['states'])} 状态）")
    return 0


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass
    ap = argparse.ArgumentParser(description="音频总监：自适应音乐 / 动态音效 / 情绪声 / 质检")
    ap.add_argument("--project", default=None)
    ap.add_argument("--plan", action="store_true")
    ap.add_argument("--emit", action="store_true")
    ap.add_argument("--qc", action="store_true")
    ap.add_argument("--emit-ts", action="store_true", help="生成 src/game/audio-config.ts")
    ap.add_argument("--validate", action="store_true")
    ap.add_argument("--strict", action="store_true")
    args = ap.parse_args()
    if args.plan:
        return cmd_plan(args)
    if args.emit:
        return cmd_emit(args)
    if getattr(args, "emit_ts"):
        return cmd_emit_ts(args)
    if args.qc:
        return cmd_qc(args)
    if args.validate:
        return cmd_validate(args)
    ap.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
