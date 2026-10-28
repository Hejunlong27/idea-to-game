#!/usr/bin/env python3
"""一键打包交付（模块 11 · ship）：构建 → 审计 → 过审自检 → 打 zip → 商店素材 → 自检清单。

把 ship 阶段里所有确定性动作串起来，一条命令跑完，避免手工漏项。

用法:
    python ship_pack.py --build                 # 按 state.yaml 的选定平台全流程
    python ship_pack.py --platforms taptap --build
    python ship_pack.py --platforms taptap      # 不重新构建，直接审计已有的 dist/
    python ship_pack.py --build --no-zip        # 只审计，不打 zip

产物:
    dist/<平台>.zip                             解压后根目录即 index.html
    docs/06-perf/measure-<平台>.json            体积审计原始数据
    docs/08-ship/precheck-<平台>.json           过审自检原始数据
    docs/08-ship/store/<平台>/                  商店素材（icon / cover / 截图）
    docs/08-ship/submit-checklist.md            逐平台实测数值 + 待人工事项
    docs/08-ship/store-copy.md                  文案骨架（不存在时创建）

注意：本脚本**不执行提交**，也不替代 R2 终审。提交前仍需 gate_check.py --stage ship 通过。
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import zipfile
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import (  # noqa: E402
    PLATFORM_KEYS,
    human_size,
    iter_files,
    load_state,
    ok,
    platform_conf,
    project_dir,
    warn,
)

try:
    from PIL import Image
except ImportError:
    Image = None  # type: ignore

SCRIPTS = Path(__file__).resolve().parent

# 商店素材规格：以后台最新要求为准，这里给可直接用的保守规格
STORE_SPECS = {
    "taptap": {"icon": (512, 512), "cover": (1280, 720), "screens": 3},
    "crazygames": {"icon": (512, 512), "cover": (1920, 1080), "screens": 3},
    "poki": {"icon": (512, 512), "cover": (1920, 1080), "screens": 3},
    "gamedistribution": {"icon": (512, 512), "cover": (1920, 1080), "screens": 3},
    "playgama": {"icon": (512, 512), "cover": (1920, 1080), "screens": 3},
}

# 各平台需用户自己完成的前置事项（写进清单，防止交付后才发现卡住）
MANUAL_ITEMS = {
    "taptap": [
        "开发者实名认证（TapTap 开发者中心）",
        "小游戏前置备案（若上 Tap 小游戏形态；网页游戏 H5 形态无此要求）",
        "Dirichlet 广告平台创建广告位并回填 adUnitId（若要接广告变现）",
        "隐私政策链接（详情页必须可访问）",
        "用 taptap-cli 上传/提审（写操作需 --dry-run 预览后由你确认）",
    ],
    "crazygames": [
        "CrazyGames 开发者账号 + 提交 Basic Launch",
        "按官方要求补 3 张实机截图与商店文案",
    ],
    "poki": ["Poki 提报（需可玩链接 + 3 张实机截图）"],
    "gamedistribution": ["确认平台目录内无同款游戏", "GD 开发者账号提交"],
    "playgama": ["Playgama 账号上传"],
}


def run(cmd: list[str], cwd: Path) -> tuple[int, str]:
    try:
        p = subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True, timeout=900)
        return p.returncode, (p.stdout or "") + (p.stderr or "")
    except FileNotFoundError:
        return 127, f"命令不存在：{cmd[0]}"
    except subprocess.TimeoutExpired:
        return 124, "命令超时（900s）"


def npm_build(proj: Path, key: str) -> bool:
    npm = shutil.which("npm")
    if not npm:
        print("ERROR: 未找到 npm，请手动执行构建：", file=sys.stderr)
        print(f"  npm run build:{'cg' if key == 'crazygames' else key}", file=sys.stderr)
        return False
    script = {
        "crazygames": "build:cg",
        "poki": "build:poki",
        "gamedistribution": "build:gd",
        "playgama": "build:pg",
        "taptap": "build:taptap",
    }[key]
    print(f"  构建：npm run {script}")
    code, out = run([npm, "run", script], proj)
    if code != 0:
        print(out[-2500:])
        return False
    tail = [ln for ln in out.strip().splitlines() if ln.strip()][-4:]
    for ln in tail:
        print(f"    {ln}")
    return True


def cover_resize(im, size: tuple[int, int]):
    im = im.convert("RGBA")
    tw, th = size
    scale = max(tw / im.width, th / im.height)
    nw, nh = max(1, int(im.width * scale + 0.5)), max(1, int(im.height * scale + 0.5))
    im = im.resize((nw, nh), Image.LANCZOS)
    left, top = (nw - tw) // 2, (nh - th) // 2
    return im.crop((left, top, left + tw, top + th))


def make_store_assets(proj: Path, key: str) -> dict:
    """从 QA 截图与图标生成商店素材。缺料时如实报告，不伪造。"""
    if Image is None:
        return {"ok": False, "error": "缺少 Pillow（pip install pillow）"}
    spec = STORE_SPECS[key]
    out_dir = proj / "docs" / "08-ship" / "store" / key
    out_dir.mkdir(parents=True, exist_ok=True)

    shot_dir = proj / "docs" / "07-qa" / "screenshots"
    shots = sorted(
        [p for p in shot_dir.glob("*") if p.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}]
    ) if shot_dir.is_dir() else []
    result: dict = {"screenshots": [], "missing": []}

    # 截图：保留原比例，仅做等比 cover 裁到目标画幅
    for i, src in enumerate(shots[: spec["screens"]], 1):
        im = Image.open(src)
        target = (1080, 1920) if im.height > im.width else (1920, 1080)
        dst = out_dir / f"screenshot-{i}.png"
        cover_resize(im, target).save(dst, "PNG")
        result["screenshots"].append(dst.name)
    if len(shots) < spec["screens"]:
        result["missing"].append(f"实机截图 {spec['screens'] - len(shots)} 张（需真机/无头浏览器截图 → docs/07-qa/screenshots/）")

    # 图标：优先专用 icon 素材，否则用首张截图中心方裁
    icon_src = None
    for cand in ("assets/processed/icon.png", "assets/raw/icon.png", "assets/processed/logo.png"):
        p = proj / cand
        if p.exists():
            icon_src = p
            break
    if icon_src is None and shots:
        icon_src = shots[0]
        result.setdefault("notes", []).append("icon 由首张截图中心裁剪生成，建议后续替换为专门设计的图标")
    if icon_src:
        im = Image.open(icon_src)
        side = min(im.width, im.height)
        box = ((im.width - side) // 2, (im.height - side) // 2, (im.width + side) // 2, (im.height + side) // 2)
        im.crop(box).convert("RGBA").resize(spec["icon"], Image.LANCZOS).save(out_dir / "icon.png", "PNG")
        result["icon"] = "icon.png"
    else:
        result["missing"].append("图标源素材（assets/processed/icon.png）")

    # 封面：优先 cover 素材，否则用首张截图
    cover_src = None
    for cand in ("assets/processed/cover.png", "assets/raw/cover.png"):
        p = proj / cand
        if p.exists():
            cover_src = p
            break
    if cover_src is None and shots:
        cover_src = shots[0]
        result.setdefault("notes", []).append("cover 由首张截图生成，建议后续替换为宣传图")
    if cover_src:
        cover_resize(Image.open(cover_src), spec["cover"]).save(out_dir / "cover.png", "PNG")
        result["cover"] = "cover.png"
    else:
        result["missing"].append("封面源素材（assets/processed/cover.png）")

    result["dir"] = out_dir.relative_to(proj).as_posix()
    return result


def make_zip(proj: Path, key: str) -> tuple[bool, str, int]:
    src = proj / "dist" / key
    dst = proj / "dist" / f"{key}.zip"
    if not src.is_dir():
        return False, "产物目录不存在", 0
    if not (src / "index.html").is_file():
        return False, "产物根目录缺少 index.html", 0
    if dst.exists():
        dst.unlink()
    n = 0
    with zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for f in sorted(iter_files(src)):
            z.write(f, f.relative_to(src).as_posix())
            n += 1
    return True, human_size(dst.stat().st_size), n


def read_json(p: Path) -> dict:
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {}


STORE_COPY_TEMPLATE = """# 商店文案（{label}）

