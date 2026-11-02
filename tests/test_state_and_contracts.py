"""状态机与文件契约的测试。

重点验证「向后兼容」：v1/v2 的 15 个阶段键必须仍然存在，
新增的 v3 阶段只 append，旧项目缺键时按 pending 处理。
"""

from __future__ import annotations

import json

import pytest

from conftest import SKILL, load, run

LEGACY_STAGES = [
    "brief", "content", "review_plan", "review_richness", "scaffold", "art_bible",
    "core_loop", "review_graybox", "art_forge", "sprite_tools", "audio_forge",
    "polish", "perf_audit", "qa", "review_final", "ship",
]
V3_STAGES = ["creative", "creative_dna", "visual_dna", "audio_director",
             "juice", "experience", "playtest", "review_specialist"]


def test_all_legacy_stages_preserved():
    import _common

    for s in LEGACY_STAGES:
        assert s in _common.STAGES, f"旧阶段 {s} 被删了 —— 会破坏旧项目的 state.yaml"


def test_v3_stages_added():
    import _common

    for s in V3_STAGES:
        assert s in _common.STAGES, f"缺 v3 阶段 {s}"
        assert s in _common.V3_STAGES


def test_stage_order_is_sane():
    """创意必须在写代码之前；审核必须在其对应生产阶段之后。"""
    import _common

    idx = {s: i for i, s in enumerate(_common.STAGES)}
    assert idx["creative"] < idx["content"] < idx["scaffold"]
    assert idx["creative_dna"] < idx["review_plan"]
    assert idx["scaffold"] < idx["core_loop"] < idx["review_graybox"]
    assert idx["audio_forge"] < idx["audio_director"]
    assert idx["qa"] < idx["playtest"] < idx["review_specialist"] < idx["review_final"] < idx["ship"]


def test_every_stage_has_module_mapping():
    """修 T9：模块文件必须是显式映射，不能靠序号推断。"""
    import _common

    missing = [s for s in _common.STAGES if s not in _common.STAGE_MODULES]
    assert not missing, f"这些阶段没有模块映射：{missing}"
    for s, rel in _common.STAGE_MODULES.items():
        assert (SKILL / rel).exists(), f"{s} 指向的 {rel} 不存在"


def test_state_show_lists_all_stages(proj):
    rc, out = run("state.py", "show", "--project", proj)
    assert rc == 0, out
    import _common

    for s in _common.STAGES:
        assert s in out, f"state show 未显示阶段 {s}"


def test_new_project_marks_v3_stages_pending(tmp_path):
    """新建项目时全部阶段都是 pending（用独立项目，避免被其它测试改动影响）。"""
    from _common import load_state

    root = tmp_path / "fresh"
    rc, out = run("init_project.py", "--name", "f", "--idea", "一个测试用的小游戏",
                  "--platforms", "crazygames", "--out", root)
    assert rc == 0, out
    st = load_state(root / "f")
    for s in V3_STAGES:
        assert st["stages"][s]["status"] == "pending", f"{s} 初始状态不是 pending"


def test_legacy_project_without_v3_keys_still_works(tmp_path):
    """模拟一个 v2 项目：state.yaml 里没有 v3 的键，show/next 不能崩。"""
    import yaml

    p = tmp_path / "old"
    (p / ".gamedev").mkdir(parents=True)
    state = {
        "project": {"name": "old", "idea": "老项目", "genre": "arcade"},
        "stages": {s: {"status": "done"} for s in LEGACY_STAGES},
        "delivery": {"platforms": ["crazygames"], "platform_confirmed": True, "tier": "L2"},
    }
    (p / ".gamedev" / "state.yaml").write_text(
        yaml.safe_dump(state, allow_unicode=True), encoding="utf-8")

    rc, out = run("state.py", "show", "--project", p)
    assert rc == 0, out
    assert "creative" in out

    rc, out = run("state.py", "next", "--project", p)
    assert rc == 0, out
    # 旧项目第一个未完成的是 v3 的 creative，提示应给出正确模块名
    assert "modules/01c-creative-director.md" in out


def test_state_set_rejects_unknown_stage(proj):
    rc, out = run("state.py", "set", "--project", proj, "--stage", "nope", "--status", "done")
    assert rc == 1
    assert "未知阶段" in out


def test_gate_check_required_files_cover_all_stages():
    """每个阶段都必须有产物要求，否则门禁形同虚设。"""
    import gate_check
    from _common import STAGES

    missing = [s for s in STAGES if s not in gate_check.REQUIRED_FILES]
    assert not missing, f"这些阶段没有 REQUIRED_FILES：{missing}"


def test_gate_check_checkers_registered():
    """有语义判据的阶段必须有 checker；纯产物阶段只靠 REQUIRED_FILES 也合规。"""
    import gate_check

    # 这些阶段的判据不只是「文件存在」，必须有语义校验
    must_have = ["brief", "creative", "creative_dna", "content", "review_richness",
                 "visual_dna", "audio_director", "juice", "experience", "playtest",
                 "review_specialist", "review_plan", "review_graybox", "review_final", "ship"]
    for s in must_have:
        assert s in gate_check.CHECKERS, f"阶段 {s} 缺语义 checker"


def test_gate_check_blocks_without_platform_confirmation(tmp_path):
    """G0 未确认时 brief 必须失败 —— 这是最便宜的一道闸。"""
    import yaml

    p = tmp_path / "np"
    (p / "docs/01-brief").mkdir(parents=True)
    (p / "docs/00-platforms").mkdir(parents=True)
    (p / ".gamedev").mkdir(parents=True)
    (p / ".gamedev" / "state.yaml").write_text(yaml.safe_dump(
        {"project": {"name": "np"}, "stages": {}, "delivery": {"platforms": []}},
        allow_unicode=True), encoding="utf-8")
    (p / "docs/00-platforms/platform-plan.md").write_text("x", encoding="utf-8")
    (p / "docs/01-brief/gdd.md").write_text("x", encoding="utf-8")
    (p / "docs/01-brief/scope.json").write_text(json.dumps({
        "genre": "arcade", "core_loop": "x", "controls": "x", "mvp_features": [],
        "out_of_scope": ["a"], "assets": {}}), encoding="utf-8")

    rc, out = run("gate_check.py", "--project", p, "--stage", "brief")
    assert rc == 1
    assert "尚未确认目标平台" in out
