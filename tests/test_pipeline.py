"""美术 / 音频 / 表现 / 体验 / 专项审核 / 端到端链路的测试。"""

from __future__ import annotations

import json
import subprocess
import sys

import pytest

from conftest import SCHEMAS, SKILL, fill_concept, fill_dna, load, run


# ------------------------------------------------------------------ 美术
def test_color_math():
    import art_director as ad

    assert ad.contrast("#FFFFFF", "#000000") > 20
    assert ad.contrast("#777777", "#777777") == 1.0
    assert ad.hue_distance("#FF0000", "#FF0000") == 0
    assert 170 < ad.hue_distance("#FF0000", "#00FFFF") <= 180
    # 往返转换不丢精度
    for h in ("#0E1B2A", "#F2C14A", "#7FD8CD"):
        assert ad.shift(h, 0, 0, 0).upper() == h.upper()


def test_three_proposals_are_distinguishable(dna_project):
    rc, out = run("art_director.py", "--project", dna_project, "--propose")
    assert rc == 0, out
    d = load(dna_project / "docs/02-art/style-proposals.json")
    ps = d["proposals"]
    assert len(ps) == 3
    # 三套的主色相或色温必须不同
    hues = [ad_hue(p["color_system"]["primary"][0]) for p in ps]
    assert len({round(h / 10) for h in hues}) >= 2, f"三套提案颜色太像：{hues}"
    for p in ps:
        assert p["positive_prompt"] and p["negative_prompt"]
        assert len(p["contrast_checks"]) == 4


def ad_hue(hex_color: str) -> float:
    import art_director as ad

    return ad.hex_to_hsl(hex_color)[0]


def test_visual_dna_passes_and_syncs_palette(dna_project):
    fill_dna(dna_project)
    rc, out = run("art_director.py", "--project", dna_project, "--dna", "--pick", "S1")
    assert rc == 0, out
    vd = load(dna_project / "docs/02-art/visual-dna.json")
    pal = load(dna_project / "docs/02-art/palette.json")

    # Visual DNA 必须真的包含 v2 完全缺失的那些字段
    for key in ("outline", "shape_language", "materials", "texture_rules"):
        assert vd["form"].get(key), f"form.{key} 为空"
    assert vd["light"]["direction"] and vd["light"]["shadow_rules"]
    assert vd["ui"]["text_render"]
    assert vd["character"]["ratio"]
    assert vd["scene_narrative"], "场景叙事为空"

    # 向后兼容：palette.json 仍要写出来，且 style_tokens 一致
    assert pal["style_tokens"] == vd["style"]["style_tokens"]
    assert pal["primary"] == vd["color"]["primary"]


def test_visual_dna_validate_blocks_low_contrast(dna_project):
    p = dna_project / "docs/02-art/visual-dna.json"
    d = load(p)
    for c in d["color"]["contrast_checks"]:
        c["pass"] = False
    p.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
    rc, out = run("art_director.py", "--project", dna_project, "--validate", "--strict")
    assert rc == 2
    assert "对比度" in out


def test_consistency_status_not_overclaimed(dna_project):
    rc, out = run("art_director.py", "--project", dna_project, "--consistency")
    assert rc == 0, out
    vd = load(dna_project / "docs/02-art/visual-dna.json")
    st = vd["character"]["consistency"]["status"]
    # 没有参考图时不允许声称 full_ref_chain
    assert st != "full_ref_chain"
    assert st in ("seed_only", "prompt_only", "degraded_no_ref")


