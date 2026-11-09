#!/usr/bin/env python3
"""Comfy 生成 —— 草稿探索阶段的本地出图。

## 为什么单独写一个

`gen_assets.py` 是「按 asset-spec 批量出全套」，流程重、依赖项目结构。
草稿阶段需要的是**快速试风格**：改提示词 → 出图 → 看效果，一轮 30 秒。

所以这个脚本只做一件事：给提示词，出图。

## 分层用法的定位

| 阶段 | 通道 | 工具 |
|---|---|---|
| 草稿探索（试风格） | ComfyUI 本地 | **本脚本** |
| 定型精修 | 闭源模型 | 另行接入 |
| 批量变体 | ComfyUI + i2i ref | `gen_assets.py` |

## 用法

  python comfy_gen.py --prompt "..." --out out.png
  python comfy_gen.py --prompt "..." --out out.png --square --prefix enemy
  python comfy_gen.py --probe

## 注意

- 必须绕系统代理（`ProxyHandler({})`），否则 127.0.0.1 被劫持成 502。
- 显存 8GB 下 1024² 约 25–35 秒。
- 产物在 ComfyUI 的 output 目录，脚本会自动下载到 `--out`。
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
WORKFLOW = SKILL_DIR / "assets" / "workflows" / "qwen_image_21_turbo_t2i.json"
BASE = "http://127.0.0.1:8188"
OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def call(path: str, payload: dict | None = None, timeout: int = 30):
    data = json.dumps(payload).encode() if payload is not None else None
    headers = {"Content-Type": "application/json"} if data else {}
    req = urllib.request.Request(BASE + path, data=data, headers=headers)
    try:
        with OPENER.open(req, timeout=timeout) as r:
            raw = r.read()
            try:
                return r.status, json.loads(raw)
            except json.JSONDecodeError:
                return r.status, raw
    except urllib.error.HTTPError as e:
        return e.code, e.read()[:400]
    except Exception as e:  # noqa: BLE001
        return 0, repr(e)


def probe() -> bool:
    st, body = call("/system_stats", timeout=5)
    if st != 200:
        print(f"ComfyUI 未就绪（{BASE}）：{body}")
        print("  → 启动：cd <ComfyUI> && ./.venv/Scripts/python.exe main.py --port 8188")
        return False
    ver = (body.get("system") or {}).get("comfyui_version", "?") if isinstance(body, dict) else "?"
    print(f"ComfyUI 就绪：{ver}")
    return True


def generate(prompt: str, prefix: str, out: Path, square: bool) -> bool:
    wf = json.loads(WORKFLOW.read_text(encoding="utf-8"))

    # 提示词节点：PrimitiveStringMultiline
    prompt_set = False
    for nid, node in wf.items():
        ct = node.get("class_type", "")
        if ct == "PrimitiveStringMultiline":
            node["inputs"]["value"] = prompt
            prompt_set = True
        elif ct == "SaveImage":
            node["inputs"]["filename_prefix"] = prefix
        elif ct == "ResolutionSelector" and square:
            node["inputs"]["aspect_ratio"] = "1:1 (Square)"
            node["inputs"]["megapixels"] = 1
    if not prompt_set:
        print("工作流里没有 PrimitiveStringMultiline 节点，无法注入提示词")
        return False

    client_id = str(uuid.uuid4())
    st, body = call("/prompt", {"prompt": wf, "client_id": client_id}, timeout=30)
    if st != 200 or not isinstance(body, dict) or "prompt_id" not in body:
        print(f"提交失败：{body}")
        return False
    pid = body["prompt_id"]
    print(f"  任务 {pid[:12]} 已提交")

    # 轮询
    # 首次生成含模型加载，给足 10 分钟；之后每张约 45 秒
    deadline = time.time() + 600
    while time.time() < deadline:
        time.sleep(4)
        st, hist = call(f"/history/{pid}", timeout=15)
        if st != 200 or not isinstance(hist, dict) or pid not in hist:
            continue
        entry = hist[pid]
        status = (entry.get("status") or {}).get("status_str", "")
        if status == "error":
            print(f"  生成报错：{json.dumps(entry.get('status'), ensure_ascii=False)[:300]}")
            return False
        outputs = entry.get("outputs") or {}
        for node_out in outputs.values():
            for img in node_out.get("images") or []:
                q = urllib.parse.urlencode({
                    "filename": img["filename"],
                    "subfolder": img.get("subfolder", ""),
                    "type": img.get("type", "output"),
                })
                st2, data = call(f"/view?{q}", timeout=60)
                if st2 == 200 and isinstance(data, bytes):
                    out.parent.mkdir(parents=True, exist_ok=True)
                    out.write_bytes(data)
                    print(f"  → {out}  {len(data)/1024:.0f}KB")
                    return True
        # 有 outputs 但没图片，继续等
    print("  超时")
    return False


def main() -> int:
    ap = argparse.ArgumentParser(description="ComfyUI 快速出图")
    ap.add_argument("--probe", action="store_true")
    ap.add_argument("--prompt", default="")
    ap.add_argument("--out", default="", help="输出图片路径")
    ap.add_argument("--prefix", default="draft", help="ComfyUI 输出前缀")
    ap.add_argument("--square", action="store_true", help="方图（游戏单位推荐）")
    args = ap.parse_args()

    if args.probe:
        return 0 if probe() else 2
    if not args.prompt or not args.out:
        print("需要 --prompt 和 --out", file=sys.stderr)
        return 2
    if not probe():
        return 2
    return 0 if generate(args.prompt, args.prefix, Path(args.out), args.square) else 1


if __name__ == "__main__":
    sys.exit(main())