> 硬约束：标题 ≤60 字符 / 简短描述 ≤120 字符 / 详细描述 ≤500 字符。
> 文案由本项目实际玩法决定，禁止写成与游戏不符的描述。

## 标题
（待填，≤60 字符）

## 简短描述
（待填，≤120 字符）

## 详细描述
（待填，≤500 字符）

## 标签 / 分类
（待填，参考平台类目，不要堆砌无关标签）

## 截图清单
（见 docs/08-ship/store/{key}/screenshot-*.png）

## 隐私政策
（纯本地存档、不收集个人信息时也要在详情页声明；收集则必须提供可访问链接）
"""


def main() -> int:
    ap = argparse.ArgumentParser(description="一键打包交付（构建 + 审计 + 自检 + 打 zip + 商店素材）")
    ap.add_argument("--project", default=None)
    ap.add_argument("--platforms", default="", help="逗号分隔；默认取 state.yaml 的 delivery.platforms")
    ap.add_argument("--build", action="store_true", help="先执行 npm run build:<平台>")
    ap.add_argument("--no-zip", action="store_true", help="不打 zip")
    ap.add_argument("--no-store", action="store_true", help="不生成商店素材")
    args = ap.parse_args()

    proj = project_dir(args.project)
    try:
        st = load_state(proj)
    except SystemExit:
        print("ERROR: 无法读取 state.yaml（需要 PyYAML）", file=sys.stderr)
        return 1
    delivery = st.get("delivery") or {}
    platforms = [p.strip() for p in args.platforms.split(",") if p.strip()] or list(delivery.get("platforms") or [])
    if not platforms:
        print("ERROR: 没有目标平台。先完成 G0：state.py set-platforms --platforms <...> --confirm", file=sys.stderr)
        return 1
    unknown = [p for p in platforms if p not in PLATFORM_KEYS]
    if unknown:
        print(f"ERROR: 未知平台 {unknown}；可选：{', '.join(PLATFORM_KEYS)}", file=sys.stderr)
        return 1
    if not delivery.get("platform_confirmed"):
        warn("state.yaml 里 platform_confirmed 不是 true —— 交付包范围必须经用户确认（G0）")

    # R2 终审先行校验（一票否决）
    verdict_p = proj / "docs" / "09-review" / "verdict-r2.json"
    verdict = read_json(verdict_p) if verdict_p.exists() else {}
    if verdict.get("verdict") not in ("PASS", "PASS_WITH_DEVIATIONS"):
        warn(
            f"R2 终审结论为 {verdict.get('verdict') or '缺失'} —— 本次只做打包演练，"
            "正式交付前必须让审核官通过（gate_check.py --stage ship 会硬阻断）"
        )

    summary: list[dict] = []
    print("=" * 64)
    for key in platforms:
        conf = platform_conf(key)
        print(f"▶ {conf['label']}（{key}）")
        item: dict = {"platform": key, "label": conf["label"]}

        if args.build:
            if not npm_build(proj, key):
                print("  ✗ 构建失败，跳过该平台")
                item["error"] = "构建失败"
                summary.append(item)
                continue

        dist = proj / "dist" / key
        if not (dist / "index.html").is_file():
            print(f"  ✗ 缺少产物：{dist}/index.html（加 --build 或手动构建）")
            item["error"] = "缺少产物"
            summary.append(item)
            continue

        # 体积审计
        perf_json = proj / "docs" / "06-perf" / f"measure-{key}.json"
        perf_json.parent.mkdir(parents=True, exist_ok=True)
        code, out = run(
            [sys.executable, str(SCRIPTS / "measure_bundle.py"), "--dir", str(dist), "--platform", key, "--json", str(perf_json)],
            proj,
        )
        perf = read_json(perf_json)
        item["measure"] = perf
        print(f"  体积审计：{'PASS' if code == 0 else 'FAIL'}  "
              f"总 {human_size(perf.get('total_bytes', 0))} / {perf.get('file_count', 0)} 文件")

        # 过审自检
        pre_json = proj / "docs" / "08-ship" / f"precheck-{key}.json"
        pre_json.parent.mkdir(parents=True, exist_ok=True)
        code2, out2 = run(
            [sys.executable, str(SCRIPTS / "precheck.py"), "--dir", str(dist), "--platform", key, "--json", str(pre_json)],
            proj,
        )
        pre = read_json(pre_json)
        item["precheck"] = pre
        print(f"  过审自检：{'PASS' if code2 == 0 else 'FAIL'}  "
              f"{pre.get('passed', 0)} 通过 / {pre.get('failed', 0)} 未通过")
        if code2 != 0:
            for c in pre.get("checks", []):
                if not c.get("pass"):
                    print(f"    ✗ {c['name']}  {c.get('detail', '')[:100]}")

        # 打 zip
        if not args.no_zip:
            good, info, n = make_zip(proj, key)
            item["zip"] = {"ok": good, "info": info, "files": n}
            print(f"  打包：{'✓ ' + info + f'（{n} 文件）' if good else '✗ ' + info}")

        # 商店素材
        if not args.no_store:
            store = make_store_assets(proj, key)
            item["store"] = store
            got = [k for k in ("icon", "cover") if store.get(k)] + store.get("screenshots", [])
            print(f"  商店素材：{len(got)} 项 → {store.get('dir', '-')}")
            for m in store.get("missing", []):
                print(f"    ! 缺 {m}")

        summary.append(item)
        print("-" * 64)

    # 汇总清单
    now = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M")
    lines = [
        "# 提交自检清单",
        "",
        f"- 项目：{st.get('project', {}).get('name', '-')}",
        f"- 生成时间：{now}",
        f"- 交付平台：{', '.join(platforms)}",
        f"- R2 终审：{verdict.get('verdict') or '未执行'}"
        + (f"（第 {verdict.get('round')} 轮）" if verdict.get("round") else ""),
        "",
        "## 一、逐平台实测数值",
        "",
        "| 平台 | 总大小 | 文件数 | 首包(估) | 体积结论 | 自检 | zip |",
        "|---|---|---|---|---|---|---|",
    ]
    for it in summary:
        if it.get("error"):
            lines.append(f"| {it['label']} | - | - | - | {it['error']} | - | - |")
            continue
        m = it.get("measure") or {}
        p = it.get("precheck") or {}
        z = it.get("zip") or {}
        lines.append(
            f"| {it['label']} | {human_size(m.get('total_bytes', 0))} | {m.get('file_count', 0)} | "
            f"{human_size(m.get('initial_bytes', 0))} | "
            f"{'PASS' if not m.get('fails') else 'FAIL: ' + '; '.join(m.get('fails', []))} | "
            f"{p.get('passed', 0)}/{p.get('passed', 0) + p.get('failed', 0)} | "
            f"{'✓ ' + str(z.get('info', '')) if z.get('ok') else '✗'} |"
        )
    lines += ["", "## 二、自动检查明细", ""]
    for it in summary:
        if it.get("error"):
            continue
        lines.append(f"### {it['label']}")
        lines.append("")
        for c in (it.get("precheck") or {}).get("checks", []):
            lines.append(f"- [{'x' if c.get('pass') else ' '}] {c['name']}" + (f" —— {c['detail']}" if c.get("detail") and not c.get("pass") else ""))
        for w in (it.get("measure") or {}).get("warns", []):
            lines.append(f"- [ ] WARN：{w}")
        lines.append("")

    lines += ["## 三、商店素材", ""]
    for it in summary:
        s = it.get("store") or {}
        if not s:
            continue
        lines.append(f"- {it['label']}：`{s.get('dir', '-')}`"
                     f"（icon {s.get('icon', '缺')} / cover {s.get('cover', '缺')} / 截图 {len(s.get('screenshots', []))} 张）")
        for m in s.get("missing", []):
            lines.append(f"  - 缺：{m}")
        for n in s.get("notes", []):
            lines.append(f"  - 注：{n}")

    lines += ["", "## 四、需要你本人完成的前置事项", ""]
    for key in platforms:
        lines.append(f"### {platform_conf(key)['label']}")
        for m in MANUAL_ITEMS.get(key, []):
            lines.append(f"- [ ] {m}")
        lines.append("")

    lines += [
        "## 五、交付前最后一道门",
        "",
        "```bash",
        "python <skill>/scripts/gate_check.py --project <proj> --stage ship",
        "```",
        "",
        "该命令会校验 R0/R1/R2 三段审核结论与「交付包范围 = 用户选定平台」的一致性，未通过不得提交。",
        "",
    ]
    cl = proj / "docs" / "08-ship" / "submit-checklist.md"
    cl.parent.mkdir(parents=True, exist_ok=True)
    cl.write_text("\n".join(lines), encoding="utf-8")
    ok(f"自检清单已写入：{cl.relative_to(proj).as_posix()}")

    for key in platforms:
        sc = proj / "docs" / "08-ship" / "store-copy.md"
        if not sc.exists():
            sc.write_text(STORE_COPY_TEMPLATE.format(label=platform_conf(key)["label"], key=key), encoding="utf-8")
            ok("已创建 docs/08-ship/store-copy.md 骨架（文案需按实际玩法填写）")
            break

    bad = [it["label"] for it in summary if it.get("error")]
    print("=" * 64)
    if bad:
        print(f"未完成：{', '.join(bad)}")
        return 1
    print(f"完成：{', '.join(it['label'] for it in summary)}")
    print("下一步：gate_check.py --stage ship → 按清单完成人工事项 → 提交")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
