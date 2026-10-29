#!/usr/bin/env python3
"""音效设计器：把「游戏事件」变成「可生产的音频方案」。

三层结构（见 references/audio-design.md）：
  L1 反馈层 —— 程序化合成（gen_audio.py，体积几十 KB）
  L2 氛围层 —— YuE2-Studio 本地 MCP 生成音乐
  L3 叙事层 —— 本地 TTS 2.5 生成对白

本脚本只做「设计与编目」，实际生产由三个通道各自执行：
    gen_audio.py --spec          L1 合成音效
    YuE2-Studio MCP             L2 音乐（--emit-yue2 出调用清单）
    本地 TTS                    L3 对白（--emit-tts 出请求清单）

用法:
    python audio_forge.py --project . --plan        # 蓝图 → sfx/music/voice 三份 plan
    python audio_forge.py --project . --emit-yue2   # 出 YuE2 MCP 调用清单
    python audio_forge.py --project . --emit-tts    # 出 TTS 请求清单
    python audio_forge.py --project . --probe       # 探测三个通道是否在线
    python audio_forge.py --project . --synth       # 用 L1 合成全部可自动的音效

产物:
    docs/05-audio/sfx-plan.json      音效规格（事件 → 配方 → 文件）
    docs/05-audio/music-plan.json    音乐规格（mood → YuE2 style → 转码参数）
    docs/05-audio/voice-plan.json    对白规格（台词 → 音色 → 文件）
    docs/05-audio/yue2-calls.json    MCP 调用清单
    docs/05-audio/tts-calls.json     TTS 请求清单
    .gamedev/audio.yaml              通道配置（首次运行自动生成）
"""

from __future__ import annotations

import argparse
import json
import socket
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import dump_json, load_state, ok, project_dir, require_yaml, warn  # noqa: E402
from gen_audio import RECIPES  # noqa: E402  只读配方名，用于校验

AUDIO_DIR = "docs/05-audio"

AUDIO_YAML = """\
# 音频通道配置（scripts/audio_forge.py 读取）
# 三层：L1 程序化合成（内置）/ L2 YuE2-Studio（本地 MCP）/ L3 TTS（本地服务）

yue2:
  enabled: true
  endpoint: http://127.0.0.1:8791/mcp      # YuE2-Studio 运行时提供（streamable HTTP）
  timeout_seconds: 600
  # 产物是 48kHz 立体声 FLAC（约 6MB/33s），必须转码，见 transcode

tts:
  enabled: false                            # boss 确认本地 TTS 2.5 端点后再打开
  provider: local
  endpoint: ""                              # 例 http://127.0.0.1:9880/tts
  method: POST
  body_template: '{"text":"{text}","speaker":"{voice}","speed":1.0}'
  out_format: wav
  voices:
    narrator: "zh-female-warm"
    protagonist: "zh-male-young"
    antagonist: "zh-male-deep"

transcode:
  # YuE2 产物统一按此转码，否则单首曲子就吃掉首包 1/3
  ss: 2                 # 跳过前奏
  t: 28                 # 取 28 秒（YuE2 请求 30s 实际约 26–34s，取中段最稳）
  ac: 1                 # 单声道
  bitrate: "96k"
  loop: true            # 首尾交叉淡化做无缝循环
"""

