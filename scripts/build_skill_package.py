#!/usr/bin/env python3
"""把技能目录打成可分发 zip。

    python scripts/build_skill_package.py                      # 出到 ./dist/
    python scripts/build_skill_package.py --out D:/pkgs        # 指定输出目录
    python scripts/build_skill_package.py --skip-verify        # 跳过自检（不推荐）
    python scripts/build_skill_package.py --with-examples      # 带上 examples/（默认带）

## 与「技能市场上架包」的区别

本脚本产出的是**可安装分发包**：解压到 `~/.workbuddy-ai/skills/` 就能直接用，
保留完整目录结构（`assets/` `modules/` `docs/` `tests/` `examples/`）。

技能市场要求只有 `SKILL.md` + `references/` `scripts/` `templates/` 三目录，
而这个技能的脚本依赖 `assets/template`（整个 Vite 工程模板）与 `assets/data`（模式库），
把它们拍平会直接破坏运行。所以**本包不上架市场**，只做本地/团队分发。
详见 `references/packaging.md`。

## zip 结构

    idea-to-game/
        SKILL.md
        scripts/  modules/  references/  assets/  tests/  docs/  examples/

顶层只有一个目录，且目录名 == SKILL.md 的 `name` —— 安装脚本据此校验。
"""

from __future__ import annotations

import argparse
import hashlib
import re
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent

# 目录级排除：缓存、依赖、构建产物、版本库
EXCLUDE_DIRS = {
    ".git", ".pytest_cache", "__pycache__", "node_modules", "dist",
    ".venv", "venv", ".idea", ".vscode", ".mypy_cache", ".ruff_cache",
}

# 文件级排除：系统垃圾、字节码、日志、临时文件
EXCLUDE_SUFFIX = {".pyc", ".pyo", ".log", ".tmp", ".swp"}
EXCLUDE_NAMES = {".DS_Store", "Thumbs.db", "desktop.ini", ".gitignore"}

# 体积大且对复用无价值的路径（前缀匹配）
EXCLUDE_PREFIX = (
    "examples/echo-ferry/assets/raw",   # 原始生图，13MB
    "examples/echo-ferry/dist",
)


def read_name(skill_dir: Path) -> str:
    p = skill_dir / "SKILL.md"
    if not p.exists():
        raise SystemExit(f"缺 SKILL.md：{p}")
    text = p.read_text(encoding="utf-8")
    m = re.search(r"^name:\s*(\S+)\s*$", text, re.M)
    if not m:
        raise SystemExit("SKILL.md 的 frontmatter 里没有 name 字段")
    return m.group(1).strip("\"'")


def read_version(skill_dir: Path) -> str:
    text = (skill_dir / "SKILL.md").read_text(encoding="utf-8")
    m = re.search(r"^version:\s*(\S+)\s*$", text, re.M)
    return m.group(1).strip("\"'") if m else "0.0.0"


def iter_files(skill_dir: Path, with_examples: bool):
    for p in sorted(skill_dir.rglob("*")):
        if not p.is_file():
            continue
        rel = p.relative_to(skill_dir).as_posix()
        parts = set(rel.split("/"))

        if parts & EXCLUDE_DIRS:
            continue
        if p.suffix.lower() in EXCLUDE_SUFFIX:
            continue
        if p.name in EXCLUDE_NAMES:
            continue
        if any(rel.startswith(pref) for pref in EXCLUDE_PREFIX):
            continue
        if not with_examples and rel.startswith("examples/"):
            continue
        yield p, rel


def human(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f}{unit}" if unit == "B" else f"{n/1:.1f}{unit}"
        n /= 1024
    return f"{n:.1f}GB"


def run_verify(skill_dir: Path) -> bool:
    script = skill_dir / "scripts" / "verify_skill.py"
    if not script.exists():
        print("[warn] 找不到 scripts/verify_skill.py，跳过自检")
        return True
    print("== 打包前自检 ==")
    r = subprocess.run([sys.executable, str(script), "--path", str(skill_dir)],
                       capture_output=True, text=True, encoding="utf-8")
    tail = [ln for ln in r.stdout.splitlines() if ln.strip()][-3:]
    for ln in tail:
        print("  " + ln)
    return r.returncode == 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--path", default=str(SKILL_DIR), help="技能目录，默认本包")
    ap.add_argument("--out", default="", help="输出目录，默认 <技能目录>/dist")
    ap.add_argument("--skip-verify", action="store_true", help="跳过自检")
    ap.add_argument("--with-examples", default=True, action="store_true",
                    help="带上 examples/（默认带）")
    ap.add_argument("--no-examples", dest="with_examples", action="store_false",
                    help="不带 examples/，包体最小")
    args = ap.parse_args()

    skill_dir = Path(args.path).resolve()
    name = read_name(skill_dir)
    version = read_version(skill_dir)

    if not args.skip_verify and not run_verify(skill_dir):
        print("\n自检未通过，已中止打包。修完再跑，或用 --skip-verify 强制出包。")
        return 1

    out_dir = Path(args.out).resolve() if args.out else skill_dir / "dist"
    out_dir.mkdir(parents=True, exist_ok=True)
    zip_path = out_dir / f"{name}-{version}.zip"
    if zip_path.exists():
        zip_path.unlink()

    files = list(iter_files(skill_dir, args.with_examples))
    raw_total = 0
    print(f"\n== 打包 {name} {version} ==")
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for p, rel in files:
            raw_total += p.stat().st_size
            # 顶层目录 == name：解压后直接是一个可直接放进 skills/ 的目录
            z.write(p, arcname=f"{name}/{rel}")

    size = zip_path.stat().st_size
    sha = hashlib.sha256(zip_path.read_bytes()).hexdigest()[:16]
    ratio = size / raw_total * 100 if raw_total else 0

    print(f"  文件数     : {len(files)}")
    print(f"  原始体积   : {human(raw_total)}")
    print(f"  zip 体积   : {human(size)}（压缩到 {ratio:.0f}%）")
    print(f"  sha256[:16]: {sha}")
    print(f"  产物       : {zip_path}")

    # 结构自检：顶层必须只有一个目录，且等于 name
    with zipfile.ZipFile(zip_path) as z:
        tops = {n.split("/")[0] for n in z.namelist()}
        if tops != {name}:
            print(f"\n[FAIL] zip 顶层目录不唯一或与 name 不符：{tops}")
            return 1
        if f"{name}/SKILL.md" not in z.namelist():
            print(f"\n[FAIL] zip 里没有 {name}/SKILL.md")
            return 1

    print("\n  安装：解压到 ~/.workbuddy-ai/skills/ 即可（目录名必须是 "
          f"{name}）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
