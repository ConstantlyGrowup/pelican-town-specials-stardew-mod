"""Explicit capability probe CLI tests (no network without a key)."""

from __future__ import annotations

from pathlib import Path

import pytest
import scripts.probe_provider as probe


def test_probe_without_key_reports_unsupported_without_network(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PTS_OPENAI_API_KEY", "")

    capabilities = probe._run_probe()

    assert capabilities.chat_multimodal.supported is False
    assert capabilities.image_edits.supported is False
    assert capabilities.image_generations.supported is False


def test_probe_writes_redacted_report(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("PTS_OPENAI_API_KEY", "")
    output_path = tmp_path / "provider-capabilities.json"
    monkeypatch.setattr(probe, "_OUTPUT_PATH", output_path)

    probe.main()

    text = output_path.read_text(encoding="utf-8")
    assert '"supported": false' in text
    assert "sk-" not in text
