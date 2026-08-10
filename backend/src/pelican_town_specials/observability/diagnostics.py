"""Diagnostic bundle builder.

A diagnostic bundle is an in-memory ZIP containing only app/OS/version/
schema/capability summaries, error/stage summaries and redacted structured
logs. It never contains business records (drafts/cookbook), image payloads
or secrets.
"""

from __future__ import annotations

import io
import json
import platform
import sys
import zipfile
from collections.abc import Mapping
from pathlib import Path

from pelican_town_specials.persistence.workspace import WorkspacePaths

from .logging import read_log_lines
from .redaction import redact_json, redact_value

APP_NAME = "PelicanTownSpecials"
APP_VERSION = "1.1.0"
API_VERSION = "v1"


class DiagnosticsBuilder:
    """Builds an in-memory diagnostic ZIP for a workspace."""

    def __init__(
        self,
        *,
        workspace: WorkspacePaths,
        logs_dir: Path | None = None,
        app_name: str = APP_NAME,
        app_version: str = APP_VERSION,
        api_version: str = API_VERSION,
        schema_version: int = 1,
        capabilities: Mapping[str, object] | None = None,
    ) -> None:
        self._workspace = workspace
        self._logs_dir = logs_dir or workspace.app_state_dir / "logs"
        self._app_name = app_name
        self._app_version = app_version
        self._api_version = api_version
        self._schema_version = schema_version
        self._capabilities = dict(capabilities or {})

    def build(self, request_id: str) -> bytes:
        records = self._scrub_logs(read_log_lines(self._logs_dir))
        payloads = {
            "app.json": self._json(
                {
                    "app": redact_value("app", self._app_name),
                    "version": redact_value("version", self._app_version),
                    "apiVersion": redact_value(
                        "apiVersion", self._api_version
                    ),
                    "schemaVersion": redact_value(
                        "schemaVersion", self._schema_version
                    ),
                    "requestId": redact_value("requestId", request_id),
                }
            ),
            "os.json": self._json(self._os_summary()),
            "capabilities.json": self._json(redact_json(self._capabilities)),
            "errors.json": self._json(
                [record for record in records if "errorCode" in record]
            ),
            "stages.json": self._json(
                [record for record in records if "stage" in record]
            ),
            "logs.json": self._json(records),
        }
        return self._to_zip(payloads)

    @staticmethod
    def _scrub_logs(
        records: list[dict[str, object]],
    ) -> list[dict[str, object]]:
        scrubbed: list[dict[str, object]] = []
        for record in records:
            item: dict[str, object] = {}
            for key, value in record.items():
                item[key] = redact_value(key, value)
            scrubbed.append(item)
        return scrubbed

    @staticmethod
    def _os_summary() -> dict[str, str]:
        return {
            "platform": sys.platform,
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
            "python": platform.python_version(),
        }

    @staticmethod
    def _json(value: object) -> str:
        return json.dumps(value, ensure_ascii=False, indent=2)

    @staticmethod
    def _to_zip(payloads: Mapping[str, str]) -> bytes:
        buffer = io.BytesIO()
        with zipfile.ZipFile(
            buffer, "w", compression=zipfile.ZIP_DEFLATED
        ) as handle:
            for name in sorted(payloads):
                handle.writestr(name, payloads[name])
        return buffer.getvalue()
