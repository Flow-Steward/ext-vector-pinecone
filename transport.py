"""Pinecone-only HTTPS, pinned DNS, strict TLS and no redirects/retries."""

import ipaddress
import json
import re
import time
from urllib.request import Request
from urllib.error import HTTPError
from flowsteward_extension_sdk import open_pinned_url, resolve_pinned_ips
from validation import Failure, require


def host_name(value):
    require(
        isinstance(value, str)
        and len(value) <= 253
        and re.fullmatch(
            r"[a-z0-9](?:[a-z0-9-]*[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]*[a-z0-9])?)*\.pinecone\.io",
            value,
        ),
        "Invalid Pinecone index host.",
        code="invalid_connection",
    )
    require(
        value != "api.pinecone.io",
        "Control plane cannot be a data host.",
        code="invalid_connection",
    )
    return value


class Transport:
    def __init__(self, key, timeout):
        self.key = key
        self.deadline = time.monotonic() + timeout
        self.pins = {}
        self.attempted_write = False

    def request(self, host, method, path, body=None, *, write=False):
        require(
            host == "api.pinecone.io" or host_name(host), "Invalid host.", code="invalid_connection"
        )
        require(path.startswith("/") and not path.startswith("//"), "Invalid API path.")
        remaining = self.deadline - time.monotonic()
        require(remaining > 0, "Operation deadline exceeded.", code="timeout")
        if host not in self.pins:
            try:
                pins = tuple(resolve_pinned_ips(host, port=443, purpose="Pinecone API"))
                require(
                    bool(pins) and all(ipaddress.ip_address(p).is_global for p in pins),
                    "Pinecone endpoint blocked.",
                    code="network_blocked",
                )
                self.pins[host] = pins
            except (OSError, ValueError) as exc:
                raise Failure("network_blocked", "Pinecone endpoint blocked.") from exc
        encoded = None if body is None else json.dumps(body, allow_nan=False).encode()
        request = Request(
            "https://" + host + path,
            data=encoded,
            method=method,
            headers={
                "Api-Key": self.key,
                "Content-Type": "application/json",
                "Accept": "application/json",
                "X-Pinecone-Api-Version": "2026-04",
            },
        )
        remaining = self.deadline - time.monotonic()
        require(remaining > 0, "Operation deadline exceeded.", code="timeout")
        try:
            self.attempted_write = self.attempted_write or write
            with open_pinned_url(
                request,
                timeout_seconds=remaining,
                purpose="Pinecone API",
                pinned_ips=self.pins[host],
            ) as response:
                require(
                    response.status < 300,
                    "Unexpected Pinecone response.",
                    code="invalid_provider_response",
                )
                raw = response.read(480 * 1024 + 1)
                require(
                    len(raw) <= 480 * 1024,
                    "Pinecone response exceeds inline limit.",
                    code="response_too_large",
                )
        except HTTPError as exc:
            codes = {
                401: "authentication_failed",
                403: "authentication_failed",
                404: "not_found",
                409: "conflict",
                429: "rate_limited",
            }
            raise Failure(
                codes.get(exc.code, "provider_unavailable"),
                f"Pinecone returned HTTP {exc.code}.",
                dispatched=write,
            ) from exc
        except Failure:
            raise
        except Exception as exc:
            raise Failure(
                "provider_unavailable", "Pinecone request failed.", dispatched=write
            ) from exc
        if not raw and method == "DELETE":
            return {}
        try:
            data = json.loads(raw)
            require(
                isinstance(data, dict),
                "Invalid Pinecone JSON response.",
                code="invalid_provider_response",
            )
            return data
        except (ValueError, TypeError) as exc:
            raise Failure(
                "invalid_provider_response", "Invalid Pinecone JSON response.", dispatched=write
            ) from exc
