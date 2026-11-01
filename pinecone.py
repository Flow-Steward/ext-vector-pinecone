"""Bounded dense vector and serverless lifecycle operations."""

import hashlib
import json
import math
import re
from urllib.parse import quote, urlencode
from transport import Transport, host_name
from validation import Failure, require, bounded_json, integer, text

WRITES = {
    "create_index",
    "configure_index_protection",
    "delete_index",
    "create_namespace",
    "delete_namespace",
    "upsert_vectors",
    "update_vector",
    "delete_vectors",
    "replace_document",
    "delete_document",
}
READS = {
    "list_indexes",
    "describe_index",
    "verify_schema",
    "list_namespaces",
    "describe_namespace",
    "index_stats",
    "fetch_vectors",
    "list_vectors",
    "query_vectors",
}


def identifier(v):
    text(v, "vector ID", 512, nonempty=True)
    require(
        not any(c.isspace() or ord(c) < 32 for c in v), "IDs cannot contain whitespace or controls."
    )
    return v


def vector(v, dimension):
    require(
        isinstance(v, list) and len(v) == dimension, "Vector dimension does not match connection."
    )
    require(
        all(type(x) in (int, float) and math.isfinite(x) and abs(x) <= 3.4028235e38 for x in v),
        "Vectors require finite float32 values.",
    )
    return v


def metadata(v):
    require(isinstance(v, dict) and len(v) <= 128, "Metadata must be a bounded object.")
    bounded_json(v, 40 * 1024)
    for k, x in v.items():
        text(k, "metadata key", 256, nonempty=True)
        require(not k.startswith("$"), "Invalid metadata key.")
        require(
            type(x) in (str, int, float, bool)
            or isinstance(x, list)
            and len(x) <= 1024
            and all(isinstance(s, str) for s in x),
            "Metadata requires flat values or string lists.",
        )
    return v


def document_metadata(chunk, document_id, generation, index):
    result = metadata(chunk.get("metadata", {})).copy()
    require(not any(k.startswith("_fs_") for k in result), "Reserved metadata key.")
    result.update(
        {
            "document_id": document_id,
            "text": text(chunk.get("text"), "chunk text", 32000, nonempty=True),
            "_fs_generation": generation,
            "chunk_index": index,
        }
    )
    return metadata(result)


def filters(v, depth=0):
    require(
        isinstance(v, dict) and bool(v) and depth <= 8 and len(v) <= 32, "Invalid metadata filter."
    )
    bounded_json(v, 16 * 1024)
    for k, x in v.items():
        if k in {"$and", "$or"}:
            require(isinstance(x, list) and 1 <= len(x) <= 32, "Invalid filter group.")
            for child in x:
                filters(child, depth + 1)
        else:
            require(
                isinstance(k, str) and not k.startswith("$") and len(k) <= 256,
                "Invalid filter field.",
            )
            require(isinstance(x, dict) and bool(x), "Filter operators required.")
            for op, val in x.items():
                require(
                    op in {"$eq", "$ne", "$gt", "$gte", "$lt", "$lte", "$in", "$nin", "$exists"},
                    "Unsupported filter operator.",
                )
                if op in {"$in", "$nin"}:
                    require(
                        isinstance(val, list)
                        and 1 <= len(val) <= 100
                        and all(type(i) in (str, int, float, bool) for i in val),
                        "Invalid membership filter.",
                    )
                elif op == "$exists":
                    require(type(val) is bool, "Exists requires boolean.")
                else:
                    require(type(val) in (str, int, float, bool), "Invalid comparison filter.")
    return v


