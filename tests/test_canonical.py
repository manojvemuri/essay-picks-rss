from __future__ import annotations

from contextlib import suppress

import pytest
from hypothesis import given
from hypothesis import strategies as st

from essay_picks.canonical import canonicalize_url, validate_public_https_url
from essay_picks.errors import ValidationFailure


def test_canonicalize_removes_tracking_and_fragment_but_preserves_gift() -> None:
    url = "https://Example.COM/story/?utm_source=chatgpt&gift=abc#section"
    assert canonicalize_url(url) == "https://example.com/story/?gift=abc"


@pytest.mark.parametrize(
    "url",
    [
        "http://example.com/story",
        "https://localhost/story",
        "https://127.0.0.1/story",
        "https://10.0.0.1/story",
        "https://user@example.com/story",
        "https://example.com:8443/story",
        "https://app.localhost/story",
        "https://bad_host/story",
        "https://[not-an-ip]/story",
        "javascript:alert(1)",
    ],
)
def test_validate_public_https_url_rejects_unsafe_targets(url: str) -> None:
    with pytest.raises(ValidationFailure):
        validate_public_https_url(url)


@given(st.text(alphabet=st.characters(blacklist_categories=("Cs",)), max_size=100))
def test_canonicalization_never_raises_unexpected_errors(value: str) -> None:
    with suppress(ValidationFailure):
        canonicalize_url(value)


def test_public_global_ip_is_allowed_without_dns_lookup() -> None:
    assert canonicalize_url("https://8.8.8.8/story") == "https://8.8.8.8/story"