# ------------------------------------------------------------------ 默认音效库
# 蓝图没写 sfx_events 时用它兜底：开箱就是 22 条，覆盖四个 layer。
# (id, layer, cue, desc, recipe, params, priority)
DEFAULT_EVENTS = [
    ("ui_click",       "ui", "menu_button", "按钮点击，极短",              "blip",       {"freq": 1320, "dur": 0.04}, "high"),
    ("ui_hover",       "ui", "menu_hover", "悬停提示，比点击更轻",          "blip",       {"freq": 1760, "dur": 0.03, "gain": 0.5}, "low"),
    ("ui_back",        "ui", "menu_back", "返回，下行两音",                "sweep_down", {"f0": 660, "f1": 440, "dur": 0.08}, "low"),
    ("ui_confirm",     "ui", "menu_confirm", "确认，上行两音",              "arp",        {"notes": "784,1046", "step": 0.07}, "low"),
    ("gameplay_action",  "gameplay", "main_action", "主行为（攻击/敲击）",   "hit",        {}, "high"),
    ("gameplay_action_b", "gameplay", "alt_action", "次要行为",             "blip",       {"freq": 660, "dur": 0.08, "kind": "tri"}, "low"),
    ("gameplay_place",   "gameplay", "place_object", "放置/建造，有重量感", "thud",       {"f0": 160, "f1": 100, "dur": 0.14, "noise": 0.2}, "high"),
    ("gameplay_cast",    "gameplay", "cast_skill", "施法/触发",             "sweep_up",   {"f0": 400, "f1": 900, "dur": 0.14}, "low"),
    ("gameplay_move",    "gameplay", "move", "移动/切换",                  "blip",       {"freq": 520, "dur": 0.04}, "low"),
    ("gameplay_block",   "gameplay", "blocked", "被挡住/无效操作",          "noise_burst", {"dur": 0.1, "cutoff": 40}, "low"),
    ("feedback_score",     "feedback", "score", "得分（小）",              "chime",      {"freq": 1320, "dur": 0.2}, "high"),
    ("feedback_score_big", "feedback", "score_big", "得分（大/暴击）",     "arp",        {"notes": "988,1318,1760", "step": 0.08}, "high"),
    ("feedback_combo",     "feedback", "combo_up", "连击上升",             "combo",      {}, "high"),
    ("feedback_hurt",      "feedback", "hurt", "受伤/受损，下行",           "sweep_down", {"f0": 300, "f1": 150, "dur": 0.18}, "high"),
    ("feedback_levelup",   "feedback", "levelup", "升级/过关",             "levelup",    {}, "high"),
    ("feedback_win",       "feedback", "victory", "胜利 stinger",           "levelup",    {}, "high"),
    ("feedback_defeat",    "feedback", "defeat", "失败 stinger（克制）",    "fail",       {}, "high"),
    ("feedback_boss",      "feedback", "boss", "首领登场 stinger",          "thud",       {"f0": 90, "f1": 40, "dur": 0.5, "noise": 0.45}, "high"),
    ("feedback_event",     "feedback", "reveal", "关键揭示（叙事反转）",    "chime",      {"freq": 880, "dur": 0.5}, "high"),
    ("ambience_wind",      "ambience", "ambient", "环境：风/海",            "pad_loop",   {"freq": 98.0, "dur": 6.0}, "low"),
    ("ambience_hum",       "ambience", "ambient", "环境：机械/电流",        "pad_loop",   {"freq": 130.8, "dur": 6.0, "bright": 0.15}, "low"),
    ("ambience_water",     "ambience", "ambient", "环境：水声底噪",          "pad_loop",   {"freq": 146.8, "dur": 6.0, "bright": 0.4}, "low"),
]

# mood → YuE2 style（<genre> · <mood> · <instruments> · <tempo> · <texture>）
MUSIC_STYLES = {
    "calm": ("ambient folk, gentle and sparse, solo music box with soft pad, 72 bpm, "
             "no drums, long reverb tails, loopable",
             {"bpm": 72, "mode": "major"}),
    "tense": ("dark minimal techno, uneasy and patient, low pulse with metallic ticks, 104 bpm, "
              "no melody, tight low end, loopable",
              {"bpm": 104, "mode": "minor"}),
    "mystery": ("cinematic drone, mysterious and cold, bowed strings and distant bells, 66 bpm, "
                "no percussion, wide stereo bed, loopable",
                {"bpm": 66, "mode": "minor"}),
    "busy": ("upbeat chiptune, playful and driving, square lead with noise snare, 128 bpm, "
             "steady groove, loopable",
             {"bpm": 128, "mode": "major"}),
    "victory": ("uplifting orchestral pop, triumphant, brass and bells, 128 bpm, major key, "
                "big ending, not loopable",
                {"bpm": 128, "mode": "major"}),
    "defeat": ("melancholic piano, resigned and quiet, single piano with room tone, 60 bpm, "
               "no percussion, not loopable",
               {"bpm": 60, "mode": "minor"}),
}
DEFAULT_MOODS = ["calm", "tense", "victory"]

