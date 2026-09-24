"""Release runner installs the pinned RAG builder closure, not runtime deps."""

from __future__ import annotations

import tomllib
from pathlib import Path


def test_release_workflow_installs_the_pinned_build_group() -> None:
    repository_root = Path(__file__).resolve().parents[3]
    project = tomllib.loads(
        (repository_root / "backend" / "pyproject.toml").read_text(encoding="utf-8")
    )
    workflow = (repository_root / ".github" / "workflows" / "build.yml").read_text(
        encoding="utf-8"
    )

    assert project["dependency-groups"]["build"] == [
        "huggingface-hub==1.29.0",
        "onnx==1.21.0",
        "tokenizers==0.23.2",
        "sympy==1.14.0",
    ]
    assert "python -m pip install --group dev --group build -e ." in workflow

    runtime_dependencies = project["project"]["dependencies"]
    assert not any(
        dependency.lower().startswith(("huggingface-hub", "onnx==", "tokenizers=="))
        for dependency in runtime_dependencies
    )

    spec = (
        repository_root / "packaging" / "pyinstaller" / "PelicanTownSpecials.spec"
    ).read_text(encoding="utf-8")
    excludes = spec.split("excludes=[", maxsplit=1)[1].split("],", maxsplit=1)[0]
    assert all(
        f'"{module}"' in excludes
        for module in ("huggingface_hub", "onnx", "tokenizers")
    )
