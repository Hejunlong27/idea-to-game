#!/usr/bin/env python3
"""资产生成（模块 05 · art forge）—— 本地 ComfyUI / RunningHub 工作流 / 程序化占位。

用法:
    # 体检：探测 ComfyUI 是否可达、RunningHub 凭证是否可用
    python gen_assets.py --probe

    # 预演：只列出将要生成的素材与最终提示词，不发请求
    python gen_assets.py --dry-run

    # 生成（provider 默认 auto：ComfyUI → RunningHub → 占位）
    python gen_assets.py
    python gen_assets.py --provider comfyui
    python gen_assets.py --provider runninghub --force
    python gen_assets.py --only fruit,ui --max 3

输入契约（只读）:
    docs/02-art/prompts/<asset>.txt        单行提示词（必须含 style_tokens）
    docs/02-art/prompts/<asset>.json       可选：逐素材覆盖 {width,height,seed,negative,provider,ref}
    docs/02-art/palette.json               占位素材取色
输出契约（只写）:
    assets/raw/<asset>.png
    assets/raw/manifest.json               生成台账（provider / seed / prompt hash / 尺寸）
    assets/raw/.artgen-report.json         本次运行报告

配置优先级：命令行 > 环境变量 > .gamedev/artgen.yaml > 内置默认
环境变量：COMFYUI_HOST / RUNNINGHUB_API_KEY / RUNNINGHUB_BASE_URL / RUNNINGHUB_WORKFLOW_ID / I2G_ARTGEN_PROVIDER

依赖: Pillow（占位素材与抠图需要）；读写 yaml 需要 PyYAML（缺失时可用 .gamedev/artgen.json）
"""

from __future__ import annotations

import argparse
import hashlib
import json
import mimetypes
import os
import random
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from datetime import datetime
from pathlib import Path

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:
    print("ERROR: 需要 Pillow。请安装：pip install pillow", file=sys.stderr)
    raise SystemExit(1)

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import (  # noqa: E402
    SKILL_DIR,
    dump_json,
    human_size,
    load_state,
    ok,
    project_dir,
    save_state,
    warn,
)

DEFAULT_WORKFLOW = SKILL_DIR / "assets" / "workflows" / "comfyui_txt2img.json"

DEFAULT_NEGATIVE = (
    "low quality, blurry, jpeg artifacts, watermark, signature, text, caption, "
    "frame, border, cropped, extra limbs, deformed, photorealistic, 3d render"
)

DEFAULTS = {
    "provider": "auto",
    "size": {"width": 1024, "height": 1024},
    "seed": 20261016,
    "steps": None,
    "cfg": None,
    "negative": DEFAULT_NEGATIVE,
    "fallback_placeholder": True,
    "remove_bg": "",          # 设成 #RRGGBB 则出图后把该背景色抠成透明（SDXL 不出 alpha）
    "trim": False,            # 出图后按 alpha 裁边
    "comfyui": {
        "host": "http://127.0.0.1:8188",
        "workflow": str(DEFAULT_WORKFLOW),
        "checkpoint": "",
        "timeout": 300,
        "node_map": {},
    },
    "runninghub": {
        "base_url": "https://www.runninghub.cn",
        "api_key": "",
        "workflow_id": "",
        "timeout": 600,
        "poll": 3.0,
        "node_map": {},
        "workflow_json": "",
        "instance_type": "",
    },
}


