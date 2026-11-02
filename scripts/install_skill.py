#!/usr/bin/env python3
"""把技能包安装到 skills 目录。

    python scripts/install_skill.py --zip dist/idea-to-game-3.0.0.zip
    python scripts/install_skill.py --dir .                    # 从当前目录装
    python scripts/install_skill.py --zip x.zip --target D:/skills --force

行为：
1. 从 zip 或目录读出技能名与版本（读 SKILL.md 的 frontmatter）
2. 目标已存在时**先备份**成 `<name>.bak-<时间戳>`，再覆盖（`--force` 跳过备份）
3. 装完跑一次 verify_skill.py，失败会提示但不回滚（备份还在）

为什么默认备份而不是直接覆盖：技能目录里有 state.yaml 这类**用户数据**，
直接覆盖等于删档。备份让人有后悔药。
"""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path

DEFAULT_TARGET = Path.home() / ".workbuddy-ai" / "skills"


def read_meta(skill_md: Path) -> tuple[str, str]:
    text = skill_md.read_text(encoding="utf-8")
    name = re.search(r"^name:\s*(\S+)\s*$", text, re.M)
    ver = re.search(r"^version:\s*(\S+)\s*$", text, re.M)
    if not name:
        raise SystemExit(f"{skill_md} 的 frontmatter 里没有 name")
    return name.group(1).strip("\"'"), (ver.group(1).strip("\"'") if ver else "0.0.0")


def verify(skill_dir: Path) -> bool:
    v = skill_dir / "scripts" / "verify_skill.py"
    if not v.exists():
        print("[warn] 包里没有 verify_skill.py，跳过安装后自检")
        return True
    r = subprocess.run([sys.executable, str(v), "--path", str(skill_dir)],
                       capture_output=True, text=True, encoding="utf-8")
    for ln in [x for x in r.stdout.splitlines() if x.strip()][-3:]:
        print("  " + ln)
    return r.returncode == 0


def main() -> int:
    ap = argparse.ArgumentParser()
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--zip", help="技能包 zip")
    src.add_argument("--dir", help="技能目录（直接复制）")
    ap.add_argument("--target", default=str(DEFAULT_TARGET), help="skills 目录")
    ap.add_argument("--force", action="store_true", help="覆盖前不备份")
    ap.add_argument("--no-verify", action="store_true", help="跳过安装后自检")
    args = ap.parse_args()

    target_root = Path(args.target).expanduser().resolve()
    target_root.mkdir(parents=True, exist_ok=True)

    tmp: tempfile.TemporaryDirectory | None = None
    try:
        if args.zip:
            zpath = Path(args.zip).expanduser().resolve()
            if not zpath.exists():
                raise SystemExit(f"找不到 {zpath}")
            with zipfile.ZipFile(zpath) as z:
                tops = {n.split("/")[0] for n in z.namelist() if n.strip("/")}
                if len(tops) != 1:
                    raise SystemExit(f"zip 顶层必须只有一个目录，实际有：{sorted(tops)}")
                top = tops.pop()
                tmp = tempfile.TemporaryDirectory()
                z.extractall(tmp.name)
            stage = Path(tmp.name) / top
        else:
            stage = Path(args.dir).expanduser().resolve()
            if not (stage / "SKILL.md").exists():
                raise SystemExit(f"{stage} 里没有 SKILL.md，不是技能目录")

        name, ver = read_meta(stage / "SKILL.md")
        if stage.name != name:
            print(f"[warn] 目录名 {stage.name} 与 name {name} 不一致，按 name 安装")

        dest = target_root / name
        if dest.exists():
            if args.force:
                print(f"[force] 删除已有 {dest}")
                shutil.rmtree(dest)
            else:
                stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
                bak = target_root / f"{name}.bak-{stamp}"
                print(f"备份已有版本 → {bak.name}")
                shutil.move(str(dest), str(bak))

        shutil.copytree(stage, dest,
                        ignore=shutil.ignore_patterns(
                            "__pycache__", ".pytest_cache", "node_modules", ".git", "dist"))
        print(f"已安装 {name} {ver} → {dest}")

        if not args.no_verify:
            print("\n安装后自检：")
            ok = verify(dest)
            if not ok:
                print("\n[FAIL] 自检未通过。备份仍在，可回滚：把 .bak-* 目录改回原名。")
                return 1
        print("\n完成。新会话中技能即可被加载。")
        return 0
    finally:
        if tmp:
            tmp.cleanup()


if __name__ == "__main__":
    sys.exit(main())
