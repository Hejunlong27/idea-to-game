#!/usr/bin/env python3
"""技能包自检 —— 打包前跑一遍，任何 FAIL 都不该出包。

    python scripts/verify_skill.py                    # 自检本包
    python scripts/verify_skill.py --path <目录>       # 自检任意技能目录
    python scripts/verify_skill.py --json             # 机读输出

为什么需要它：技能包一旦分发给别人，装错一个目录、漏一个模式库、
frontmatter 少一个字段，症状都是「技能加载了但不工作」或「平台解析失败」，
很难从报错反推。这里把能机器判定的东西全部前置。

不检查的东西（无法离线判定，别假装检查了）：
- 生成质量的优劣
- 外部服务可达性（ComfyUI / YuE2 / TTS）
- 真机性能
"""

from __future__ import annotations

import argparse
import json
import py_compile
import re
import sys
import tempfile
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent

# 平台规定的 8 个必填字段（见 skill-market-packager/references/platform-spec.md）
REQUIRED_FIELDS = [
    "name",
    "display_name",
    "display_name_en",
    "description",
    "description_zh",
    "description_en",
    "version",
    "author",
]

# 展示名只允许中英文、数字、- 与 —（付费资产硬约束）
DISPLAY_RE = re.compile(r"^[A-Za-z0-9\u4e00-\u9fa5\-—]+$")

# 分发包必须有这些目录，缺一个都会导致某些环节静默失败
REQUIRED_DIRS = [
    "scripts",
    "modules",
    "references",
    "references/schemas",
    "assets/template",
    "assets/data",
    "tests",
]

# 模板缺这些文件，init_project 出来的项目就跑不起来
TEMPLATE_MUST = [
    "package.json",
    "index.html",
    "tsconfig.json",
    "vite.config.ts",
    "src/main.ts",
    "src/game/config.ts",
    "src/game/art.ts",
    "src/game/events.ts",
    "src/game/audio.ts",
    "src/game/juice.ts",
    "src/game/scenes/BootScene.ts",
    "src/game/scenes/PlayScene.ts",
    "scripts/qa.mjs",
    "scripts/smoke.mjs",
    "scripts/playtest.mjs",
]

# 模式库：v3 的身份契约全靠这些数据，缺了生成器会静默降级成通用文案
DATA_MUST = [
    "assets/data/creative-patterns/interaction-verbs.json",
    "assets/data/creative-patterns/twist-dimensions.json",
    "assets/data/gameplay-patterns/archetypes.json",
    "assets/data/visual-styles/styles.json",
    "assets/data/audio-styles/palettes.json",
    "assets/data/emotional-patterns/curves.json",
]

SCHEMA_MUST = [
    "references/schemas/creative-dna.schema.json",
    "references/schemas/visual-dna.schema.json",
    "references/schemas/audio-dna.schema.json",
    "references/schemas/juice-plan.schema.json",
    "references/schemas/experience-blueprint.schema.json",
]


class Report:
    def __init__(self) -> None:
        self.items: list[dict] = []

    def add(self, level: str, code: str, msg: str, fix: str = "") -> None:
        self.items.append({"level": level, "code": code, "msg": msg, "fix": fix})

    def ok(self, code: str, msg: str) -> None:
        self.add("PASS", code, msg)

    def fail(self, code: str, msg: str, fix: str = "") -> None:
        self.add("FAIL", code, msg, fix)

    def warn(self, code: str, msg: str, fix: str = "") -> None:
        self.add("WARN", code, msg, fix)

    @property
    def fails(self) -> list[dict]:
        return [i for i in self.items if i["level"] == "FAIL"]

    @property
    def warns(self) -> list[dict]:
        return [i for i in self.items if i["level"] == "WARN"]


def parse_frontmatter(text: str) -> tuple[dict, str]:
    """极简 frontmatter 解析（不依赖 PyYAML，保证自检在任何环境都能跑）。

    只处理本技能实际会用的两种形式：`key: value` 与 `key:` 后跟 `- item` 列表。
    刻意不支持多行块标量 —— 平台本来也不接受多行 description。
    """
    if not text.startswith("---"):
        return {}, text
    end = text.find("\n---", 3)
    if end < 0:
        return {}, text
    fm_raw = text[3:end].strip("\n")
    body = text[end + 4 :]

    fm: dict = {}
    key = None
    for line in fm_raw.splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if line.lstrip().startswith("- ") and key:
            fm.setdefault(key, [])
            if isinstance(fm[key], list):
                fm[key].append(line.lstrip()[2:].strip().strip("\"'"))
            continue
        m = re.match(r"^([A-Za-z0-9_\-]+):\s*(.*)$", line)
        if not m:
            continue
        key, val = m.group(1), m.group(2).strip()
        if val == "":
            fm[key] = []
        else:
            fm[key] = val.strip("\"'")
    return fm, body


