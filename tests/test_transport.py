"""Exercise actual HTTP transport at the SDK boundary; no Pinecone credentials."""

import io
import json
from urllib.error import HTTPError
import pytest
import transport
from validation import Failure

HOST = "docs-123.svc.aped-123.pinecone.io"


@pytest.mark.parametrize(
    "host",
    [
        "evil.example",
        "pinecone.io.evil.example",
        "api.pinecone.io",
        "https://docs.pinecone.io",
        "docs.pinecone.io@evil.example",
        "docs.pinecone.io:443",
        "docs.pinecone.io/path",
        "DOCS.pinecone.io",
        "docs..pinecone.io",
    ],
)
def test_host_rejected(host):
    with pytest.raises(Failure):
        transport.host_name(host)


def test_pinned_request_headers_and_version(monkeypatch):
    seen = []
    monkeypatch.setattr(transport, "resolve_pinned_ips", lambda *a, **k: ["8.8.8.8"])

    class Response(io.BytesIO):
        status = 200

    def open_url(req, **kw):
        seen.append((req, kw))
        return Response(b'{"upsertedCount":1}')

    monkeypatch.setattr(transport, "open_pinned_url", open_url)
    t = transport.Transport("hidden", 15)
    assert t.request(
        HOST, "POST", "/vectors/upsert", {"namespace": "x", "vectors": []}, write=True
    ) == {"upsertedCount": 1}
    req, kw = seen[0]
    assert req.full_url == "https://" + HOST + "/vectors/upsert"
    assert req.get_header("Api-key") == "hidden"
    assert req.get_header("X-pinecone-api-version") == "2026-04"
    assert kw["pinned_ips"] == ("8.8.8.8",) and 0 < kw["timeout_seconds"] <= 15
    assert json.loads(req.data)["namespace"] == "x"


def test_private_dns_fails_before_write(monkeypatch):
    monkeypatch.setattr(transport, "resolve_pinned_ips", lambda *a, **k: ["127.0.0.1"])
    t = transport.Transport("hidden", 15)
    with pytest.raises(Failure):
        t.request(HOST, "POST", "/vectors/upsert", {}, write=True)
    assert not t.attempted_write


@pytest.mark.parametrize("status", [301, 307, 401, 403, 404, 429, 503])
def test_no_retry_redirect_or_provider_body_exposure(monkeypatch, status):
    monkeypatch.setattr(transport, "resolve_pinned_ips", lambda *a, **k: ["8.8.8.8"])
    calls = []

    def open_url(req, **kw):
        calls.append(req)
        raise HTTPError(req.full_url, status, "hidden-secret", {}, io.BytesIO(b"hidden-secret"))

    monkeypatch.setattr(transport, "open_pinned_url", open_url)
    t = transport.Transport("hidden-secret", 15)
    with pytest.raises(Failure) as raised:
        t.request(HOST, "POST", "/vectors/upsert", {}, write=True)
    assert len(calls) == 1 and raised.value.dispatched
    assert "hidden-secret" not in str(raised.value)


def test_expired_deadline_no_dns(monkeypatch):
    t = transport.Transport("hidden", 15)
    t.deadline = 0
    monkeypatch.setattr(
        transport, "resolve_pinned_ips", lambda *a, **k: pytest.fail("DNS after deadline")
    )
    with pytest.raises(Failure):
        t.request(HOST, "GET", "/namespaces")


def test_response_size_limit(monkeypatch):
    monkeypatch.setattr(transport, "resolve_pinned_ips", lambda *a, **k: ["8.8.8.8"])

    class Response(io.BytesIO):
        status = 200

    monkeypatch.setattr(
        transport, "open_pinned_url", lambda *a, **k: Response(b"x" * (480 * 1024 + 1))
    )
    with pytest.raises(Failure) as raised:
        transport.Transport("hidden", 15).request(HOST, "GET", "/namespaces")
    assert raised.value.code == "response_too_large"
