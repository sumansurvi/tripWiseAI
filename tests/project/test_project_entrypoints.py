from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

import main


REPO_ROOT = Path(__file__).resolve().parents[2]


def test_root_package_has_expected_scripts() -> None:
    package_path = REPO_ROOT / "package.json"
    data = json.loads(package_path.read_text(encoding="utf-8"))
    scripts = data.get("scripts", {})
    assert scripts["dev"] == "npm run dev --prefix phases/frontend/phase-11-chat-ui"
    assert scripts["build"] == "npm run build --prefix phases/frontend/phase-11-chat-ui"
    assert scripts["install:ui"] == "npm install --prefix phases/frontend/phase-11-chat-ui"


def test_frontend_prefix_target_exists() -> None:
    frontend_dir = REPO_ROOT / "phases" / "frontend" / "phase-11-chat-ui"
    assert frontend_dir.is_dir()
    assert (frontend_dir / "package.json").is_file()


def test_main_delegates_to_phase5_runner(monkeypatch: pytest.MonkeyPatch) -> None:
    called = {}

    class Loader:
        def exec_module(self, module: object) -> None:
            called["module"] = module

    spec = importlib.util.spec_from_loader("tripwise_run_phase5", Loader())
    fake_module = SimpleNamespace(main=lambda argv: 7)

    monkeypatch.setattr(main, "RUN_PHASE5", Path("/tmp/run_phase5.py"))
    monkeypatch.setattr(importlib.util, "spec_from_file_location", lambda *_: spec)
    monkeypatch.setattr(importlib.util, "module_from_spec", lambda _spec: fake_module)

    assert main.main(["--x"]) == 7
    assert called["module"] is fake_module


def test_main_returns_1_when_phase5_spec_is_missing(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    missing_path = Path("/tmp/missing_run_phase5.py")
    monkeypatch.setattr(main, "RUN_PHASE5", missing_path)
    monkeypatch.setattr(importlib.util, "spec_from_file_location", lambda *_: None)

    assert main.main() == 1
    stderr = capsys.readouterr().err
    assert f"Cannot load {missing_path}" in stderr
