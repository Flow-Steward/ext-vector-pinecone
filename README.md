# Pinecone Vector Database for Flow Steward

Flow Steward extension `flowsteward.pinecone`, version **1.0.3**.

Use Pinecone as a dense vector store for Flow Steward search and document retrieval workflows. Insert or update vectors with metadata, fetch or delete records by ID, list vectors by prefix, and query an embedding with metadata filters. Retrieval returns scores and source information such as record IDs, document IDs and stored text, so a later workflow step can assemble context for an answer or select related records.

The extension also manages index and namespace lifecycle: create a serverless index, list or inspect indexes, verify dimensions and metric, change deletion protection, and create, inspect, list or delete namespaces. Document replacement accepts prepared text chunks and their vectors, writes a new generation, and removes older generations; document deletion removes the selected document’s chunks.

Data operations use namespaces tied to the account, project and connection. Index administration operates at the wider Pinecone project level, so use a dedicated index when that separation matters. Supply embeddings and answer generation through other steps. Vector batches accept up to 100 records and searches return up to 50 matches, with pagination controls for larger record listings.

Create a project Pinecone connection with index name, vector dimension, metric and secret API key; an optional index host can pin the expected endpoint. Use a ready dense index, or create a serverless index with cloud and region, and provide embeddings from a separate provider.

## Connection

Select a project connection of type `pinecone`; config requires `index` (lowercase name, max 45 characters), `dimension` (1–20000), optionally `metric` (`cosine`, `euclidean`, `dotproduct`), `index_host` (hostname only), and `request_timeout_seconds` (1–30, default 15). Secret: `api_key`. The action's `connection_ref` must match the selected connection ID. Both account and project context are required.

Control plane is fixed to `https://api.pinecone.io`. Data hosts come from the configured index's describe response, must be lowercase subdomains of `.pinecone.io`, and must match `index_host` when set. DNS resolves through the SDK and only public IPs are accepted; pinned HTTPS verifies TLS hostname/certificate, disallows redirects and does not retry. Keys and provider error bodies are never returned. A process-level wall-clock alarm covers the entire operation, including DNS and response reads; per-request socket timeouts also use the remaining budget. The supported Linux host-v2 entrypoint is a single-threaded subprocess.

## Operations

All actions accept `connection_ref`, and optional logical `namespace` (default `default`, 1–64 letters, digits, underscores or hyphens). Physical namespace is `fs-<sha256(account_id, project_id, connection_id)[:32]>-<namespace>`. Data operations cannot select another account/project/connection namespace. Use a dedicated index per project connection if index administration must also be isolated: index create/delete/list/describe operate at Pinecone project scope and index deletion affects every namespace. `list_namespaces` removes names belonging to other connection scopes; `index_stats` only returns the selected namespace's counts.

- `create_index`: `region`, optional `cloud` (`aws` default, `gcp`, `azure`). Creates a dense serverless index with configured dimension/metric and deletion protection enabled. Provisioning is asynchronous; call `describe_index` until ready. Existing indexes are never implicitly modified.
- `list_indexes`, `describe_index`, `verify_schema`: index lifecycle and dimension/metric checks. Every data action describes the index and requires a ready, matching dense schema before data I/O.
- `configure_index_protection`: `enabled` (boolean), `confirm_index` (configured name). Explicitly enables/disables deletion protection using PATCH; does not alter dimension, metric, region or cloud.
- `delete_index`: `confirm_index` must equal the configured name. Call `configure_index_protection` first to disable protection explicitly; deletion never disables it automatically.
- `create_namespace`, `describe_namespace`, `list_namespaces` (`limit` 1–100 and opaque `pagination_token`), `delete_namespace` (`confirm: true`). Namespace lifecycle is serverless-only. Namespace creation indexes metadata using Pinecone's default schema; custom metadata schema management is outside this release.
- `index_stats`, `list_vectors` (`limit` 1–100, optional `prefix`, `pagination_token`). Pagination is explicit, with no unbounded scan. A filtered namespace page can be empty while retaining the provider's next token.
- `upsert_vectors`: 1–100 `{id, values, metadata?}` records; finite vectors must exactly match dimension. IDs are nonempty strings up to 512 UTF-8 bytes without whitespace or controls. Upsert pages are at most 20 records. Metadata is flat scalar/string-list data, at most 40KiB per record. `_fs_` fields are reserved.
- `fetch_vectors`, `delete_vectors`: 1–100 `ids`. No unscoped delete-all operation.
- `update_vector`: `id`, optional `values`, optional `metadata` (Pinecone `setMetadata`, merges fields); at least one required.
- `query_vectors`: `vector`, optional `top_k` (1–50), optional Pinecone metadata `filter`. Supports bounded `$and/$or`, `$eq/$ne/$gt/$gte/$lt/$lte/$in/$nin/$exists`. Returns `data` with raw scores and `sources` containing stable source labels, record IDs, document IDs, text, score and metadata. Supply embeddings externally; this extension does not generate embeddings or answers.
- `replace_document`: `document_id`, 1–100 `chunks` with `text`, `values`, optional `metadata`. Validates the entire input, upserts generation-addressed chunks, then deletes previous generations using a namespace-scoped document filter. Reserved metadata stores generation and chunk index. `delete_document` removes only the selected document in that namespace.

Document replacement is a multi-request operation, not a transaction. Pinecone is eventually consistent: reads may briefly show old/new generations, and concurrent replacements of the same document must be serialized by the caller. If a later page or stale-generation delete fails, partial writes can exist. Reconcile before a deliberate new attempt. All writes require a durable `external_effect_id`, are suppressed in test mode before DNS or HTTP, and are never automatically retried. After possible write dispatch, failures return `external_effect_status: timeout_unknown`; pre-dispatch failures return `not_applied`.

Input including host envelope is limited to 256KiB, provider responses and final results to 480KiB. Oversized results require smaller pages, filters or fewer matches. Dates/schema/embeddings are caller responsibilities.

## API and verification

Pinned REST API `2026-04`, intentionally the traditional dense-vector API. The newer 2026-07 document-schema model is not silently substituted. Official references checked 2026-11-01 using Context7 and Pinecone documentation:

- [Create index](https://docs.pinecone.io/reference/api/2026-04/control-plane/create_index)
- [Namespaces](https://docs.pinecone.io/reference/api/2026-04/data-plane/createnamespace)
- [Upsert](https://docs.pinecone.io/reference/api/2026-04/data-plane/upsert), [fetch](https://docs.pinecone.io/reference/api/2026-04/data-plane/fetch), [query](https://docs.pinecone.io/reference/api/2026-04/data-plane/query)

Verification uses isolated Docker extension-static and extension-tests gates: manifest validation, compileall, Ruff, mypy, Bandit and independent mocked HTTP/SDK-boundary tests for lifecycle, schema, isolation, CRUD, limits, errors, deadlines, write phases and packages. Cloud credentials were unavailable; no live Pinecone verification is claimed. The mocked fixture is test-only and does not emulate all server behavior.

Build releases with `python scripts/package_extension.py --runtime-target linux-amd64` and `--runtime-target linux-arm64`. Both ZIPs include `.fs-package.yaml` with `runtime_target`; `native_executable` is omitted because there is no native payload. The deterministic builder excludes caches, local environments, Git and release output. Linux target labels describe supported host runtimes, not separate Python implementations.
