"""JSON Schema 校验器与五份契约 schema 的测试。"""

from __future__ import annotations

import json

import pytest

from conftest import SCHEMAS, run

REQUIRED_SCHEMAS = [
    "creative-dna.schema.json",
    "visual-dna.schema.json",
    "audio-dna.schema.json",
    "juice-plan.schema.json",
    "experience-blueprint.schema.json",
]


def test_selftest_passes():
    rc, out = run("schema_check.py", "--selftest")
    assert rc == 0, out
    assert "全部通过" in out


@pytest.mark.parametrize("name", REQUIRED_SCHEMAS)
def test_schema_is_valid_json_and_has_structure(name: str):
    p = SCHEMAS / name
    assert p.exists(), f"缺 schema：{name}"
    d = json.loads(p.read_text(encoding="utf-8"))
    assert d.get("$schema"), f"{name} 缺 $schema"
    assert d.get("type") == "object", f"{name} 顶层应为 object"
    assert d.get("required"), f"{name} 应声明 required"


def test_validator_catches_type_and_required(tmp_path):
    data = tmp_path / "d.json"
    schema = tmp_path / "s.json"
    data.write_text('{"a": "x"}', encoding="utf-8")
    schema.write_text(
        json.dumps({"type": "object", "required": ["a", "b"],
                    "properties": {"a": {"type": "integer"}}}),
        encoding="utf-8")
    rc, out = run("schema_check.py", "--data", data, "--schema", schema)
    assert rc == 2
    assert "缺少必填字段" in out
    assert "类型应为 integer" in out


def test_validator_accepts_valid(tmp_path):
    data = tmp_path / "d.json"
    schema = tmp_path / "s.json"
    data.write_text('{"a": 3}', encoding="utf-8")
    schema.write_text(json.dumps({"type": "object", "required": ["a"],
                                  "properties": {"a": {"type": "integer", "minimum": 1}}}),
                      encoding="utf-8")
    rc, out = run("schema_check.py", "--data", data, "--schema", schema)
    assert rc == 0, out
    assert "PASS" in out


def test_creative_dna_schema_rejects_numeric_only_mechanic():
    """独特机制声明 non_numeric=false 必须被 schema 拒绝（只改数值不算独特机制）。"""
    import schema_check

    schema = json.loads((SCHEMAS / "creative-dna.schema.json").read_text(encoding="utf-8"))
    minimal = {
        "version": "3.0",
        "meta": {"idea": "测试想法", "concept_id": "C1", "created": "2026-01-01", "judged_by": "x"},
        "identity": {"game_title": "测试", "core_fantasy": "我想测试一个足够长的幻想",
                     "unique_hook": "一个足够长的独特钩子描述", "creative_promise": "一个足够长的承诺",
                     "signature_moment": "一个足够长的标志性时刻描述内容"},
        "gameplay": {
            "genre": ["puzzle"],
            "core_mechanic": {
                "id": "m1", "name": "机制", "one_sentence": "一句话解释这个机制",
                "why_unique": "足够长的独特性论证内容", "non_numeric": False,
                "interacts": ["m2", "m3"], "changes_decision": "足够长的策略改变描述",
                "signature_moment": "足够长的标志时刻描述",
            },
            "supporting_mechanics": [
                {"id": "m2", "name": "a", "role": "support", "interacts": ["m1"]},
                {"id": "m3", "name": "b", "role": "twist", "interacts": ["m1"]},
            ],
            "player_decisions": [{"question": "足够长的问题描述", "cost": "足够长的代价"}],
            "progression_identity": "推进方式是地图越来越不可信",
        },
        "narrative": {"world_rules": ["规则一足够长", "规则二足够长", "规则三足够长"],
                      "theme": "主题", "emotional_arc": [{"beat": "a", "emotion": "b"}]},
        "visual": {"style_identity": "水墨 × 水彩绘本混血", "visual_keywords": ["a", "b", "c", "d", "e"],
                   "palette": {"primary": ["#111111", "#222222", "#333333"],
                               "accent": ["#FFAA00"], "danger": "#FF0000"},
                   "materials": ["paper", "ink"], "lighting": "侧光 2700K 偏暖",
                   "camera": "俯视", "shape_language": "圆润对硬角"},
        "audio": {"audio_identity": "木质船体与海浪", "music_mood": ["a", "b"],
                  "instrumentation": ["x", "y", "z"], "sound_signature": ["s1", "s2"],
                  "dynamic_audio_rules": [{"when": "a", "change": "b"}, {"when": "c", "change": "d"}]},
        "experience": {"target_emotions": [{"emotion": "孤独", "weight": 0.5}],
                       "pacing": [{"phase": "curiosity", "intensity": 0.3},
                                  {"phase": "learning", "intensity": 0.4},
                                  {"phase": "climax", "intensity": 1.0},
                                  {"phase": "satisfaction", "intensity": 0.4}],
                       "player_memory": "足够长的记忆点描述"},
    }
    errs = schema_check.validate(minimal, schema)
    assert any("non_numeric" in e for e in errs), f"应拒绝 non_numeric=false，实际：{errs}"

    minimal["gameplay"]["core_mechanic"]["non_numeric"] = True
    rest = schema_check.validate(minimal, schema)
    assert not any("non_numeric" in e for e in rest), f"改回 true 后不该再报 non_numeric：{rest}"


def test_all_known_contracts_point_to_existing_schema():
    import schema_check

    for rel, schema_name in schema_check.KNOWN_CONTRACTS.items():
        assert (SCHEMAS / schema_name).exists(), f"{rel} 指向的 {schema_name} 不存在"