def test_asset_forge_reads_visual_dna(dna_project):
    """v3 关键：Visual DNA 必须真的拼进提示词，且 ref 链默认生效。"""
    # 骨架蓝图的 role 按品类推断，puzzle 不含 character；这里显式加上，
    # 并给主角一个英文名（中文名会 slug 成空，属另一个用例覆盖的情况）
    bp_path = dna_project / "docs/01-brief/content-blueprint.json"
    bp = load(bp_path)
    bp.setdefault("art", {})["roles_required"] = [
        "character", "prop", "tile", "bg", "ui", "fx", "keyart"]
    bp.setdefault("story", {}).setdefault("protagonist", {})["name"] = "ferryman"
    bp_path.write_text(json.dumps(bp, ensure_ascii=False, indent=2), encoding="utf-8")

    rc, out = run("asset_forge.py", "--project", dna_project, "--spec", "--force")
    assert rc == 0, out
    spec = load(dna_project / "docs/02-art/asset-spec.json")
    assert spec["version"] == "3.0"
    assert spec["visual_dna"], "spec 没有记录 Visual DNA 来源"
    applied = spec["visual_dna_applied"]
    assert applied["outline"] and applied["lighting"], "Visual DNA 未被读取"

    # 修复 T4 + ref 只给主角：主角三视图（front/side/back），side/back 必须挂 ref
    chars = [i for i in spec["items"] if i["role"] == "character"]
    hero_ids = {i["id"] for i in chars if i.get("use_hero_ref") or i.get("base")}
    assert {"ferryman", "ferryman_side", "ferryman_back"} <= {i["id"] for i in chars}, \
        f"主角三视图没生成：{[i['id'] for i in chars]}"
    with_ref = [i for i in chars if i.get("use_hero_ref")]
    assert len(with_ref) >= 2, "主角侧/背视图没有挂 ref（T4 未修）"
    # 反派/路人绝不能挂主角的 ref（否则会被画成主角换皮）
    others = [i for i in chars if i["id"] not in hero_ids]
    assert all(not i.get("use_hero_ref") for i in others), "非主角角色挂上了主角 ref"

    rc, out = run("asset_forge.py", "--project", dna_project, "--prompts")
    assert rc == 0, out
    # 提示词里应出现 Visual DNA 的槽位（轮廓/材质/光照）
    prompt_files = list((dna_project / "docs/02-art/prompts").glob("*.txt"))
    assert prompt_files
    joined = "\n".join(f.read_text(encoding="utf-8") for f in prompt_files)
    vd = load(dna_project / "docs/02-art/visual-dna.json")
    assert vd["form"]["materials"][0] in joined, "材质未进入提示词"


# ------------------------------------------------------------------ 音频
def test_audio_plan_states_are_distinct(dna_project):
    rc, out = run("audio_forge.py", "--project", dna_project, "--plan")
    assert rc == 0, out
    rc, out = run("audio_director.py", "--project", dna_project, "--plan")
    assert rc == 0, out
    d = load(dna_project / "docs/05-audio/audio-dna.json")
    states = d["music"]["states"]
    assert len(states) >= 2
    sigs = {json.dumps(s["stem_gains"], sort_keys=True) for s in states}
    assert len(sigs) == len(states), "有状态的分轨配比完全相同 —— 自适应是假的"
    # 每个状态必须覆盖全部 stem
    stem_ids = {s["id"] for s in d["music"]["stems"]}
    for s in states:
        assert set(s["stem_gains"]) == stem_ids


def test_audio_validate_rejects_duplicate_states(dna_project):
    p = dna_project / "docs/05-audio/audio-dna.json"
    d = load(p)
    d["music"]["states"][1]["stem_gains"] = dict(d["music"]["states"][0]["stem_gains"])
    p.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
    rc, out = run("audio_director.py", "--project", dna_project, "--validate", "--strict")
    assert rc == 2
    assert "完全相同" in out