# ------------------------------------------------------------------ 配置
def deep_merge(base: dict, over: dict) -> dict:
    out = dict(base)
    for k, v in (over or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def load_config(proj: Path) -> dict:
    cfg = json.loads(json.dumps(DEFAULTS))  # deep copy
    yml = proj / ".gamedev" / "artgen.yaml"
    jsn = proj / ".gamedev" / "artgen.json"
    raw = None
    if yml.exists():
        try:
            import yaml  # noqa
        except ImportError:
            warn("检测到 .gamedev/artgen.yaml 但缺少 PyYAML，尝试回退 artgen.json")
            yaml = None
        if yaml is not None:
            with yml.open("r", encoding="utf-8") as f:
                raw = yaml.safe_load(f) or {}
    elif jsn.exists():
        raw = json.loads(jsn.read_text(encoding="utf-8"))
    if raw:
        cfg = deep_merge(cfg, raw)

    # 环境变量覆盖
    env = os.environ
    if env.get("I2G_ARTGEN_PROVIDER"):
        cfg["provider"] = env["I2G_ARTGEN_PROVIDER"]
    if env.get("COMFYUI_HOST"):
        cfg["comfyui"]["host"] = env["COMFYUI_HOST"]
    if env.get("RUNNINGHUB_API_KEY"):
        cfg["runninghub"]["api_key"] = env["RUNNINGHUB_API_KEY"]
    if env.get("RUNNINGHUB_BASE_URL"):
        cfg["runninghub"]["base_url"] = env["RUNNINGHUB_BASE_URL"]
    if env.get("RUNNINGHUB_WORKFLOW_ID"):
        cfg["runninghub"]["workflow_id"] = env["RUNNINGHUB_WORKFLOW_ID"]
    return cfg


def resolve_path(proj: Path, p: str) -> Path:
    if not p:
        return Path("")
    q = Path(p).expanduser()
    return q if q.is_absolute() else (proj / q)


# ------------------------------------------------------------------ 素材清单
def collect_assets(proj: Path, only: list[str], limit: int | None) -> list[dict]:
    pdir = proj / "docs" / "02-art" / "prompts"
    if not pdir.is_dir():
        print(f"ERROR: 提示词目录不存在：{pdir}（先跑 modules/03-art-bible.md 或 gen_prompts.py）", file=sys.stderr)
        raise SystemExit(1)
    items = []
    for f in sorted(pdir.iterdir()):
        if not f.is_file() or f.suffix.lower() != ".txt":
            continue
        name = f.stem
        if only and not any(k.lower() in name.lower() for k in only):
            continue
        prompt = f.read_text(encoding="utf-8", errors="ignore").strip()
        if not prompt:
            warn(f"提示词为空，跳过：{f.name}")
            continue
        side = f.with_suffix(".json")
        over = {}
        if side.exists():
            try:
                over = json.loads(side.read_text(encoding="utf-8"))
            except Exception as e:
                warn(f"{side.name} 解析失败，已忽略：{e}")
        items.append({"name": name, "prompt": prompt, "file": f, "override": over})
    if limit:
        items = items[:limit]
    if not items:
        print("ERROR: 没有匹配的提示词文件（docs/02-art/prompts/*.txt）", file=sys.stderr)
        raise SystemExit(1)
    return items


def asset_params(cfg: dict, item: dict) -> dict:
    o = item.get("override") or {}
    size = o.get("size") or {}
    return {
        "prompt": item["prompt"],
        "negative": o.get("negative", cfg["negative"]),
        "width": int(size.get("width") or o.get("width") or cfg["size"]["width"]),
        "height": int(size.get("height") or o.get("height") or cfg["size"]["height"]),
        "seed": int(o.get("seed", cfg["seed"])),
        "ref": o.get("ref", ""),
        "provider": o.get("provider", cfg["provider"]),
    }


def signature(p: dict, provider: str, extra: str = "") -> str:
    blob = "|".join(
        [
            provider,
            p["prompt"],
            p["negative"],
            str(p["width"]),
            str(p["height"]),
            str(p["seed"]),
            p["ref"],
            extra,
        ]
    )
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


# ------------------------------------------------------------------ HTTP
def _open(req: urllib.request.Request, timeout: float, no_proxy: bool = False):
    """no_proxy=True 时绕过系统代理 —— 本地 ComfyUI 走 127.0.0.1，
    若系统设了 http_proxy 会被转发出去并返回 502，必须显式绕过。"""
    if no_proxy:
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        return opener.open(req, timeout=timeout)
    return urllib.request.urlopen(req, timeout=timeout)


def http_json(
    url: str,
    payload: dict | None = None,
    timeout: float = 60,
    headers: dict | None = None,
    no_proxy: bool = False,
) -> dict:
    data = None
    hdrs = {"Accept": "application/json"}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        hdrs["Content-Type"] = "application/json"
    hdrs.update(headers or {})
    req = urllib.request.Request(url, data=data, headers=hdrs, method="POST" if data else "GET")
    with _open(req, timeout, no_proxy) as r:
        body = r.read().decode("utf-8", errors="replace")
    try:
        return json.loads(body)
    except json.JSONDecodeError:
        raise RuntimeError(f"响应不是 JSON（{url}）：{body[:300]}")


def http_get_bytes(url: str, timeout: float = 120, no_proxy: bool = False) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "idea-to-game/artgen"})
    with _open(req, timeout, no_proxy) as r:
        return r.read()


def http_multipart(
    url: str, fields: dict, file_field: str, file_path: Path, timeout: float = 120, no_proxy: bool = False
) -> dict:
    boundary = "----i2g" + uuid.uuid4().hex
    parts: list[bytes] = []
    for k, v in fields.items():
        parts.append(
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"{k}\"\r\n\r\n{v}\r\n".encode("utf-8")
        )
    ctype = mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
    parts.append(
        (
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"{file_field}\"; "
            f"filename=\"{file_path.name}\"\r\nContent-Type: {ctype}\r\n\r\n"
        ).encode("utf-8")
    )
    parts.append(file_path.read_bytes())
    parts.append(f"\r\n--{boundary}--\r\n".encode("utf-8"))
    body = b"".join(parts)
    req = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        method="POST",
    )
    with _open(req, timeout, no_proxy) as r:
        return json.loads(r.read().decode("utf-8", errors="replace"))


