"""Redaction unit tests (Task 19 Step 1).

Covers T19-REDACTION-001: secret-shaped tokens (API keys, Bearer tokens,
launch tokens), sensitive headers (Cookie/Authorization), query-string
secrets, prompt fields, data-image payloads, and the structured log field
whitelist.
"""

from __future__ import annotations

from pelican_town_specials.observability.redaction import (
    LOG_FIELD_WHITELIST,
    REDACTED,
    redact_business_paths,
    redact_fields,
    redact_headers,
    redact_query,
    redact_text,
    redact_value,
)


def test_redact_text_hides_openai_style_api_keys() -> None:
    result = redact_text("provider key is sk-test-secret and must stay local")

    assert "sk-test-secret" not in result
    assert REDACTED in result


def test_redact_text_hides_bearer_tokens() -> None:
    result = redact_text("Authorization: Bearer sk-bearer-secret-1234567890")

    assert "sk-bearer-secret" not in result
    assert REDACTED in result


def test_redact_text_hides_launch_tokens() -> None:
    token = "nX8oQ2wE9rT4yU6iOpA1sDfGhJkLzXcVbNmQwErTyUiOpAsDfG"
    result = redact_text(f"open app at http://127.0.0.1:43127/#launch={token}")

    assert token not in result
    assert REDACTED in result


def test_redact_text_hides_data_image_payloads() -> None:
    data_url = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
    result = redact_text(f"vision payload {data_url}")

    assert "data:image" not in result
    assert "iVBORw0KGgo" not in result
    assert REDACTED in result


def test_redact_text_leaves_short_plain_ids_untouched() -> None:
    text = "draft 1234 updated stage DISH_ANALYSIS request req-1"
    assert redact_text(text) == text


def test_redact_headers_redacts_cookie_and_authorization() -> None:
    headers = {
        "Host": "127.0.0.1:8000",
        "Cookie": "PTS_SESSION=session-secret-token-123",
        "Authorization": "Bearer sk-header-secret-1234567890",
        "X-PTS-CSRF": "csrf-secret-value",
        "X-Custom": "keep-me",
    }
    redacted = redact_headers(headers)

    assert redacted["Cookie"] == REDACTED
    assert redacted["Authorization"] == REDACTED
    assert redacted["X-PTS-CSRF"] == REDACTED
    assert redacted["Host"] == "127.0.0.1:8000"
    assert redacted["X-Custom"] == "keep-me"


def test_redact_query_redacts_sensitive_parameters() -> None:
    url = "https://example.test/path?token=secret-token&launch=launch-value&page=2"
    redacted = redact_query(url)

    assert "secret-token" not in redacted
    assert "launch-value" not in redacted
    assert "page=2" in redacted


def test_redact_fields_keeps_only_whitelisted_fields() -> None:
    fields = {
        "timestamp": "2026-08-06T00:00:00Z",
        "level": "INFO",
        "requestId": "req-1",
        "draftId": "draft-1",
        "prompt": "make a pumpkin soup",
        "internalNote": "should never leak",
    }
    redacted = redact_fields(fields)

    assert set(redacted.keys()) <= LOG_FIELD_WHITELIST
    assert "internalNote" not in redacted
    assert redacted["requestId"] == "req-1"


def test_redact_value_redacts_prompt_and_secret_values() -> None:
    assert redact_value("prompt", "draw sk-test-secret data:image/png;base64,AAAA") == REDACTED
    assert redact_value("apiKey", "sk-test-secret") == REDACTED
    assert redact_value("Authorization", "Bearer sk-header-secret-123") == REDACTED
    assert redact_value("requestId", "req-1") == "req-1"


def test_redact_fields_drops_prompt_and_secret_values() -> None:
    fields = {
        "requestId": "req-1",
        "attemptId": "attempt-1",
        "prompt": "draw sk-test-secret and data:image/png;base64,AAAA",
        "apiKey": "sk-test-secret",
    }
    redacted = redact_fields(fields)

    assert set(redacted.keys()) <= LOG_FIELD_WHITELIST
    assert "sk-test-secret" not in str(redacted)
    assert "data:image" not in str(redacted)


