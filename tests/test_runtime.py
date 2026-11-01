"""Independent Pinecone wire-contract and failure phase regression tests."""

import json
from copy import deepcopy
import pytest
import main
import pinecone


def envelope(name, **args):
    return {
        "contract_version": "extension_host_v2",
        "mode": "action",
        "runtime_context": {
            "contract_version": "extension_host_v2",
            "account_id": "a",
            "project_id": "p",
            "group_id": "g",
            "for_each_id": None,
            "step_id": "s",
            "step_execution_id": "e",
            "external_effect_id": "claim",
        },
        "action": {
            "action_id": name,
            "input": {"connection_ref": "c", **args},
            "target": {
                "connection": {
                    "connection_id": "c",
                    "connection_type": "pinecone",
                    "config": {"index": "docs", "dimension": 2},
                    "secrets": {"api_key": "SECRET"},
                }
            },
        },
    }


@pytest.fixture
def wire(monkeypatch):
    calls = []

    def request(self, host, method, path, body=None, **kw):
        calls.append((host, method, path, deepcopy(body)))
        if path == "/indexes/docs":
            return {
                "name": "docs",
                "dimension": 2,
                "metric": "cosine",
                "vector_type": "dense",
                "host": "docs-abc.svc.aped-123.pinecone.io",
                "status": {"ready": True},
            }
        if path == "/query":
            return {
                "matches": [
                    {
                        "id": "v1",
                        "score": 0.8,
                        "metadata": {"document_id": "doc", "text": "Evidence"},
                    }
                ]
            }
        if path.startswith("/vectors/fetch"):
            return {"vectors": {"v1": {"id": "v1", "values": [1, 0]}}}
        if path == "/vectors/upsert":
            return {"upsertedCount": len(body["vectors"])}
        return {}

    monkeypatch.setattr(pinecone.Transport, "request", request)
    return calls


def test_crud_and_scoped_query(wire):
    for action, args in [
        ("upsert_vectors", {"vectors": [{"id": "v1", "values": [1, 0]}]}),
        ("fetch_vectors", {"ids": ["v1"]}),
        ("update_vector", {"id": "v1", "values": [0, 1]}),
        ("query_vectors", {"vector": [1, 0]}),
        ("delete_vectors", {"ids": ["v1"]}),
    ]:
        result = main.handle(envelope(action, **args))
        assert result["ok"], result
    query = next(c for c in wire if c[2] == "/query")
    assert query[3]["includeMetadata"] is True
    assert query[3]["namespace"].startswith("fs-")
    result = main.handle(envelope("query_vectors", vector=[1, 0]))["result"]
    assert result["sources"][0]["text"] == "Evidence" and result["sources"][0]["score"] == 0.8


def test_namespace_account_project_connection_isolation(wire):
    names = []
    for field in [None, "account_id", "project_id"]:
        p = envelope("create_namespace")
        if field:
            p["runtime_context"][field] = "other"
        assert main.handle(p)["ok"]
        names.append(wire[-1][3]["name"])
    assert len(set(names)) == 3


@pytest.mark.parametrize(
    "name,args",
    [
        ("delete_index", {"confirm_index": "docs"}),
        ("create_namespace", {}),
        ("delete_namespace", {"confirm": True}),
        ("upsert_vectors", {"vectors": [{"id": "v", "values": [1, 2]}]}),
    ],
)
def test_writes_suppress_before_network(wire, name, args):
    p = envelope(name, **args)
    p["runtime_context"]["test_mode"] = True
    assert main.handle(p)["error_code"] == "test_mode_suppressed"
    assert not wire
    p["runtime_context"]["test_mode"] = False
    p["runtime_context"].pop("external_effect_id")
    assert main.handle(p)["error_code"] == "effect_claim_required"
    assert not wire


@pytest.mark.parametrize(
    "args",
    [
        {"vectors": [{"id": "x", "values": [float("nan"), 0]}]},
        {"vectors": [{"id": "x", "values": [1]}]},
        {"vectors": [{"id": "x" * 513, "values": [1, 0]}]},
    ],
)
def test_invalid_vectors_no_write(wire, args):
    r = main.handle(envelope("upsert_vectors", **args))
    assert not r["ok"]
    assert not any(c[1] == "POST" for c in wire)


def test_filter_rejected_and_size_bound(wire):
    assert not main.handle(envelope("query_vectors", vector=[1, 0], filter={"$where": "attack"}))[
        "ok"
    ]
    assert not main.handle(
        envelope("query_vectors", vector=[1, 0], filter={"x": {"$eq": "x" * 300000}})
    )["ok"]
    assert not wire


def test_delete_confirm_and_schema_mismatch(wire):
    assert not main.handle(envelope("delete_index"))["ok"]
    assert not wire
    p = envelope("upsert_vectors", vectors=[{"id": "v", "values": [1, 0]}])
    p["action"]["target"]["connection"]["config"]["dimension"] = 3
    assert not main.handle(p)["ok"]
    assert not any(c[1] == "POST" for c in wire)


def test_unknown_write_and_redacted_failure(monkeypatch):
    def fail(self, *a, **kw):
        raise pinecone.Failure("provider_unavailable", "Pinecone request failed.", dispatched=True)

    monkeypatch.setattr(pinecone.Transport, "request", fail)
    r = main.handle(envelope("upsert_vectors", vectors=[{"id": "v", "values": [1, 0]}]))
    assert r["definitely_no_external_effect"] is True  # failure while describing schema
    assert "SECRET" not in json.dumps(r)


