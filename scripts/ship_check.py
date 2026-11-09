#!/usr/bin/env python3
"""Ship Check —— 交付前的统一技术回归。

## 它解决什么

交付前要跑的东西散在四个脚本里，各管一段：

  measure_bundle.py   产物体积与文件数
  precheck.py         单平台过审自检（SDK 标记、必需文件）
  asset_registry.py   素材台账一致性
  scenario.mjs        玩法用例

问题不是「缺工具」，是**没有一个地方能回答「这个项目现在能不能发」**。
本脚本把它们串成一次检查，输出一个结论。

## 与 gate_check.py 的分工

| 工具 | 检查什么 |
|---|---|
| `gate_check.py` | **流程门禁**：阶段产物（GDD / 视觉 DNA / 审核结论）齐不齐 |
| `ship_check.py` | **技术门禁**：构建、体积、素材、音频、用例过不过 |

前者管「该做的事做了没」，后者管「做出来的东西能不能跑、能不能提交」。

## 用法

  python ship_check.py --project .                        # 只查已有产物
  python ship_check.py --project . --build                # 先构建再查
  python ship_check.py --project . --build --platforms crazygames,taptap
  python ship_check.py --project . --build --tests        # 连用例一起跑
  python ship_check.py --project . --platforms preview    # 只有 preview 产物时

## 退出码

0 = 全部通过（允许 WARN）
1 = 有 FAIL
2 = 环境问题（缺产物 / 缺工具）
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import PLATFORMS, PLATFORM_KEYS  # noqa: E402

SKILL_SCRIPTS = Path(__file__).resolve().parent
REPORT = Path("docs/07-qa/ship-check.json")

# 音频硬性规范（见 references/audio-pipeline.md）
AUDIO_RULES = {
    "sample_rate": 44100,
    "channels": 1,
    "sfx_max_sec": 1.5,
    "bgm_min_sec": 20.0,
    "bgm_max_sec": 35.0,
    "single_max_kb": 500,
    "total_max_kb": 1536,
}


def log(msg: str = "") -> None:
    print(msg, flush=True)


def run(cmd: list[str], cwd: Path | None = None, timeout: int = 900) -> tuple[int, str]:
    try:
        r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout)
        return r.returncode, (r.stdout or "") + (r.stderr or "")
    except subprocess.TimeoutExpired:
        return 124, "超时"
    except FileNotFoundError as e:
        return 127, str(e)


def bin_of(name: str) -> str:
    """Windows 上 npm/node 实际是 .cmd / .exe，subprocess 直接调会 WinError 2。"""
    for cand in (name, f"{name}.cmd", f"{name}.exe"):
        p = shutil.which(cand)
        if p:
            return p
    return name


def find_ffprobe() -> str:
    p = shutil.which("ffprobe")
    if p:
        return p
    guess = Path("C:/Users/15274/AppData/Local/Microsoft/WinGet/Links/ffprobe.exe")
    return str(guess) if guess.exists() else ""


# ---------------------------------------------------------------- 构建

def build_platform(proj: Path, platform: str) -> tuple[bool, str]:
    pkg = proj / "package.json"
    if not pkg.exists():
        return False, "没有 package.json"
    try:
        scripts = json.loads(pkg.read_text(encoding="utf-8")).get("scripts") or {}
    except json.JSONDecodeError:
        return False, "package.json 解析失败"

    # npm script 名约定：build:cg / build:poki / build:taptap / build（preview）
    alias = {
        "crazygames": "build:cg", "poki": "build:poki",
        "gamedistribution": "build:gd", "playgama": "build:pg", "taptap": "build:taptap",
    }
    key = alias.get(platform, "build" if platform == "preview" else f"build:{platform}")
    if key not in scripts:
        return False, f"package.json 里没有 {key} 脚本"
    log(f"  构建 {platform}（npm run {key}）…")
    code, out = run([bin_of("npm"), "run", key], cwd=proj, timeout=900)
    if code != 0:
        tail = "\n".join(out.strip().splitlines()[-6:])
        return False, f"构建失败：{tail}"
    return True, ""


def dist_dir(proj: Path, platform: str) -> Path:
    return proj / "dist" / platform


# ---------------------------------------------------------------- 音频

def check_audio(proj: Path) -> dict:
    """音频参数校验。规范在 references/audio-pipeline.md，这里只执行。"""
    audio_root = proj / "assets" / "audio"
    if not audio_root.is_dir():
        return {"status": "SKIP", "note": "没有 assets/audio（纯程序化项目可能如此）", "files": 0}

    ffprobe = find_ffprobe()
    if not ffprobe:
        return {"status": "SKIP", "note": "找不到 ffprobe", "files": 0}

    files: list[dict] = []
    issues: list[str] = []
    total_kb = 0.0

    for p in sorted(audio_root.rglob("*.mp3")):
        rel = p.relative_to(proj).as_posix()
        kb = p.stat().st_size / 1024
        total_kb += kb
        info = {"path": rel, "kb": round(kb, 1)}
        # 必须用 JSON 输出：default=nw=1 的字段顺序随 ffprobe 版本变，
        # 曾把「声道数 1」当成「时长 1.0s」，误判所有 BGM 超短。
        code, out = run([
            ffprobe, "-v", "error",
            "-show_entries", "format=duration:stream=sample_rate,channels",
            "-of", "json", str(p),
        ], timeout=30)
        if code != 0:
            issues.append(f"{rel}：ffprobe 读不出（文件损坏？）")
            files.append(info)
            continue
        dur = sr = ch = None
        try:
            meta = json.loads(out)
            dur = float((meta.get("format") or {}).get("duration") or 0) or None
            streams = meta.get("streams") or []
            if streams:
                sr = int(streams[0].get("sample_rate") or 0) or None
                ch = int(streams[0].get("channels") or 0) or None
        except (json.JSONDecodeError, ValueError, TypeError):
            issues.append(f"{rel}：ffprobe 输出无法解析")
            files.append(info)
            continue
        info.update({"duration": dur, "sample_rate": sr, "channels": ch})

        if sr and sr != AUDIO_RULES["sample_rate"]:
            issues.append(f"{rel}：采样率 {sr}，应为 {AUDIO_RULES['sample_rate']}")
        if ch and ch != AUDIO_RULES["channels"]:
            issues.append(f"{rel}：{ch} 声道，应为单声道（体积差 2 倍）")
        if kb > AUDIO_RULES["single_max_kb"]:
            issues.append(f"{rel}：{kb:.0f}KB 超过单文件上限 {AUDIO_RULES['single_max_kb']}KB")
        is_bgm = "/bgm/" in rel
        if dur is not None:
            if is_bgm and not (AUDIO_RULES["bgm_min_sec"] <= dur <= AUDIO_RULES["bgm_max_sec"]):
                issues.append(f"{rel}：BGM 时长 {dur:.1f}s 不在 {AUDIO_RULES['bgm_min_sec']}–{AUDIO_RULES['bgm_max_sec']}s")
            if not is_bgm and dur > AUDIO_RULES["sfx_max_sec"]:
                issues.append(f"{rel}：音效 {dur:.2f}s 超过 {AUDIO_RULES['sfx_max_sec']}s（反馈会被拖沓）")
        files.append(info)

    if total_kb > AUDIO_RULES["total_max_kb"]:
        issues.append(f"音频总量 {total_kb:.0f}KB 超过 {AUDIO_RULES['total_max_kb']}KB")

    return {
        "status": "FAIL" if issues else "PASS",
        "files": len(files),
        "total_kb": round(total_kb, 1),
        "issues": issues,
        "detail": files,
    }


# ---------------------------------------------------------------- 主流程

def main() -> int:
    ap = argparse.ArgumentParser(description="交付前统一技术回归")
    ap.add_argument("--project", default=".", help="项目根目录")
    ap.add_argument("--build", action="store_true", help="先构建再检查")
    ap.add_argument("--platforms", default="preview", help=f"逗号分隔；preview 或 {','.join(PLATFORM_KEYS)}")
    ap.add_argument("--tests", action="store_true", help="跑玩法用例（scenario.mjs）")
    ap.add_argument("--json", default=str(REPORT))
    args = ap.parse_args()

    proj = Path(args.project).resolve()
    if not (proj / "package.json").exists():
        log(f"ERROR: {proj} 下没有 package.json")
        return 2

    platforms = [p.strip() for p in args.platforms.split(",") if p.strip()]
    unknown = [p for p in platforms if p != "preview" and p not in PLATFORM_KEYS]
    if unknown:
        log(f"ERROR: 未知平台 {unknown}；可选：preview, {', '.join(PLATFORM_KEYS)}")
        return 2

    log(f"交付检查：{proj.name}")
    log("═" * 66)

    issues: list[str] = []
    platform_results: list[dict] = []

    # ---- 1. 构建 + 体积 + 预检
    for plat in platforms:
        log(f"\n[{plat}]")
        if args.build:
            ok, err = build_platform(proj, plat)
            if not ok:
                issues.append(f"{plat}：{err}")
                platform_results.append({"platform": plat, "build": False, "error": err})
                log(f"  ✗ {err}")
                continue

        d = dist_dir(proj, plat)
        if not d.is_dir():
            issues.append(f"{plat}：没有产物目录 {d.relative_to(proj)}（加 --build）")
            platform_results.append({"platform": plat, "build": False, "error": "产物不存在"})
            log(f"  ✗ 没有产物目录")
            continue

        # 体积
        code, out = run([sys.executable, str(SKILL_SCRIPTS / "measure_bundle.py"),
                         "--dir", str(d), "--platform", "crazygames" if plat == "preview" else plat,
                         "--json", str(proj / ".gamedev" / f"bundle-{plat}.json")], timeout=120)
        size_mb = files = None
        try:
            data = json.loads((proj / ".gamedev" / f"bundle-{plat}.json").read_text(encoding="utf-8"))
            # measure_bundle 输出的是字节数，不是 MB
            tb = data.get("total_bytes")
            size_mb = round(tb / 1048576, 2) if isinstance(tb, (int, float)) else None
            files = data.get("file_count")
        except (OSError, json.JSONDecodeError):
            pass
        log(f"  体积 {size_mb if size_mb is not None else '?'}MB / {files if files is not None else '?'} 文件")
        if code != 0:
            issues.append(f"{plat}：体积审计未通过")
            log("  ✗ 体积审计未通过")

        # 预检（只有真平台才有 SDK 要求）
        precheck_ok = None
        if plat != "preview":
            code, out = run([sys.executable, str(SKILL_SCRIPTS / "precheck.py"),
                             "--dir", str(d), "--platform", plat,
                             "--json", str(proj / ".gamedev" / f"precheck-{plat}.json")], timeout=180)
            precheck_ok = code == 0
            if not precheck_ok:
                tail = "\n".join(out.strip().splitlines()[-5:])
                issues.append(f"{plat}：过审预检未通过\n    {tail}")
                log(f"  ✗ 预检未通过")
            else:
                log("  ✓ 预检通过")

        platform_results.append({
            "platform": plat, "build": True,
            "size_mb": size_mb, "files": files, "precheck": precheck_ok,
        })

    # ---- 2. 音频
    log("\n[音频]")
    audio = check_audio(proj)
    if audio["status"] == "SKIP":
        log(f"  跳过：{audio['note']}")
    else:
        log(f"  {audio['files']} 个 / {audio['total_kb']}KB → {audio['status']}")
        for i in audio["issues"]:
            log(f"    ✗ {i}")
        if audio["status"] == "FAIL":
            issues.extend(audio["issues"])

    # ---- 3. 素材台账
    log("\n[素材台账]")
    reg = proj / "assets" / "registry.json"
    assets_result: dict = {"status": "SKIP"}
    if not reg.exists():
        log("  跳过：还没有 assets/registry.json（跑 asset_registry.py scan）")
    else:
        code, out = run([sys.executable, str(SKILL_SCRIPTS / "asset_registry.py"),
                         "check", "--project", str(proj)], timeout=120)
        assets_result = {"status": "PASS" if code == 0 else "FAIL"}
        summary = [ln.strip() for ln in out.splitlines() if "检查：" in ln]
        log(f"  {summary[0] if summary else ('PASS' if code == 0 else 'FAIL')}")
        if code != 0:
            issues.append("素材台账：一致性检查未通过")

    # ---- 4. 用例
    log("\n[玩法用例]")
    tests_result = None
    if not args.tests:
        log("  跳过（加 --tests）")
    else:
        script = proj / "scripts" / "scenario.mjs"
        if not script.exists():
            log("  跳过：没有 scripts/scenario.mjs")
        else:
            log("  跑用例…")
            code, out = run([bin_of("node"), str(script), "--serve", "--port", "5193"], cwd=proj, timeout=1200)
            line = next((ln for ln in out.splitlines() if "结果:" in ln), "")
            log(f"  {line.strip() if line else ('通过' if code == 0 else '未通过')}")
            tests_result = {"ok": code == 0, "line": line.strip()}
            if code != 0:
                issues.append("玩法用例未全过")

    # ---- 汇总
    verdict = "PASS" if not issues else "FAIL"
    log("\n" + "═" * 66)
    log(f"结论：{verdict}")
    if issues:
        for i in issues:
            log(f"  ✗ {i}")
    else:
        log("  构建、体积、音频、素材、用例全部通过")

    out_path = proj / args.json
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps({
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "project": proj.name,
        "verdict": verdict,
        "platforms": platform_results,
        "audio": audio,
        "assets": assets_result,
        "tests": tests_result,
        "issues": issues,
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    log(f"\n报告：{out_path.relative_to(proj)}")

    return 0 if verdict == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
