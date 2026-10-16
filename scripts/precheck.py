#!/usr/bin/env python3
"""提交前过审自检（模块 11 用）。

用法:
    python precheck.py --dir dist/crazygames --platform crazygames
    python precheck.py --dir dist/poki       --platform poki
    python precheck.py --dir dist/playgama   --platform playgama
    python precheck.py --dir dist/gd         --platform gamedistribution

对照 references/platform-requirements.md 的硬红线逐条检查。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import human_size, iter_files, scan_absolute_paths, scan_external_urls  # noqa: E402

SDK_MARKERS = {
    "crazygames": ["sdk.crazygames.com", "crazygames-sdk", "CrazyGames.SDK"],
    "poki": ["game-cdn.poki.com", "poki-sdk", "PokiSDK"],
    "playgama": ["playgama", "bridge.playgama"],
    "gamedistribution": ["html5.api.gamedistribution.com", "gdsdk", "GD_OPTIONS"],
}

PLATFORM_LIMITS = {
    "crazygames": {"total_mb": 250, "files": 1500, "initial_mb": 50, "mobile_mb": 20},
    "poki": {"total_mb": 250, "files": 1500, "initial_mb": 50, "mobile_mb": 20},
    "playgama": {"total_mb": 250, "files": 1500, "initial_mb": 50, "mobile_mb": 20},
    "gamedistribution": {"total_mb": 250, "files": 1500, "initial_mb": 50, "mobile_mb": 20},
}

TEXT_EXT = {".html", ".htm", ".js", ".mjs", ".cjs", ".css"}


def read_all_text(root: Path, limit_bytes: int = 6_000_000):
    blob = []
    for f in iter_files(root):
        if f.suffix.lower() in TEXT_EXT:
            try:
                if f.stat().st_size > limit_bytes:
                    continue
                blob.append(f.read_text(encoding="utf-8", errors="ignore"))
            except OSError:
                continue
    return "\n".join(blob)


def main() -> int:
    ap = argparse.ArgumentParser(description="提交前过审自检")
    ap.add_argument("--dir", required=True)
    ap.add_argument("--platform", required=True,
                    choices=["crazygames", "poki", "playgama", "gamedistribution"])
    args = ap.parse_args()

    root = Path(args.dir).expanduser().resolve()
    if not root.is_dir():
        print(f"ERROR: 目录不存在：{root}", file=sys.stderr)
        return 1

    lim = PLATFORM_LIMITS[args.platform]
    checks: list[tuple[str, bool, str]] = []

    def add(name: str, passed: bool, detail: str = ""):
        checks.append((name, passed, detail))

    files = [(p, p.stat().st_size) for p in iter_files(root)]
    total = sum(s for _, s in files)
    count = len(files)
    text = read_all_text(root)

    # 1. 入口位置
    index = root / "index.html"
    add("index.html 位于产物根目录", index.is_file(),
        "" if index.is_file() else "zip 解压后根目录必须直接是 index.html")

    # 2. 体积
    add(f"总大小 <= {lim['total_mb']}MB", total <= lim["total_mb"] * 1024 * 1024,
        f"实测 {human_size(total)}")
    add(f"文件数 <= {lim['files']}", count <= lim["files"], f"实测 {count}")

    # 3. 相对路径
    abs_hits = scan_absolute_paths(root)
    add("无根绝对路径引用", not abs_hits,
        f"发现 {len(abs_hits)} 处，例如 {abs_hits[0][0]}: {abs_hits[0][1]}" if abs_hits else "")

    # 3b. 外部 URL（仅提示）
    ext_hits = scan_external_urls(root)
    if ext_hits:
        hosts = sorted({u.split("/")[2] for _, u in ext_hits if len(u.split("/")) > 2})
        print(f"NOTE: 外部 URL {len(ext_hits)} 处，域名: {', '.join(hosts[:8])}（SDK CDN 属正常）")

    # 4. 移动端 CSS
    has_user_select = "user-select" in text
    add("body 含 user-select: none", has_user_select,
        "" if has_user_select else "移动端长按会弹出选择菜单，CrazyGames 要求加")
    has_viewport = "viewport" in text
    add("含 viewport meta", has_viewport, "" if has_viewport else "移动端缩放会异常")

    # 5. SDK 注入
    markers = SDK_MARKERS[args.platform]
    hit = next((m for m in markers if m in text), None)
    add(f"已注入 {args.platform} SDK", bool(hit),
        f"命中标记：{hit}" if hit else f"未找到任一标记 {markers}；确认 VITE_TARGET 是否指向了 mock")

    # 6. 适配层未使用 mock
    mock_leak = "__MOCK__" in text or "platform: mock" in text.lower()
    add("未使用 mock 适配器", not mock_leak,
        "" if not mock_leak else "构建时注入了 mock 实现，需重新构建")

    # 7. iOS 音频恢复
    has_touchend = "touchend" in text
    has_resume = "resume(" in text
    add("含 iOS 音频恢复逻辑", has_touchend and has_resume,
        "" if (has_touchend and has_resume) else
        "需在 touchend/click 回调内调用 audioContext.resume()（只监听 visibilitychange 无效）")

    # 8. 广告调用异常捕获
    add("SDK 调用含异常捕获", "catch" in text or "try" in text,
        "" if ("catch" in text or "try" in text) else "广告/存档调用失败时必须静默降级")

    # 9. 平台生命周期事件
    gp = "gameplayStart" in text or "gameplay_start" in text or "gameplaystart" in text.lower()
    add("含 gameplayStart/Stop 事件", gp,
        "" if gp else "CrazyGames 用它测首包体积，Poki 用它算加载完成，必须实现")

    # 10. 遗留调试输出
    if "console.log" in text:
        print("WARN: 产物中存在 console.log，建议生产构建剔除")

    print("=" * 62)
    print(f"平台: {args.platform}   目录: {root}")
    print("=" * 62)
    failed = 0
    for name, passed, detail in checks:
        mark = "PASS" if passed else "FAIL"
        if not passed:
            failed += 1
        print(f"[{mark}] {name}")
        if detail:
            print(f"       {detail}")
    print("=" * 62)
    if failed:
        print(f"{failed} 项未通过。修复后再提交。")
        return 1
    print("全部通过，可提交。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