def test_audio_qc_detects_clipping(tmp_path):
    """真实波形检查：人为造一个削波文件，必须被判出来。"""
    import numpy as np
    import wave

    d = tmp_path / "a"
    d.mkdir()
    wav = d / "clip.wav"
    sr = 44100
    x = (np.ones(sr) * 32767).astype(np.int16)
    with wave.open(str(wav), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(x.tobytes())

    import audio_director as ad

    r = ad.analyze_audio(wav)
    assert r["exists"] is True
    assert r["clipped"] is True, r
    assert any("削波" in i for i in r["issues"])


def test_audio_qc_detects_silence(tmp_path):
    import numpy as np
    import wave

    wav = tmp_path / "silent.wav"
    sr = 44100
    x = np.zeros(sr, dtype=np.int16)
    with wave.open(str(wav), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(x.tobytes())

    import audio_director as ad

    r = ad.analyze_audio(wav)
    assert r["silent"] is True
    assert any("静音" in i for i in r["issues"])


# ------------------------------------------------------------------ 表现
def test_juice_plan_tiers_and_hard_limits(dna_project):
    rc, out = run("juice_forge.py", "--project", dna_project, "--plan")
    assert rc == 0, out
    d = load(dna_project / "docs/04-core-loop/juice-plan.json")
    tiers = {r["tier"] for r in d["rules"]}
    assert {"micro", "medium", "heavy"} <= tiers, f"分档不全：{tiers}"
    # 闪屏不得用于低严重度事件
    for r in d["rules"]:
        for f in r["effects"]:
            if f["type"] == "screen_flash":
                assert r["severity"] >= 0.7, f"{r['event']} 严重度 {r['severity']} 用了闪屏"
    s = d["settings"]
    assert s["flashMaxPerSecond"] <= 1
    assert s["shakeMaxMs"] <= 300
    assert len({f["type"] for r in d["rules"] for f in r["effects"]}) >= 8


def test_juice_emit_ts_is_importable_shape(dna_project):
    rc, out = run("juice_forge.py", "--project", dna_project, "--emit-ts")
    assert rc == 0, out
    ts = (dna_project / "src/game/juice-config.ts").read_text(encoding="utf-8")
    assert "export const JUICE_RULES" in ts
    assert "export const JUICE_SETTINGS" in ts
    assert "flashMaxPerSecond" in ts


# ------------------------------------------------------------------ 体验
def test_experience_verify_marks_unverified_without_playtest(dna_project):
    rc, out = run("experience_forge.py", "--project", dna_project, "--plan")
    assert rc == 0, out
    rc, out = run("experience_forge.py", "--project", dna_project, "--verify")
    # 没有试玩报告时，E2/E8 必须是 UNVERIFIED，而不是 PASS
    d = load(dna_project / "docs/03-experience/experience-blueprint.json")
    by_id = {c["id"]: c for c in d["checks"]}
    assert by_id["E2"]["result"] == "UNVERIFIED"
    assert by_id["E8"]["result"] == "UNVERIFIED"
    assert not any(c["result"] == "PASS" and len(c["evidence"]) < 6 for c in d["checks"])


# ------------------------------------------------------------------ 专项审核
def test_specialist_returns_incomplete_without_artifacts(proj):
    """缺产物时必须是 INCOMPLETE（未验证），绝不能是 PASS。"""
    rc, out = run("specialist_review.py", "--project", proj, "--only", "art,audio")
    v = load(proj / "docs/09-review/verdict-specialist.json")
    assert v["verdict"] in ("INCOMPLETE", "FAIL")
    assert v["verdict"] != "PASS"


def test_specialist_blocks_ship_when_fail(proj):
    """把专项审核写成 FAIL，ship 必须被拦。"""
    v = load(proj / "docs/09-review/verdict-specialist.json")
    v["verdict"] = "FAIL"
    v["blocking"] = [{"review": "art", "code": "A2", "title": "对比度", "result": "FAIL", "fix": "x"}]
    (proj / "docs/09-review/verdict-specialist.json").write_text(
        json.dumps(v, ensure_ascii=False), encoding="utf-8")

    rc, out = run("gate_check.py", "--project", proj, "--stage", "ship")
    assert rc == 1
    assert "专项审核 FAIL" in out


def test_specialist_blocks_ship_when_incomplete(proj):
    v = load(proj / "docs/09-review/verdict-specialist.json")
    v["verdict"] = "INCOMPLETE"
    v["blocking"] = [{"review": "audio", "code": "U3", "title": "音频实测", "result": "UNVERIFIED"}]
    (proj / "docs/09-review/verdict-specialist.json").write_text(
        json.dumps(v, ensure_ascii=False), encoding="utf-8")

    rc, out = run("gate_check.py", "--project", proj, "--stage", "ship")
    assert rc == 1
    assert "未验证不算通过" in out


# ------------------------------------------------------------------ 端到端
def test_full_pipeline_end_to_end(tmp_path):
    """从零建项目，一路跑到专项审核，验证整条 v3 链路可用。"""
    root = tmp_path / "e2e"
    rc, out = run("init_project.py", "--name", "g", "--idea", "在雾里靠回声摆渡灵魂",
                  "--platforms", "crazygames", "--genre", "puzzle", "--out", root)
    assert rc == 0, out
    p = root / "g"

    steps = [
        ("creative_forge.py", "--project", p, "--diverge", "--n", "5"),
    ]
    for script, *args in steps:
        rc, out = run(script, *args)
        assert rc == 0, f"{script} 失败：{out}"

    # 先填一个方案再评估：空壳方案必须被判 REJECT（这正是 gate 的设计意图）
    fill_concept(p, "C1")
    rc, out = run("creative_forge.py", "--project", p, "--evaluate")
    assert rc == 0, out
    ev = load(p / "docs/01-brief/creative-concepts.json")["evaluation"]
    assert any(e["verdict"] == "ACCEPT" for e in ev), "填好的方案应能 ACCEPT"

    rc, out = run("creative_forge.py", "--project", p, "--dna", "--pick", "C1", "--force")
    assert rc == 0, out

    fill_dna(p)
    rc, out = run("creative_forge.py", "--project", p, "--validate", "--strict")
    assert rc == 0, out

    for script, *args in [
        ("art_director.py", "--project", p, "--propose"),
        ("art_director.py", "--project", p, "--dna", "--pick", "S1"),
        ("art_director.py", "--project", p, "--consistency"),
        ("art_director.py", "--project", p, "--validate", "--strict"),
        ("audio_forge.py", "--project", p, "--plan"),
        ("audio_forge.py", "--project", p, "--plan"),
        ("audio_director.py", "--project", p, "--plan"),
        ("audio_director.py", "--project", p, "--emit"),
        ("audio_director.py", "--project", p, "--emit-ts"),
        ("audio_director.py", "--project", p, "--validate", "--strict"),
        ("juice_forge.py", "--project", p, "--plan"),
        ("juice_forge.py", "--project", p, "--emit-ts"),
        ("juice_forge.py", "--project", p, "--validate", "--strict"),
        ("experience_forge.py", "--project", p, "--plan"),
        ("experience_forge.py", "--project", p, "--validate", "--strict"),
    ]:
        rc, out = run(script, *args)
        assert rc == 0, f"{script} {' '.join(map(str, args))} 失败：{out}"

    # 音频：没有实测证据时 gate 必须拦下来（这是「不许虚报」的关键）
    rc, out = run("gate_check.py", "--project", p, "--stage", "audio_director")
    assert rc == 1, "缺 audio-qc.json 时 audio_director 门禁不该通过"
    assert "audio-qc.json" in out

    # 真正生产音频后再校验（需要 ffmpeg；没有就跳过这一段，不伪装通过）
    import shutil as _sh

    import audio_director as _ad

    if _ad.ffmpeg_bin() or _sh.which("ffmpeg"):
        rc, out = run("gen_audio.py", "--project", p, "--spec",
                      p / "docs/05-audio/sfx-plan.json", timeout=300)
        assert rc == 0, out
        rc, out = run("gen_stems.py", "--project", p, "--seconds", "4", timeout=300)
        assert rc == 0, out
        rc, out = run("audio_director.py", "--project", p, "--qc")
        assert rc == 0, out
        rc, out = run("gate_check.py", "--project", p, "--stage", "audio_director")
        assert rc == 0, f"音频就绪后仍不通过：{out}"
    else:
        pytest.skip("环境无 ffmpeg，跳过音频生产环节（不伪装通过）")

    # 门禁：创意 / DNA / Visual DNA / 表现 / 体验 必须全绿
    for stage in ("creative", "creative_dna", "visual_dna", "juice", "experience"):
        rc, out = run("gate_check.py", "--project", p, "--stage", stage)
        assert rc == 0, f"gate_check {stage} 未通过：{out}"

    # schema 全量
    rc, out = run("schema_check.py", "--all", "--project", p)
    assert rc == 0, f"schema --all 失败：{out}"
