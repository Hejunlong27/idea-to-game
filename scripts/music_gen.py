#!/usr/bin/env python3
"""Music Gen —— 音乐生成的 provider 抽象层。

## 为什么要有这一层

「以后能接任何音乐生成软件」不是靠写死一个客户端，而是靠**接口隔离**：
游戏只认 `assets/audio/bgm/stem_melody.mp3` 这个文件，谁生成的它不关心。

新增一个音乐软件 = 新增一个 Provider 类，不改调用方，不改游戏代码。

## 已实现

| provider | 通道 | 说明 |
|---|---|---|
| `yue2-http` | `127.0.0.1:8087` 的 `/synth` + `/job` | YuE2 引擎**直连**，不需要 GUI |
| `procedural` | `gen_audio.py` 的 `bgm_loop` | 程序化和弦循环，永远可用 |

`auto` 会按 `yue2-http` → `procedural` 顺序探测。

## YuE2 引擎怎么起（关键）

不要启动 `YuE2-Studio.exe`（GUI，进程会被会话回收）。**直接起引擎**：

```bash
cd "<YuE2>/resources/yue2-cpp"
./yue-server.exe --model "<YuE2>/data/models/yue2-cpp/YuE2-3B-Q8_0.gguf" \
  --vae "<YuE2>/data/models/yue2-cpp/YuE2-Vae-F32.gguf" \
  --companion "<YuE2>/data/models/yue2-cpp/nar_lora_joint_v9.safetensors" \
  --adapters "<YuE2>/data/adapters" --device Vulkan1 --host 127.0.0.1 --port 8087
```

或让本脚本代劳：`python music_gen.py --start-engine`

注意：
- **CUDA 后端当前不可用**（`--device CUDA0` 报 not found，cuda13 的 dll 依赖不全），用 `Vulkan1`。
- Vulkan 下 25 秒音频约需 100 秒（0.2x 实时），比 CUDA 慢，但结果一样。

## 用法

  python music_gen.py --provider auto --all
  python music_gen.py --provider yue2-http --track calm
  python music_gen.py --provider procedural --all
  python music_gen.py --probe                 # 只探测通道可用性
  python music_gen.py --start-engine          # 用 detached 进程拉起引擎

## 产物

规格里的 `target`（如 `assets/audio/bgm/stem_melody.mp3`），统一转成
**96k 单声道 MP3，取中段 `trimSec` 秒**。原始 48kHz 立体声 128k 会被丢弃。
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

# 必须绕系统代理：127.0.0.1 走代理会被劫持成 502
OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))

YUE2_ROOT = Path("D:/编程/ai音乐创作工作台/vendor/YuE2-Studio")
YUE2_ENGINE = YUE2_ROOT / "resources" / "yue2-cpp" / "yue-server.exe"
YUE2_MODELS = YUE2_ROOT / "data" / "models" / "yue2-cpp"
YUE2_PORT = 8087

SPEC = Path("docs/05-audio/bgm-plan.json")


# ---------------------------------------------------------------- 工具

def log(msg: str) -> None:
    print(msg, flush=True)


def http(method: str, url: str, payload: dict | None = None, timeout: int = 30) -> tuple[int, bytes]:
    data = json.dumps(payload).encode() if payload is not None else None
    headers = {"Accept": "application/json, */*"}
    if data:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with OPENER.open(req, timeout=timeout) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()
    except Exception as e:  # noqa: BLE001
        return 0, repr(e).encode()


def ffmpeg_bin(name: str) -> str:
    p = shutil.which(name)
    if p:
        return p
    guess = Path("C:/Users/15274/AppData/Local/Microsoft/WinGet/Links") / f"{name}.exe"
    return str(guess) if guess.exists() else name


def transcode(src: Path, dst: Path, trim_sec: float) -> bool:
    """48kHz 立体声 → 96k 单声道，取中段。开头常有渐入、结尾常有收束，中段最稳。"""
    ffmpeg, ffprobe = ffmpeg_bin("ffmpeg"), ffmpeg_bin("ffprobe")
    probe = subprocess.run(
        [ffprobe, "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(src)],
        capture_output=True, text=True,
    )
    try:
        total = float(probe.stdout.strip())
    except ValueError:
        total = trim_sec * 2
    start = max(0.0, (total - trim_sec) / 2)
    dst.parent.mkdir(parents=True, exist_ok=True)
    r = subprocess.run(
        [ffmpeg, "-y", "-loglevel", "error", "-ss", f"{start:.2f}", "-t", f"{trim_sec:.1f}",
         "-i", str(src), "-ac", "1", "-ar", "44100", "-codec:a", "libmp3lame", "-b:a", "96k", str(dst)],
        capture_output=True, text=True,
    )
    if r.returncode != 0:
        log(f"  转码失败：{r.stderr[:200]}")
        return False
    return True


# ---------------------------------------------------------------- Provider 基类

class MusicProvider:
    """音乐生成通道。新增软件只需实现这三个方法。"""

    name = "base"

    def available(self) -> bool:
        raise NotImplementedError

    def generate(self, spec: dict, workdir: Path) -> Path | None:
        """返回原始音频文件路径（任意格式，调用方负责转码）。"""
        raise NotImplementedError

    def hint(self) -> str:
        """不可用时的提示。"""
        return ""


# ---------------------------------------------------------------- YuE2 HTTP

class Yue2HttpProvider(MusicProvider):
    """直连 YuE2 引擎的 HTTP 服务。

    三步：POST /synth 拿任务 id → GET /job?id= 轮询 → GET /job?id=&result=1 取 multipart。

    为什么不用 MCP：MCP 由 GUI 提供，GUI 进程活不下来；引擎是纯 CLI，能常驻。
    """

    name = "yue2-http"

    def __init__(self, base: str = f"http://127.0.0.1:{YUE2_PORT}"):
        self.base = base

    def available(self) -> bool:
        st, body = http("GET", f"{self.base}/health", timeout=5)
        return st == 200 and b"ok" in body

    def hint(self) -> str:
        return (
            f"YuE2 引擎未运行（{self.base}）。\n"
            f"  → 跑 `python music_gen.py --start-engine`，或手动起：\n"
            f"    {YUE2_ENGINE} --model {YUE2_MODELS / 'YuE2-3B-Q8_0.gguf'} "
            f"--vae {YUE2_MODELS / 'YuE2-Vae-F32.gguf'} --device Vulkan1 --port {YUE2_PORT}"
        )

    def generate(self, spec: dict, workdir: Path) -> Path | None:
        payload = {
            "style": spec.get("prompt", ""),
            # lyrics 必须留空：带歌词会生成人声，游戏 BGM 不需要
            "lyrics": spec.get("lyrics", ""),
            "duration": float(spec.get("durationSec", 30)),
            "output_format": "mp3",
            "steps": int(spec.get("steps", 24)),
        }
        st, body = http("POST", f"{self.base}/synth", payload, timeout=30)
        if st != 200:
            log(f"  提交失败：{body[:200]!r}")
            return None
        try:
            job_id = json.loads(body).get("id")
        except json.JSONDecodeError:
            log(f"  提交返回不可解析：{body[:200]!r}")
            return None
        if not job_id:
            log(f"  没有拿到任务 id：{body[:200]!r}")
            return None
        log(f"  任务 {job_id} 已提交，等待生成…")

        # 轮询。Vulkan 下 25 秒音频约 100 秒，给足上限。
        deadline = time.time() + float(spec.get("timeoutSec", 600))
        waited = 0
        while time.time() < deadline:
            time.sleep(6)
            waited += 6
            st, body = http("GET", f"{self.base}/job?id={job_id}", timeout=15)
            try:
                status = json.loads(body).get("status")
            except json.JSONDecodeError:
                status = "?"
            if status == "done":
                log(f"  生成完成（{waited}s）")
                break
            if status in ("failed", "error"):
                log(f"  生成失败：{body[:200]!r}")
                return None
            if waited % 30 == 0:
                log(f"    …{waited}s")
        else:
            log("  超时")
            return None

        # 取结果：multipart，audio/mpeg 那一段就是成品
        st, raw = http("GET", f"{self.base}/job?id={job_id}&result=1", timeout=120)
        if st != 200 or not raw:
            log(f"  取结果失败：HTTP {st}")
            return None
        audio = self._extract_audio(raw)
        if not audio:
            log("  multipart 里没找到 audio/mpeg 段")
            return None
        out = workdir / f"yue2_{job_id}.mp3"
        out.write_bytes(audio)
        return out

    @staticmethod
    def _extract_audio(raw: bytes) -> bytes | None:
        """从 multipart 里挑 Content-Type: audio/mpeg 的段。"""
        m = re.search(rb'--([\w\-]+)\r?\n', raw)
        if not m:
            return None
        boundary = b"--" + m.group(1)
        for part in raw.split(boundary):
            sep = part.find(b"\r\n\r\n")
            if sep < 0:
                continue
            headers = part[:sep].decode("ascii", "ignore").lower()
            if "audio/mpeg" in headers:
                return part[sep + 4:].rstrip(b"\r\n-")
        return None


# ---------------------------------------------------------------- 程序化

class ProceduralProvider(MusicProvider):
    """调 gen_audio.py 的和弦循环。永远可用，是兜底。"""

    name = "procedural"

    def available(self) -> bool:
        return shutil.which("ffmpeg") is not None or Path(ffmpeg_bin("ffmpeg")).exists()

    def hint(self) -> str:
        return "找不到 ffmpeg，程序化通道不可用。"

    def generate(self, spec: dict, workdir: Path) -> Path | None:
        script = Path(__file__).resolve().parent / "gen_audio.py"
        if not script.exists():
            log(f"  找不到 {script}")
            return None
        bpm = int(spec.get("bpm", 96))
        mode = "minor" if spec.get("mood") == "tense" else "major"
        name = f"proc_{spec.get('id', 'bgm')}"
        r = subprocess.run(
            [sys.executable, str(script), "--project", str(workdir), "--sfx", "none",
             "--bgm", name, "--bpm", str(bpm), "--mode", mode],
            capture_output=True, text=True,
        )
        if r.returncode != 0:
            log(f"  程序化生成失败：{(r.stderr or r.stdout)[:200]}")
            return None
        out = workdir / "assets" / "audio" / "bgm" / f"{name}.mp3"
        return out if out.exists() else None


# ---------------------------------------------------------------- 引擎启动

def start_engine() -> bool:
    """用 detached 进程拉起引擎，脚本退出后它继续活着。"""
    if not YUE2_ENGINE.exists():
        log(f"找不到引擎：{YUE2_ENGINE}")
        return False
    model = YUE2_MODELS / "YuE2-3B-Q8_0.gguf"
    vae = YUE2_MODELS / "YuE2-Vae-F32.gguf"
    comp = YUE2_MODELS / "nar_lora_joint_v9.safetensors"
    if not model.exists() or not vae.exists():
        log(f"模型缺失：{model} / {vae}")
        return False

    cmd = [
        str(YUE2_ENGINE), "--model", str(model), "--vae", str(vae),
        "--companion", str(comp), "--adapters", str(YUE2_ROOT / "data" / "adapters"),
        "--device", "Vulkan1", "--host", "127.0.0.1", "--port", str(YUE2_PORT),
    ]
    flags = 0
    if os.name == "nt":
        # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP：脱离当前会话，不被回收
        flags = 0x00000008 | 0x00000200
    subprocess.Popen(
        cmd, cwd=str(YUE2_ENGINE.parent),
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        creationflags=flags, close_fds=True,
    )
    log(f"引擎已拉起（PID 见任务管理器），等待 {YUE2_PORT} 就绪…")
    provider = Yue2HttpProvider()
    for i in range(30):
        time.sleep(4)
        if provider.available():
            log("引擎就绪")
            return True
        if i % 3 == 0:
            log(f"  …{(i + 1) * 4}s（模型加载约 20–40 秒）")
    log("等待超时，检查 GPU 占用或引擎日志")
    return False


# ---------------------------------------------------------------- 主流程

PROVIDERS = {p.name: p for p in (Yue2HttpProvider(), ProceduralProvider())}


def pick_provider(name: str) -> MusicProvider | None:
    if name == "auto":
        for key in ("yue2-http", "procedural"):
            p = PROVIDERS[key]
            if p.available():
                log(f"选用通道：{p.name}")
                return p
            log(f"通道 {p.name} 不可用。{p.hint()}")
        return None
    p = PROVIDERS.get(name)
    if not p:
        log(f"未知 provider：{name}（可用：{', '.join(PROVIDERS)}）")
        return None
    if not p.available():
        log(f"通道 {p.name} 不可用。{p.hint()}")
        return None
    return p


PROVENANCE = Path("docs/05-audio/bgm-provenance.json")


def record_provenance(target: Path, spec: dict, provider_name: str) -> None:
    """记录「这个音频是谁生成的」。

    不记的话 asset_registry 只能把它标成 procedural —— 台账失真，
    以后分不清哪段是模型生成、哪段是合成兜底，也没法回答「改了 prompt 要不要重出」。
    """
    data: dict = {}
    if PROVENANCE.exists():
        try:
            data = json.loads(PROVENANCE.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            data = {}
    key = target.as_posix()
    data[key] = {
        "source": "ai" if provider_name != "procedural" else "procedural",
        "provider": provider_name,
        "prompt": spec.get("prompt", ""),
        "lyrics": spec.get("lyrics", ""),
        "durationSec": spec.get("durationSec"),
        "trimSec": spec.get("trimSec"),
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
    }
    PROVENANCE.parent.mkdir(parents=True, exist_ok=True)
    PROVENANCE.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(description="BGM 生成（provider 可插拔）")
    ap.add_argument("--provider", default="auto", choices=["auto", *PROVIDERS])
    ap.add_argument("--track", default="", help="只生成指定 id")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--spec", default=str(SPEC))
    ap.add_argument("--probe", action="store_true", help="只探测通道")
    ap.add_argument("--start-engine", action="store_true", help="拉起 YuE2 引擎")
    ap.add_argument("--keep-raw", action="store_true", help="保留原始音频")
    args = ap.parse_args()

    if args.start_engine:
        return 0 if start_engine() else 1

    if args.probe:
        for name, p in PROVIDERS.items():
            log(f"{name:12} {'可用' if p.available() else '不可用'}")
            if not p.available():
                log(f"             {p.hint()}")
        return 0

    spec_path = Path(args.spec)
    if not spec_path.exists():
        log(f"没有规格文件：{spec_path}")
        return 2
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    tracks = spec.get("tracks") or []
    if args.track:
        tracks = [t for t in tracks if t.get("id") == args.track]
    if not tracks:
        log("没有匹配的曲目")
        return 2

    provider = pick_provider(args.provider)
    if not provider:
        return 2

    workdir = Path.cwd() / ".gamedev" / "music"
    workdir.mkdir(parents=True, exist_ok=True)

    ok = 0
    for t in tracks:
        log(f"\n[{t['id']}] {t.get('prompt', '')[:70]}…")
        raw = provider.generate(t, workdir)
        if not raw or not raw.exists():
            log("  没有产物，跳过")
            continue
        target = Path(t["target"])
        if transcode(raw, target, float(t.get("trimSec", 28))):
            log(f"  → {target}  {target.stat().st_size / 1024:.0f}KB")
            record_provenance(target, t, provider.name)
            ok += 1
        if not args.keep_raw:
            raw.unlink(missing_ok=True)

    log(f"\n完成 {ok}/{len(tracks)} 条（provider={provider.name}）")
    return 0 if ok == len(tracks) else 1


if __name__ == "__main__":
    sys.exit(main())
