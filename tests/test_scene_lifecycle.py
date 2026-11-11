"""场景生命周期契约检查器：真实调用脚本验证 PASS/FAIL 行为。"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

SKILL = Path(__file__).resolve().parent.parent
CHECK = SKILL / "scripts" / "check_scene_lifecycle.mjs"
NODE = shutil.which("node") or shutil.which("node.exe")


def _find_typescript() -> Path | None:
    candidates = [
        SKILL.parent / "tower-defense" / "node_modules" / "typescript",
        SKILL.parent / "simulator" / "node_modules" / "typescript",
        Path.cwd() / "node_modules" / "typescript",
    ]
    return next((p for p in candidates if (p / "lib" / "typescript.js").exists()), None)


TYPESCRIPT = _find_typescript()
pytestmark = pytest.mark.skipif(not NODE or not TYPESCRIPT, reason="需要 node 与 TypeScript 依赖")


def _project(tmp_path: Path, source: str) -> Path:
    root = tmp_path / "project"
    scenes = root / "src" / "game" / "scenes"
    scenes.mkdir(parents=True)
    (root / "package.json").write_text('{"private": true}', encoding="utf-8")
    (scenes / "MenuScene.ts").write_text(source, encoding="utf-8")
    return root


def _run(project: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [NODE or "node", str(CHECK), "--project", str(project), "--typescript", str(TYPESCRIPT)],
        cwd=str(project),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
    )


def test_sync_create_passes(tmp_path):
    project = _project(
        tmp_path,
        "class MenuScene {\n"
        "  create() { this.load(); }\n"
        "  async load() { await Promise.resolve(); }\n"
        "}\n",
    )
    result = _run(project)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "PASS: 1 create()" in result.stdout


def test_async_create_fails(tmp_path):
    project = _project(
        tmp_path,
        "class MenuScene {\n"
        "  async create() { await Promise.resolve(); }\n"
        "}\n",
    )
    result = _run(project)
    assert result.returncode == 1, result.stdout + result.stderr
    assert "async create() is forbidden" in result.stderr
    assert "direct await inside create()" in result.stderr


def test_await_in_nested_callback_is_allowed(tmp_path):
    project = _project(
        tmp_path,
        "class MenuScene {\n"
        "  create() {\n"
        "    const onClick = async () => { await Promise.resolve(); };\n"
        "    onClick();\n"
        "  }\n"
        "}\n",
    )
    result = _run(project)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "PASS: 1 create()" in result.stdout