def check_frontmatter(root: Path, rep: Report) -> dict:
    p = root / "SKILL.md"
    if not p.exists():
        rep.fail("fm.missing", "缺 SKILL.md（技能的唯一入口文件）", "在包根目录放 SKILL.md")
        return {}
    text = p.read_text(encoding="utf-8")
    fm, body = parse_frontmatter(text)
    if not fm:
        rep.fail("fm.parse", "SKILL.md 没有可解析的 frontmatter", "文件必须以 --- 开头，第二段 --- 收尾")
        return {}

    missing = [f for f in REQUIRED_FIELDS if not fm.get(f)]
    if missing:
        rep.fail("fm.required", f"缺必填字段：{', '.join(missing)}",
                 "按 references/platform-spec.md 的模板补齐，值必须单行")
    else:
        rep.ok("fm.required", f"8 个必填字段齐全（name={fm['name']}, version={fm['version']}）")

    for f in ("display_name", "display_name_en"):
        v = str(fm.get(f) or "")
        if v and not DISPLAY_RE.match(v):
            rep.fail("fm.display_charset",
                     f"{f} 含非法字符：{v!r}（只允许中英文、数字、- 和 —）",
                     f"改成如 IdeaToGame-Creative-Game-Studio 的形式，空格换 -")

    desc = str(fm.get("description") or "")
    if len(desc) > 300:
        rep.warn("fm.desc_len", f"description 长 {len(desc)} 字，市场卡片会截断（建议 ≤300）",
                 "压缩描述，但保留全部触发词")
    elif desc:
        rep.ok("fm.desc_len", f"description {len(desc)} 字")

    # 触发词是技能能否被唤起的关键，缺了等于装了不用
    triggers = ["做个游戏", "小游戏", "HTML5", "CrazyGames"]
    hit = [t for t in triggers if t in desc or t.lower() in desc.lower()]
    if len(hit) < 3:
        rep.warn("fm.triggers", f"description 里的触发词偏少（命中 {hit}）",
                 "把用户真实会说的话写进 description")
    else:
        rep.ok("fm.triggers", f"触发词命中 {len(hit)}/{len(triggers)}")

    if not body.strip():
        rep.fail("fm.body", "SKILL.md 只有 frontmatter，没有正文")
    if "TODO" in body:
        rep.warn("fm.todo", "正文含 TODO", "交付前清掉")

    name = str(fm.get("name") or "")
    if name and name != root.name:
        rep.warn("fm.name_dir", f"name={name} 与目录名 {root.name} 不一致",
                 "安装时目录名必须等于 name，否则脚本按 SKILL_DIR 定位会错")
    return fm


def check_dirs(root: Path, rep: Report) -> None:
    miss = [d for d in REQUIRED_DIRS if not (root / d).is_dir()]
    if miss:
        rep.fail("dir.missing", f"缺目录：{', '.join(miss)}",
                 "分发包必须保持完整结构（不要为了上架市场把目录拍平）")
    else:
        rep.ok("dir.required", f"{len(REQUIRED_DIRS)} 个必需目录齐全")


def check_files(root: Path, rep: Report, must: list[str], code: str, label: str,
                base: str = "") -> None:
    base_dir = root / base if base else root
    miss = [f for f in must if not (base_dir / f).exists()]
    if miss:
        rep.fail(code, f"{label}缺 {len(miss)} 个：{', '.join(miss[:4])}"
                       + (" …" if len(miss) > 4 else ""),
                 f"从 {base or '包根'} 下补齐；缺模板会导致 init_project 出来的项目跑不起来")
    else:
        rep.ok(code, f"{label}{len(must)} 个全部存在")


def check_scripts(root: Path, rep: Report) -> None:
    scripts = sorted((root / "scripts").glob("*.py"))
    if not scripts:
        rep.fail("scripts.empty", "scripts/ 下没有 .py")
        return
    bad = []
    with tempfile.TemporaryDirectory() as td:
        for f in scripts:
            try:
                py_compile.compile(str(f), cfile=str(Path(td) / (f.stem + ".pyc")),
                                   doraise=True)
            except py_compile.PyCompileError as e:
                bad.append(f"{f.name}: {str(e).splitlines()[-1][:80]}")
    if bad:
        rep.fail("scripts.compile", f"{len(bad)} 个脚本编译失败", "；".join(bad[:3]))
    else:
        rep.ok("scripts.compile", f"{len(scripts)} 个脚本全部编译通过")

    # 脚本必须能独立定位到包根（SKILL_DIR = 文件上两级）
    common = root / "scripts" / "_common.py"
    if common.exists():
        t = common.read_text(encoding="utf-8")
        if "SKILL_DIR" not in t:
            rep.fail("scripts.skilldir", "_common.py 未定义 SKILL_DIR", "脚本无法定位包内资源")
        else:
            rep.ok("scripts.skilldir", "_common.py 定义了 SKILL_DIR")


