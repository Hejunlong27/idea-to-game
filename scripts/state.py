#!/usr/bin/env python3
"""读写项目状态机 .gamedev/state.yaml。

用法:
    python state.py show --project <proj>
    python state.py set  --project <proj> --stage brief --status done
    python state.py set  --project <proj> --stage brief --gate G1_passed
    python state.py set  --project <proj> --stage perf_audit --retries 2
    python state.py next --project <proj>
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import (  # noqa: E402
    GATED_STAGES,
    PLATFORM_KEYS,
    STAGES,
    STATUSES,
    load_state,
    ok,
    project_dir,
    save_state,
)

# 平台确认是流程前的第 0 步（G0），不在 STAGES 里，但 show/next 要体现
PLATFORM_STEP = "platforms"

MARK = {
    "pending": "[ ]",
    "in_progress": "[~]",
    "done": "[x]",
    "failed": "[!]",
    "degraded": "[D]",
    "skipped": "[-]",
}


def cmd_show(proj: Path) -> int:
    st = load_state(proj)
    p = st.get("project", {})
    d = st.get("delivery", {})
    platforms = d.get("platforms") or []
    confirmed = bool(d.get("platform_confirmed"))

    if platforms and confirmed:
        pmark, pstatus = "[x]", f"done  ({', '.join(platforms)})"
    elif platforms:
        pmark, pstatus = "[~]", f"in_progress  ({', '.join(platforms)}，待用户确认)"
    else:
        pmark, pstatus = "[ ]", "pending  ← 必须先做：问用户发到哪些平台"

    print(f"项目: {p.get('name')}  |  品类: {p.get('genre') or '-'}")
    print(f"想法: {p.get('idea')}")
    print(f"参考图: {p.get('style_ref') or '-'}")
    print("-" * 64)
    print(f"{pmark} {PLATFORM_STEP:<14} {pstatus}")
    for s in STAGES:
        info = st.get("stages", {}).get(s, {})
        status = info.get("status", "pending")
        extra = []
        if info.get("gate"):
            extra.append(info["gate"])
        if info.get("self_test"):
            extra.append(f"self_test={info['self_test']}")
        if info.get("retries"):
            extra.append(f"retries={info['retries']}")
        if info.get("note"):
            extra.append(info["note"])
        print(f"{MARK.get(status, '[?]')} {s:<14} {status:<12} {' '.join(extra)}")
    print("-" * 64)
    print(f"档位: {d.get('tier') or '未评估'}")
    if d.get("platform_notes"):
        for k, v in d["platform_notes"].items():
            print(f"  {k}: {v}")
    return 0


def cmd_set_platforms(args) -> int:
    proj = project_dir(args.project)
    st = load_state(proj)
    d = st.setdefault("delivery", {})

    if args.platforms:
        plats = [p.strip().lower() for p in args.platforms.split(",") if p.strip()]
        unknown = [p for p in plats if p not in PLATFORM_KEYS]
        if unknown:
            print(f"ERROR: 未知平台 {unknown}；可选：{', '.join(PLATFORM_KEYS)}", file=sys.stderr)
            return 1
        if not plats:
            print("ERROR: 平台列表为空", file=sys.stderr)
            return 1
        d["platforms"] = plats
        if args.note:
            d.setdefault("platform_notes", {})[args.note.split("=", 1)[0]] = args.note.split("=", 1)[-1]
        # 平台变更后需要重新确认
        if not args.confirm:
            d["platform_confirmed"] = False

    if args.confirm:
        if not d.get("platforms"):
            print("ERROR: 尚未设置平台，无法确认", file=sys.stderr)
            return 1
        d["platform_confirmed"] = True

    save_state(proj, st)
    ok(f"平台: {', '.join(d.get('platforms') or [])} | 已确认: {d.get('platform_confirmed')}")
    return 0


def cmd_set(args) -> int:
    proj = project_dir(args.project)
    st = load_state(proj)
    stages = st.setdefault("stages", {})
    if args.stage not in STAGES:
        print(f"ERROR: 未知阶段 {args.stage}；可选：{', '.join(STAGES)}", file=sys.stderr)
        return 1
    node = stages.setdefault(args.stage, {})
    if args.status:
        if args.status not in STATUSES:
            print(f"ERROR: 未知状态 {args.status}；可选：{', '.join(sorted(STATUSES))}", file=sys.stderr)
            return 1
        node["status"] = args.status
    if args.gate:
        expected = GATED_STAGES.get(args.stage)
        if not expected:
            print(f"ERROR: 阶段 {args.stage} 不是门禁阶段", file=sys.stderr)
            return 1
        if args.gate != expected:
            print(f"ERROR: 阶段 {args.stage} 的门禁值应为 {expected}", file=sys.stderr)
            return 1
        node["gate"] = args.gate
    if args.retries is not None:
        node["retries"] = args.retries
    if args.note:
        node["note"] = args.note
    save_state(proj, st)
    ok(f"{args.stage} 已更新：{node}")
    return 0


def cmd_next(proj: Path) -> int:
    st = load_state(proj)
    d = st.get("delivery", {})
    if not d.get("platforms"):
        print("下一个动作：platforms —— 必须先问用户发到哪些平台（门禁 G0）")
        print("读模块：modules/00-platforms.md")
        return 0
    if not d.get("platform_confirmed"):
        print(f"下一个动作：platforms —— 等待用户确认平台（当前: {', '.join(d['platforms'])}）")
        print("确认后执行：state.py set-platforms --confirm")
        return 0

    stages = st.get("stages", {})
    for s in STAGES:
        status = stages.get(s, {}).get("status", "pending")
        if status in ("done", "skipped"):
            continue
        if s in GATED_STAGES and stages.get(s, {}).get("gate") != GATED_STAGES[s]:
            print(f"下一个动作：{s} —— 完成后需要人工门禁 {GATED_STAGES[s]}")
            return 0
        print(f"下一个动作：{s}（当前 {status}）")
        idx = STAGES.index(s) + 1
        print(f"读模块：modules/{idx:02d}-*.md")
        return 0
    print("全部阶段已完成。可执行 ship 阶段产出最终交付包。")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="IdeaToGame 状态机")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("show", help="显示当前进度")
    sp.add_argument("--project", default=None)

    ss = sub.add_parser("set", help="更新阶段状态")
    ss.add_argument("--project", default=None)
    ss.add_argument("--stage", required=True)
    ss.add_argument("--status", default=None)
    ss.add_argument("--gate", default=None)
    ss.add_argument("--retries", type=int, default=None)
    ss.add_argument("--note", default=None)

    sn = sub.add_parser("next", help="显示下一步动作")
    sn.add_argument("--project", default=None)

    spf = sub.add_parser("set-platforms", help="设置/确认目标平台（门禁 G0）")
    spf.add_argument("--project", default=None)
    spf.add_argument("--platforms", default="", help=f"逗号分隔。可选：{', '.join(PLATFORM_KEYS)}")
    spf.add_argument("--confirm", action="store_true", help="标记为用户已确认")
    spf.add_argument("--note", default="", help="备注，格式 <平台key>=<说明>")

    args = ap.parse_args()
    if args.cmd == "show":
        return cmd_show(project_dir(args.project))
    if args.cmd == "set":
        return cmd_set(args)
    if args.cmd == "next":
        return cmd_next(project_dir(args.project))
    if args.cmd == "set-platforms":
        return cmd_set_platforms(args)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
