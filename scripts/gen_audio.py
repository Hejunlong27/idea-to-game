#!/usr/bin/env python3
"""程序化音频生成（模块 07 用）：音效 + 可循环 BGM，直出 MP3。

为什么程序化：小游戏音频只要「反馈明确、不刺耳」，合成比找素材更快更可控，
且体积可压到几十 KB（本包 4 个音频合计 < 200KB）。

用法:
    python gen_audio.py --project .                      # 默认 4 个音效 + 1 段 BGM
    python gen_audio.py --project . --sfx hit,miss       # 只出指定音效
    python gen_audio.py --project . --bgm none           # 不要 BGM

产物（严格 MP3，不留 WAV —— gate_check 会因 .wav 判失败）:
    assets/audio/sfx/{hit,miss,over,click}.mp3
    assets/audio/bgm/loop.mp3

依赖: numpy、ffmpeg（PATH 里能找到）
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tempfile
import wave
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import ok, project_dir, warn  # noqa: E402

try:
    import numpy as np
except ImportError:
    print("ERROR: 需要 numpy。请安装：pip install numpy", file=sys.stderr)
    raise SystemExit(1)

SR = 44100


def env(t: np.ndarray, attack: float = 0.005, decay: float = 0.12) -> np.ndarray:
    """简单 AD 包络，避免爆音。"""
    a = np.clip(t / max(attack, 1e-6), 0, 1)
    d = np.exp(-t / max(decay, 1e-6))
    return a * d


def tone(freq: float, dur: float, kind: str = "sine", detune: float = 0.0) -> np.ndarray:
    t = np.linspace(0, dur, int(SR * dur), endpoint=False)
    f = freq * (1 + detune)
    if kind == "sine":
        w = np.sin(2 * np.pi * f * t)
    elif kind == "tri":
        w = 2 * np.abs(2 * ((t * f) % 1) - 1) - 1
    else:  # square 经过低通近似，避免刺耳
        w = np.tanh(3 * np.sin(2 * np.pi * f * t))
    return w * env(t)


def sweep(f0: float, f1: float, dur: float, kind: str = "sine") -> np.ndarray:
    t = np.linspace(0, dur, int(SR * dur), endpoint=False)
    f = np.linspace(f0, f1, t.size)
    phase = 2 * np.pi * np.cumsum(f) / SR
    w = np.sin(phase) if kind == "sine" else np.tanh(3 * np.sin(phase))
    return w * env(t, 0.004, dur * 0.45)


def mix(*tracks: np.ndarray) -> np.ndarray:
    n = max(t.size for t in tracks)
    out = np.zeros(n)
    for t in tracks:
        out[: t.size] += t
    peak = np.max(np.abs(out)) or 1.0
    return out / peak * 0.85


# ------------------------------------------------------------------ 音效配方
def sfx_hit() -> np.ndarray:
    """命中：明亮的短促上滑 + 一点三角波厚度。"""
    return mix(sweep(660, 1180, 0.09), tone(990, 0.07, "tri") * 0.35)


def sfx_miss() -> np.ndarray:
    """漏掉：低沉的短下滑，不刺耳（失败反馈要克制）。"""
    return mix(sweep(300, 150, 0.16), tone(140, 0.14, "sine") * 0.4)


def sfx_over() -> np.ndarray:
    """结算：下行三音，收尾干净。"""
    seq = [784, 659, 523]
    parts = []
    for i, f in enumerate(seq):
        parts.append(tone(f, 0.22, "tri") * (1.0 - i * 0.15))
    out = np.concatenate(parts)
    return out / (np.max(np.abs(out)) or 1.0) * 0.85


def sfx_click() -> np.ndarray:
    """UI 点击：极短，不喧宾夺主。"""
    return tone(1320, 0.04, "sine") * 0.8


def _hit_pitch(freq: float):
    """连击音阶：连击越高音越高，玩家不用看数字也知道自己在爬。"""

    def fn() -> np.ndarray:
        return mix(sweep(freq, freq * 1.7, 0.09), tone(freq * 1.5, 0.07, "tri") * 0.3)

    return fn


def sfx_gold() -> np.ndarray:
    """金色史莱姆：两声清脆铃音，比普通命中更"贵"。"""
    return mix(tone(1320, 0.22, "sine"), tone(1980, 0.18, "sine") * 0.6, tone(2640, 0.12, "sine") * 0.3)


def sfx_bomb() -> np.ndarray:
    """炸弹：低频冲击 + 短噪声，明确"负面"。"""
    rng = np.random.default_rng(7)
    t = np.linspace(0, 0.28, int(SR * 0.28), endpoint=False)
    noise = rng.uniform(-1, 1, t.size) * np.exp(-t / 0.05)
    # 简单一阶低通，去掉刺耳的高频
    lp = np.convolve(noise, np.ones(24) / 24, mode="same")
    thump = np.sin(2 * np.pi * np.linspace(120, 55, t.size) * t) * np.exp(-t / 0.12)
    return mix(lp * 0.8, thump * 0.9)


def sfx_ice() -> np.ndarray:
    """冰冻：玻璃质感的高频泛音，短促。"""
    return mix(tone(1760, 0.2, "sine"), tone(2637, 0.14, "sine") * 0.5, tone(3520, 0.08, "sine") * 0.25)


def sfx_combo() -> np.ndarray:
    """连击里程碑：三连上行，短。"""
    seq = [659, 880, 1174]
    out = np.concatenate([tone(f, 0.09, "tri") for f in seq])
    return out / (np.max(np.abs(out)) or 1.0) * 0.85


def sfx_levelup() -> np.ndarray:
    """过关：四音上行小号角。"""
    seq = [523, 659, 784, 1046]
    out = np.concatenate([tone(f, 0.14, "tri") for f in seq])
    return out / (np.max(np.abs(out)) or 1.0) * 0.9


def sfx_fail() -> np.ndarray:
    """未过关：两音下行，不刺耳（失败反馈要克制）。"""
    seq = [392, 294]
    out = np.concatenate([tone(f, 0.2, "tri") for f in seq])
    return out / (np.max(np.abs(out)) or 1.0) * 0.8


SFX = {
    "hit": sfx_hit,
    "hit1": _hit_pitch(660),
    "hit2": _hit_pitch(784),
    "hit3": _hit_pitch(880),
    "hit4": _hit_pitch(1046),
    "miss": sfx_miss,
    "over": sfx_over,
    "click": sfx_click,
    "gold": sfx_gold,
    "bomb": sfx_bomb,
    "ice": sfx_ice,
    "combo": sfx_combo,
    "levelup": sfx_levelup,
    "fail": sfx_fail,
}


def bgm_loop(bars: int = 8, bpm: int = 96) -> np.ndarray:
    """可循环的轻快 BGM：I–V–vi–IV 四和弦循环 + 简单琶音。

    循环点处理：首尾各留 0 增益的 1 拍，避免接缝爆音。
    """
    beat = 60.0 / bpm
    bar = beat * 4
    total = bar * bars
    n = int(SR * total)
    out = np.zeros(n)

    # C 大调：C  G  Am F
    chords = [(261.6, 329.6, 392.0), (196.0, 246.9, 392.0), (220.0, 261.6, 329.6), (174.6, 220.0, 349.2)]

    for b in range(bars):
        root = chords[b % len(chords)]
        start = int(SR * bar * b)
        # 和弦铺底（柔和的三角波，长衰减）
        for f in root:
            seg = tone(f * 0.5, bar * 0.92, "tri") * 0.16
            out[start : start + seg.size] += seg[: max(0, min(seg.size, n - start))]
        # 琶音（每半拍一个音）
        for i in range(8):
            f = root[i % 3] * (2 if i % 4 >= 2 else 1)
            seg = tone(f, beat * 0.42, "sine") * 0.2
            s = start + int(SR * beat * 0.5 * i)
            if s + seg.size <= n:
                out[s : s + seg.size] += seg

    # 首尾淡入淡出，保证 loop 接缝无爆音
    fade = int(SR * 0.03)
    out[:fade] *= np.linspace(0, 1, fade)
    out[-fade:] *= np.linspace(1, 0, fade)
    peak = np.max(np.abs(out)) or 1.0
    return out / peak * 0.5


# ------------------------------------------------------------------ 输出
def write_mp3(samples: np.ndarray, dst: Path) -> None:
    ffmpeg = shutil.which("ffmpeg") or "ffmpeg"
    dst.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as td:
        wav = Path(td) / "t.wav"
        data = np.clip(samples, -1, 1)
        pcm = (data * 32767).astype("<i2").tobytes()
        with wave.open(str(wav), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(SR)
            w.writeframes(pcm)
        cmd = [ffmpeg, "-y", "-loglevel", "error", "-i", str(wav), "-codec:a", "libmp3lame",
               "-b:a", "96k", "-ac", "1", str(dst)]
        subprocess.run(cmd, check=True)


def main() -> int:
    ap = argparse.ArgumentParser(description="程序化音频生成")
    ap.add_argument("--project", default=None)
    ap.add_argument("--sfx", default="hit,miss,over,click", help="逗号分隔；none 表示不生成音效")
    ap.add_argument("--bgm", default="loop", help="BGM 文件名（不含扩展名）；none 表示不生成")
    ap.add_argument("--bpm", type=int, default=96)
    args = ap.parse_args()

    proj = project_dir(args.project)
    if not shutil.which("ffmpeg"):
        print("ERROR: 找不到 ffmpeg（PATH 里没有）。装好后重试，或把 ffmpeg 目录加进 PATH", file=sys.stderr)
        return 1

    names = [] if args.sfx.strip().lower() == "none" else [s.strip() for s in args.sfx.split(",") if s.strip()]
    for name in names:
        fn = SFX.get(name)
        if not fn:
            warn(f"未知音效 {name}；可选：{', '.join(SFX)}")
            continue
        dst = proj / "assets" / "audio" / "sfx" / f"{name}.mp3"
        write_mp3(fn(), dst)
        ok(f"音效 {name}.mp3  {dst.stat().st_size / 1024:.1f}KB")

    if args.bgm.strip().lower() != "none":
        dst = proj / "assets" / "audio" / "bgm" / f"{args.bgm}.mp3"
        write_mp3(bgm_loop(bpm=args.bpm), dst)
        ok(f"BGM {args.bgm}.mp3  {dst.stat().st_size / 1024:.1f}KB")

    # 清掉误留的 wav（gate_check 会因 .wav 判失败）
    for w in (proj / "assets" / "audio").rglob("*.wav"):
        w.unlink()
        warn(f"已删除 wav：{w.name}")

    total = sum(f.stat().st_size for f in (proj / "assets" / "audio").rglob("*.mp3"))
    print(f"音频合计 {total / 1024:.1f}KB（预算 2MB）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
