#!/usr/bin/env python3
"""程序化 stem 合成：没有音乐生成服务时，也能得到真正的分轨自适应音乐。

为什么需要它 —— 自适应音乐的前提是「同一首曲子的分轨可以独立控音量」。
如果外部音乐通道（YuE2 等）不可用，退化成「几段不同的曲子」就失去了分层的意义：
切歌会有接缝，情绪变化只能是硬切。

本脚本用 numpy 合成 5 条**同调、同速、可无缝循环**的 stem（旋律/节奏/低频/打击/氛围），
所有状态共用这 5 条，切换状态只改音量 —— 这就是 stem 方案的全部好处。

产物是 96kbps 单声道 MP3（体积红线要求），不保留 wav。

用法:
    python gen_stems.py --project .
    python gen_stems.py --project . --seconds 20 --bpm 68 --root 45
    python gen_stems.py --project . --only melody,bass

退出码: 0=成功　2=ffmpeg 缺失（文件已留 wav，需手工转码）
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import wave
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import ok, project_dir, warn  # noqa: E402
from audio_director import ffmpeg_bin  # noqa: E402

SR = 44100
STEMS = ["melody", "rhythm", "bass", "percussion", "atmosphere"]


def midi_hz(n: int) -> float:
    return 440.0 * 2 ** ((n - 69) / 12)


def env(n: int, attack: float, decay: float, sr: int = SR):
    """简单 AD 包络。attack/decay 单位秒。"""
    import numpy as np
    a = max(1, int(attack * sr))
    d = max(1, int(decay * sr))
    total = a + d
    if total > n:
        total = n
        a = max(1, int(n * attack / (attack + decay)))
        d = max(1, n - a)
    e = np.concatenate([np.linspace(0, 1, a), np.exp(-np.linspace(0, 6, d))])
    if e.size < n:
        e = np.pad(e, (0, n - e.size))
    return e[:n]


def tone(freq: float, dur: float, kind: str = "sine", detune: float = 0.0, sr: int = SR):
    import numpy as np
    n = int(dur * sr)
    t = np.arange(n) / sr
    if kind == "sine":
        x = np.sin(2 * np.pi * freq * t)
        if detune:
            x = 0.6 * x + 0.4 * np.sin(2 * np.pi * (freq * (1 + detune)) * t)
    elif kind == "tri":
        x = 2 * np.abs(2 * ((t * freq) % 1) - 1) - 1
    elif kind == "noise":
        x = np.random.default_rng(7).standard_normal(n) * 0.5
    else:
        x = np.sin(2 * np.pi * freq * t)
    return x


def lowpass(x, alpha: float = 0.02):
    """一阶低通（IIR），alpha 越小越闷。"""
    import numpy as np
    y = np.empty_like(x)
    acc = 0.0
    for i in range(x.size):
        acc += alpha * (x[i] - acc)
        y[i] = acc
    return y


def make_loop(x, sr: int = SR, fade_s: float = 0.35):
    """把任意信号变成可无缝循环：尾部与头部交叉淡化，长度不变。"""
    import numpy as np
    n = int(fade_s * sr)
    if x.size < n * 3:
        return x
    head = x[:n].copy()
    tail = x[-n:].copy()
    w = np.linspace(0, 1, n)
    x[:n] = head * w + tail * (1 - w)
    return x


def build_stem(stem: str, seconds: float, bpm: float, root: int) -> "object":
    import numpy as np
    sr = SR
    n = int(seconds * sr)
    out = np.zeros(n, dtype=np.float32)
    rng = np.random.default_rng(20261101 + sum(map(ord, stem)))
    beat = 60.0 / bpm
    minor = [0, 2, 3, 5, 7, 8, 10]  # 自然小调

    def place(sig, at_s: float, gain: float = 1.0):
        i = int(at_s * sr) % n
        m = min(sig.size, n - i)
        if m <= 0:
            return
        out[i:i + m] += sig[:m] * gain
        # 溢出部分绕回开头，保证循环边界连续
        if sig.size > m:
            rest = sig.size - m
            out[:rest] += sig[m:] * gain

    if stem == "melody":
        # 稀疏单音，乐句之间留大量空白（探索状态的主层）
        phrase = [0, 4, 7, 3]
        t = 1.2
        k = 0
        while t < seconds - 1.5:
            deg = minor[phrase[k % len(phrase)] % len(minor)]
            f = midi_hz(root + 12 + deg)
            sig = tone(f, 1.6, "sine", detune=0.002) * env(int(1.6 * sr), 0.01, 1.5)
            place(sig, t, 0.34)
            t += beat * (3 if k % 3 else 5)
            k += 1

    elif stem == "rhythm":
        # 弱拍木质感 tick，像船体的节律
        t = 0.0
        while t < seconds:
            f = midi_hz(root + 24)
            sig = tone(f, 0.06, "tri") * env(int(0.06 * sr), 0.001, 0.05)
            place(sig, t, 0.16)
            t += beat

    elif stem == "bass":
        # 持续低频 drone + 极慢呼吸
        t = np.arange(n) / sr
        f = midi_hz(root)
        sig = (np.sin(2 * np.pi * f * t) * 0.6
               + np.sin(2 * np.pi * f * 0.5 * t) * 0.25)
        lfo = 0.75 + 0.25 * np.sin(2 * np.pi * t / max(1.0, seconds / 2))
        out += (sig * lfo).astype(np.float32) * 0.4

    elif stem == "percussion":
        # 稀疏冲击：低频 thump + 短噪声
        t = 0.0
        while t < seconds:
            thump = tone(midi_hz(root - 12), 0.5, "sine") * env(int(0.5 * sr), 0.002, 0.45)
            noise = tone(0, 0.12, "noise") * env(int(0.12 * sr), 0.001, 0.1)
            place(thump, t, 0.3)
            place(lowpass(noise, 0.05), t, 0.12)
            t += beat * 4

    elif stem == "atmosphere":
        # 带通噪声 wash（海浪/雾），缓慢起伏
        t = np.arange(n) / sr
        base = rng.standard_normal(n).astype(np.float32) * 0.5
        sig = lowpass(base, 0.004)
        lfo = 0.5 + 0.5 * np.sin(2 * np.pi * t / max(1.0, seconds / 3))
        out += (sig * lfo).astype(np.float32) * 0.9

    out = make_loop(out)
    # 归一化到 -6dBFS 峰值，给混音留余量
    peak = float(np.max(np.abs(out))) or 1.0
    out = out / peak * 0.5
    return out


def write_wav(path: Path, data) -> None:
    import numpy as np
    pcm = np.clip(data * 32767, -32768, 32767).astype(np.int16)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())


def to_mp3(wav: Path, mp3: Path, bitrate: str = "96k") -> bool:
    ff = ffmpeg_bin()
    if not ff:
        return False
    mp3.parent.mkdir(parents=True, exist_ok=True)
    r = subprocess.run([ff, "-y", "-v", "error", "-i", str(wav), "-ac", "1", "-ar", "44100",
                        "-codec:a", "libmp3lame", "-b:a", bitrate, str(mp3)], capture_output=True)
    return r.returncode == 0 and mp3.exists()


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass
    ap = argparse.ArgumentParser(description="程序化 stem 合成（自适应音乐降级通道）")
    ap.add_argument("--project", default=None)
    ap.add_argument("--seconds", type=float, default=20.0)
    ap.add_argument("--bpm", type=float, default=68.0)
    ap.add_argument("--root", type=int, default=45, help="MIDI 根音（45=A2）")
    ap.add_argument("--only", default="", help="逗号分隔，只合成指定 stem")
    ap.add_argument("--keep-wav", action="store_true")
    args = ap.parse_args()

    proj = project_dir(args.project)
    outdir = proj / "assets" / "audio" / "bgm"
    outdir.mkdir(parents=True, exist_ok=True)
    only = [s.strip() for s in args.only.split(",") if s.strip()] or STEMS

    try:
        import numpy  # noqa: F401
    except ImportError:
        print("ERROR: 需要 numpy（托管 venv 已内置）", file=sys.stderr)
        return 1

    fail_mp3 = False
    for stem in only:
        if stem not in STEMS:
            warn(f"未知 stem `{stem}`，跳过（可用：{', '.join(STEMS)}）")
            continue
        data = build_stem(stem, args.seconds, args.bpm, args.root)
        wav = outdir / f"stem_{stem}.wav"
        write_wav(wav, data)
        mp3 = outdir / f"stem_{stem}.mp3"
        if to_mp3(wav, mp3):
            size = mp3.stat().st_size / 1024
            print(f"  ✅ stem_{stem}.mp3  {args.seconds:.0f}s  {size:.0f}KB")
            if not args.keep_wav:
                wav.unlink(missing_ok=True)
        else:
            fail_mp3 = True
            print(f"  ⚠️ stem_{stem}.wav 已生成，但 ffmpeg 不可用，无法转 mp3")

    if fail_mp3:
        warn("ffmpeg 缺失：请安装 ffmpeg 后重跑，或手工转码（不能把 wav 交付，gate 会判失败）")
        return 2
    ok(f"stem 合成完成 → {outdir.relative_to(proj)}")
    print("下一步：python scripts/audio_director.py --project . --qc")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
