#!/usr/bin/env python3
"""通用 JSON Schema 校验器（零依赖，JSON Schema Draft-07 子集）。

为什么不用 jsonschema 包：本技能的分发约束是「只依赖 PyYAML / Pillow / numpy」，
pip 装不上时整条链路会断。这里实现项目实际用到的那部分关键字，够用且可控。

支持关键字：
  type / enum / const / required / properties / additionalProperties / items
  minItems / maxItems / uniqueItems / minLength / maxLength / pattern
  minimum / maximum / exclusiveMinimum / exclusiveMaximum
  allOf / anyOf / oneOf / not / $ref（仅本地 #/definitions/...）

用法:
    python schema_check.py --data docs/01-brief/creative-dna.json \\
                           --schema references/schemas/creative-dna.schema.json
    python schema_check.py --all --project .        # 校验项目内全部已知契约文件
    python schema_check.py --selftest               # 校验器自身的回归用例

退出码: 0=通过　2=有校验错误
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import SKILL_DIR, die, ok, project_dir, warn  # noqa: E402

SCHEMA_DIR = SKILL_DIR / "references" / "schemas"

# 数据文件 → schema 文件（--all 用；也是文档里「契约在哪」的答案）
KNOWN_CONTRACTS = {
    "docs/01-brief/creative-dna.json": "creative-dna.schema.json",
    "docs/02-art/visual-dna.json": "visual-dna.schema.json",
    "docs/03-experience/experience-blueprint.json": "experience-blueprint.schema.json",
    "docs/04-core-loop/juice-plan.json": "juice-plan.schema.json",
    "docs/05-audio/audio-dna.json": "audio-dna.schema.json",
}


class SchemaError(Exception):
    pass


def _type_ok(value, t: str) -> bool:
    if t == "object":
        return isinstance(value, dict)
    if t == "array":
        return isinstance(value, list)
    if t == "string":
        return isinstance(value, str)
    if t == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if t == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if t == "boolean":
        return isinstance(value, bool)
    if t == "null":
        return value is None
    return True


def _resolve(ref: str, root: dict) -> dict:
    if not ref.startswith("#/"):
        raise SchemaError(f"只支持本地 $ref，收到 {ref}")
    node = root
    for part in ref[2:].split("/"):
        part = part.replace("~1", "/").replace("~0", "~")
        if not isinstance(node, dict) or part not in node:
            raise SchemaError(f"$ref 无法解析：{ref}")
        node = node[part]
    return node


def validate(data, schema: dict, root: dict | None = None, path: str = "$") -> list[str]:
    """返回错误列表（空列表 = 通过）。"""
    root = root if root is not None else schema
    errs: list[str] = []

    if schema is True or schema == {}:
        return errs
    if schema is False:
        return [f"{path}: schema 为 false，禁止任何值"]

    if "$ref" in schema:
        return validate(data, _resolve(schema["$ref"], root), root, path)

    if "type" in schema:
        types = schema["type"] if isinstance(schema["type"], list) else [schema["type"]]
        if not any(_type_ok(data, t) for t in types):
            errs.append(f"{path}: 类型应为 {'/'.join(types)}，实际 {type(data).__name__}")
            return errs  # 类型不对，后续关键字无意义

    if "const" in schema and data != schema["const"]:
        errs.append(f"{path}: 必须等于 {schema['const']!r}，实际 {data!r}")

    if "enum" in schema and data not in schema["enum"]:
        errs.append(f"{path}: 必须是 {schema['enum']} 之一，实际 {data!r}")

    if isinstance(data, str):
        if "minLength" in schema and len(data) < schema["minLength"]:
            errs.append(f"{path}: 长度 {len(data)} < minLength {schema['minLength']}")
        if "maxLength" in schema and len(data) > schema["maxLength"]:
            errs.append(f"{path}: 长度 {len(data)} > maxLength {schema['maxLength']}")
        if "pattern" in schema and not re.search(schema["pattern"], data):
            errs.append(f"{path}: 不匹配 pattern {schema['pattern']!r}")

    if isinstance(data, (int, float)) and not isinstance(data, bool):
        if "minimum" in schema and data < schema["minimum"]:
            errs.append(f"{path}: {data} < minimum {schema['minimum']}")
        if "maximum" in schema and data > schema["maximum"]:
            errs.append(f"{path}: {data} > maximum {schema['maximum']}")
        if "exclusiveMinimum" in schema and data <= schema["exclusiveMinimum"]:
            errs.append(f"{path}: {data} <= exclusiveMinimum {schema['exclusiveMinimum']}")
        if "exclusiveMaximum" in schema and data >= schema["exclusiveMaximum"]:
            errs.append(f"{path}: {data} >= exclusiveMaximum {schema['exclusiveMaximum']}")

    if isinstance(data, list):
        if "minItems" in schema and len(data) < schema["minItems"]:
            errs.append(f"{path}: 元素 {len(data)} 个 < minItems {schema['minItems']}")
        if "maxItems" in schema and len(data) > schema["maxItems"]:
            errs.append(f"{path}: 元素 {len(data)} 个 > maxItems {schema['maxItems']}")
        if schema.get("uniqueItems"):
            seen, dup = [], []
            for x in data:
                key = json.dumps(x, sort_keys=True, ensure_ascii=False)
                if key in seen:
                    dup.append(x)
                seen.append(key)
            if dup:
                errs.append(f"{path}: 存在重复元素 {dup[:3]}")
        if "items" in schema:
            for i, x in enumerate(data):
                errs += validate(x, schema["items"], root, f"{path}[{i}]")

    if isinstance(data, dict):
        for req in schema.get("required", []):
            if req not in data:
                errs.append(f"{path}: 缺少必填字段 `{req}`")
        props = schema.get("properties") or {}
        for k, v in data.items():
            if k in props:
                errs += validate(v, props[k], root, f"{path}.{k}")
            else:
                ap = schema.get("additionalProperties", True)
                if ap is False:
                    errs.append(f"{path}: 不允许的字段 `{k}`")
                elif isinstance(ap, dict):
                    errs += validate(v, ap, root, f"{path}.{k}")
        for key in ("minProperties", "maxProperties"):
            if key == "minProperties" and "minProperties" in schema and len(data) < schema["minProperties"]:
                errs.append(f"{path}: 字段 {len(data)} 个 < minProperties {schema['minProperties']}")
            if key == "maxProperties" and "maxProperties" in schema and len(data) > schema["maxProperties"]:
                errs.append(f"{path}: 字段 {len(data)} 个 > maxProperties {schema['maxProperties']}")

    for sub in schema.get("allOf", []):
        errs += validate(data, sub, root, path)
    if "anyOf" in schema:
        if not any(not validate(data, s, root, path) for s in schema["anyOf"]):
            errs.append(f"{path}: 不满足 anyOf 任一分支")
    if "oneOf" in schema:
        n = sum(1 for s in schema["oneOf"] if not validate(data, s, root, path))
        if n != 1:
            errs.append(f"{path}: oneOf 应恰好命中 1 个分支，实际 {n}")
    if "not" in schema and not validate(data, schema["not"], root, path):
        errs.append(f"{path}: 命中了 not 分支")

    return errs


def load(p: Path):
    with p.open("r", encoding="utf-8") as f:
        return json.load(f)


def check_file(data_path: Path, schema_path: Path, quiet: bool = False) -> list[str]:
    if not data_path.exists():
        return [f"数据文件不存在：{data_path}"]
    if not schema_path.exists():
        return [f"schema 不存在：{schema_path}"]
    try:
        data = load(data_path)
    except Exception as e:  # noqa: BLE001
        return [f"{data_path.name} 解析失败：{e}"]
    try:
        schema = load(schema_path)
    except Exception as e:  # noqa: BLE001
        return [f"{schema_path.name} 解析失败：{e}"]
    errs = validate(data, schema)
    if not quiet:
        name = data_path.name
        if errs:
            print(f"[FAIL] {name}  ({len(errs)} 个问题)")
            for e in errs[:40]:
                print(f"       - {e}")
            if len(errs) > 40:
                print(f"       … 另有 {len(errs) - 40} 个")
        else:
            print(f"[PASS] {name}")
    return errs


# ------------------------------------------------------------------ selftest
SELFTEST_CASES = [
    # (schema, data, 期望是否通过)
    ({"type": "string", "minLength": 3}, "abcd", True),
    ({"type": "string", "minLength": 3}, "ab", False),
    ({"type": "integer"}, 3, True),
    ({"type": "integer"}, 3.5, False),
    ({"type": "integer"}, True, False),
    ({"type": "number"}, 3, True),
    ({"type": "object", "required": ["a"]}, {"a": 1}, True),
    ({"type": "object", "required": ["a"]}, {"b": 1}, False),
    ({"type": "object", "additionalProperties": False, "properties": {"a": {}}}, {"a": 1, "b": 2}, False),
    ({"type": "array", "minItems": 2}, [1, 2], True),
    ({"type": "array", "minItems": 2}, [1], False),
    ({"type": "array", "uniqueItems": True}, [1, 1], False),
    ({"enum": ["a", "b"]}, "c", False),
    ({"const": 5}, 5, True),
    ({"minimum": 0, "maximum": 1}, 1.5, False),
    ({"pattern": "^[a-z_]+$"}, "abc_def", True),
    ({"pattern": "^[a-z_]+$"}, "abc-Def", False),
    ({"anyOf": [{"type": "string"}, {"type": "integer"}]}, 3, True),
    ({"oneOf": [{"type": "number"}, {"type": "integer"}]}, 3, False),  # 两个都命中
    ({"not": {"type": "null"}}, "x", True),
    ({"allOf": [{"type": "object"}, {"required": ["x"]}]}, {"x": 1}, True),
    ({"type": "array", "items": {"type": "string"}}, ["a", 1], False),
    ({"$ref": "#/definitions/pos"}, {"v": 1}, False),  # 缺 definitions → 抛错 → 视为失败
]


def cmd_selftest() -> int:
    bad = 0
    for i, (schema, data, expect) in enumerate(SELFTEST_CASES):
        try:
            errs = validate(data, schema)
            got = not errs
        except SchemaError:
            got = False
        if got != expect:
            bad += 1
            print(f"[FAIL] case {i}: schema={schema} data={data!r} 期望 {expect} 实际 {got}")
    # $ref 正常路径
    root = {"definitions": {"pos": {"type": "integer", "minimum": 1}},
            "properties": {"v": {"$ref": "#/definitions/pos"}}, "type": "object"}
    if validate({"v": 2}, root):
        bad += 1
        print("[FAIL] $ref 正常路径")
    if not validate({"v": 0}, root):
        bad += 1
        print("[FAIL] $ref 最小值未生效")
    total = len(SELFTEST_CASES) + 2
    if bad:
        print(f"selftest 失败 {bad}/{total}")
        return 2
    ok(f"selftest 全部通过（{total} 个用例）")
    return 0


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass
    ap = argparse.ArgumentParser(description="JSON Schema 校验（Draft-07 子集）")
    ap.add_argument("--data", default=None)
    ap.add_argument("--schema", default=None)
    ap.add_argument("--project", default=None)
    ap.add_argument("--all", action="store_true", help="校验项目内全部已知契约")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()

    if args.selftest:
        return cmd_selftest()

    if args.all:
        proj = project_dir(args.project)
        missing = 0
        failed = 0
        for rel, schema_name in KNOWN_CONTRACTS.items():
            dp = proj / rel
            if not dp.exists():
                missing += 1
                print(f"[SKIP] {rel}（尚未产出）")
                continue
            if check_file(dp, SCHEMA_DIR / schema_name):
                failed += 1
        print("-" * 56)
        print(f"已校验 {len(KNOWN_CONTRACTS) - missing} 份，未产出 {missing} 份，失败 {failed} 份")
        return 2 if failed else 0

    if not args.data or not args.schema:
        die("需要 --data 与 --schema，或用 --all / --selftest")
    errs = check_file(Path(args.data), Path(args.schema))
    if errs:
        warn("schema 校验未通过")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
