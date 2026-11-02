"""pytest 公共夹具：所有测试都通过**真实调用脚本**来验证，不 import 内部函数替代执行。

为什么这么设计：v3 之前的 20 个脚本零测试，改判据只能靠手工跑一个真实项目看输出。
这里的原则是「测可执行的行为」——子进程跑脚本、读它落盘的文件、断言退出码。
这样测试挂掉时，说明真实链路坏了，而不是断言写法变了。
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

SKILL = Path(__file__).resolve().parent.parent
SCRIPTS = SKILL / "scripts"
SCHEMAS = SKILL / "references" / "schemas"

# 让测试可以直接 import 脚本模块（测内部纯函数时用），同时保证脚本自己的 _common 可导入
for _p in (str(SCRIPTS), str(Path(__file__).resolve().parent)):
    if _p not in sys.path:
        sys.path.insert(0, _p)


def run(script: str, *args: str, cwd: Path | None = None, timeout: int = 180):
    """跑一个脚本，返回 (returncode, stdout+stderr)。"""
    cmd = [sys.executable, str(SCRIPTS / script), *[str(a) for a in args]]
    r = subprocess.run(cmd, cwd=str(cwd) if cwd else None, capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=timeout)
    return r.returncode, (r.stdout or "") + (r.stderr or "")


@pytest.fixture(scope="session")
def proj(tmp_path_factory) -> Path:
    """建一个干净的测试项目（走 init_project.py，与真实流程一致）。"""
    root = tmp_path_factory.mktemp("i2g")
    p = root / "demo"
    rc, out = run("init_project.py", "--name", "demo",
                  "--idea", "守一座会失去光的灯塔，你只能靠光和声音判断黑暗里的东西",
                  "--platforms", "crazygames", "--genre", "puzzle", "--out", root)
    assert rc == 0, out
    assert (p / ".gamedev" / "state.yaml").exists()
    return p


def fill_concept(proj: Path, cid: str = "C1") -> None:
    """把某个创意方案填成能通过评估的内容（模拟 Agent 的工作，不是造假数据）。"""
    p = proj / "docs/01-brief/creative-concepts.json"
    d = load(p)
    c = next(x for x in d["concepts"] if x["id"] == cid)
    c["game_title"] = "测试之灯"
    c["one_liner"] = "你发出一声，世界亮一瞬；黑暗也听见了你。"
    c["core_fantasy"] = "我想成为雾里唯一还敢发出声音的人，用声音丈量世界也用声音付出代价"
    c["world"] = ("雾海没有方向只有回声。黑暗吞掉光却吞不掉声音；"
                  "听见你的东西会朝你走来；记忆是唯一的货币，用完就没有了。")
    c["signature_scene"] = ("记忆归零的那一刻所有残影同时褪成黑，只剩船头一盏将熄的灯和水纹；"
                            "你听见左前方三格处有桨声，于是闭着眼划了过去。")
    c["unique_mechanic"].update({
        "id": "listen_locate_audio_gated",
        "name": "回声残影",
        "one_sentence": "你发出的每一声都会留下一张会腐烂的地图。",
        "why_unique": "视野不是被给予的，是被借来的；借来的地图会过期，而世界不会等你。",
        "interacts": ["echo_exposure", "memory_budget", "ghost_drift"],
        "changes_decision": "原本会一直敲钟保持全图可见，现在每敲一次都在烧掉唯一的地图。",
        "signature_moment": "最后一格记忆用掉的那一刻全图同时熄灭，只剩心跳和远处桨声。",
    })
    c["supporting_mechanics"] = [
        {"id": "echo_exposure", "name": "回声暴露", "role": "twist",
         "interacts": ["listen_locate_audio_gated", "memory_budget"]},
        {"id": "memory_budget", "name": "记忆格", "role": "pressure",
         "interacts": ["listen_locate_audio_gated", "ghost_drift"]},
        {"id": "ghost_drift", "name": "残影漂移", "role": "twist",
         "interacts": ["listen_locate_audio_gated", "memory_budget"]},
    ]
    c["player_decisions"] = [
        {"question": "现在敲钟确认方向，还是凭上一次的回声赌一把",
         "cost": "敲钟消耗一格记忆并让附近的东西朝你靠近一步", "cadence": "per_second"},
        {"question": "把最后一格记忆留给落水者，还是留给自己靠岸",
         "cost": "救人多渡一个灵魂，但你可能在无光中撞上礁石", "cadence": "per_level"},
    ]
    c["audio_style"]["identity"] = "木质船体吱呀 + 远处海浪 + 单音钢琴"
    c.pop("_todo", None)
    p.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")


def fill_concept(proj: Path, cid: str = "C1") -> None:
    """把某个创意方案填成能通过评估的内容（模拟 Agent 的工作，不是造假数据）。"""
    p = proj / "docs/01-brief/creative-concepts.json"
    d = load(p)
    c = next(x for x in d["concepts"] if x["id"] == cid)
    c["game_title"] = "测试之灯"
    c["one_liner"] = "你发出一声，世界亮一瞬；黑暗也听见了你。"
    c["core_fantasy"] = "我想成为雾里唯一还敢发出声音的人，用声音丈量世界也用声音付出代价"
    c["world"] = ("雾海没有方向只有回声。黑暗吞掉光却吞不掉声音；"
                  "听见你的东西会朝你走来；记忆是唯一的货币，用完就没有了。")
    c["signature_scene"] = ("记忆归零的那一刻所有残影同时褪成黑，只剩船头一盏将熄的灯和水纹；"
                            "你听见左前方三格处有桨声，于是闭着眼划了过去。")
    c["unique_mechanic"].update({
        "id": "listen_locate_audio_gated",
        "name": "回声残影",
        "one_sentence": "你发出的每一声都会留下一张会腐烂的地图。",
        "why_unique": "视野不是被给予的，是被借来的；借来的地图会过期，而世界不会等你。",
        "interacts": ["echo_exposure", "memory_budget", "ghost_drift"],
        "changes_decision": "原本会一直敲钟保持全图可见，现在每敲一次都在烧掉唯一的地图。",
        "signature_moment": "最后一格记忆用掉的那一刻全图同时熄灭，只剩心跳和远处桨声。",
    })
    c["supporting_mechanics"] = [
        {"id": "echo_exposure", "name": "回声暴露", "role": "twist",
         "interacts": ["listen_locate_audio_gated", "memory_budget"]},
        {"id": "memory_budget", "name": "记忆格", "role": "pressure",
         "interacts": ["listen_locate_audio_gated", "ghost_drift"]},
        {"id": "ghost_drift", "name": "残影漂移", "role": "twist",
         "interacts": ["listen_locate_audio_gated", "memory_budget"]},
    ]
    c["player_decisions"] = [
        {"question": "现在敲钟确认方向，还是凭上一次的回声赌一把",
         "cost": "敲钟消耗一格记忆并让附近的东西朝你靠近一步", "cadence": "per_second"},
        {"question": "把最后一格记忆留给落水者，还是留给自己靠岸",
         "cost": "救人多渡一个灵魂，但你可能在无光中撞上礁石", "cadence": "per_level"},
    ]
    c["audio_style"]["identity"] = "木质船体吱呀 + 远处海浪 + 单音钢琴"
    c.pop("_todo", None)
    p.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")


@pytest.fixture(scope="session")
def dna_project(proj: Path) -> Path:
    """跑到 Creative DNA 就绪的项目（供后续测试复用，避免重复跑）。"""
    rc, out = run("creative_forge.py", "--project", proj, "--diverge", "--n", "5")
    assert rc == 0, out
    fill_concept(proj, "C1")
    rc, out = run("creative_forge.py", "--project", proj, "--evaluate")
    assert rc == 0, out
    rc, out = run("creative_forge.py", "--project", proj, "--dna", "--pick", "C1", "--force")
    assert rc == 0, out
    # asset_forge 需要蓝图（它从 blueprint.art 取 roles_required）
    rc, out = run("content_forge.py", "--project", proj, "--scaffold")
    assert rc == 0, out
    return proj


def load(p: Path):
    return json.loads(Path(p).read_text(encoding="utf-8"))


def fill_dna(proj: Path) -> Path:
    """把 DNA 骨架填成可通过校验的最小完整内容（模拟 Agent 的工作）。"""
    p = proj / "docs/01-brief/creative-dna.json"
    d = load(p)
    cid = d["meta"]["concept_id"]
    d["identity"].update({
        "game_title": "测试之灯",
        "core_fantasy": "我想成为雾里唯一还敢发出声音的人，用声音丈量世界",
        "unique_hook": "你发出的每一声都会留下一张会腐烂的地图",
        "creative_promise": "你会体验到明明看见过却不敢确定它还算不算数的紧张",
        "signature_moment": "最后一格记忆用掉的瞬间整片海熄灭，只剩心跳和远处桨声",
    })
    d["gameplay"].update({
        "progression_identity": "推进不是变快，而是你的地图越来越不可信：残影褪得更快、记忆不再回复",
        "fail_state": "被吞没时只留下最后一次敲钟的残影",
        "win_condition": "把 3 个灵魂送上岸",
        "supporting_mechanics": [
            {"id": "echo_exposure", "name": "回声暴露", "role": "twist",
             "interacts": [d["gameplay"]["core_mechanic"]["id"]]},
            {"id": "memory_budget", "name": "记忆格", "role": "pressure",
             "interacts": [d["gameplay"]["core_mechanic"]["id"]]},
        ],
    })
    d["gameplay"]["core_mechanic"].update({
        "one_sentence": "你发出的每一声都会留下一张会腐烂的地图",
        "why_unique": "视野不是被给予的，是被借来的；借来的地图会过期",
        "interacts": ["echo_exposure", "memory_budget"],
        "changes_decision": "原本会一直敲钟保持全图可见，现在每敲一次都在烧掉唯一的地图",
        "signature_moment": "最后一格记忆用掉的那一刻全图同时熄灭",
    })
    d["gameplay"]["player_decisions"] = [
        {"question": "现在敲钟确认方向，还是凭上一次的回声赌一把", "cost": "消耗一格记忆并暴露自己",
         "cadence": "per_second"},
        {"question": "把最后一格记忆留给落水者，还是留给自己靠岸", "cost": "救人多渡一个灵魂但可能撞礁",
         "cadence": "per_level"},
    ]
    d["narrative"].update({
        "world_rules": ["黑暗吞掉光但吞不掉声音", "发出声音的东西会被听见", "记忆用完就无法恢复"],
        "theme": "记住的代价是不敢再确认",
        "narrative_mechanic_link": "第三条世界规则被写成机制：记忆格就是确认世界的次数",
    })
    d["visual"].update({
        "style_identity": "水墨 × 水彩绘本（留白保证可读性，晕染制造记忆感）",
        "visual_keywords": ["washi paper", "ink wash", "wet watercolor", "brass lantern", "sea fog"],
        "palette": {"primary": ["#0E1B2A", "#1B3A4B", "#2E5D6B", "#4A8A8C", "#E8DCC0"],
                    "accent": ["#F2C14A"], "danger": "#C6463C", "background": "#08121C",
                    "ratio": {"background": 0.6}},
        "materials": ["washi paper", "ink wash"],
        "lighting": "单一侧光自左上来，2700K 偏暖，衰减极快",
        "camera": "俯视 45 度斜角",
        "shape_language": "圆润的船与方硬的礁石对比",
        "shadow_rules": "单层软投影，方向与主光一致",
        "ui_language": "线框 + 单一强调色，圆角 0",
        "typography": "系统无衬线，28/18/14 三档",
        "character_ratio": "1:1.2 横向剪影",
        "animation_style": "慢入快出，循环带呼吸停顿",
        "fx_style": "水纹扩散圈 + 墨点飞溅，不用发光粒子",
    })
    d["audio"].update({
        "audio_identity": "木质船体吱呀 + 远处海浪 + 单音钢琴",
        "music_mood": ["exploration", "danger"],
        "instrumentation": ["wood_creak", "sea_waves", "felt_piano"],
        "sound_signature": ["敲钟后的回声三连", "记忆消耗的木质轻响"],
        "dynamic_audio_rules": [
            {"when": "敲钟瞬间", "change": "全部 stem 压低 6dB 让回声成为主角"},
            {"when": "记忆 ≤1", "change": "环境声衰减 70%，加入心跳"},
        ],
        "sound_as_gameplay": {"enabled": True, "mechanic": "回声定位", "why": "声音携带视觉不提供的信息"},
    })
    d["experience"].update({
        "target_emotions": [{"emotion": "孤独", "weight": 0.6}, {"emotion": "紧张", "weight": 0.4}],
        "player_memory": "你会记得钟响之后海面亮起来又暗下去的样子",
        "first_10s": "第一次敲钟，海面亮起，你看见三个影子",
        "first_30s": "你接住第一个灵魂，听到它唱了一句",
    })
    d["references"] = [{"pattern_id": "listen_locate", "source": "原创整理", "license": "CC0-1.0",
                        "how_used": "取其信息隐藏 + 不可逆指纹"}]
    d.pop("_todo", None)
    p.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
    return p