def retry(fn, attempts: int = 3, base_delay: float = 2.0, label: str = ""):
    last = None
    for i in range(attempts):
        try:
            return fn()
        except Exception as e:  # noqa: BLE001
            last = e
            if i < attempts - 1:
                delay = base_delay * (2**i)
                warn(f"{label or '调用'}失败（第 {i + 1}/{attempts} 次）：{e}；{delay:.0f}s 后重试")
                time.sleep(delay)
    raise RuntimeError(f"{label or '调用'}连续 {attempts} 次失败：{last}")


# ------------------------------------------------------------------ 工作流节点探测
def detect_nodes(wf: dict) -> dict:
    """从 API 格式工作流里推断需要注入的节点。

    返回 {positive: (node_id, field), negative: (...), seed: (...),
          width: (...), height: (...), checkpoint: (...), sampler: node_id}
    识别不到则为 None —— 此时必须在配置里显式给 node_map。
    """
    nodes = {str(k): v for k, v in wf.items() if isinstance(v, dict) and "class_type" in v}
    out: dict = {}

    # 采样器：优先取带 positive/negative 输入的 KSampler 家族
    sampler_id = None
    for nid, n in nodes.items():
        ins = n.get("inputs") or {}
        if "positive" in ins and "negative" in ins and "latent_image" in ins:
            sampler_id = nid
            break
    if sampler_id is None:
        for nid, n in nodes.items():
            if "KSampler" in str(n.get("class_type", "")):
                sampler_id = nid
                break
    if sampler_id:
        out["sampler"] = sampler_id
        ins = nodes[sampler_id].get("inputs") or {}
        for key in ("positive", "negative"):
            ref = ins.get(key)
            if isinstance(ref, list) and ref:
                ref_id = str(ref[0])
                tnode = nodes.get(ref_id) or {}
                tins = tnode.get("inputs") or {}
                field = "text" if "text" in tins else ("value" if "value" in tins else None)
                if field:
                    out[key] = (ref_id, field)
        for key in ("seed", "noise_seed"):
            if key in ins:
                out["seed"] = (sampler_id, key)
                break
        # 尺寸：优先采样器 latent 指向的节点
        latent = ins.get("latent_image")
        cand = []
        if isinstance(latent, list) and latent:
            cand.append(str(latent[0]))
        cand += [nid for nid, n in nodes.items() if str(n.get("class_type", "")).startswith("Empty")]
        for nid in cand:
            tins = (nodes.get(nid) or {}).get("inputs") or {}
            if "width" in tins and "height" in tins:
                out["width"] = (nid, "width")
                out["height"] = (nid, "height")
                break
    else:
        # 无采样器：退化为「找 CLIPTextEncode」
        encs = [nid for nid, n in nodes.items() if n.get("class_type") == "CLIPTextEncode"]
        if encs:
            out["positive"] = (encs[0], "text")
            if len(encs) > 1:
                out["negative"] = (encs[1], "text")

    for nid, n in nodes.items():
        if n.get("class_type") in ("CheckpointLoaderSimple", "CheckpointLoader"):
            if "ckpt_name" in (n.get("inputs") or {}):
                out["checkpoint"] = (nid, "ckpt_name")
                break
    return out


def patch_workflow(wf: dict, params: dict, cfg: dict, nodes: dict, ref_name: str = "") -> dict:
    wf = json.loads(json.dumps(wf))
    mapping = {
        "positive": params["prompt"],
        "negative": params["negative"],
        "seed": params["seed"],
        "width": params["width"],
        "height": params["height"],
    }
    for key, val in mapping.items():
        tgt = nodes.get(key)
        if not tgt:
            continue
        nid, field = tgt
        node = wf.get(nid) or wf.get(str(nid))
        if node and "inputs" in node:
            node["inputs"][field] = val
    if cfg["steps"] is not None and nodes.get("sampler"):
        sid = nodes["sampler"]
        wf[sid]["inputs"]["steps"] = int(cfg["steps"])
    if cfg["cfg"] is not None and nodes.get("sampler"):
        sid = nodes["sampler"]
        wf[sid]["inputs"]["cfg"] = float(cfg["cfg"])
    ckpt = (cfg.get("comfyui") or {}).get("checkpoint")
    if ckpt and nodes.get("checkpoint"):
        nid, field = nodes["checkpoint"]
        wf[nid]["inputs"][field] = ckpt
    if ref_name:
        for nid, node in wf.items():
            if node.get("class_type") == "LoadImage" and "image" in (node.get("inputs") or {}):
                node["inputs"]["image"] = ref_name
                break
    return wf