# 关键词 → 配方 猜测（蓝图只写了 desc 时用）
GUESS = [
    (("combo", "连击"), "combo"),
    (("level", "升级", "过关"), "levelup"),
    (("win", "胜利", "成功"), "levelup"),
    (("fail", "失败"), "fail"),
    (("hurt", "受伤", "受击", "损失"), "sweep_down"),
    (("place", "放", "建", "落地"), "thud"),
    (("score", "得分", "金币", "收集"), "chime"),
    (("ambient", "环境", "底噪"), "pad_loop"),
    (("click", "点", "按"), "blip"),
]


def load_json(p: Path, default=None):
    if not p.exists():
        return default
    try:
        with p.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:  # noqa: BLE001
        warn(f"解析失败 {p}：{e}")
        return default


def read_audio_cfg(proj: Path) -> dict:
    yaml = require_yaml()
    p = proj / ".gamedev" / "audio.yaml"
    if not p.exists():
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(AUDIO_YAML, encoding="utf-8")
        ok("已生成 .gamedev/audio.yaml（音频通道配置）")
    try:
        return yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    except Exception as e:  # noqa: BLE001
        warn(f"audio.yaml 解析失败：{e}")
        return {}


def guess_recipe(layer: str, text: str) -> str:
    t = text.lower()
    for keys, rec in GUESS:
        if any(k in t for k in keys):
            return rec
    return {"ui": "blip", "gameplay": "hit", "feedback": "chime", "ambience": "pad_loop"}.get(layer, "blip")