class Client:
    def __init__(self, connection, context):
        c = connection.get("config") or {}
        s = connection.get("secrets") or {}
        require(
            isinstance(c, dict) and isinstance(s, dict),
            "Invalid connection.",
            code="invalid_connection",
        )
        require(
            set(c) <= {"index", "dimension", "metric", "index_host", "request_timeout_seconds"}
            and set(s) == {"api_key"},
            "Unknown connection settings.",
            code="invalid_connection",
        )
        self.index = c.get("index")
        require(
            isinstance(self.index, str) and re.fullmatch("[a-z0-9][a-z0-9-]{0,44}", self.index),
            "Invalid index.",
            code="invalid_connection",
        )
        self.dimension = integer(c.get("dimension"), "dimension", 1, 20000)
        self.metric = c.get("metric", "cosine")
        require(self.metric in {"cosine", "euclidean", "dotproduct"}, "Invalid metric.")
        key = text(s.get("api_key"), "api key", 8192, nonempty=True)
        require(
            not any(ord(x) < 33 or ord(x) > 126 for x in key),
            "Invalid key.",
            code="invalid_connection",
        )
        self.host = host_name(c["index_host"]) if c.get("index_host") else None
        self.transport = Transport(
            key, integer(c.get("request_timeout_seconds", 15), "timeout", 1, 30)
        )
        self.scope = hashlib.sha256(
            json.dumps(
                [context["account_id"], context["project_id"], connection["connection_id"]],
                separators=(",", ":"),
            ).encode()
        ).hexdigest()[:32]
        self.claim = context.get("external_effect_id", "")
        self.wrote = False

    def call(self, host, method, path, body=None, write=False):
        try:
            result = self.transport.request(host, method, path, body, write=write)
            self.wrote = self.wrote or write
            return result
        except Failure as exc:
            self.wrote = self.wrote or (
                write and (exc.dispatched or self.transport.attempted_write)
            )
            raise
        except Exception:
            self.wrote = self.wrote or write
            raise

    def validate(self, name, a):
        fields = {
            "create_index": {"cloud", "region"},
            "configure_index_protection": {"enabled", "confirm_index"},
            "delete_index": {"confirm_index"},
            "list_indexes": set(),
            "describe_index": set(),
            "verify_schema": set(),
            "create_namespace": set(),
            "describe_namespace": set(),
            "list_namespaces": {"limit", "pagination_token"},
            "delete_namespace": {"confirm"},
            "index_stats": set(),
            "list_vectors": {"prefix", "limit", "pagination_token"},
            "fetch_vectors": {"ids"},
            "delete_vectors": {"ids"},
            "upsert_vectors": {"vectors"},
            "update_vector": {"id", "values", "metadata"},
            "query_vectors": {"vector", "top_k", "filter"},
            "replace_document": {"document_id", "chunks"},
            "delete_document": {"document_id"},
        }
        require(name in fields, "Unknown Pinecone action.", code="unknown_action")
        require(set(a) <= fields[name] | {"connection_ref", "namespace"}, "Unknown input field.")
        ns = a.get("namespace", "default")
        require(
            isinstance(ns, str) and re.fullmatch("[A-Za-z0-9_-]{1,64}", ns),
            "Invalid logical namespace.",
        )
        if name == "create_index":
            require(a.get("cloud", "aws") in {"aws", "gcp", "azure"}, "Invalid cloud.")
            region = text(a.get("region"), "region", 64, nonempty=True)
            require(re.fullmatch("[a-z0-9-]+", region), "Invalid region.")
        if name == "configure_index_protection":
            require(type(a.get("enabled")) is bool, "enabled must be boolean.")
            require(a.get("confirm_index") == self.index, "Confirm configured index name.")
        if name == "delete_index":
            require(a.get("confirm_index") == self.index, "Confirm configured index name.")
        if name == "delete_namespace":
            require(a.get("confirm") is True, "Explicit namespace deletion confirmation required.")
        if name in {"list_namespaces", "list_vectors"}:
            integer(a.get("limit", 100), "limit", 1, 100)
            if "pagination_token" in a:
                text(a["pagination_token"], "pagination token", 4096)
            if "prefix" in a:
                text(a["prefix"], "prefix", 512)
        if name in {"fetch_vectors", "delete_vectors"}:
            ids = a.get("ids")
            require(isinstance(ids, list) and 1 <= len(ids) <= 100, "Require 1 to 100 IDs.")
            for value in ids:
                identifier(value)
        if name == "update_vector":
            identifier(a.get("id"))
            require("values" in a or "metadata" in a, "Values or metadata required.")
            if "values" in a:
                vector(a["values"], self.dimension)
            if "metadata" in a:
                m = metadata(a["metadata"])
                require(not any(k.startswith("_fs_") for k in m), "Reserved metadata key.")
        if name == "query_vectors":
            vector(a.get("vector"), self.dimension)
            integer(a.get("top_k", 10), "top_k", 1, 50)
            if a.get("filter") is not None:
                filters(a["filter"])
        if name == "upsert_vectors":
            records = a.get("vectors")
            require(
                isinstance(records, list) and 1 <= len(records) <= 100, "Require 1 to 100 vectors."
            )
            ids = []
            for record in records:
                require(
                    isinstance(record, dict) and set(record) <= {"id", "values", "metadata"},
                    "Invalid vector record.",
                )
                ids.append(identifier(record.get("id")))
                vector(record.get("values"), self.dimension)
                m = metadata(record.get("metadata", {}))
                require(not any(k.startswith("_fs_") for k in m), "Reserved metadata key.")
            require(len(set(ids)) == len(ids), "Duplicate vector IDs.")
        if name in {"replace_document", "delete_document"}:
            identifier(a.get("document_id"))
        if name == "replace_document":
            chunks = a.get("chunks")
            require(
                isinstance(chunks, list) and 1 <= len(chunks) <= 100, "Require 1 to 100 chunks."
            )
            for index, chunk in enumerate(chunks):
                require(
                    isinstance(chunk, dict) and set(chunk) <= {"text", "values", "metadata"},
                    "Invalid chunk.",
                )
                text(chunk.get("text"), "chunk text", 32000, nonempty=True)
                vector(chunk.get("values"), self.dimension)
                document_metadata(chunk, a["document_id"], "0" * 64, index)

    def execute(self, name, a):
        require(name in WRITES | READS, "Unknown Pinecone action.", code="unknown_action")
        ns = a.get("namespace", "default")
        require(
            isinstance(ns, str) and re.fullmatch("[A-Za-z0-9_-]{1,64}", ns),
            "Invalid logical namespace.",
        )
        ns = "fs-" + self.scope + "-" + ns
        if name == "query_vectors" and a.get("filter") is not None:
            filters(a["filter"])
        if name == "delete_index":
            require(a.get("confirm_index") == self.index, "Confirm configured index name.")
        path = "/indexes/" + self.index

        def control(method, p=path, b=None, write=False):
            return self.call("api.pinecone.io", method, p, b, write)

        if name == "configure_index_protection":
            return {
                "data": control(
                    "PATCH",
                    b={"deletion_protection": "enabled" if a["enabled"] else "disabled"},
                    write=True,
                )
            }
        if name == "list_indexes":
            return {"data": control("GET", "/indexes")}
        if name == "create_index":
            cloud = a.get("cloud", "aws")
            require(cloud in {"aws", "gcp", "azure"}, "Invalid cloud.")
            region = text(a.get("region"), "region", 64, nonempty=True)
            require(re.fullmatch("[a-z0-9-]+", region), "Invalid region.")
            return {
                "data": control(
                    "POST",
                    "/indexes",
                    {
                        "name": self.index,
                        "vector_type": "dense",
                        "dimension": self.dimension,
                        "metric": self.metric,
                        "spec": {"serverless": {"cloud": cloud, "region": region}},
                        "deletion_protection": "enabled",
                    },
                    True,
                )
            }
        if name == "delete_index":
            require(
                a.get("confirm_index") == self.index,
                "Confirm configured index name; deletion protection must be disabled separately.",
            )
            return {"data": control("DELETE", write=True)}
        # Describe before every data operation; never silently change an index schema.
        schema = control("GET")
        require(
            schema.get("dimension") == self.dimension
            and schema.get("metric") == self.metric
            and schema.get("vector_type", "dense") == "dense",
            "Index schema differs from connection.",
            code="schema_mismatch",
        )
        if name in {"describe_index", "verify_schema"}:
            return {"data": schema}
        require(
            schema.get("status", {}).get("ready") is True,
            "Index is not ready.",
            code="schema_mismatch",
        )
        host = host_name(schema.get("host"))
        require(
            not self.host or self.host == host,
            "Configured host differs from described index.",
            code="invalid_connection",
        )

        def data(method, p, b=None, write=False):
            return self.call(host, method, p, b, write)

        result = None
        if name == "create_namespace":
            result = data("POST", "/namespaces", {"name": ns}, True)
        elif name == "describe_namespace":
            result = data("GET", "/namespaces/" + quote(ns, safe=""))
        elif name == "list_namespaces":
            # Never reveal namespaces belonging to other project connections.
            q = {
                "limit": integer(a.get("limit", 100), "limit", 1, 100),
                "prefix": "fs-" + self.scope + "-",
            }
            if a.get("pagination_token"):
                q["paginationToken"] = text(a["pagination_token"], "pagination token", 4096)
            result = data("GET", "/namespaces?" + urlencode(q))
            result["namespaces"] = [
                n
                for n in result.get("namespaces", [])
                if n.get("name", "").startswith("fs-" + self.scope + "-")
            ]
        elif name == "delete_namespace":
            require(a.get("confirm") is True, "Explicit namespace deletion confirmation required.")
            result = data("DELETE", "/namespaces/" + quote(ns, safe=""), write=True)
        elif name == "index_stats":
            raw = data("POST", "/describe_index_stats", {})
            result = {
                "dimension": raw.get("dimension"),
                "namespace": ns,
                "namespace_stats": raw.get("namespaces", {}).get(ns, {}),
                "metric": self.metric,
            }
        elif name == "list_vectors":
            q = {"namespace": ns, "limit": integer(a.get("limit", 100), "limit", 1, 100)}
            for k, api in [("prefix", "prefix"), ("pagination_token", "paginationToken")]:
                if k in a:
                    q[api] = text(a[k], k, 4096)
            result = data("GET", "/vectors/list?" + urlencode(q))
        elif name in {"fetch_vectors", "delete_vectors"}:
            ids = a.get("ids")
            require(isinstance(ids, list) and 1 <= len(ids) <= 100, "Require 1 to 100 IDs.")
            ids = [identifier(i) for i in ids]
            if name == "fetch_vectors":
                result = data(
                    "GET",
                    "/vectors/fetch?" + urlencode([("namespace", ns)] + [("ids", i) for i in ids]),
                )
            else:
                result = data("POST", "/vectors/delete", {"namespace": ns, "ids": ids}, True)
        elif name == "update_vector":
            body = {"namespace": ns, "id": identifier(a.get("id"))}
            require("values" in a or "metadata" in a, "Values or metadata required.")
            if "values" in a:
                body["values"] = vector(a["values"], self.dimension)
            if "metadata" in a:
                body["setMetadata"] = metadata(a["metadata"])
                require(
                    not any(k.startswith("_fs_") for k in body["setMetadata"]),
                    "Reserved metadata key.",
                )
            result = data("POST", "/vectors/update", body, True)
        elif name in {"upsert_vectors", "replace_document"}:
            records = []
            if name == "replace_document":
                doc = identifier(a.get("document_id"))
                chunks = a.get("chunks")
                require(
                    isinstance(chunks, list) and 1 <= len(chunks) <= 100, "Require 1 to 100 chunks."
                )
                generation = hashlib.sha256(
                    json.dumps([self.claim, doc, chunks], sort_keys=True).encode()
                ).hexdigest()
                for i, c in enumerate(chunks):
                    require(isinstance(c, dict), "Invalid chunk.")
                    m = document_metadata(c, doc, generation, i)
                    records.append(
                        {
                            "id": hashlib.sha256(
                                (doc + ":" + generation + ":" + str(i)).encode()
                            ).hexdigest(),
                            "values": vector(c.get("values"), self.dimension),
                            "metadata": m,
                        }
                    )
            else:
                records = a.get("vectors")
                require(
                    isinstance(records, list) and 1 <= len(records) <= 100,
                    "Require 1 to 100 vectors.",
                )
                clean = []
                for rec in records:
                    require(
                        isinstance(rec, dict) and set(rec) <= {"id", "values", "metadata"},
                        "Invalid vector record.",
                    )
                    m = metadata(rec.get("metadata", {}))
                    require(not any(k.startswith("_fs_") for k in m), "Reserved metadata.")
                    clean.append(
                        {
                            "id": identifier(rec.get("id")),
                            "values": vector(rec.get("values"), self.dimension),
                            "metadata": m,
                        }
                    )
                records = clean
            require(len({r["id"] for r in records}) == len(records), "Duplicate vector IDs.")
            # Bounded pages; validate the complete batch before the first write.
            for start in range(0, len(records), 20):
                page = records[start : start + 20]
                ack = data("POST", "/vectors/upsert", {"namespace": ns, "vectors": page}, True)
                require(
                    ack.get("upsertedCount") == len(page),
                    "Invalid upsert acknowledgement.",
                    code="invalid_provider_response",
                )
            result = {"upserted_count": len(records), "namespace": ns}
            if name == "replace_document":
                data(
                    "POST",
                    "/vectors/delete",
                    {
                        "namespace": ns,
                        "filter": {
                            "$and": [
                                {"document_id": {"$eq": doc}},
                                {"_fs_generation": {"$ne": generation}},
                            ]
                        },
                    },
                    True,
                )
                result["document_id"] = doc
        elif name == "delete_document":
            result = data(
                "POST",
                "/vectors/delete",
                {
                    "namespace": ns,
                    "filter": {"document_id": {"$eq": identifier(a.get("document_id"))}},
                },
                True,
            )
        elif name == "query_vectors":
            body = {
                "namespace": ns,
                "vector": vector(a.get("vector"), self.dimension),
                "topK": integer(a.get("top_k", 10), "top_k", 1, 50),
                "includeMetadata": True,
                "includeValues": False,
            }
            if a.get("filter") is not None:
                body["filter"] = filters(a["filter"])
            raw = data("POST", "/query", body)
            matches = raw.get("matches")
            require(
                isinstance(matches, list) and len(matches) <= body["topK"],
                "Invalid query response.",
                code="invalid_provider_response",
            )
            sources = []
            for i, match in enumerate(matches):
                require(
                    isinstance(match, dict)
                    and type(match.get("score")) in (int, float)
                    and math.isfinite(match["score"]),
                    "Invalid query score.",
                    code="invalid_provider_response",
                )
                m = match.get("metadata") or {}
                require(
                    isinstance(m, dict), "Invalid query metadata.", code="invalid_provider_response"
                )
                sources.append(
                    {
                        "source_id": f"S{i + 1}",
                        "id": identifier(match.get("id")),
                        "score": match["score"],
                        "document_id": m.get("document_id"),
                        "text": m.get("text", ""),
                        "metadata": m,
                    }
                )
            return {"data": raw, "sources": sources, "namespace": ns}
        return {"data": result, "namespace": ns}