# ------------------------------------------------------------------ ComfyUI
class ComfyUI:
    name = "comfyui"

    def __init__(self, cfg: dict, proj: Path):
        c = cfg["comfyui"]
        self.host = str(c["host"]).rstrip("/")
        self.timeout = float(c["timeout"])
        self.workflow_path = resolve_path(proj, str(c["workflow"]))
        self.cfg = cfg
        self.client_id = uuid.uuid4().hex
        self._wf = None
        self._nodes = None

    def probe(self) -> tuple[bool, str]:
        try:
            st = http_json(f"{self.host}/system_stats", timeout=8, no_proxy=True)
            dev = (st.get("devices") or [{}])[0]
            v = st.get("system", {}).get("comfyui_version", "?")
            return True, f"可达 · ComfyUI {v} · {dev.get('name', 'unknown')}"
        except Exception as e:  # noqa: BLE001
            return False, f"不可达（{self.host}）：{e}"

    def workflow(self) -> tuple[dict, dict]:
        if self._wf is None:
            if not self.workflow_path.exists():
                raise RuntimeError(f"工作流不存在：{self.workflow_path}")
            self._wf = json.loads(self.workflow_path.read_text(encoding="utf-8"))
            manual = (self.cfg["comfyui"].get("node_map") or {})
            detected = detect_nodes(self._wf)
            if manual:
                for k, v in manual.items():
                    if isinstance(v, dict):
                        detected[k] = (str(v.get("nodeId") or v.get("node")), v.get("fieldName") or v.get("field"))
                    elif isinstance(v, list) and len(v) == 2:
                        detected[k] = (str(v[0]), v[1])
            self._nodes = detected
        return self._wf, self._nodes

    def upload(self, path: Path) -> str:
        r = http_multipart(
            f"{self.host}/upload/image",
            {"overwrite": "true", "type": "input"},
            "image",
            path,
            timeout=60,
            no_proxy=True,
        )
        sub = r.get("subfolder") or ""
        return f"{sub}/{r['name']}" if sub else r["name"]

    def generate(self, params: dict, out: Path) -> dict:
        wf, nodes = self.workflow()
        if not nodes.get("positive"):
            raise RuntimeError(
                "工作流里没找到提示词节点。请在 .gamedev/artgen.yaml 的 comfyui.node_map 里显式指定，"
                "例如 {prompt: {nodeId: '6', fieldName: 'text'}}"
            )
        ref_name = ""
        if params.get("ref"):
            rp = resolve_path(out.parent.parent.parent, params["ref"])
            if rp.exists():
                ref_name = self.upload(rp)
        patched = patch_workflow(wf, params, self.cfg, nodes, ref_name)

        pid = retry(
            lambda: http_json(
                f"{self.host}/prompt",
                {"prompt": patched, "client_id": self.client_id},
                timeout=60,
                no_proxy=True,
            ).get("prompt_id"),
            attempts=2,
            label="ComfyUI 提交",
        )
        if not pid:
            raise RuntimeError("ComfyUI 未返回 prompt_id")

        deadline = time.time() + self.timeout
        images = []
        while time.time() < deadline:
            time.sleep(1.2)
            hist = http_json(f"{self.host}/history/{pid}", timeout=30, no_proxy=True)
            entry = hist.get(pid)
            if not entry:
                continue
            status = (entry.get("status") or {})
            if status.get("status_str") == "error":
                raise RuntimeError(f"ComfyUI 执行报错：{json.dumps(status)[:400]}")
            for _nid, out_node in (entry.get("outputs") or {}).items():
                for im in out_node.get("images") or []:
                    if im.get("type", "output") == "output":
                        images.append(im)
            if images:
                break
        if not images:
            raise RuntimeError(f"ComfyUI 超时（{self.timeout:.0f}s）未产出图片")

        im0 = images[0]
        q = urllib.parse.urlencode(
            {
                "filename": im0.get("filename", ""),
                "subfolder": im0.get("subfolder", ""),
                "type": im0.get("type", "output"),
            }
        )
        out.write_bytes(http_get_bytes(f"{self.host}/view?{q}", timeout=120, no_proxy=True))
        return {"raw": im0.get("filename"), "extra": f"workflow={self.workflow_path.name}"}


