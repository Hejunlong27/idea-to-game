#!/usr/bin/env python3
"""试玩编排：起本地服务 → 跑 playtest.mjs（真实浏览器操作）→ 生成试玩报告。

分工：
  - `assets/template/scripts/playtest.mjs`  真正去玩（Puppeteer，四种玩家策略）
  - 本脚本                                起服务、汇总、出 HTML 报告、更新状态机

为什么必须有这一步：`shots.mjs` 只截图、`test-standalone.mjs` 只冒烟，
两者都发现不了「玩家不知道按哪个键」「第三关卡住」「40 秒没有任何反馈」。
但也要明确：**AI 模拟试玩不等于真实用户测试**，报告里三类结论分开列。

用法:
    python playtest.py --project .                          # 用 dist/crazygames
    python playtest.py --project . --dir dist/taptap
    python playtest.py --project . --seconds 45 --strategy strategist
    python playtest.py --project . --no-run                 # 只用已有 playtest.json 出报告

产物:
    docs/07-qa/playtest.json          机读（playtest.mjs 产出）
    docs/07-qa/playtest-shots/*.png   各策略的关键截图
    docs/07-qa/playtest-report.html   人读报告（含截图与分类结论）
"""

from __future__ import annotations

import argparse
import html
import http.server
import json
import os
import shutil
import socket
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import SKILL_DIR, dump_json, load_state, ok, project_dir, save_state, warn  # noqa: E402


def free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


class Handler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):  # 静音
        pass

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()


def serve(directory: Path, port: int) -> http.server.ThreadingHTTPServer:
    os.chdir(directory)
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", port), Handler)
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    return httpd


def run_node(script: Path, cwd: Path, url: str, out: str, seconds: int, strategy: str) -> int:
    node = shutil.which("node") or "node"
    cmd = [node, str(script), "--url", url, "--out", out, "--seconds", str(seconds)]
    if strategy:
        cmd += ["--strategy", strategy]
    print("运行：", " ".join(cmd))
    r = subprocess.run(cmd, cwd=str(cwd))
    return r.returncode


# ------------------------------------------------------------------ report
def build_report(proj: Path, data: dict) -> Path:
    s = data.get("summary") or {}
    strategies = data.get("strategies") or []
    shots = sorted((proj / "docs" / "07-qa" / "playtest-shots").glob("*.png"))

    def esc(x):
        return html.escape(str(x))

    rows = []
    for r in strategies:
        rows.append(
            "<tr>"
            f"<td>{esc(r.get('label', r.get('strategy')))}</td>"
            f"<td>{r.get('duration_s')}s</td>"
            f"<td>{r.get('actions')}</td>"
            f"<td>{r.get('distinct_states')}</td>"
            f"<td>{r.get('repetition_ratio')}</td>"
            f"<td>{r.get('stuck_events')}</td>"
            f"<td>{r.get('max_idle_ms')}ms</td>"
            f"<td>{'-' if r.get('first_positive_feedback_s') is None else str(r.get('first_positive_feedback_s')) + 's'}</td>"
            f"<td>{len(r.get('errors') or [])}</td>"
            "</tr>")

    ev_rows = []
    for r in strategies:
        for k, v in (r.get("event_counts") or {}).items():
            ev_rows.append(f"<tr><td>{esc(r.get('strategy'))}</td><td>{esc(k)}</td><td>{v}</td></tr>")

    err_items = "".join(f"<li>{esc(e)}</li>" for e in (s.get("errors") or [])) or "<li>无</li>"

    # 三类结论分开写（任务书要求）
    prog_issues = []
    ai_notes = []
    human_todo = []
    if s.get("any_stuck"):
        prog_issues.append("检测到卡死：有策略出现连续 6 秒状态不变")
    if (s.get("repetition_ratio") or 0) > 0.7:
        prog_issues.append(f"重复动作占比 {(s.get('repetition_ratio') or 0) * 100:.0f}%（阈值 70%）")
    if (s.get("max_idle_ms") or 0) > 8000:
        prog_issues.append(f"最长无反馈间隔 {(s.get('max_idle_ms') or 0) / 1000:.1f}s")
    if (s.get("first_positive_feedback_s") or 999) > 30:
        prog_issues.append(f"首次正反馈在 {s.get('first_positive_feedback_s')}s（要求 ≤30s）")
    if s.get("errors"):
        prog_issues.append(f"运行时错误 {len(s['errors'])} 条")

    if not prog_issues:
        ai_notes.append("四种策略均未发现卡死、异常或长时间无反馈")
    if (s.get("total_events") or 0) < 20:
        ai_notes.append("事件总数偏少，可能反馈密度不足（也可能只是试玩时间短）")
    human_todo.append("操作是否「一看就懂」需要真人判断 —— AI 的策略是脚本化的，不能代表新手")
    human_todo.append("难度曲线是否合适需要真人玩 3 局以上")
    human_todo.append("「值得记住的瞬间」是否成立，只能由人回答")

    img_html = "".join(
        f'<figure><img src="playtest-shots/{esc(p.name)}" alt="{esc(p.name)}"><figcaption>{esc(p.name)}</figcaption></figure>'
        for p in shots[:12])

    doc = f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<title>试玩报告 · {esc(proj.name)}</title>