def check_module_refs(root: Path, rep: Report) -> None:
    """SKILL.md 里写的 modules/xxx.md 必须真实存在 —— 这是最常见的断链。"""
    p = root / "SKILL.md"
    if not p.exists():
        return
    text = p.read_text(encoding="utf-8")
    refs = sorted(set(re.findall(r"modules/[0-9A-Za-z_\-]+\.md", text)))
    miss = [r for r in refs if not (root / r).exists()]
    if miss:
        rep.fail("ref.modules", f"SKILL.md 引用了不存在的模块：{', '.join(miss[:5])}",
                 "补文件或改引用")
    elif refs:
        rep.ok("ref.modules", f"SKILL.md 引用的 {len(refs)} 个模块全部存在")


def check_json(root: Path, rep: Report, pattern: str, code: str, label: str) -> None:
    files = sorted(root.glob(pattern))
    bad = []
    for f in files:
        try:
            json.loads(f.read_text(encoding="utf-8"))
        except Exception as e:  # noqa: BLE001
            bad.append(f"{f.relative_to(root)}: {str(e)[:60]}")
    if bad:
        rep.fail(code, f"{len(bad)} 个 {label} JSON 非法", "；".join(bad[:3]))
    elif files:
        rep.ok(code, f"{len(files)} 个 {label} JSON 合法")


def check_encoding(root: Path, rep: Report) -> None:
    """Windows 上最容易出的问题是某个文件被存成 GBK，Linux/mac 读到就是乱码。"""
    bad = []
    for f in root.rglob("*"):
        if not f.is_file():
            continue
        if f.suffix.lower() not in (".md", ".py", ".json", ".ts", ".mjs", ".yaml", ".yml",
                                    ".html", ".css", ".txt"):
            continue
        if any(x in f.parts for x in (".git", "node_modules", "__pycache__", ".pytest_cache")):
            continue
        try:
            f.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            bad.append(str(f.relative_to(root)))
    if bad:
        rep.fail("file.encoding", f"{len(bad)} 个文件不是 UTF-8",
                 f"例如 {bad[0]}；统一转成 UTF-8")
    else:
        rep.ok("file.encoding", "文本文件全部 UTF-8")


def check_junk(root: Path, rep: Report) -> None:
    junk = []
    for name in (".pytest_cache", "__pycache__"):
        junk += [str(p.relative_to(root)) for p in root.rglob(name) if p.is_dir()]
    if junk:
        rep.warn("pack.junk", f"有 {len(junk)} 个缓存目录会被打进包", "打包脚本会自动排除")
    else:
        rep.ok("pack.junk", "无缓存目录残留")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--path", default=str(SKILL_DIR), help="技能目录，默认本包")
    ap.add_argument("--json", action="store_true", help="机读输出")
    args = ap.parse_args()

    root = Path(args.path).resolve()
    if not root.is_dir():
        print(f"目录不存在：{root}")
        return 2

    rep = Report()
    check_frontmatter(root, rep)
    check_dirs(root, rep)
    check_files(root, rep, TEMPLATE_MUST, "file.template", "模板文件", base="assets/template")
    check_files(root, rep, DATA_MUST, "file.data", "模式库")
    check_files(root, rep, SCHEMA_MUST, "file.schema", "JSON Schema")
    check_scripts(root, rep)
    check_module_refs(root, rep)
    check_json(root, rep, "assets/data/**/*.json", "json.data", "模式库")
    check_json(root, rep, "references/schemas/*.json", "json.schema", "Schema")
    check_encoding(root, rep)
    check_junk(root, rep)

    if args.json:
        print(json.dumps({
            "path": str(root),
            "pass": len([i for i in rep.items if i["level"] == "PASS"]),
            "warn": len(rep.warns),
            "fail": len(rep.fails),
            "items": rep.items,
            "ok": not rep.fails,
        }, ensure_ascii=False, indent=2))
        return 0 if not rep.fails else 1

    print(f"技能包自检：{root}\n")
    for i in rep.items:
        mark = {"PASS": "[PASS]", "WARN": "[WARN]", "FAIL": "[FAIL]"}[i["level"]]
        print(f"{mark} {i['msg']}")
        if i["fix"]:
            print(f"       → {i['fix']}")

    print(f"\n合计：PASS {len([i for i in rep.items if i['level']=='PASS'])}　"
          f"WARN {len(rep.warns)}　FAIL {len(rep.fails)}")
    if rep.fails:
        print("\n结论：FAIL —— 不要出包。")
        return 1
    print("\n结论：PASS —— 可以打包分发。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