# ------------------------------------------------------------------ plan
def cmd_plan(args) -> int:
    proj = project_dir(args.project)
    bp = load_json(proj / "docs" / "01-brief" / "content-blueprint.json", {}) or {}
    a = bp.get("audio") or {}
    cfg = read_audio_cfg(proj)
    tc = cfg.get("transcode") or {}

    # --- sfx-plan
    events = a.get("sfx_events") or []
    by_id = {e.get("id"): e for e in events if e.get("id")}
    items = []
    used = set()
    for eid, layer, cue, desc, rec, params, prio in DEFAULT_EVENTS:
        over = by_id.get(eid) or {}
        recipe = (over.get("synth") or {}).get("recipe") or over.get("recipe") or rec
        if recipe not in RECIPES:
            warn(f"{eid} 的配方 `{recipe}` 不存在，回退 {rec}")
            recipe = rec
        items.append({
            "id": eid,
            "layer": over.get("layer") or layer,
            "cue": over.get("cue") or cue,
            "desc": over.get("desc") or desc,
            "duration_ms": int(round((over.get("duration_ms") or 0) or 120)),
            "pitch_dir": over.get("pitch_dir") or ("down" if "down" in recipe else ("up" if "up" in recipe else "flat")),
            "priority": over.get("priority") or prio,
            "synth": {"recipe": recipe, "params": (over.get("synth") or {}).get("params") or params},
            "file": f"assets/audio/sfx/{eid}.mp3",
        })
        used.add(eid)
    # 蓝图里额外声明的事件（不在默认库里）也纳入
    for e in events:
        eid = e.get("id")
        if not eid or eid in used:
            continue
        layer = e.get("layer") or "gameplay"
        desc = e.get("desc") or e.get("name") or eid
        recipe = (e.get("synth") or {}).get("recipe") or guess_recipe(layer, f"{eid} {desc}")
        items.append({
            "id": eid, "layer": layer, "cue": e.get("cue") or eid, "desc": desc,
            "duration_ms": int(e.get("duration_ms") or 150),
            "pitch_dir": e.get("pitch_dir") or "flat",
            "priority": e.get("priority") or "low",
            "synth": {"recipe": recipe, "params": (e.get("synth") or {}).get("params") or {}},
            "file": f"assets/audio/sfx/{eid}.mp3",
        })

    sfx_plan = {
        "version": "2.0",
        "total_budget_kb": 400,
        "layers_required": ["ui", "gameplay", "feedback", "ambience"],
        "items": items,
        "note": "gen_audio.py --spec 会按 synth.recipe 合成；无配方的事件标 manual 交外部工具",
    }
    dump_json(proj / AUDIO_DIR / "sfx-plan.json", sfx_plan)

    # --- music-plan
    moods = a.get("mood_arc") or DEFAULT_MOODS
    if len(moods) < 2:
        moods = list(dict.fromkeys(moods + DEFAULT_MOODS))[:2]
    cues_declared = {c.get("id") or c.get("mood"): c for c in (a.get("music_cues") or [])}
    try:
        proj_slug = (load_state(proj).get("project") or {}).get("name") or "game"
    except SystemExit:
        proj_slug = "game"
    music_items = []
    for mood in dict.fromkeys(moods):
        style, fb = MUSIC_STYLES.get(mood, MUSIC_STYLES["calm"])
        over = cues_declared.get(mood) or {}
        music_items.append({
            "id": mood,
            "mood": mood,
            "when": over.get("when") or "",
            "style": over.get("style") or style,
            "lyrics": "",
            "title": f"{proj_slug}-{mood}",
            "duration_seconds": int(over.get("duration_seconds") or 30),
            "provider": "yue2",
            "target_file": f"assets/audio/bgm/{mood}.mp3",
            "transcode": {
                "ss": int(tc.get("ss", 2)), "t": int(tc.get("t", 28)),
                "ac": int(tc.get("ac", 1)), "bitrate": str(tc.get("bitrate", "96k")),
                "loop": bool(tc.get("loop", True)),
            },
            "fallback": {"enabled": True, **fb},
        })
    dump_json(proj / AUDIO_DIR / "music-plan.json", {
        "version": "2.0",
        "provider": "yue2",
        "endpoint": (cfg.get("yue2") or {}).get("endpoint", ""),
        "items": music_items,
        "note": "lyrics 必须留空（YuE2 有人声会盖住反馈音）；产物需按 transcode 转码",
    })

    # --- voice-plan
    dlg = ((bp.get("story") or {}).get("dialogue")) or []
    vcfg = cfg.get("tts") or {}
    voices = vcfg.get("voices") or {}
    vitems = []
    for i, d in enumerate(dlg):
        spk = str(d.get("speaker") or "narrator")
        cue = str(d.get("cue") or "misc")
        vitems.append({
            "id": f"v{i+1:02d}",
            "cue": cue,
            "speaker": spk,
            "voice": voices.get(spk) or voices.get("narrator") or "zh-female-warm",
            "text": d.get("line") or "",
            "emotion": d.get("emotion") or "calm",
            "target_file": f"assets/audio/voice/{spk}_{cue}_{i}.mp3",
        })
    voice = {
        "version": "2.0",
        "enabled": bool(vcfg.get("enabled")) and bool(vitems),
        "reason": "" if (vcfg.get("enabled") and vitems) else (
            "TTS 通道未启用（.gamedev/audio.yaml 的 tts.enabled=false）" if vitems else "本游戏无对白"),
        "cover_ratio_target": 0.6,
        "items": vitems,
    }
    dump_json(proj / AUDIO_DIR / "voice-plan.json", voice)

    layers = {i["layer"] for i in items}
    print(f"sfx-plan：{len(items)} 条，覆盖 layer {len(layers)}/4 → {', '.join(sorted(layers))}")
    print(f"music-plan：{len(music_items)} 段（{', '.join(m['mood'] for m in music_items)}）")
    print(f"voice-plan：{len(vitems)} 条对白，启用={voice['enabled']}")
    ok(f"三份 plan 已写入 {AUDIO_DIR}/")
    print("\n下一步：")
    print("  python scripts/audio_forge.py --project . --probe")
    print("  python scripts/gen_audio.py --project . --spec docs/05-audio/sfx-plan.json")
    print("  python scripts/gen_audio.py --project . --music-spec docs/05-audio/music-plan.json  # 兜底 BGM")
    return 0