# ------------------------------------------------------------------ RunningHub
class RunningHub:
    name = "runninghub"

    def __init__(self, cfg: dict, proj: Path):
        c = cfg["runninghub"]
        self.base = str(c["base_url"]).rstrip("/")
        self.key = str(c["api_key"] or "")
        self.wid = str(c["workflow_id"] or "")
        self.timeout = float(c["timeout"])
        self.poll = float(c["poll"])
        self.cfg = cfg
        self.proj = proj
        self._map = None

    def probe(self) -> tuple[bool, str]:
        if not self.key:
            return False, "缺少 apiKey（设 RUNNINGHUB_API_KEY 或 .gamedev/artgen.yaml 的 runninghub.api_key）"
        if not self.wid:
            return False, "缺少 workflowId（在 RunningHub 工作流页面取数字 ID）"
        try:
            r = http_json(
                f"{self.base}/task/openapi/outputs",
                {"taskId": "0", "apiKey": self.key},
                timeout=15,
            )
            msg = str(r.get("msg", ""))
            if r.get("code") == 0 or "TASK" in msg.upper() or "NOT" in msg.upper():
                return True, f"凭证可用 · {self.base} · workflow {self.wid}"
            return True, f"已连通（返回 {r.get('code')}: {msg[:80]}）—— 真实可用性以首次出图为准"
        except Exception as e:  # noqa: BLE001
            return False, f"不可达（{self.base}）：{e}"

    def fetch_workflow(self) -> dict:
        return http_json(
            f"{self.base}/api/openapi/getJsonApiFormat",
            {"apiKey": self.key, "workflowId": self.wid},
            timeout=60,
        )

    def node_map(self) -> dict:
        if self._map is not None:
            return self._map
        manual = dict(self.cfg["runninghub"].get("node_map") or {})
        wf_json = self.cfg["runninghub"].get("workflow_json") or ""
        if not manual:
            src = None
            if wf_json:
                p = resolve_path(self.proj, str(wf_json))
                if p.exists():
                    src = json.loads(p.read_text(encoding="utf-8"))
            if src is None:
                try:
                    src = self.fetch_workflow()
                    src = src.get("data") or src
                except Exception as e:  # noqa: BLE001
                    raise RuntimeError(
                        "无法自动拉取 RunningHub 工作流结构（"
                        f"{e}）。请把 API 格式工作流导出为 docs/02-art/rh-workflow.json 并配置 "
                        "runninghub.workflow_json，或直接在 node_map 里写死节点"
                    )
            detected = detect_nodes(src)
            for key in ("positive", "negative", "seed", "width", "height"):
                tgt = detected.get(key)
                if tgt:
                    manual.setdefault(key, {"nodeId": tgt[0], "fieldName": tgt[1]})
            if "prompt" not in manual and "positive" in manual:
                manual["prompt"] = manual["positive"]
        self._map = manual
        return manual

    def generate(self, params: dict, out: Path) -> dict:
        nm = self.node_map()
        if "prompt" not in nm:
            raise RuntimeError("RunningHub node_map 缺少 prompt 节点映射")
        vals = {
            "prompt": params["prompt"],
            "negative": params["negative"],
            "seed": params["seed"],
            "width": params["width"],
            "height": params["height"],
        }
        node_info = []
        for key, val in vals.items():
            spec = nm.get(key)
            if not spec:
                continue
            node_info.append(
                {"nodeId": str(spec.get("nodeId")), "fieldName": spec.get("fieldName"), "fieldValue": val}
            )
        payload = {"workflowId": self.wid, "apiKey": self.key, "nodeInfoList": node_info}
        inst = self.cfg["runninghub"].get("instance_type")
        if inst:
            payload["instanceType"] = inst

        created = retry(
            lambda: http_json(f"{self.base}/task/openapi/create", payload, timeout=60),
            attempts=3,
            label="RunningHub 提交",
        )
        if created.get("code") != 0:
            raise RuntimeError(f"RunningHub 拒绝任务：{created.get('code')} {created.get('msg')}")
        task_id = (created.get("data") or {}).get("taskId")
        if not task_id:
            raise RuntimeError(f"RunningHub 未返回 taskId：{created}")

        deadline = time.time() + self.timeout
        last = ""
        while time.time() < deadline:
            time.sleep(self.poll)
            r = http_json(
                f"{self.base}/task/openapi/outputs",
                {"taskId": task_id, "apiKey": self.key},
                timeout=30,
            )
            msg = str(r.get("msg", ""))
            last = msg
            if r.get("code") == 0 and isinstance(r.get("data"), list) and r["data"]:
                urls = [d.get("fileUrl") for d in r["data"] if d.get("fileUrl")]
                if not urls:
                    raise RuntimeError("RunningHub 返回成功但没有 fileUrl")
                out.write_bytes(http_get_bytes(urls[0], timeout=180))
                return {"task_id": task_id, "raw": urls[0], "extra": f"workflow={self.wid}"}
            if "FAILED" in msg.upper() or "ERROR" in msg.upper():
                raise RuntimeError(f"RunningHub 任务失败：{msg}")
        raise RuntimeError(f"RunningHub 超时（{self.timeout:.0f}s，最后状态 {last or 'QUEUED'}）")


