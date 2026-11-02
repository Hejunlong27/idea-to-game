"""Creative Director / Creative DNA 的测试。

核心断言不是「能跑」，而是三条设计约束：
  1. 同一 idea 必须**确定性**地产出同一组方案（可复现是测试的前提）
  2. 5 个方案必须在结构指纹上真正不同（防换皮）
  3. 新颖度必须是**启发式相似度**，不能假装是原创性证明
"""

from __future__ import annotations

import json

from conftest import fill_dna, load, run

FP_KEYS = ["spatial", "time", "info", "resource", "risk"]


def test_diverge_is_deterministic(tmp_path):
    """同一个 idea 跑两次，seed 与方案结构必须完全一致。"""
    outs = []
    for i in range(2):
        root = tmp_path / f"r{i}"
        rc, out = run("init_project.py", "--name", "d", "--idea", "守一座会下沉的灯塔",
                      "--platforms", "crazygames", "--out", root)
        assert rc == 0, out
        rc, out = run("creative_forge.py", "--project", root / "d", "--diverge")
        assert rc == 0, out
        d = load(root / "d" / "docs/01-brief/creative-concepts.json")
        outs.append((d["seed"], [c["structure"] for c in d["concepts"]],
                     [c["twist_dimension"] for c in d["concepts"]]))
    assert outs[0] == outs[1]


def test_five_concepts_structurally_distinct(dna_project):
    d = load(dna_project / "docs/01-brief/creative-concepts.json")
    cs = d["concepts"]
    assert len(cs) == 5
    fps = [c["structure"] for c in cs]
    # 任意两个方案至少在 3 个结构维度上不同
    for i in range(len(fps)):
        for j in range(i + 1, len(fps)):
            diff = sum(1 for k in FP_KEYS if fps[i].get(k) != fps[j].get(k))
            assert diff >= 3, f"C{i + 1} 与 C{j + 1} 只差 {diff} 个维度（换皮）"
    assert d["structural_distance"]["pass"] is True


def test_twist_dimensions_are_unique(dna_project):
    d = load(dna_project / "docs/01-brief/creative-concepts.json")
    twists = [c["twist_dimension"] for c in d["concepts"]]
    assert len(set(twists)) == len(twists), f"反转维度重复：{twists}"


def test_evaluate_marks_empty_concepts_reject(proj):
    """没填内容的方案必须被判 REJECT —— 不允许空壳通过。"""
    d = load(proj / "docs/01-brief/creative-concepts.json")
    ev = d["evaluation"]
    assert len(ev) == 5
    rejects = [e for e in ev if e["verdict"] == "REJECT"]
    assert len(rejects) >= 3, "空方案应被大量判 REJECT"
    assert all(e["total"] < 70 for e in rejects)


def test_evaluate_gives_evidence_for_every_item(dna_project):
    d = load(dna_project / "docs/01-brief/creative-concepts.json")
    for e in d["evaluation"]:
        assert e["items"], "评分必须有逐条明细"
        for it in e["items"]:
            assert it["note"].strip(), f"{e['concept_id']}/{it['code']} 缺证据说明"
        assert e["similarity"]["top_archetype"], "必须有相似原型对照"


def test_similarity_flags_known_archetype():
    """打地鼠式的结构必须被判为高相似（换皮检测真的有效）。"""
    import creative_forge as cf

    libs = cf.load_libs()
    whack = next(a for a in libs["archetypes"] if a["id"] == "whack_mole")
    concept = {
        "structure": {"spatial": "free", "time": "realtime", "info": "full",
                      "resource": "renewable", "risk": "reversible"},
        "unique_mechanic": {"name": "打地鼠", "one_sentence": "在时限内点到出现的东西"},
        "core_gameplay": "定点出现 + 限时点击 + 连击计分",
    }
    s, _hits = cf.similarity(concept, whack)
    assert s >= 0.7, f"与打地鼠重合度只有 {s}，换皮检测失效"
    assert cf.reskin_verdict(s) in ("HIGH", "MEDIUM")


def test_numeric_only_ignores_negation():
    """「不是变快，而是……」是反对数值推进，不能误判。"""
    import creative_forge as cf

    assert cf.numeric_only("推进不是变快，而是地图越来越不可信") == []
    assert cf.numeric_only("每关更快更多更强") != []
    assert cf.numeric_only("残影褪得更快") != []


def test_dna_skeleton_has_todo_then_filled_passes(dna_project):
    """骨架应有 _todo；填完后必须通过 schema + 语义校验。"""
    p = dna_project / "docs/01-brief/creative-dna.json"
    d = load(p)
    assert d.get("_todo"), "骨架应带 _todo 清单"

    fill_dna(dna_project)
    rc, out = run("creative_forge.py", "--project", dna_project, "--validate", "--strict")
    assert rc == 0, out
    assert "ERROR 0" in out


def test_dna_validate_rejects_numeric_progression(dna_project):
    """把推进方式改成纯数值，必须被语义校验拦住。"""
    p = dna_project / "docs/01-brief/creative-dna.json"
    d = load(p)
    d["gameplay"]["progression_identity"] = "每关敌人更多、速度更快、血量更高"
    p.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")

    rc, out = run("creative_forge.py", "--project", dna_project, "--validate", "--strict")
    assert rc == 2, out
    assert "数值加强" in out

    fill_dna(dna_project)  # 复原


def test_dna_validate_rejects_missing_license(dna_project):
    p = dna_project / "docs/01-brief/creative-dna.json"
    d = load(p)
    d["references"] = [{"pattern_id": "x", "source": "", "license": ""}]
    p.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")

    rc, out = run("creative_forge.py", "--project", dna_project, "--validate", "--strict")
    assert rc == 2
    assert "许可" in out

    fill_dna(dna_project)


def test_pattern_library_has_license_and_source():
    """任务书 §12.5：每个参考模式都必须记录来源与许可。"""
    from conftest import SKILL

    files = list((SKILL / "assets/data").rglob("*.json"))
    assert files, "模式库为空"
    for f in files:
        d = json.loads(f.read_text(encoding="utf-8"))
        if not isinstance(d, dict):
            continue
        assert d.get("source"), f"{f.name} 缺 source"
        assert d.get("license"), f"{f.name} 缺 license"