# ------------------------------------------------------------------ emit
def cmd_emit_yue2(args) -> int:
    proj = project_dir(args.project)
    plan = load_json(proj / AUDIO_DIR / "music-plan.json")
    if not plan:
        print("ERROR: 缺 music-plan.json（先跑 --plan）", file=sys.stderr)
        return 1
    calls = []
    for it in plan.get("items") or []:
        tr = it.get("transcode") or {}
        calls.append({
            "tool": "song_create",
            "args": {
                "style": it["style"],
                "lyrics": "",
                "title": it.get("title") or it["id"],
                "duration_seconds": int(it.get("duration_seconds") or 30),
            },
            "then": ["song_job_get", "library_song_get"],
            "target_file": it["target_file"],
            "ffmpeg": (
                f'ffmpeg -y -i <generated.flac> -ss {tr.get("ss", 2)} -t {tr.get("t", 28)} '
                f'-ac {tr.get("ac", 1)} -ar 44100 -codec:a libmp3lame -b:a {tr.get("bitrate", "96k")} '
                f'{it["target_file"]}'
            ),
            "note": "YuE2 出 48kHz 立体声 FLAC（约 6MB/33s），必须按 ffmpeg 转码后再进游戏",
        })
    out = {
        "version": "2.0",
        "endpoint": plan.get("endpoint") or "http://127.0.0.1:8791/mcp",
        "how": "YuE2-Studio 必须保持窗口运行；MCP streamable HTTP，最小链见 calls",
        "calls": calls,
        "volume_warning": "30s×96kbps 单声道 ≈ 360KB/段；3 段 ≈ 1.1MB，占首包 5.5%",
    }
    dump_json(proj / AUDIO_DIR / "yue2-calls.json", out)
    ok(f"已生成 {len(calls)} 条 YuE2 调用 → {AUDIO_DIR}/yue2-calls.json")
    for c in calls:
        print(f"  song_create style=\"{c['args']['style'][:60]}…\"  → {c['target_file']}")
    return 0


def cmd_emit_tts(args) -> int:
    proj = project_dir(args.project)
    plan = load_json(proj / AUDIO_DIR / "voice-plan.json")
    cfg = read_audio_cfg(proj)
    if not plan:
        print("ERROR: 缺 voice-plan.json（先跑 --plan）", file=sys.stderr)
        return 1
    tts = cfg.get("tts") or {}
    calls = []
    for it in plan.get("items") or []:
        calls.append({
            "id": it["id"],
            "endpoint": tts.get("endpoint", ""),
            "method": tts.get("method", "POST"),
            "body": (tts.get("body_template") or '{"text":"{text}","speaker":"{voice}"}')
                    .replace("{text}", it["text"]).replace("{voice}", it["voice"]),
            "raw": {"text": it["text"], "voice": it["voice"], "emotion": it["emotion"], "cue": it["cue"]},
            "out": it["target_file"],
            "post": "ffmpeg -y -i <out.wav> -ac 1 -codec:a libmp3lame -b:a 96k " + it["target_file"],
        })
    dump_json(proj / AUDIO_DIR / "tts-calls.json", {
        "version": "2.0",
        "enabled": bool(tts.get("enabled")),
        "endpoint": tts.get("endpoint", ""),
        "blocker": "" if tts.get("endpoint") else "tts.endpoint 未配置：需 boss 提供本地 TTS 2.5 的实际端口/路径",
        "calls": calls,
    })
    ok(f"已生成 {len(calls)} 条 TTS 请求 → {AUDIO_DIR}/tts-calls.json")
    if not tts.get("enabled"):
        warn("TTS 未启用（.gamedev/audio.yaml 的 tts.enabled=false），清单仅供参考")
    return 0


