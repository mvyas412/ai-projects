from __future__ import annotations

import json
import tomllib
from pathlib import Path

import pytest

from backend.app.visual import artifacts

ROOT = Path(__file__).parents[1]


def test_docling_package_guard_and_lock_match_security_patch() -> None:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text())
    lock = tomllib.loads((ROOT / "uv.lock").read_text())
    assert "docling==2.132.0" in project["project"]["dependencies"]
    assert artifacts.DOCLING_PACKAGE_VERSION == "2.132.0"
    for name in ("docling", "docling-slim"):
        packages = [package for package in lock["package"] if package["name"] == name]
        assert packages and all(package["version"] == "2.132.0" for package in packages)


@pytest.mark.parametrize(
    ("name", "version"),
    [("next", "16.3.8"), ("sharp", "0.35.5"), ("source-map-js", "1.2.2")],
)
def test_candidate_lock_excludes_flagged_dependency_versions(name: str, version: str) -> None:
    candidate = ROOT / "frontend-next"
    project = json.loads((candidate / "package.json").read_text())
    lock = json.loads((candidate / "package-lock.json").read_text())
    if name == "next":
        assert project["dependencies"][name] == version
        assert lock["packages"][""]["dependencies"][name] == version
    else:
        assert project["overrides"][name] == version
    packages = [
        package
        for path, package in lock["packages"].items()
        if path.endswith(f"node_modules/{name}")
    ]
    assert packages and all(package["version"] == version for package in packages)


def test_docling_package_change_keeps_reviewed_model_tree_and_fails_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert artifacts.DOCLING_MODEL_PROFILE == "docling-layout-tableformer-v1"
    assert artifacts.DOCLING_MODEL_TREE_SHA256 == (
        "84c523c99eb4e43b36ebf5aee678b66c7017b18ff4db3de22b67dcd2ab3a92cc"
    )
    monkeypatch.setattr(artifacts, "version", lambda _: "2.124.0")
    with pytest.raises(artifacts.VisualModelArtifactError, match="pinned Docling"):
        artifacts.inspect_docling_artifacts(tmp_path)


def test_next_native_packages_track_the_patched_release() -> None:
    lock = json.loads((ROOT / "frontend-next/package-lock.json").read_text())
    packages = [
        package
        for path, package in lock["packages"].items()
        if path.startswith("node_modules/@next/")
    ]
    assert packages and all(package["version"] == "16.3.8" for package in packages)
