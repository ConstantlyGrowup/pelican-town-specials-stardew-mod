"""Redaction primitives for observability.

Anything that flows into structured logs or diagnostic bundles must be
scrubbed of secrets (API keys, Bearer tokens, launch tokens), sensitive
headers (Cookie/Authorization), query-string secrets, prompt fields,
business-record paths (``cookbook/``, ``drafts/``) and data-image payloads
before it leaves the machine. This module owns those primitives; the
structured logger and the diagnostics builder consume them.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any
from urllib.parse import quote, unquote

REDACTED = "[REDACTED]"

# Structured diagnostics keep only these fields (Task 19 Step 1/3). Any other
# field is dropped before it can reach a log line or diagnostic bundle.
LOG_FIELD_WHITELIST = frozenset(
    {
        "timestamp",
        "level",
        "requestId",
        "draftId",
        "attemptId",
        "stage",
        "errorCode",
        "elapsedMs",
        "modelId",
        "providerRequestId",
        "usage",
    }
)

_SENSITIVE_HEADERS = frozenset(
    {
        "authorization",
        "cookie",
        "set-cookie",
        "proxy-authorization",
        "x-pts-csrf",
        "x-pts-session",
        "x-pts-launch-token",
    }
)

_SENSITIVE_QUERY_KEYS = frozenset(
    {
        "token",
        "access_token",
        "api_key",
        "apikey",
        "auth",
        "authorization",
        "key",
        "secret",
        "password",
        "passwd",
        "signature",
        "sig",
        "launch",
    }
)

# All-lowercase so ``redact_value`` can compare ``key.lower()`` directly.
_SENSITIVE_VALUE_KEYS = frozenset(
    {
        "prompt",
        "api_key",
        "apikey",
        "authorization",
        "cookie",
        "password",
        "passwd",
        "secret",
        "token",
        "launch_token",
        "launchtoken",
        "access_token",
        "csrf",
        "x-pts-csrf",
        "x-pts-session",
        "x-pts-launch-token",
        # User context and matcher payloads are business content, not
        # aggregate usage telemetry. Keep token-count keys below untouched.
        "contexttext",
        "context_text",
        "matcherpayload",
        "matcher_payload",
        "matcherprompt",
        "matcher_prompt",
        "matcherrequest",
        "matcher_request",
        "matcherresponse",
        "matcher_response",
        "matchresponse",
        "match_response",
        "response",
    }
)

# Bearer scheme followed by a base64url-ish credential.
_BEARER_RE = re.compile(r"(?i)\bbearer\s+[a-z0-9._~+/=-]+")
# OpenAI-style sk-... keys.
_SK_KEY_RE = re.compile(r"\bsk-[a-z0-9_-]{8,}")
# Launch tokens / session ids / CSRF tokens are secrets.token_urlsafe(32),
# i.e. 43-char urlsafe base64 (mixed case). UUIDs are 36 chars, so 40+ keeps
# UUIDs intact.
_LAUNCH_TOKEN_RE = re.compile(r"\b[a-zA-Z0-9_-]{40,}\b")
# data:image URL payloads (data URL of a dish photo).
_DATA_URL_RE = re.compile(
    r"data:image(?:/[a-z0-9.+-]+)?(?:;base64)?,[a-z0-9+/=]*",
    re.IGNORECASE,
)
# Business-record path references that must never appear in diagnostics.
# Both POSIX (cookbook/dish-1) and Windows (drafts\abc\recipe.json) separators
# are matched.
_BUSINESS_PATH_RE = re.compile(
    r"(?i)\b(?:cookbook|drafts)[/\\][\w.()\[\]{} \\-]*"
)

_TOKEN_REDACTORS = (_BEARER_RE, _SK_KEY_RE, _LAUNCH_TOKEN_RE, _DATA_URL_RE)


def _redact_tokens(text: str) -> str:
    for regex in _TOKEN_REDACTORS:
        text = regex.sub(REDACTED, text)
    return text


def redact_text(text: str) -> str:
    """Replace every secret-shaped token in ``text`` with REDACTED.

    Query-string parameters are additionally URL-decoded and scrubbed so that
    encoded secrets (``token=sk-test%2Dsecret``) and encoded business paths
    (``next=%2Fdrafts%2Fabc``) do not survive.
    """
    redacted = _redact_tokens(text)
    return redact_query(redacted)


def redact_business_paths(text: str) -> str:
    """Replace cookbook/draft record path references with REDACTED."""
    return _BUSINESS_PATH_RE.sub(REDACTED, text)


def redact_headers(headers: Mapping[str, str]) -> dict[str, str]:
    """Return a copy of ``headers`` with sensitive values redacted."""
    redacted: dict[str, str] = {}
    for key, value in headers.items():
        lowered = key.lower()
        if lowered in _SENSITIVE_HEADERS or any(
            marker in lowered
            for marker in ("authorization", "cookie", "csrf", "token")
        ):
            redacted[key] = REDACTED
        else:
            redacted[key] = redact_text(value)
    return redacted


def redact_query(url: str) -> str:
    """Redact sensitive query-string parameter values in ``url``.

    Values are URL-decoded before inspection so encoded secrets (for example
    ``token=sk-test%2Dsecret``) and encoded business paths
    (``next=%2Fdrafts%2Fabc``) are caught too.
    """
    base, separator, query = url.partition("?")
    if not separator:
        return url
    redacted_parts: list[str] = []
    for part in query.split("&"):
        raw_key, eq, raw_value = part.partition("=")
        if not eq:
            redacted_parts.append(part)
            continue
        decoded_key = unquote(raw_key)
        decoded_value = unquote(raw_value)
        if decoded_key.lower() in _SENSITIVE_QUERY_KEYS:
            redacted_parts.append(f"{raw_key}={REDACTED}")
            continue
        redacted_value = redact_business_paths(_redact_tokens(decoded_value))
        if redacted_value != decoded_value:
            redacted_parts.append(f"{raw_key}={quote(redacted_value, safe='/')}")
        else:
            redacted_parts.append(part)
    return f"{base}?{'&'.join(redacted_parts)}"


def _scrub_leaf_text(text: str) -> str:
    return redact_business_paths(redact_text(text))


_SUBSTRING_SENSITIVE_MARKERS = (
    "prompt",
    "key",
    "token",
    "secret",
    "cookie",
    "password",
)


def _scrub_structure(value: Any) -> Any:
    """Recursively redact secrets and business paths from a JSON structure.

    Nested mappings apply key semantics through ``redact_value`` so a field
    named ``prompt``/``cookie``/``authorization`` inside ``usage`` cannot leak
    plaintext just because it is not at the top level.
    """
    if isinstance(value, Mapping):
        return {
            str(key): redact_value(str(key), item)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [_scrub_structure(item) for item in value]
    if isinstance(value, str):
        return _scrub_leaf_text(value)
    return value


def redact_json(value: Any) -> Any:
    """Recursively redact secrets and business paths from a JSON structure."""
    return _scrub_structure(value)


def redact_value(key: str, value: Any) -> Any:
    """Redact a single field value by its key and content, recursively.

    Dict/list values are traversed so nested secrets, ``data:image`` payloads
    and business paths are scrubbed at every level. Key semantics apply at
    every nesting level:

    - Exact members of ``_SENSITIVE_VALUE_KEYS`` (prompt, cookie,
      authorization, secret, token, ...) are fully redacted regardless of the
      value type, so a nested ``{"prompt": {"text": "..."}}`` cannot leak.
    - Keys that merely contain a sensitive marker (e.g. ``prompt_tokens``,
      ``x-api-key``) redact string values only; non-string telemetry such as
      integer token counts is preserved.
    """
    lowered = key.lower()
    if lowered in _SENSITIVE_VALUE_KEYS:
        return REDACTED
    if any(marker in lowered for marker in _SUBSTRING_SENSITIVE_MARKERS):
        if isinstance(value, str):
            return REDACTED
        return _scrub_structure(value)
    return _scrub_structure(value)


def redact_fields(fields: Mapping[str, Any]) -> dict[str, Any]:
    """Keep only whitelisted fields, redacting sensitive values recursively.

    Fields outside the structured-log whitelist are dropped entirely; the
    remaining values are scrubbed by key and content at every nesting level.
    """
    redacted: dict[str, Any] = {}
    for key, value in fields.items():
        if key not in LOG_FIELD_WHITELIST:
            continue
        redacted[key] = redact_value(key, value)
    return redacted
