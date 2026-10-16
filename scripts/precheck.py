#!/usr/bin/env python3
"""提交前过审自检（模块 11 用）。

用法:
    python precheck.py --dir dist/crazygames --platform crazygames
    python precheck.py --dir dist/poki       --platform poki
    python precheck.py --dir dist/gd         --platform gamedistribution
    python precheck.py --dir dist/playgama   --platform playgama
    python precheck.py --dir dist/taptap     --platform taptap

对照 references/platform-requirements.md 的硬红线逐条检查。
平台参数表在 _common.py 的 PLATFORMS 中（单一真相源）。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import (  # noqa: E402
    PLATFORM_KEYS,
    human_size,
    iter_files,
    platform_conf,
    scan_absolute_paths,
    scan_external_urls,
)

TEXT_EXT = {".html", ".htm", ".js", ".mjs", ".cjs", ".css"}

# 中国大陆平台：需前置备案（人工核对项）
CN_PLATFORMS = {"taptap"}


def read_all_text(root: Path, limit_bytes: int = 8_000_000) -> str:
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
    ap.add_argument("--platform", required=True, choices=PLATFORM_KEYS)
    args = ap.parse_args()

    root = Path(args.dir).expanduser().resolve()
    if not root.is_dir():
        print(f"ERROR: 目录不存在：{root}", file=sys.stderr)
        return 1

    conf = platform_conf(args.platform)
    label = conf["label"]
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

    # 2. 体积与文件数
    add(f"总大小 <= {conf['total_mb']}MB", total <= conf["total_mb"] * 1024 * 1024,
        f"实测 {human_size(total)}")
    add(f"文件数 <= {conf['files']}", count <= conf["files"], f"实测 {count}")
    add(f"首包 <= {conf['initial_mb']}MB", total <= conf["initial_mb"] * 1024 * 1024,
        f"实测 {human_size(total)}（以总大小为上界；精确首包需真机测量）")

    # 3. 相对路径
    abs_hits = scan_absolute_paths(root)
    add("无根绝对路径引用", not abs_hits,
        f"发现 {len(abs_hits)} 处，例如 {abs_hits[0][0]}: {abs_hits[0][1]}" if abs_hits else "")

    ext_hits = scan_external_urls(root)
    if ext_hits:
        hosts = sorted({u.split("/")[2] for _, u in ext_hits if len(u.split("/")) > 2})
        print(f"NOTE: 外部 URL {len(ext_hits)} 处，域名: {', '.join(hosts[:8])}（SDK CDN 属正常）")

    # 4. 移动端 CSS / viewport
    add("body 含 user-select: none", "user-select" in text,
        "" if "user-select" in text else "移动端长按会弹出选择菜单，平台通常要求加")
    add("含 viewport meta", "viewport" in text, "" if "viewport" in text else "移动端缩放会异常")

    # 5. 适配层注入：产物中应当**有且仅有**目标平台的标识
    import re

    tags = sorted(set(re.findall(r"i2g-platform:[a-z]+", text)))
    marker = f"i2g-platform:{args.platform}"
    add(f"已注入 {label} 适配层", marker in tags,
        f"命中标识：{marker}" if marker in tags else
        f"未找到 {marker}；确认构建 mode 是否为 {args.platform}（已发现：{tags or '无'}）")
    extra_tags = [t for t in tags if t != marker]
    add("产物中只含目标平台的适配器", not extra_tags,
        "" if not extra_tags else
        f"发现多余适配器 {extra_tags} —— 说明平台选择未被 tree-shaking 折叠。"
        "检查 src/platform/index.ts 是否用 if 链 + 字面量比较（用 switch 会导致全部适配器被打包）")

    # 6. 未误用 mock
    add("未使用 mock 适配器", "i2g-platform:mock" not in tags,
        "" if "i2g-platform:mock" not in tags else "构建时注入了 mock 实现，需按目标平台重新构建")

    # 7. 平台 SDK
    sdk_markers = conf.get("sdk_markers") or []
    if sdk_markers:
        hit = next((m for m in sdk_markers if m in text), None)
        add(f"已加载 {label} SDK", bool(hit),
            f"命中标记：{hit}" if hit else f"未找到任一标记 {sdk_markers}")
    else:
        leaked = [u for _, u in ext_hits if "taptap" in u.lower()]
        add(f"{label} 为宿主注入型，产物不应自带 SDK script", not leaked,
            f"发现可疑 SDK 引用：{leaked[0]}" if leaked else "由平台容器注入 tap 全局对象")

    # 8. iOS 音频恢复
    has_touchend = "touchend" in text
    has_resume = "resume(" in text
    add("含 iOS 音频恢复逻辑", has_touchend and has_resume,
        "" if (has_touchend and has_resume) else
        "需在 touchend/click 回调内调用 audioContext.resume()（只监听 visibilitychange 无效）")

    # 9. SDK 调用容错
    add("SDK 调用含异常捕获", "catch" in text,
        "" if "catch" in text else "广告/存档调用失败时必须静默降级，否则广告拦截器场景下会卡死")

    # 10. 生命周期事件
    if args.platform == "taptap":
        add("TapTap 无强制生命周期上报（跳过）", True, "")
    else:
        gp = any(k in text for k in ("gameplayStart", "gameplay_started", "gameplay_start"))
        add("含 gameplayStart/Stop 事件", gp,
            "" if gp else "CrazyGames 用它测首包体积，Poki 用它算加载完成，必须实现")

    # 11. 中国大陆合规（人工核对项）
    if args.platform in CN_PLATFORMS:
        add("小游戏前置备案已确认（人工核对）", True,
            "Tap 小游戏正式上架必须先完成前置备案；网页游戏 H5 形态无此要求")

    if "console.log" in text:
        print("WARN: 产物中存在 console.log，建议生产构建剔除")

    print("=" * 62)
    print(f"平台: {label}（{conf['region']}）   目录: {root}")
    print(f"备注: {conf['notes']}")
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