def test_redact_business_paths_hides_cookbook_and_draft_records() -> None:
    text = "referencing cookbook/dish-1 and drafts/draft-1 and drafts/ask-gus-42"
    redacted = redact_business_paths(text)

    assert "cookbook/" not in redacted
    assert "drafts/" not in redacted


def test_redact_business_paths_hides_windows_backslash_paths() -> None:
    text = r"C:\workspace\app-state\drafts\abc\recipe.json and cookbook\recipes\dish-1.json"
    redacted = redact_business_paths(text)

    assert "drafts" not in redacted
    assert "cookbook" not in redacted
    assert REDACTED in redacted


def test_redact_query_decodes_encoded_secrets_and_paths() -> None:
    url = (
        "https://example.test/path"
        "?next=%2Fdrafts%2Fabc&token=sk-test%2Dsecret&page=2"
    )
    redacted = redact_query(url)

    assert "sk-test-secret" not in redacted
    assert "sk-test%2Dsecret" not in redacted
    assert "drafts" not in redacted
    assert "page=2" in redacted


def test_redact_text_applies_query_redaction() -> None:
    text = "queried https://example.test/path?token=sk-test%2Dsecret"
    redacted = redact_text(text)

    assert "sk-test-secret" not in redacted
    assert REDACTED in redacted


def test_redact_fields_recursively_redacts_nested_secrets() -> None:
    fields = {
        "requestId": "req-1",
        "usage": {
            "prompt": "sk-test-secret",
            "image": "data:image/png;base64,AAAA",
            "tokens": {"total": 10},
        },
    }
    redacted = redact_fields(fields)

    assert set(redacted.keys()) <= LOG_FIELD_WHITELIST
    assert "sk-test-secret" not in str(redacted)
    assert "data:image" not in str(redacted)
    assert redacted["usage"]["tokens"]["total"] == 10


def test_redact_value_recurses_into_nested_lists_and_dicts() -> None:
    value = [
        "sk-test-secret",
        {"path": "cookbook/dish-1", "payload": ["data:image/png;base64,AAAA"]},
    ]
    redacted = redact_value("usage", value)

    assert "sk-test-secret" not in str(redacted)
    assert "cookbook" not in str(redacted)
    assert "data:image" not in str(redacted)


def test_redact_value_redacts_nested_prompt_and_cookie() -> None:
    redacted = redact_value(
        "usage", {"prompt": "plaintext", "cookie": "session=xyz"}
    )

    assert redacted["prompt"] == REDACTED
    assert redacted["cookie"] == REDACTED


def test_redact_fields_redacts_nested_prompt_and_cookie() -> None:
    fields = {
        "requestId": "req-1",
        "usage": {"prompt": "plaintext", "cookie": "session=xyz"},
    }
    redacted = redact_fields(fields)

    assert redacted["usage"]["prompt"] == REDACTED
    assert redacted["usage"]["cookie"] == REDACTED


def test_redact_value_redacts_sensitive_key_with_dict_value() -> None:
    assert redact_value("prompt", {"text": "x"}) == REDACTED


def test_redact_value_redacts_mixed_case_sensitive_key_with_dict_value() -> None:
    assert redact_value("launchToken", {"value": "launch secret"}) == REDACTED
    assert redact_value("apiKey", {"value": "x"}) == REDACTED


def test_redact_value_preserves_numeric_telemetry_substring_keys() -> None:
    usage = {"prompt_tokens": 123, "completion_tokens": 456}
    redacted = redact_value("usage", usage)

    assert redacted == usage


def test_redact_value_removes_context_and_matcher_content_but_keeps_token_counts() -> None:
    usage = {
        "contextText": "user context",
        "context_text": "user context snake case",
        "matcherPayload": "candidate payload",
        "matcher_prompt": "candidate prompt",
        "matcherResponse": "candidate response",
        "response": "raw matcher response",
        "prompt": "raw user prompt",
        "prompt_tokens": 123,
        "completion_tokens": 456,
        "total_tokens": 579,
    }

    redacted = redact_value("usage", usage)

    for key in (
        "contextText",
        "context_text",
        "matcherPayload",
        "matcher_prompt",
        "matcherResponse",
        "response",
        "prompt",
    ):
        assert redacted[key] == REDACTED
    assert redacted["prompt_tokens"] == 123
    assert redacted["completion_tokens"] == 456
    assert redacted["total_tokens"] == 579