def test_replace_document_generation_then_stale_delete(wire):
    p = envelope(
        "replace_document",
        document_id="d",
        chunks=[{"text": "one", "values": [1, 0]}, {"text": "two", "values": [0, 1]}],
    )
    r = main.handle(p)
    assert r["ok"], r
    writes = [c for c in wire if c[1] == "POST"]
    assert writes[0][2] == "/vectors/upsert" and writes[-1][2] == "/vectors/delete"
    assert writes[-1][3]["filter"]["$and"][0] == {"document_id": {"$eq": "d"}}
    assert "$ne" in writes[-1][3]["filter"]["$and"][1]["_fs_generation"]


def test_partial_write_unknown(monkeypatch, wire):
    original = pinecone.Transport.request

    def fail(self, host, method, path, body=None, **kw):
        if path == "/vectors/delete":
            raise pinecone.Failure(
                "provider_unavailable", "Pinecone request failed.", dispatched=True
            )
        return original(self, host, method, path, body, **kw)

    monkeypatch.setattr(pinecone.Transport, "request", fail)
    r = main.handle(
        envelope("replace_document", document_id="d", chunks=[{"text": "one", "values": [1, 0]}])
    )
    assert not r["ok"] and r["external_effect_status"] == "timeout_unknown" and not r["retryable"]


def test_namespace_pagination_wire_contract(wire):
    from urllib.parse import parse_qs, urlsplit

    r = main.handle(envelope("list_namespaces", pagination_token="opaque+token", limit=2))
    assert r["ok"], r
    query = parse_qs(urlsplit(wire[-1][2]).query)
    assert query["paginationToken"] == ["opaque+token"]
    assert query["prefix"][0].startswith("fs-")


def test_lifecycle_control_plane_and_no_implicit_update(wire):
    r = main.handle(envelope("create_index", region="us-east-1"))
    assert r["ok"], r
    assert wire[-1][:3] == ("api.pinecone.io", "POST", "/indexes")
    assert wire[-1][3]["dimension"] == 2
    assert wire[-1][3]["spec"] == {"serverless": {"cloud": "aws", "region": "us-east-1"}}
    assert wire[-1][3]["deletion_protection"] == "enabled"
    assert main.handle(envelope("verify_schema"))["ok"]
    assert not any(c[1] == "PATCH" for c in wire)
    assert main.handle(envelope("delete_index", confirm_index="docs"))["ok"]
    assert wire[-1][:3] == ("api.pinecone.io", "DELETE", "/indexes/docs")


def test_all_write_operations_claim_and_test_mode(wire):
    samples = {
        "create_index": {"region": "us-east-1"},
        "configure_index_protection": {"enabled": False, "confirm_index": "docs"},
        "delete_index": {"confirm_index": "docs"},
        "create_namespace": {},
        "delete_namespace": {"confirm": True},
        "upsert_vectors": {"vectors": [{"id": "v", "values": [1, 0]}]},
        "update_vector": {"id": "v", "values": [1, 0]},
        "delete_vectors": {"ids": ["v"]},
        "replace_document": {"document_id": "d", "chunks": [{"text": "one", "values": [1, 0]}]},
        "delete_document": {"document_id": "d"},
    }
    assert set(samples) == pinecone.WRITES
    for action, args in samples.items():
        p = envelope(action, **args)
        p["runtime_context"]["test_mode"] = True
        assert main.handle(p)["error_code"] == "test_mode_suppressed"
        p["runtime_context"]["test_mode"] = False
        del p["runtime_context"]["external_effect_id"]
        assert main.handle(p)["error_code"] == "effect_claim_required"
    assert wire == []


@pytest.mark.parametrize(
    "args",
    [
        {"vectors": [{"id": "v", "values": [1]}]},
        {"vectors": [{"id": "v", "values": [1, 0]}], "unknown": True},
        {"vectors": [{"id": "v", "values": [1, 0], "unknown": True}]},
    ],
)
def test_invalid_write_precedes_suppression(wire, args):
    p = envelope("upsert_vectors", **args)
    p["runtime_context"]["test_mode"] = True
    assert main.handle(p)["error_code"] == "invalid_payload"
    assert wire == []


def test_invalid_connection_precedes_suppression(wire):
    p = envelope("create_namespace")
    p["runtime_context"]["test_mode"] = True
    p["action"]["target"]["connection"]["config"]["index_host"] = "evil.example"
    assert main.handle(p)["error_code"] == "invalid_connection"
    assert wire == []


def test_complete_input_validation_before_first_page(wire):
    records = [{"id": str(i), "values": [1, 0]} for i in range(21)]
    records[-1]["values"] = [1]
    assert not main.handle(envelope("upsert_vectors", vectors=records))["ok"]
    assert not any(c[2] == "/vectors/upsert" for c in wire)


def test_bounded_pages_and_preserved_metadata(wire):
    records = [
        {"id": str(i), "values": [1, 0], "metadata": {"text": "evidence"}} for i in range(41)
    ]
    assert main.handle(envelope("upsert_vectors", vectors=records))["ok"]
    pages = [c[3]["vectors"] for c in wire if c[2] == "/vectors/upsert"]
    assert list(map(len, pages)) == [20, 20, 1]
    assert pages[-1][0]["metadata"]["text"] == "evidence"


def test_configure_protection_is_explicit_confirmed_write(wire):
    assert main.handle(envelope("configure_index_protection", enabled=False, confirm_index="docs"))[
        "ok"
    ]
    assert wire[-1] == (
        "api.pinecone.io",
        "PATCH",
        "/indexes/docs",
        {"deletion_protection": "disabled"},
    )
    wire.clear()
    assert not main.handle(
        envelope("configure_index_protection", enabled=False, confirm_index="other")
    )["ok"]
    assert not wire
