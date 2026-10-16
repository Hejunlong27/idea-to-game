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
from _common import GATED_STAGES, STAGES, STATUSES, load_state, ok, project_dir, save_state  # noqa: E402

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
    print(f"项目: {p.get('name')}  |  品类: {p.get('genre') or '-'}")
    print(f"想法: {p.get('idea')}")
    print(f"参考图: {p.get('style_ref') or '-'}")
    print("-" * 56)
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
    d = st.get("delivery", {})
    print("-" * 56)
    print(f"档位: {d.get('tier') or '未评估'}  |  平台: {', '.join(d.get('platforms') or []) or '-'}")
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
    stages = st.get("stages", {})
    for s in STAGES:
        status = stages.get(s, {}).get("status", "pending")
        if status in ("done", "skipped"):
            continue
        if s in GATED_STAGES and stages.get(s, {}).get("gate") != GATED_STAGES[s]:
            print(f"下一个动作：{s} —— 完成后需要人工门禁 {GATED_STAGES[s]}")
            return 0
        print(f"下一个动作：{s}（当前 {status}）")
        print(f"读模块：modules/{STAGES.index(s) + 1:02d}-*.md")
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

    args = ap.parse_args()
    if args.cmd == "show":
        return cmd_show(project_dir(args.project))
    if args.cmd == "set":
        return cmd_set(args)
    if args.cmd == "next":
        return cmd_next(project_dir(args.project))
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
