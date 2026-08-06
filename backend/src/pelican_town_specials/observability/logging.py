"""Structured, redacted logging for Pelican Town Specials observability.

A rotating file handler writes JSON lines whose keys are restricted to the
observability whitelist. Total log size is bounded (20 MiB by default) and
stale files are purged after the retention window (7 days by default). The
diagnostics builder consumes the same files.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime, timedelta
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

from .redaction import redact_business_paths, redact_fields, redact_text

DEFAULT_TOTAL_MAX_BYTES = 20 * 1024 * 1024  # 20 MiB
DEFAULT_BACKUP_COUNT = 6
DEFAULT_MAX_DAYS = 7
LOG_FILE_NAME = "pts-structured.log"
LOG_FILE_PREFIX = "pts-structured"

_LOGGER_NAME = "pelican_town_specials.observability"
_LEGACY_LEVEL = "WARN"


def _iso_now() -> str:
    return (
        datetime.now(UTC)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z")
    )


def configure_logging(
    log_dir: Path,
    *,
    total_max_bytes: int = DEFAULT_TOTAL_MAX_BYTES,
    backup_count: int = DEFAULT_BACKUP_COUNT,
    level: int = logging.INFO,
    max_days: int = DEFAULT_MAX_DAYS,
) -> Path:
    """Install the redacting rotating handler on the observability logger.

    ``total_max_bytes`` is the total budget across all log files. The per-file
    limit is ``total // (backup_count + 2)`` so the ``backup_count`` rotated
    files plus the active file stay strictly under the budget.

    Existing expired files are purged and any rotated files beyond
    ``backup_count`` are trimmed so a previous run's accumulation never breaks
    the retention window or the total size bound.
    """
    log_dir.mkdir(parents=True, exist_ok=True)
    purge_expired_logs(log_dir, max_days=max_days)
    _trim_excess_rotated(log_dir, backup_count)
    log_path = log_dir / LOG_FILE_NAME
    per_file = max(1, total_max_bytes // (backup_count + 2))
    handler = RotatingFileHandler(
        log_path,
        maxBytes=per_file,
        backupCount=backup_count,
        encoding="utf-8",
    )
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger = logging.getLogger(_LOGGER_NAME)
    logger.setLevel(level)
    logger.propagate = False
    logger.handlers.clear()
    logger.addHandler(handler)
    return log_path


def log_event(
    level: int,
    *,
    request_id: str | None = None,
    draft_id: str | None = None,
    attempt_id: str | None = None,
    stage: str | None = None,
    error_code: str | None = None,
    elapsed_ms: int | None = None,
    model_id: str | None = None,
    provider_request_id: str | None = None,
    usage: object | None = None,
    **extra_fields: Any,
) -> None:
    """Emit one structured, redacted JSON log line.

    Only the whitelisted observability fields are written; any other keyword
    argument is ignored. Values are scrubbed by ``redact_fields``.
    """
    fields: dict[str, Any] = {
        "timestamp": _iso_now(),
        "level": logging.getLevelName(level),
    }
    values: dict[str, Any] = {
        "requestId": request_id,
        "draftId": draft_id,
        "attemptId": attempt_id,
        "stage": stage,
        "errorCode": error_code,
        "elapsedMs": elapsed_ms,
        "modelId": model_id,
        "providerRequestId": provider_request_id,
        "usage": usage,
    }
    for key, value in values.items():
        if value is not None:
            fields[key] = value
    fields.update(extra_fields)
    redacted = redact_fields(fields)
    line = json.dumps(redacted, ensure_ascii=False, separators=(",", ":"))
    logging.getLogger(_LOGGER_NAME).log(level, line)


def read_log_lines(log_dir: Path) -> list[dict[str, Any]]:
    """Parse and redact every non-expired structured log file under ``log_dir``.

    Expired files are purged first so stale records can never reach a
    diagnostic bundle or a reader.
    """
    records: list[dict[str, Any]] = []
    if not log_dir.is_dir():
        return records
    purge_expired_logs(log_dir)
    for path in sorted(log_dir.glob(f"{LOG_FILE_PREFIX}*")):
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for raw in text.splitlines():
            if not raw.strip():
                continue
            try:
                payload = json.loads(raw)
            except json.JSONDecodeError:
                records.append(_legacy_record(raw))
                continue
            if isinstance(payload, dict):
                records.append(redact_fields(payload))
    return records


def _legacy_record(raw: str) -> dict[str, Any]:
    redacted = redact_business_paths(redact_text(raw))
    # Non-JSON lines must still respect the field whitelist: the redacted raw
    # text is carried under the whitelisted ``usage`` field (namespaced as
    # ``legacyLine``) rather than a non-whitelisted ``message`` key.
    return {"level": _LEGACY_LEVEL, "usage": {"legacyLine": redacted}}


def _trim_excess_rotated(log_dir: Path, backup_count: int) -> int:
    """Remove rotated files beyond ``backup_count``. Returns count removed.

    ``RotatingFileHandler`` only rotates the active file and would leave stale
    extra rotations from a previous run (e.g. a larger ``backup_count``) on
    disk; trimming them here keeps the on-disk total bounded at startup.
    """
    removed = 0
    for path in log_dir.glob(f"{LOG_FILE_PREFIX}.log.*"):
        suffixes = path.suffixes
        if not suffixes:
            continue
        try:
            sequence = int(suffixes[-1].lstrip("."))
        except ValueError:
            continue
        if sequence > backup_count:
            try:
                path.unlink()
                removed += 1
            except OSError:
                continue
    return removed


def purge_expired_logs(
    log_dir: Path,
    *,
    max_days: int = DEFAULT_MAX_DAYS,
) -> int:
    """Delete structured log files older than ``max_days``. Returns count."""
    if not log_dir.is_dir():
        return 0
    cutoff = datetime.now(UTC) - timedelta(days=max_days)
    removed = 0
    for path in log_dir.glob(f"{LOG_FILE_PREFIX}*"):
        if not path.is_file():
            continue
        try:
            mtime = datetime.fromtimestamp(path.stat().st_mtime, UTC)
        except OSError:
            continue
        if mtime < cutoff:
            try:
                path.unlink()
                removed += 1
            except OSError:
                continue
    return removed