# ------------------------------------------------------------------ probe
def port_open(host: str, port: int, timeout: float = 1.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def cmd_probe(args) -> int:
    proj = project_dir(args.project)
    cfg = read_audio_cfg(proj)
    yue2 = cfg.get("yue2") or {}
    tts = cfg.get("tts") or {}
    rows = []

    from urllib.parse import urlparse
    def hostport(url: str, default_port: int):
        try:
            u = urlparse(url)
            return (u.hostname or "127.0.0.1"), (u.port or default_port)
        except Exception:  # noqa: BLE001
            return "127.0.0.1", default_port

    y_url = yue2.get("endpoint") or "http://127.0.0.1:8791/mcp"
    h, p = hostport(y_url, 8791)
    rows.append(("L2 YuE2-Studio", f"{h}:{p}", port_open(h, p), "音乐生成（MCP）"))
    h2, p2 = hostport("http://127.0.0.1:8188", 8188)
    rows.append(("图像 ComfyUI", f"{h2}:{p2}", port_open(h2, p2), "素材生成"))
    if tts.get("endpoint"):
        h3, p3 = hostport(tts["endpoint"], 80)
        rows.append(("L3 TTS", f"{h3}:{p3}", port_open(h3, p3), "对白配音"))
    else:
        rows.append(("L3 TTS", "未配置", False, "需 boss 提供本地 TTS 2.5 地址"))

    print("音频通道探测：")
    for name, addr, up, note in rows:
        print(f"  {'✅' if up else '❌'} {name:<16} {addr:<22} {note}")
    print("\nL1 程序化合成：始终可用（numpy + ffmpeg 已在环境内）")
    degraded = [n for n, _a, up, _n in rows if not up]
    if degraded:
        warn(f"以下通道不可用，相关产出将降级：{', '.join(degraded)}")
        print("  降级路径：音乐 → gen_audio.py --music-spec（和弦循环）；对白 → 只出字幕")
    dump_json(proj / AUDIO_DIR / "probe.json", {
        "channels": [{"name": n, "addr": a, "up": u, "note": nt} for n, a, u, nt in rows],
    })
    return 0


def cmd_synth(args) -> int:
    proj = project_dir(args.project)
    plan = proj / AUDIO_DIR / "sfx-plan.json"
    if not plan.exists():
        print("ERROR: 缺 sfx-plan.json（先跑 --plan）", file=sys.stderr)
        return 1
    script = Path(__file__).resolve().parent / "gen_audio.py"
    cmd = [sys.executable, str(script), "--project", str(proj), "--spec", str(plan),
           "--music-spec", str(proj / AUDIO_DIR / "music-plan.json")]
    print("调用 L1 合成：", " ".join(Path(c).name if i == 1 else c for i, c in enumerate(cmd[1:], 1)))
    r = subprocess.run(cmd)
    return r.returncode


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    ap = argparse.ArgumentParser(description="音效设计器")
    ap.add_argument("--project", default=None)
    ap.add_argument("--plan", action="store_true")
    ap.add_argument("--emit-yue2", action="store_true")
    ap.add_argument("--emit-tts", action="store_true")
    ap.add_argument("--probe", action="store_true")
    ap.add_argument("--synth", action="store_true")
    args = ap.parse_args()
    if args.plan:
        return cmd_plan(args)
    if args.emit_yue2:
        return cmd_emit_yue2(args)
    if args.emit_tts:
        return cmd_emit_tts(args)
    if args.probe:
        return cmd_probe(args)
    if args.synth:
        return cmd_synth(args)
    ap.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
