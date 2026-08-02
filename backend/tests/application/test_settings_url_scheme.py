from __future__ import annotations

import pytest
from pydantic import ValidationError

from pelican_town_specials.application.settings import ProviderSettings


def test_base_url_rejects_non_http_scheme() -> None:
    with pytest.raises(ValidationError):
        ProviderSettings(baseUrl="ftp://example.test/v1")