# ------------------------------------------------------------------ 占位素材
FONT_CANDIDATES = [
    "C:/Windows/Fonts/msyh.ttc",
    "C:/Windows/Fonts/segoeui.ttf",
    "/System/Library/Fonts/PingFang.ttc",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
]


def load_font(size: int):
    for p in FONT_CANDIDATES:
        if Path(p).exists():
            try:
                return ImageFont.truetype(p, size)
            except Exception:  # noqa: BLE001
                continue
    try:
        return ImageFont.load_default(size)
    except TypeError:
        return ImageFont.load_default()


def pick_colors(proj: Path) -> tuple[list[str], str]:
    pj = proj / "docs" / "02-art" / "palette.json"
    primary = ["#4A90D9", "#F2A65A", "#5CB85C", "#D9534F", "#8E7CC3"]
    bg = "#FFF8EE"
    if pj.exists():
        try:
            d = json.loads(pj.read_text(encoding="utf-8"))
            if d.get("primary"):
                primary = d["primary"]
            if d.get("background"):
                bg = d["background"]
        except Exception:  # noqa: BLE001
            pass
    return primary, bg


def make_placeholder(name: str, w: int, h: int, primary: list[str], bg: str) -> Image.Image:
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    rnd = random.Random(name)
    fill = rnd.choice(primary)
    dark = "#2E2E38"
    r = int(min(w, h) * 0.16)
    inset = max(4, int(min(w, h) * 0.06))
    d.rounded_rectangle([inset, inset, w - inset, h - inset], radius=r, fill=fill, outline=dark, width=max(3, w // 160))
    label = name.replace("_", " ")
    fs = max(16, int(min(w, h) * 0.11))
    font = load_font(fs)
    # 简单换行：按宽度折
    words, lines, cur = label.split(" "), [], ""
    for word in words:
        trial = f"{cur} {word}".strip()
        if d.textlength(trial, font=font) > w - inset * 3 and cur:
            lines.append(cur)
            cur = word
        else:
            cur = trial
    if cur:
        lines.append(cur)
    total = len(lines) * (fs + 6)
    y = (h - total) / 2
    for line in lines:
        tw = d.textlength(line, font=font)
        d.text(((w - tw) / 2, y), line, font=font, fill=dark)
        y += fs + 6
    # 左下角标记，便于识别是占位素材
    tag = load_font(max(12, fs // 3))
    d.text((inset * 2, h - inset * 2 - fs // 3), "placeholder", font=tag, fill=(46, 46, 56, 160))
    return im


# ------------------------------------------------------------------ 后处理
def hex_to_rgb(s: str) -> tuple[int, int, int]:
    s = s.strip().lstrip("#")
    if len(s) == 3:
        s = "".join(c * 2 for c in s)
    return tuple(int(s[i : i + 2], 16) for i in (0, 2, 4))  # type: ignore


def remove_bg_color(im: Image.Image, color: str, tol: int = 40) -> Image.Image:
    """把指定背景色抠成透明（从四边泛洪，避免误伤主体同色区域）。"""
    im = im.convert("RGBA")
    w, h = im.size
    px = im.load()
    target = hex_to_rgb(color)

    def close(c) -> bool:
        return all(abs(c[i] - target[i]) <= tol for i in range(3))

    stack = [(x, 0) for x in range(w)] + [(x, h - 1) for x in range(w)]
    stack += [(0, y) for y in range(h)] + [(w - 1, y) for y in range(h)]
    seen = bytearray(w * h)
    while stack:
        x, y = stack.pop()
        if x < 0 or y < 0 or x >= w or y >= h:
            continue
        idx = y * w + x
        if seen[idx]:
            continue
        seen[idx] = 1
        r, g, b, a = px[x, y]
        if not close((r, g, b)):
            continue
        px[x, y] = (r, g, b, 0)
        stack.extend([(x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)])
    return im


def trim_alpha(im: Image.Image, pad: int = 0) -> Image.Image:
    im = im.convert("RGBA")
    bbox = im.getchannel("A").getbbox()
    if not bbox:
        return im
    x0, y0, x1, y1 = bbox
    x0, y0 = max(0, x0 - pad), max(0, y0 - pad)
    x1, y1 = min(im.width, x1 + pad), min(im.height, y1 + pad)
    return im.crop((x0, y0, x1, y1))


# ------------------------------------------------------------------ 主流程
def pick_provider(cfg: dict, proj: Path, forced: str) -> tuple[str, str]:
    if forced and forced != "auto":
        return forced, "命令行指定"
    if cfg["provider"] and cfg["provider"] != "auto":
        return cfg["provider"], "配置文件指定"
    comfy = ComfyUI(cfg, proj)
    good, msg = comfy.probe()
    if good:
        return "comfyui", msg
    rh = RunningHub(cfg, proj)
    good2, msg2 = rh.probe()
    if good2:
        return "runninghub", msg2
    return "placeholder", f"ComfyUI 与 RunningHub 均不可用（{msg}；{msg2}）"


def main() -> int:
    ap = argparse.ArgumentParser(description="资产生成：ComfyUI / RunningHub / 占位")
    ap.add_argument("--project", default=None)
    ap.add_argument("--provider", default="", choices=["", "auto", "comfyui", "runninghub", "placeholder"])
    ap.add_argument("--only", default="", help="只处理名字包含这些子串的素材，逗号分隔")
    ap.add_argument("--max", type=int, default=0, help="最多处理几个（成本控制）")
    ap.add_argument("--force", action="store_true", help="忽略台账，全部重出")
    ap.add_argument("--dry-run", action="store_true", help="只打印计划，不发请求")
    ap.add_argument("--probe", action="store_true", help="只做连通性体检")
    ap.add_argument(
        "--dump-rh-workflow",
        default="",
        help="拉取 RunningHub 工作流的 API 格式 JSON 并保存到指定路径（同时打印探测到的节点映射）",
    )
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("--size", default="", help="覆盖尺寸，如 1024x1024")
    ap.add_argument("--no-fallback", action="store_true", help="失败时不用占位素材兜底")
    ap.add_argument("--no-update-state", action="store_true", help="不改写 state.yaml")
    args = ap.parse_args()

    proj = project_dir(args.project)
    cfg = load_config(proj)
    if args.provider:
        cfg["provider"] = args.provider
    if args.seed is not None:
        cfg["seed"] = args.seed
    if args.size:
        try:
            w, h = args.size.lower().split("x")
            cfg["size"] = {"width": int(w), "height": int(h)}
        except Exception:
            print(f"ERROR: --size 格式应为 WxH（收到 {args.size}）", file=sys.stderr)
            return 1
    if args.no_fallback:
        cfg["fallback_placeholder"] = False

    if args.probe:
        print("=" * 64)
        for label, cli in (("ComfyUI", ComfyUI(cfg, proj)), ("RunningHub", RunningHub(cfg, proj))):
            good, msg = cli.probe()
            print(f"[{'PASS' if good else 'FAIL'}] {label}: {msg}")
        print("=" * 64)
        print("说明：auto 模式按 ComfyUI → RunningHub → 占位 的顺序降级。")
        return 0

    if args.dump_rh_workflow:
        rh = RunningHub(cfg, proj)
        if not rh.key or not rh.wid:
            print("ERROR: 需要 RUNNINGHUB_API_KEY 与 runninghub.workflow_id", file=sys.stderr)
            return 1
        data = rh.fetch_workflow()
        wf = data.get("data") or data
        if isinstance(wf, dict) and isinstance(wf.get("prompt"), dict):
            wf = wf["prompt"]
        out = resolve_path(proj, args.dump_rh_workflow)
        dump_json(out, wf)
        nodes = detect_nodes(wf)
        print(f"已保存工作流 → {out}")
        print("探测到的节点映射（可直接粘进 .gamedev/artgen.yaml 的 runninghub.node_map）：")
        print("  node_map:")
        for key in ("positive", "negative", "seed", "width", "height"):
            tgt = nodes.get(key)
            if tgt:
                print(f"    {key}: {{ nodeId: '{tgt[0]}', fieldName: '{tgt[1]}' }}")
        if nodes.get("positive"):
            print("    prompt: {{ nodeId: '{}', fieldName: '{}' }}".format(*nodes["positive"]))
        return 0

    provider, why = pick_provider(cfg, proj, args.provider)
    only = [s.strip() for s in args.only.split(",") if s.strip()]
    items = collect_assets(proj, only, args.max or None)

    raw_dir = proj / "assets" / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = raw_dir / "manifest.json"
    manifest = {}
    if manifest_path.exists():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            manifest = {}
    entries = manifest.setdefault("assets", {})

    print("=" * 64)
    print(f"provider: {provider}  （{why}）")
    print(f"素材数: {len(items)}   输出: {raw_dir}")
    print("=" * 64)

    if args.dry_run:
        for it in items:
            p = asset_params(cfg, it)
            print(f"- {it['name']:<22} {p['width']}x{p['height']} seed={p['seed']} provider={p['provider']}")
            print(f"  {p['prompt'][:110]}")
        print("\n（--dry-run：未发送任何请求）")
        return 0

    primary, bg = pick_colors(proj)
    client = None
    if provider == "comfyui":
        client = ComfyUI(cfg, proj)
    elif provider == "runninghub":
        client = RunningHub(cfg, proj)

    results, degraded, failed = [], [], []
    t0 = time.time()
    for idx, it in enumerate(items, 1):
        p = asset_params(cfg, it)
        out = raw_dir / f"{it['name']}.png"
        sig = signature(p, provider, str(cfg["comfyui"].get("workflow", "")) + str(cfg["runninghub"].get("workflow_id", "")))
        prev = entries.get(it["name"]) or {}
        if not args.force and out.exists() and prev.get("signature") == sig:
            print(f"[{idx}/{len(items)}] 跳过（未变化）：{it['name']}")
            results.append({"asset": it["name"], "status": "skipped", "file": out.name})
            continue

        print(f"[{idx}/{len(items)}] 生成 {it['name']}  {p['width']}x{p['height']}  seed={p['seed']}")
        rec = {
            "asset": it["name"],
            "provider": provider,
            "prompt": p["prompt"],
            "negative": p["negative"],
            "seed": p["seed"],
            "width": p["width"],
            "height": p["height"],
            "signature": sig,
            "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        }
        try:
            if client is not None:
                info = client.generate(p, out)
                rec.update(info)
            else:
                im = make_placeholder(it["name"], p["width"], p["height"], primary, bg)
                im.save(out, "PNG")
                rec["provider"] = "placeholder"
            # 后处理
            if cfg.get("remove_bg") or cfg.get("trim"):
                im2 = Image.open(out)
                if cfg.get("remove_bg"):
                    im2 = remove_bg_color(im2, cfg["remove_bg"])
                if cfg.get("trim"):
                    im2 = trim_alpha(im2)
                im2.save(out, "PNG")
            rec["bytes"] = out.stat().st_size
            rec["status"] = "ok"
            entries[it["name"]] = rec
            results.append({"asset": it["name"], "status": "ok", "file": out.name, "bytes": rec["bytes"]})
        except Exception as e:  # noqa: BLE001
            warn(f"{it['name']} 生成失败：{e}")
            if cfg["fallback_placeholder"]:
                im = make_placeholder(it["name"], p["width"], p["height"], primary, bg)
                im.save(out, "PNG")
                rec.update({"provider": "placeholder", "status": "degraded", "error": str(e)[:400]})
                entries[it["name"]] = rec
                degraded.append({"asset": it["name"], "error": str(e)[:300]})
                results.append({"asset": it["name"], "status": "degraded", "file": out.name})
            else:
                failed.append({"asset": it["name"], "error": str(e)[:300]})
                results.append({"asset": it["name"], "status": "failed"})

    manifest.update(
        {
            "version": 1,
            "provider": provider,
            "updated": datetime.now().astimezone().isoformat(timespec="seconds"),
            "assets": entries,
        }
    )
    dump_json(manifest_path, manifest)

    report = {
        "provider": provider,
        "reason": why,
        "elapsed_s": round(time.time() - t0, 1),
        "total": len(items),
        "ok": sum(1 for r in results if r["status"] == "ok"),
        "skipped": sum(1 for r in results if r["status"] == "skipped"),
        "degraded": degraded,
        "failed": failed,
        "results": results,
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
    }
    dump_json(raw_dir / ".artgen-report.json", report)

    total_bytes = sum(f.stat().st_size for f in raw_dir.glob("*.png"))
    print("-" * 64)
    print(f"完成：ok {report['ok']} / 跳过 {report['skipped']} / 降级 {len(degraded)} / 失败 {len(failed)}")
    print(f"原始素材总体积 {human_size(total_bytes)}（切图后才会进包）  耗时 {report['elapsed_s']}s")
    if degraded:
        print("降级项（已用占位素材兜底，交付报告必须列出）：")
        for d in degraded:
            print(f"  - {d['asset']}: {d['error'][:120]}")
    if failed:
        print("失败项（未产出，必须先修好再进 06-sprite-tools）：")
        for d in failed:
            print(f"  - {d['asset']}: {d['error'][:120]}")

    if not args.no_update_state:
        try:
            st = load_state(proj)
            node = st.setdefault("stages", {}).setdefault("art_forge", {})
            if failed:
                node.update({"status": "failed", "note": f"{len(failed)} 项未产出"})
            elif degraded:
                node.update({"status": "degraded", "note": f"provider={provider}，{len(degraded)} 项用占位素材兜底"})
            else:
                node.update({"status": "done", "note": f"provider={provider}，{report['ok']} 项"})
            save_state(proj, st)
            ok(f"state.yaml 已更新：art_forge = {node['status']}")
        except SystemExit:
            warn("未能更新 state.yaml（缺少 PyYAML？）")

    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