<style>
body{{font-family:system-ui,-apple-system,"Segoe UI",sans-serif;max-width:1080px;margin:0 auto;padding:28px 20px 80px;background:#0f1218;color:#e6e9f0;line-height:1.65}}
h1{{font-size:26px;margin:0 0 4px}} h2{{font-size:19px;margin:32px 0 10px;border-left:3px solid #4ea1ff;padding-left:10px}}
.sub{{color:#8b93a8;font-size:13px;margin-bottom:20px}}
table{{width:100%;border-collapse:collapse;font-size:13px;margin:8px 0 4px}}
th,td{{border:1px solid #2a3140;padding:7px 9px;text-align:left}}
th{{background:#1a2030;color:#aab3c6;font-weight:600}}
.bad{{color:#ff6b5a}} .good{{color:#46d17f}} .warn{{color:#f2b04a}}
.card{{background:#151a24;border:1px solid #242c3a;border-radius:8px;padding:14px 16px;margin:10px 0}}
.tag{{display:inline-block;font-size:11px;padding:1px 7px;border-radius:10px;background:#243044;color:#9fb4d8;margin-right:6px}}
figure{{display:inline-block;margin:6px;width:200px;vertical-align:top}}
figure img{{width:100%;border:1px solid #2a3140;border-radius:6px}}
figcaption{{font-size:11px;color:#8b93a8;text-align:center;margin-top:3px}}
ul{{margin:6px 0 6px 18px;padding:0}} li{{margin:3px 0;font-size:14px}}
.note{{font-size:12px;color:#8b93a8;border-left:2px solid #2a3140;padding-left:10px;margin-top:8px}}
</style></head><body>
<h1>试玩报告</h1>
<div class="sub">生成时间 {esc(data.get('generated_at', ''))}　被测地址 {esc(data.get('url', ''))}　
每策略 {data.get('seconds_per_strategy')}s　生成器 <code>scripts/playtest.mjs</code></div>

<div class="card"><b>{esc(data.get('disclaimer', ''))}</b></div>

<h2>1. 程序检测结果（客观）</h2>
<table><thead><tr><th>策略</th><th>时长</th><th>操作数</th><th>不同状态</th><th>重复率</th>
<th>卡死</th><th>最长无反馈</th><th>首次正反馈</th><th>错误</th></tr></thead><tbody>
{''.join(rows)}
</tbody></table>
<p>事件总数 <b>{s.get('total_events')}</b>　运行时错误 <b class="{'bad' if s.get('errors') else 'good'}">{len(s.get('errors') or [])}</b></p>
<ul>{''.join(f'<li>{esc(x)}</li>' for x in prog_issues) or '<li class="good">未发现阻断性问题</li>'}</ul>

<h2>2. AI 评价（启发式，仅供参考）</h2>
<ul>{''.join(f'<li>{esc(x)}</li>' for x in ai_notes)}</ul>
<p class="note">AI 评价来自脚本规则（事件密度、重复率、空闲间隔），不是审美判断，也不能替代人的主观体验。</p>

<h2>3. 待人工确认（AI 无法判定）</h2>
<ul>{''.join(f'<li>{esc(x)}</li>' for x in human_todo)}</ul>

<h2>4. 事件分布</h2>
<table><thead><tr><th>策略</th><th>事件</th><th>次数</th></tr></thead><tbody>
{''.join(ev_rows) or '<tr><td colspan="3">未采集到事件（检查 window.__gameEvents 是否暴露）</td></tr>'}
</tbody></table>

<h2>5. 运行时错误</h2>
<ul>{err_items}</ul>

<h2>6. 截图</h2>
<div>{img_html or '<p class="sub">无截图</p>'}</div>

<h2>7. 改进建议</h2>
<ul>
{''.join(f'<li>{esc(x)}</li>' for x in (prog_issues or ['保持当前反馈密度，重点验证真机帧率']))}
</ul>
</body></html>
"""
    out = proj / "docs" / "07-qa" / "playtest-report.html"
    out.write_text(doc, encoding="utf-8")
    return out


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass
    ap = argparse.ArgumentParser(description="试玩编排 + 报告")
    ap.add_argument("--project", default=None)
    ap.add_argument("--dir", default="dist/crazygames")
    ap.add_argument("--seconds", type=int, default=40)
    ap.add_argument("--strategy", default="")
    ap.add_argument("--no-run", action="store_true")
    args = ap.parse_args()

    proj = project_dir(args.project)
    out_rel = "docs/07-qa"
    (proj / out_rel).mkdir(parents=True, exist_ok=True)

    if not args.no_run:
        serve_dir = proj / args.dir
        if not serve_dir.is_dir():
            print(f"ERROR: 目录不存在：{serve_dir}（先 npm run build:cg）", file=sys.stderr)
            return 1
        script = proj / "scripts" / "playtest.mjs"
        if not script.exists():
            src = SKILL_DIR / "assets" / "template" / "scripts" / "playtest.mjs"
            if src.exists():
                shutil.copy2(src, script)
                warn("项目缺 playtest.mjs，已从技能模板复制")
            else:
                print("ERROR: 找不到 playtest.mjs", file=sys.stderr)
                return 1
        port = free_port()
        httpd = serve(serve_dir, port)
        url = f"http://127.0.0.1:{port}/index.html"
        try:
            rc = run_node(script, proj, url, out_rel, args.seconds, args.strategy)
        finally:
            httpd.shutdown()
        if rc not in (0, 1):
            warn(f"playtest.mjs 退出码 {rc}")

    pj = proj / out_rel / "playtest.json"
    if not pj.exists():
        print(f"ERROR: 缺 {pj}", file=sys.stderr)
        return 1
    data = json.loads(pj.read_text(encoding="utf-8"))
    rep = build_report(proj, data)

    st = load_state(proj)
    s = data.get("summary") or {}
    st.setdefault("stages", {})["qa"] = {
        "status": "done" if not s.get("errors") else "in_progress",
        "playtest": True,
        "errors": len(s.get("errors") or []),
        "repetition_ratio": s.get("repetition_ratio"),
    }
    save_state(proj, st)
    ok(f"试玩报告：{rep.relative_to(proj)}")
    print(f"  事件 {s.get('total_events')}　错误 {len(s.get('errors') or [])}　"
          f"卡死 {'有' if s.get('any_stuck') else '无'}　"
          f"首次正反馈 {s.get('first_positive_feedback_s')}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
