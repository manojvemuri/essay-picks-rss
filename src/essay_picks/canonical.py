from __future__ import annotations

import ipaddress
import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from essay_picks.errors import ValidationFailure

TRACKING_KEYS = {
    "fbclid",
    "gclid",
    "mc_cid",
    "mc_eid",
    "mkt_tok",
}
HOST_RE = re.compile(
    r"^(?=.{1,253}$)(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)+"
    r"[A-Za-z]{2,63}$"
)


def validate_public_https_url(value: str) -> None:
    """Validate URL syntax without dereferencing or resolving the host."""
    try:
        parts = urlsplit(value)
        port = parts.port
    except ValueError as exc:
        raise ValidationFailure("URL is malformed", code="UNSAFE_URL") from exc

    if parts.scheme.lower() != "https":
        raise ValidationFailure("URL must use HTTPS", code="UNSAFE_URL")
    if not parts.hostname or parts.username or parts.password:
        raise ValidationFailure(
            "URL host is missing or contains user information", code="UNSAFE_URL"
        )
    if port not in (None, 443):
        raise ValidationFailure("URL uses a nonstandard port", code="UNSAFE_URL")

    hostname = parts.hostname.rstrip(".").lower()
    if hostname == "localhost" or hostname.endswith(".localhost"):
        raise ValidationFailure("Localhost URLs are not allowed", code="UNSAFE_URL")

    try:
        address = ipaddress.ip_address(hostname)
    except ValueError as exc:
        if not HOST_RE.fullmatch(hostname):
            raise ValidationFailure(
                "URL host is not a public domain name", code="UNSAFE_URL"
            ) from exc
    else:
        if not address.is_global:
            raise ValidationFailure("Non-public IP addresses are not allowed", code="UNSAFE_URL")


def canonicalize_url(value: str) -> str:
    """Return a conservative canonical URL while preserving unknown query parameters."""
    validate_public_https_url(value)
    parts = urlsplit(value)
    hostname = (parts.hostname or "").rstrip(".").lower()
    query = [
        (key, item)
        for key, item in parse_qsl(parts.query, keep_blank_values=True)
        if not key.lower().startswith("utm_") and key.lower() not in TRACKING_KEYS
    ]
    query.sort()
    path = parts.path or "/"
    netloc = hostname
    return urlunsplit(("https", netloc, path, urlencode(query, doseq=True), ""))
