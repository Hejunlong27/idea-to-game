"""IdeaToGame 脚本公共工具。

所有脚本共用：路径解析、状态读写、输出格式化。
依赖：Python 3.9+；读写 state.yaml 需要 PyYAML。
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
TEMPLATE_DIR = SKILL_DIR / "assets" / "template"

STAGES = [
    "brief",
    "review_plan",      # R0 审核官介入：规划预审
    "scaffold",
    "art_bible",
    "core_loop",
    "review_graybox",   # R1 审核官介入：灰盒预审（生图之前）
    "art_forge",
    "sprite_tools",
    "audio_forge",
    "polish",
    "perf_audit",
    "qa",
    "review_final",     # R2 审核官介入：终审（交付之前）
    "ship",
]

# 审核官介入的三处，映射到 state.yaml 的阶段键
REVIEW_STAGES = {
    "r0": "review_plan",
    "r1": "review_graybox",
    "r2": "review_final",
}

# 允许进入后续阶段的审核结论（REJECTED / INCOMPLETE 均阻断）
PASSING_VERDICTS = {"PASS", "PASS_WITH_DEVIATIONS"}

STATUSES = {"pending", "in_progress", "done", "failed", "degraded", "skipped"}

GATED_STAGES = {"brief": "G1_passed", "art_bible": "G2_passed"}


def die(msg: str, code: int = 1):
    print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(code)


def warn(msg: str):
    print(f"WARN: {msg}")


def ok(msg: str):
    print(f"OK: {msg}")


def require_yaml():
    try:
        import yaml  # noqa
    except ImportError:
        die(
            "缺少 PyYAML。请先安装：pip install pyyaml\n"
            "（仅 state.yaml 的读写需要它；其余脚本仅需 Pillow）"
        )
    import yaml

    return yaml


def project_dir(arg: str | None) -> Path:
    """解析项目目录：优先命令行参数，其次当前目录向上查找 .gamedev/。"""
    if arg:
        p = Path(arg).expanduser().resolve()
        if not p.is_dir():
            die(f"项目目录不存在：{p}")
        return p
    cur = Path.cwd().resolve()
    for cand in [cur, *cur.parents]:
        if (cand / ".gamedev" / "state.yaml").exists():
            return cand
    die("未找到项目：请用 --project 指定，或在包含 .gamedev/state.yaml 的目录下运行")


def state_path(proj: Path) -> Path:
    return proj / ".gamedev" / "state.yaml"


def load_state(proj: Path) -> dict:
    yaml = require_yaml()
    sp = state_path(proj)
    if not sp.exists():
        die(f"状态文件不存在：{sp}")
    with sp.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def save_state(proj: Path, state: dict) -> None:
    yaml = require_yaml()
    sp = state_path(proj)
    sp.parent.mkdir(parents=True, exist_ok=True)
    with sp.open("w", encoding="utf-8") as f:
        yaml.safe_dump(state, f, allow_unicode=True, sort_keys=False, default_flow_style=False)


def dump_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def human_size(n: int) -> str:
    step = 1024.0
    for unit in ["B", "KB", "MB", "GB"]:
        if n < step or unit == "GB":
            return f"{n:.1f}{unit}" if unit != "B" else f"{n}B"
        n /= step
    return f"{n:.1f}GB"


def iter_files(root: Path):
    for dirpath, _dirnames, filenames in os.walk(root):
        for fn in filenames:
            yield Path(dirpath) / fn


TEXT_EXT = {".html", ".htm", ".js", ".mjs", ".cjs", ".css", ".json", ".txt", ".xml", ".svg"}


# ---------------------------------------------------------------- 平台定义
#
# 单一真相源：SKILL.md 的「支持的平台」表、precheck.py、measure_bundle.py
# 都从这里取数，新增平台只改这一处。
#
# marker      —— 构建产物中必须出现的适配层标识（防止误用 mock 或其他平台包）
# sdk_marker  —— 平台 SDK 的 CDN / 全局对象标识（第三方 SDK 类平台才有）
# initial_mb  —— 首包上限（MB）；mobile_mb 为移动端首页资格上限，无此规则则同 initial_mb
PLATFORMS = {
    "crazygames": {
        "label": "CrazyGames",
        "region": "海外",
        "total_mb": 250,
        "files": 1500,
        "initial_mb": 50,
        "mobile_mb": 20,
        "sdk_markers": ["sdk.crazygames.com", "CrazyGames.SDK"],
        "notes": "两阶段发布：Basic Launch（无广告无收入）→ Full Launch（开广告分成）",
    },
    "poki": {
        "label": "Poki",
        "region": "海外",
        "total_mb": 250,
        "files": 1500,
        "initial_mb": 50,
        "mobile_mb": 20,
        "sdk_markers": ["game-cdn.poki.com", "PokiSDK"],
        "notes": "提报制，需可玩构建链接 + 3 张实机截图",
    },
    "gamedistribution": {
        "label": "GameDistribution",
        "region": "海外",
        "total_mb": 250,
        "files": 1500,
        "initial_mb": 50,
        "mobile_mb": 20,
        "sdk_markers": ["html5.api.gamedistribution.com", "gdsdk", "GD_OPTIONS"],
        "notes": "SDK 强制集成；审核最长 3 周；不接受目录内同款游戏",
    },
    "playgama": {
        "label": "Playgama",
        "region": "海外",
        "total_mb": 250,
        "files": 1500,
        "initial_mb": 50,
        "mobile_mb": 20,
        "sdk_markers": ["playgama", "bridge"],
        "notes": "一套 SDK 覆盖 25+ 平台；不代发 Poki / CrazyGames",
    },
    "taptap": {
        "label": "TapTap",
        "region": "国内",
        "total_mb": 250,
        "files": 1500,
        "initial_mb": 60,
        "mobile_mb": 60,
        "sdk_markers": [],  # 由宿主容器注入 tap 全局对象，无 CDN script
        "notes": "网页游戏 H5 无需 SDK；Tap 小游戏需前置备案（中国大陆合规）",
    },
}

PLATFORM_KEYS = list(PLATFORMS.keys())


def platform_conf(key: str) -> dict:
    if key not in PLATFORMS:
        die(f"未知平台 {key}；可选：{', '.join(PLATFORM_KEYS)}")
    return PLATFORMS[key]


def scan_absolute_paths(root: Path):
    """扫描构建产物中的**根绝对路径**引用。

    只报会真正导致加载失败的形式：形如 "/assets/x.png"、"/js/game.js"、'file:///...'。
    为避免误报（压缩产物中形如 "/wCKxvRF" 的内部字符串），要求命中项
    带文件扩展名，或位于常见静态资源目录下。
    外部 http(s) URL 由 scan_external_urls 单独统计。
    """
    import re

    cand = re.compile(r"""["'\(](/[A-Za-z0-9_\-][A-Za-z0-9_\-./]*)["'\)]""")
    file_ref = re.compile(r"\.(?:js|mjs|cjs|css|html?|png|jpe?g|gif|webp|svg|ico|json|xml|txt|mp3|ogg|wav|m4a|woff2?|ttf|otf|wasm|glb|gltf|atlas)$", re.I)
    asset_dirs = (
        "/assets/", "/js/", "/css/", "/img/", "/images/", "/audio/", "/sound/",
        "/sounds/", "/fonts/", "/static/", "/media/", "/textures/", "/atlas/",
    )

    hits = []
    for f in iter_files(root):
        if f.suffix.lower() not in TEXT_EXT:
            continue
        try:
            text = f.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        rel = f.relative_to(root).as_posix()
        for m in cand.finditer(text):
            p = m.group(1)
            if file_ref.search(p) or p.lower().startswith(asset_dirs):
                hits.append((rel, p))
        for m in re.finditer(r"""file:///[^\s"')]+""", text):
            hits.append((rel, m.group(0)))
    return hits


def scan_external_urls(root: Path):
    """统计产物中引用的外部 http(s) 地址（按 URL 去重）。

    平台 SDK 的 CDN 属正常；其余域名需人工确认在 iframe 内可访问。
    """
    import re

    seen = {}
    pat = re.compile(r"""https?://[^\s"'\)<>\\]+""")
    for f in iter_files(root):
        if f.suffix.lower() not in TEXT_EXT:
            continue
        try:
            text = f.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        rel = f.relative_to(root).as_posix()
        for m in pat.finditer(text):
            seen.setdefault(m.group(0), rel)
    return [(rel, url) for url, rel in seen.items()]


# 真正会发起网络请求的写法。用于「是否依赖境外资源」判定 ——
# 不能拿 scan_external_urls 当判据：第三方库的注释、文档链接、开源协议地址
# 会大量误报（Phaser 包体里就有 phaser.io / github.com / opensource.org）。
_LOADER_PATTERNS = [
    r"""<script[^>]+src\s*=\s*["'](https?://[^"']+)""",
    r"""<link[^>]+href\s*=\s*["'](https?://[^"']+)""",
    r"""<(?:img|iframe|audio|video|source|embed)[^>]+src\s*=\s*["'](https?://[^"']+)""",
    r"""(?:fetch|importScripts)\s*\(\s*["'`](https?://[^"'`]+)""",
    r"""(?:src|href)\s*=\s*["'`](https?://[^"'`]+)""",
    r"""url\(\s*["']?(https?://[^"')\s]+)""",
    r"""@import\s+(?:url\()?\s*["']?(https?://[^"')\s]+)""",
    r"""\.open\s*\(\s*["'](?:GET|POST|PUT|DELETE)["']\s*,\s*["'`](https?://[^"'`]+)""",
    r"""new\s+(?:Image|Audio|WebSocket|EventSource)\s*\(\s*["'`](https?://[^"'`]+)""",
]


def scan_resource_urls(root: Path):
    """只报**会被真正加载**的外部 URL（script/link/src/fetch/url()/open 等）。

    返回 [(相对路径, url)]，按 URL 去重。
    """
    import re

    pats = [re.compile(p, re.I) for p in _LOADER_PATTERNS]
    seen = {}
    for f in iter_files(root):
        if f.suffix.lower() not in TEXT_EXT:
            continue
        try:
            text = f.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        rel = f.relative_to(root).as_posix()
        for p in pats:
            for m in p.finditer(text):
                url = m.group(1).rstrip("\"'`,;")
                seen.setdefault(url, rel)
    return [(rel, url) for url, rel in seen.items()]
