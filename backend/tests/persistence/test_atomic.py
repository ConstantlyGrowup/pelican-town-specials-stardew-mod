from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from pelican_town_specials.persistence.atomic import (
    atomic_write_json,
    read_json_with_backup,
)


def _validate_payload(payload: object) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise TypeError("payload must be an object")
    if "value" not in payload:
        raise ValueError("payload must include value")
    return payload


def test_atomic_write_json_uses_canonical_utf8_lf_and_sorted_keys(
    tmp_path: Path,
) -> None:
    target = tmp_path / "record.json"

    atomic_write_json(
        target,
        {
            "zebra": 2,
            "alpha": {"beta": 1},
            "text": "鹈鹕镇新菜单",
        },
    )

    assert target.read_bytes().startswith(b"{\n")
    assert target.read_text(encoding="utf-8") == (
        "{\n"
        '  "alpha": {\n'
        '    "beta": 1\n'
        "  },\n"
        '  "text": "鹈鹕镇新菜单",\n'
        '  "zebra": 2\n'
        "}\n"
    )


def test_atomic_write_json_keeps_previous_file_when_replace_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = tmp_path / "record.json"
    target.write_text('{"value":"old"}\n', encoding="utf-8", newline="\n")

    replace_calls = 0

    def failing_replace(source: str | Path, destination: str | Path) -> None:
        nonlocal replace_calls
        replace_calls += 1
        raise OSError("simulated replace failure")

    monkeypatch.setattr(
        "pelican_town_specials.persistence.atomic.os.replace", failing_replace
    )

    with pytest.raises(OSError, match="simulated replace failure"):
        atomic_write_json(target, {"value": "new"})

    assert replace_calls == 1
    assert target.read_text(encoding="utf-8") == '{"value":"old"}\n'
    assert (
        target.with_suffix(".json.bak").read_text(encoding="utf-8")
        == '{"value":"old"}\n'
    )


def test_read_json_with_backup_recovers_from_valid_backup(tmp_path: Path) -> None:
    target = tmp_path / "record.json"
    target.write_text("{not-json", encoding="utf-8", newline="\n")
    target.with_suffix(".json.bak").write_text(
        '{\n  "value": "backup"\n}\n',
        encoding="utf-8",
        newline="\n",
    )

    payload = read_json_with_backup(target, _validate_payload)

    assert payload == {"value": "backup"}


def test_read_json_with_backup_rejects_invalid_backup(tmp_path: Path) -> None:
    target = tmp_path / "record.json"
    target.write_text("{not-json", encoding="utf-8", newline="\n")
    target.with_suffix(".json.bak").write_text(
        '{\n  "unexpected": "backup"\n}\n',
        encoding="utf-8",
        newline="\n",
    )

    with pytest.raises(ValueError, match="payload must include value"):
        read_json_with_backup(target, _validate_payload)
