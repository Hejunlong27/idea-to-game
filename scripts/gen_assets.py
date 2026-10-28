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
    "frame, border, cropped, extra limbs, deformed, photorealistic, 3d render, "
    "cast shadow, drop shadow, ground shadow"
)

DEFAULTS = {
    "provider": "auto",
    "size": {"width": 1024, "height": 1024},
    "seed": 20261016,
    "steps": None,
    "cfg": None,
    "negative": DEFAULT_NEGATIVE,
    "fallback_placeholder": True,
    "remove_bg": "",          # "auto" / #RRGGBB；SDXL 不出 alpha，出图后泛洪抠色
    "remove_bg_tolerance": 60,
    "trim": False,            # 出图后按 alpha 裁边
    "comfyui": {
        "host": "http://127.0.0.1:8188",
        "workflow": str(DEFAULT_WORKFLOW),
        "workflow_i2i": "",       # 素材 sidecar 里给了 ref 时自动改用它
        "checkpoint": "",
        "unet_name": "",
        "clip_name": "",
        "vae_name": "",
        "size_mode": "auto",      # auto | latent | selector
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
        sheet = None
        kind = str(over.get("kind") or "").lower()
        if kind in ("sheet", "frames"):
            grid = str(over.get("grid") or "3x3").lower()
            try:
                rows, cols = (int(x) for x in grid.split("x"))
            except Exception:
                warn(f"{side.name} 的 grid 格式错误（应为 RxC），按 3x3 处理")
                rows, cols = 3, 3
            items_list = over.get("items") or []
            frames = int(over.get("frames") or (len(items_list) if items_list else rows * cols))
            sheet = {
                "kind": kind,
                "rows": rows,
                "cols": cols,
                "grid": f"{rows}x{cols}",
                "items": [str(x) for x in items_list],
                "frames": frames,
                "pad_to": over.get("pad_to") or 0,
            }
            if kind == "sheet" and len(sheet["items"]) not in (0, rows * cols):
                warn(
                    f"{name}: items 数量 {len(sheet['items'])} 与网格 {grid}（{rows * cols} 格）不一致，"
                    "多余/不足的格子会被忽略"
                )
        items.append({"name": name, "prompt": prompt, "file": f, "override": over, "sheet": sheet})
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
        "trim": bool(o.get("trim", cfg.get("trim"))),
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
# 文本字段优先级：不同工作流的编码节点字段名不一样
#   CLIPTextEncode → text ｜ Qwen TextEncode → prompt/negative_prompt ｜ PrimitiveString → value
TEXT_FIELDS = ("text", "prompt", "value", "string")

# ComfyUI 核心 ResolutionSelector 的固定档位（输出尺寸由 比例 + 百万像素 决定）
RATIO_OPTIONS = [
    (1, 1, "1:1 (Square)"),
    (2, 3, "2:3 (Portrait Photo)"),
    (3, 2, "3:2 (Photo)"),
    (3, 4, "3:4 (Portrait Standard)"),
    (4, 3, "4:3 (Standard)"),
    (9, 16, "9:16 (Portrait Widescreen)"),
    (16, 9, "16:9 (Widescreen)"),
    (21, 9, "21:9 (Ultrawide)"),
]


def _is_link(v) -> bool:
    return isinstance(v, list) and len(v) == 2 and isinstance(v[0], (str, int))


def _str_field(node: dict) -> str | None:
    """返回该节点里「字面量字符串」的字段名；全是链接时返回链接字段名。"""
    ins = node.get("inputs") or {}
    for f in TEXT_FIELDS:
        if f in ins and not _is_link(ins[f]):
            return f
    for f in TEXT_FIELDS:
        if f in ins:
            return f
    return None


def _resolve_text(nodes: dict, ref, prefer: str | None = None) -> tuple[str, str] | None:
    """把「编码节点输出」解析到真正持有字符串的节点字段。

    常见两种结构都要吃：
      A. 采样器 positive → CLIPTextEncode.text（直接是字符串）
      B. 采样器 positive → TextEncodeQwenImage21.prompt → PrimitiveStringMultiline.value（一层链接）
    """
    if not _is_link(ref):
        return None
    nid = str(ref[0])
    node = nodes.get(nid)
    if not node:
        return None
    ins = node.get("inputs") or {}
    field = prefer if (prefer and prefer in ins) else _str_field(node)
    if not field:
        return None
    val = ins.get(field)
    if _is_link(val):
        src = nodes.get(str(val[0])) or {}
        sf = _str_field(src)
        if sf:
            return (str(val[0]), sf)
    return (nid, field)


def _detect_size(nodes: dict, sampler_ins: dict) -> dict:
    """尺寸注入点。返回 {width,height,size_mode[,selector,ratio_field,mp_field]}。"""
    cands = []
    latent = sampler_ins.get("latent_image")
    if _is_link(latent):
        cands.append(str(latent[0]))
    cands += [nid for nid, n in nodes.items() if str(n.get("class_type", "")).startswith("Empty")]
    for nid in cands:
        ins = (nodes.get(nid) or {}).get("inputs") or {}
        if "width" in ins and "height" in ins:
            w, h = ins["width"], ins["height"]
            if isinstance(w, (int, float)) and isinstance(h, (int, float)):
                return {"width": (nid, "width"), "height": (nid, "height"), "size_mode": "latent"}
            # 宽高是链接：找上游的 ResolutionSelector（Qwen 工作流就是这种）
            for ref in (w, h):
                if _is_link(ref):
                    src = nodes.get(str(ref[0])) or {}
                    sins = src.get("inputs") or {}
                    if "aspect_ratio" in sins and "megapixels" in sins:
                        return {
                            "size_mode": "selector",
                            "selector": str(ref[0]),
                            "ratio_field": "aspect_ratio",
                            "mp_field": "megapixels",
                        }
    return {}


def detect_nodes(wf: dict) -> dict:
    """从 API 格式工作流里推断需要注入的节点。

    返回 {positive:(node_id,field), negative, seed, width/height 或 selector,
          unet/clip/vae/checkpoint, sampler}
    探测不到的项为缺失 —— 此时必须在配置里显式给 node_map。
    """
    nodes = {str(k): v for k, v in wf.items() if isinstance(v, dict) and "class_type" in v}
    out: dict = {}

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
        pos_ref, neg_ref = ins.get("positive"), ins.get("negative")

        # 同一节点双输出（Qwen：positive=output0 / negative=output1）
        if _is_link(pos_ref) and _is_link(neg_ref) and str(pos_ref[0]) == str(neg_ref[0]):
            enc = nodes.get(str(pos_ref[0])) or {}
            eins = enc.get("inputs") or {}
            if "prompt" in eins:
                tgt = _resolve_text(nodes, pos_ref, prefer="prompt")
                if tgt:
                    out["positive"] = tgt
                if "negative_prompt" in eins:
                    out["negative"] = (str(pos_ref[0]), "negative_prompt")
        else:
            for key, ref in (("positive", pos_ref), ("negative", neg_ref)):
                tgt = _resolve_text(nodes, ref)
                if tgt:
                    out[key] = tgt

        for key in ("seed", "noise_seed"):
            if key in ins:
                out["seed"] = (sampler_id, key)
                break

        out.update(_detect_size(nodes, ins))
    else:
        encs = [nid for nid, n in nodes.items() if n.get("class_type") == "CLIPTextEncode"]
        if encs:
            out["positive"] = (encs[0], "text")
            if len(encs) > 1:
                out["negative"] = (encs[1], "text")

    # 模型加载节点（可被配置覆盖）
    for nid, n in nodes.items():
        ct = str(n.get("class_type", ""))
        ins = n.get("inputs") or {}
        if ct in ("CheckpointLoaderSimple", "CheckpointLoader") and "ckpt_name" in ins:
            out.setdefault("checkpoint", (nid, "ckpt_name"))
        elif ct == "UNETLoader" and "unet_name" in ins:
            out.setdefault("unet", (nid, "unet_name"))
        elif ct == "CLIPLoader" and "clip_name" in ins:
            out.setdefault("clip", (nid, "clip_name"))
        elif ct == "VAELoader" and "vae_name" in ins:
            out.setdefault("vae", (nid, "vae_name"))
    return out


def _ratio_string(w: int, h: int) -> str:
    """把任意宽高映射到 ResolutionSelector 最接近的档位。"""
    import math

    target = w / max(1, h)
    best = min(RATIO_OPTIONS, key=lambda o: abs(math.log(target / (o[0] / o[1]))))
    return best[2]


def patch_workflow(wf: dict, params: dict, cfg: dict, nodes: dict, ref_name: str = "") -> dict:
    wf = json.loads(json.dumps(wf))
    c = cfg.get("comfyui") or {}
    mode = str(c.get("size_mode") or "auto").lower()

    for key, val in (("positive", params["prompt"]), ("negative", params["negative"]), ("seed", params["seed"])):
        tgt = nodes.get(key)
        if not tgt:
            continue
        node = wf.get(tgt[0])
        if node and "inputs" in node:
            node["inputs"][tgt[1]] = val

    # 尺寸
    use_selector = mode in ("auto", "selector") and nodes.get("size_mode") == "selector"
    if mode == "latent":
        use_selector = False
    if use_selector:
        sid = nodes["selector"]
        wf[sid]["inputs"][nodes["ratio_field"]] = _ratio_string(params["width"], params["height"])
        mp = max(0.1, min(16.0, round(params["width"] * params["height"] / 1_000_000, 1)))
        wf[sid]["inputs"][nodes["mp_field"]] = mp
    elif nodes.get("width"):
        for key in ("width", "height"):
            tgt = nodes.get(key)
            if tgt and wf.get(tgt[0]):
                wf[tgt[0]]["inputs"][tgt[1]] = params[key]

    # 采样参数（SamplerCustom 用 sigmas 控制步数，没有 steps 字段，跳过即可）
    sid = nodes.get("sampler")
    if sid and wf.get(sid):
        sins = wf[sid]["inputs"]
        if cfg.get("steps") is not None and "steps" in sins:
            sins["steps"] = int(cfg["steps"])
        if cfg.get("cfg") is not None and "cfg" in sins:
            sins["cfg"] = float(cfg["cfg"])

    # 模型覆盖
    for key, conf_key in (("checkpoint", "checkpoint"), ("unet", "unet_name"), ("clip", "clip_name"), ("vae", "vae_name")):
        val = c.get(conf_key)
        tgt = nodes.get(key)
        if val and tgt and wf.get(tgt[0]):
            wf[tgt[0]]["inputs"][tgt[1]] = val

    # 参考图：把所有 LoadImage 都指向同一张（Qwen i2i 有两个槽位，
    # 留空会引用工作流里原本的文件名，本机没有那个文件就直接校验失败）
    if ref_name:
        hit = False
        for _nid, node in wf.items():
            if node.get("class_type") == "LoadImage" and "image" in (node.get("inputs") or {}):
                node["inputs"]["image"] = ref_name
                hit = True
        if not hit:
            warn("工作流里没有 LoadImage 节点，ref 参数被忽略")
    return wf


# ------------------------------------------------------------------ ComfyUI
class ComfyUI:
    name = "comfyui"

    def __init__(self, cfg: dict, proj: Path):
        c = cfg["comfyui"]
        self.host = str(c["host"]).rstrip("/")
        self.timeout = float(c["timeout"])
        self.proj = proj
        self.workflow_path = resolve_path(proj, str(c["workflow"]))
        wf_i2i = str(c.get("workflow_i2i") or "")
        self.workflow_i2i_path = resolve_path(proj, wf_i2i) if wf_i2i else None
        self.cfg = cfg
        self.client_id = uuid.uuid4().hex
        self._cache: dict[str, tuple[dict, dict]] = {}

    def probe(self, full: bool = True) -> tuple[bool, str]:
        """full=True 时额外核对工作流引用的模型是否本机存在。

        ⚠️ `pick_provider` 只能用 full=False：模型核对要打 4~8 次 /object_info，
        而 ComfyUI 在跑重任务（视频生成）时这些请求会**长时间挂住**且 urllib 的
        timeout 管不住（服务端持续缓慢吐字节，读超时不断被重置）。
        实测因此卡死过 12 分钟，一次都没提交上去。
        """
        try:
            st = http_json(f"{self.host}/system_stats", timeout=5, no_proxy=True)
        except Exception as e:  # noqa: BLE001
            return False, f"不可达（{self.host}）：{e}"
        dev = (st.get("devices") or [{}])[0]
        v = st.get("system", {}).get("comfyui_version", "?")
        base = f"可达 · ComfyUI {v} · {dev.get('name', 'unknown')}"
        if not full:
            return True, base

        # 校验工作流引用的模型本机是否存在 —— 共享工作流最常见的失败原因
        missing = self.check_models()
        if not missing:
            return True, base + " · 模型齐备"
        detail = "；".join(missing)
        return True, (
            base
            + "\n          ⚠ 工作流引用的模型本机缺失：" + detail
            + "\n          可在 .gamedev/artgen.yaml 用 comfyui.unet_name / clip_name / vae_name 覆盖"
        )

    def _loader_options(self, node_type: str, field: str) -> list[str]:
        cache = self.__dict__.setdefault("_opt_cache", {})
        if node_type in cache:
            return cache[node_type]
        try:
            info = http_json(f"{self.host}/object_info/{node_type}", timeout=8, no_proxy=True)
            opts = info[node_type]["input"]["required"][field][0]
            out = list(opts) if isinstance(opts, list) else []
            cache[node_type] = out
            return out
        except Exception:  # noqa: BLE001
            return []

    def check_models(self) -> list[str]:
        """返回缺失的模型项（空列表=齐备）。"""
        missing: list[str] = []
        targets = [
            ("UNETLoader", "unet_name", "unet_name"),
            ("CLIPLoader", "clip_name", "clip_name"),
            ("VAELoader", "vae_name", "vae_name"),
            ("CheckpointLoaderSimple", "ckpt_name", "checkpoint"),
        ]
        checked: set[str] = set()
        for path in (self.workflow_path, self.workflow_i2i_path):
            if not path or not path.exists():
                continue
            try:
                wf = json.loads(path.read_text(encoding="utf-8"))
            except Exception:  # noqa: BLE001
                continue
            nodes = detect_nodes(wf)
            for node_type, field, key in targets:
                tgt = nodes.get(key)
                if not tgt:
                    continue
                want = (wf.get(tgt[0]) or {}).get("inputs", {}).get(tgt[1])
                override = (self.cfg["comfyui"].get(field) or "").strip()
                if override:
                    want = override
                if not isinstance(want, str) or want in checked:
                    continue
                checked.add(want)
                opts = self._loader_options(node_type, field)
                if opts and want not in opts:
                    alt = "、".join(opts[:3])
                    missing.append(f"{want}（本机可用：{alt}…）")
        return missing

    def _load(self, use_i2i: bool) -> tuple[dict, dict, Path]:
        path = self.workflow_path
        if use_i2i and self.workflow_i2i_path and self.workflow_i2i_path.exists():
            path = self.workflow_i2i_path
        key = str(path)
        if key not in self._cache:
            if not path.exists():
                raise RuntimeError(f"工作流不存在：{path}")
            wf = json.loads(path.read_text(encoding="utf-8"))
            detected = detect_nodes(wf)
            manual = self.cfg["comfyui"].get("node_map") or {}
            for k, v in manual.items():
                if isinstance(v, dict):
                    detected[k] = (str(v.get("nodeId") or v.get("node")), v.get("fieldName") or v.get("field"))
                elif isinstance(v, list) and len(v) == 2:
                    detected[k] = (str(v[0]), v[1])
            self._cache[key] = (wf, detected)
        wf, nodes = self._cache[key]
        return wf, nodes, path

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
        ref_path = None
        if params.get("ref"):
            rp = resolve_path(self.proj, str(params["ref"]))
            if rp.exists():
                ref_path = rp
            else:
                warn(f"参考图不存在，按文生图处理：{rp}")
        wf, nodes, wf_path = self._load(use_i2i=bool(ref_path))
        if not nodes.get("positive"):
            raise RuntimeError(
                f"工作流里没找到提示词节点（{wf_path.name}）。请在 .gamedev/artgen.yaml 的 "
                "comfyui.node_map 里显式指定，例如 {prompt: {nodeId: '488', fieldName: 'value'}}"
            )
        ref_name = self.upload(ref_path) if ref_path else ""
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
        return {"raw": im0.get("filename"), "extra": f"workflow={wf_path.name}"}


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


def cell_names(item: dict) -> list[str]:
    """网格图里每一格的素材名。

    kind=sheet：用 sidecar 的 items（顺序按行优先）；缺省则 <name>_0..N
    kind=frames：<name>_0..<frames-1>，便于 Phaser 建动画
    """
    s = item["sheet"]
    if s.get("kind") == "sheet" and s.get("items"):
        return s["items"][: s["rows"] * s["cols"]]
    n = s.get("frames") or s["rows"] * s["cols"]
    return [f"{item['name']}_{i}" for i in range(n)]


def split_grid(im: Image.Image, rows: int, cols: int) -> list[Image.Image]:
    w, h = im.size
    cw, ch = w // cols, h // rows
    out = []
    for r in range(rows):
        for c in range(cols):
            out.append(im.crop((c * cw, r * ch, (c + 1) * cw, (r + 1) * ch)))
    return out


def prep_cell(cell: Image.Image, cfg: dict) -> Image.Image:
    """单格预处理：抠背景 → 裁边。不做画布统一（那要看整组）。"""
    im = cell.convert("RGBA")
    if cfg.get("remove_bg"):
        im = remove_bg_color(im, cfg["remove_bg"], int(cfg.get("remove_bg_tolerance") or 60))
    return trim_alpha(im)


def pad_square(im: Image.Image, side: int) -> Image.Image:
    canvas = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    canvas.paste(im, ((side - im.width) // 2, (side - im.height) // 2))
    return canvas


def finish_cells(cells: list[Image.Image], cfg: dict, pad: int = 0) -> list[Image.Image]:
    """整组统一画布。

    ⚠️ 必须按**整组最大边**统一，不能每格各算各的 ——
    否则动画帧尺寸不一致，播放时会跳帧抖动（实测第一版就是这个毛病：
    四帧分别是 365/376/367/377px）。pad 显式指定时以它为准。
    """
    prepped = [prep_cell(c, cfg) for c in cells]
    if pad > 0:
        side = pad
    else:
        side = max(max(im.width, im.height) for im in prepped)
    return [pad_square(im, side) for im in prepped]


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


def detect_border_color(im: Image.Image) -> tuple[int, int, int]:
    """取四边像素的逐通道中位数，作为实际背景色。

    为什么需要它：模型**不会**精确画出提示词里的 #FF00FF ——
    实测 SD1.5 把 "pure magenta" 画成 (248,15,187)，与目标色差 68，
    按固定色值抠图会整张失败。所以默认从图里取样。
    """
    im = im.convert("RGBA")
    w, h = im.size
    px = im.load()
    samples = []
    step = max(1, w // 64)
    for x in range(0, w, step):
        samples.append(px[x, 0][:3])
        samples.append(px[x, h - 1][:3])
    for y in range(0, h, step):
        samples.append(px[0, y][:3])
        samples.append(px[w - 1, y][:3])
    if not samples:
        return (255, 255, 255)
    chans = list(zip(*samples))
    return tuple(sorted(c)[len(c) // 2] for c in chans)  # type: ignore


def remove_bg_color(im: Image.Image, color: "str | tuple[int, int, int] | None", tol: int = 40) -> Image.Image:
    """把背景色抠成透明（从四边泛洪，避免误伤主体同色区域）。

    color 传 None 或 "auto" 时自动从图像四边取样。
    """
    im = im.convert("RGBA")
    w, h = im.size
    px = im.load()
    if color is None or (isinstance(color, str) and color.strip().lower() in ("auto", "true", "")):
        target = detect_border_color(im)
    elif isinstance(color, str):
        target = hex_to_rgb(color)
    else:
        target = tuple(color)  # type: ignore

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
    good, msg = comfy.probe(full=False)   # 只探可达性，不做模型核对（会挂住）
    if good:
        return "comfyui", msg
    rh = RunningHub(cfg, proj)
    good2, msg2 = rh.probe()
    if good2:
        return "runninghub", msg2
    return "placeholder", f"ComfyUI 与 RunningHub 均不可用（{msg}；{msg2}）"


def generate_sheet(
    client, cfg: dict, item: dict, params: dict, sig: str, raw_dir: Path,
    entries: dict, primary: list[str], bg: str, provider: str,
) -> dict:
    """一张网格图 → 切成多个素材（kind=sheet）或一套动画帧（kind=frames）。

    为什么要这么做：
      · 风格一致性 —— 同一张图里的元素天然同光源、同笔触、同色板
      · 省调用 —— 9 个素材 1 次推理，而不是 9 次
      · 帧对齐 —— 动画帧在同一张图里，主体大小与基线更稳

    代价：格数越多越容易「多画/少画/串格」，所以每格都做 trim + 统一画布，
    并保留整张网格图（`_sheet_<name>.png`）便于肉眼核对。
    """
    spec = item["sheet"]
    names = cell_names(item)
    rows, cols = spec["rows"], spec["cols"]
    out = {"results": [], "degraded": [], "failed": []}
    sheet_path = raw_dir / f"_sheet_{item['name']}.png"
    pad = int(spec.get("pad_to") or 0)

    rec_base = {
        "provider": provider,
        "prompt": params["prompt"],
        "negative": params["negative"],
        "seed": params["seed"],
        "sheet": item["name"],
        "grid": spec["grid"],
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
    }

    try:
        if client is None:
            raise RuntimeError("provider=placeholder，跳过网格推理")
        info = client.generate(params, sheet_path)
        rec_base.update(info)
        sheet_img = Image.open(sheet_path)
        cells = split_grid(sheet_img, rows, cols)
        if len(cells) < len(names):
            raise RuntimeError(f"网格 {spec['grid']} 只有 {len(cells)} 格，需要 {len(names)}")
        done = finish_cells(cells, cfg, pad)
        for i, name in enumerate(names):
            cell = done[i]
            dst = raw_dir / f"{name}.png"
            cell.save(dst, "PNG")
            entries[name] = {
                **rec_base,
                "asset": name,
                "signature": f"{sig}:{name}",
                "cell": i,
                "width": cell.width,
                "height": cell.height,
                "bytes": dst.stat().st_size,
                "status": "ok",
            }
            out["results"].append({"asset": name, "status": "ok", "file": dst.name, "bytes": entries[name]["bytes"]})
        print(f"      网格 {spec['grid']} → {len(names)} 个素材（整图留档 {sheet_path.name}）")
    except Exception as e:  # noqa: BLE001
        warn(f"{item['name']} 网格生成失败：{e}")
        for i, name in enumerate(names):
            dst = raw_dir / f"{name}.png"
            if cfg["fallback_placeholder"]:
                make_placeholder(name, params["width"], params["height"], primary, bg).save(dst, "PNG")
                entries[name] = {
                    **rec_base,
                    "asset": name,
                    "provider": "placeholder",
                    "signature": f"{sig}:{name}",
                    "cell": i,
                    "status": "degraded",
                    "error": str(e)[:400],
                }
                out["degraded"].append({"asset": name, "error": str(e)[:300]})
                out["results"].append({"asset": name, "status": "degraded", "file": dst.name})
            else:
                out["failed"].append({"asset": name, "error": str(e)[:300]})
                out["results"].append({"asset": name, "status": "failed"})
    return out


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
    ap.add_argument("--timeout", type=int, default=0, help="单张超时秒数（覆盖配置里的 timeout）")
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
    if args.timeout:
        cfg["comfyui"]["timeout"] = args.timeout
        cfg["runninghub"]["timeout"] = args.timeout
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
        sheet = it.get("sheet")
        extra = json.dumps(sheet, ensure_ascii=False, sort_keys=True) if sheet else ""
        sig = signature(
            p,
            provider,
            str(cfg["comfyui"].get("workflow", "")) + str(cfg["runninghub"].get("workflow_id", "")) + extra,
        )
        targets = cell_names(it) if sheet else [it["name"]]
        outs = [raw_dir / f"{n}.png" for n in targets]
        if not args.force and all(o.exists() for o in outs) and all(
            (entries.get(n) or {}).get("signature") == f"{sig}:{n}" if sheet else (entries.get(n) or {}).get("signature") == sig
            for n in targets
        ):
            print(f"[{idx}/{len(items)}] 跳过（未变化）：{it['name']}" + (f"（{len(targets)} 格）" if sheet else ""))
            results.append({"asset": it["name"], "status": "skipped", "file": outs[0].name})
            continue

        print(
            f"[{idx}/{len(items)}] 生成 {it['name']}"
            + (f"（{sheet['grid']} 网格 → {len(targets)} 个素材）" if sheet else "")
            + f"  {p['width']}x{p['height']}  seed={p['seed']}"
        )
        if sheet:
            r = generate_sheet(client, cfg, it, p, sig, raw_dir, entries, primary, bg, provider)
            results.extend(r["results"])
            degraded.extend(r["degraded"])
            failed.extend(r["failed"])
            continue

        out = outs[0]
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
            if cfg.get("remove_bg") or p.get("trim"):
                im2 = Image.open(out)
                if cfg.get("remove_bg"):
                    im2 = remove_bg_color(im2, cfg["remove_bg"], int(cfg.get("remove_bg_tolerance") or 60))
                if p.get("trim"):
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
