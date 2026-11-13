# Workflow actions

Save a project Pinecone connection with API key, index name, dimensions and metric. Select it on the step. Use a ready dense index or create a serverless index first. Generate embeddings in a separate step using the same model and dimensions for documents and questions.

For document ingestion, map prepared chunks with text and values into Replace a document and its embeddings. For retrieval, embed the question and map the vector into Search similar vectors. Data namespaces are isolated by account, project and connection; index administration affects the wider Pinecone project.

Select the named action in an Extension tools step. Map workflow values to its inputs and map the returned fields needed by later steps. Examples below contain sample data; replace artifact handles and embedding values with actual earlier-step outputs.

## Create a serverless vector index

Create the configured dense index with connection dimensions and metric, using the supplied cloud and region. Deletion protection starts enabled; provisioning is asynchronous, so inspect the index until ready.

- **Logical namespace**: Optional logical name; default default. Use 1–64 letters, digits, underscores or hyphens. The connector adds account/project/connection isolation. Index administration ignores this field.
- **Serverless cloud**: Cloud provider for a new index: aws (default), gcp or azure. Choose a region supported by that cloud and your Pinecone project.
- **Serverless region**: Required cloud region for a new index. It must be supported by the selected cloud and Pinecone project.

Example input values:

```json
{
  "namespace": "knowledge_base",
  "cloud": "aws",
  "region": "us-east-1"
}
```

## Inspect the configured vector index

Read status, dimensions, metric and host for the connection index. Use after index creation to check readiness before saving or searching vectors.

- **Logical namespace**: Optional logical name; default default. Use 1–64 letters, digits, underscores or hyphens. The connector adds account/project/connection isolation. Index administration ignores this field.

Example input values:

```json
{
  "namespace": "knowledge_base"
}
```

## List indexes in the Pinecone project

List indexes visible to the API key across the Pinecone project. This is project-level administration, not limited to the selected data namespace.

- **Logical namespace**: Optional logical name; default default. Use 1–64 letters, digits, underscores or hyphens. The connector adds account/project/connection isolation. Index administration ignores this field.

Example input values:

```json
{
  "namespace": "knowledge_base"
}
```

## Check index dimensions and metric

Verify that the configured index is ready, dense and matches the connection dimensions and metric before ingestion or retrieval.

- **Logical namespace**: Optional logical name; default default. Use 1–64 letters, digits, underscores or hyphens. The connector adds account/project/connection isolation. Index administration ignores this field.

Example input values:

```json
{
  "namespace": "knowledge_base"
}
```

## Delete an index and all its namespaces

Delete the entire configured index after matching its name in confirmation. This affects every namespace; explicitly disable deletion protection first using Set index deletion protection.

- **Logical namespace**: Optional logical name; default default. Use 1–64 letters, digits, underscores or hyphens. The connector adds account/project/connection isolation. Index administration ignores this field.
- **Confirm configured index name**: Enter the exact index name saved in the connection. This operation affects the entire index, including all namespaces.

Example input values:

```json
{
  "namespace": "knowledge_base",
  "confirm_index": "knowledge-base"
}
```

## Create an isolated namespace

Create a logical namespace inside the configured serverless index, scoped to this account, project and connection. Uses Pinecone default metadata indexing.

- **Logical namespace**: Optional logical name; default default. Use 1–64 letters, digits, underscores or hyphens. The connector adds account/project/connection isolation. Index administration ignores this field.

Example input values:

```json
{
  "namespace": "knowledge_base"
}
```

## Inspect an isolated namespace

Read metadata for the selected logical namespace in the configured index, within this connection scope.

- **Logical namespace**: Optional logical name; default default. Use 1–64 letters, digits, underscores or hyphens. The connector adds account/project/connection isolation. Index administration ignores this field.

Example input values:

```json
{
  "namespace": "knowledge_base"
}
```

## List isolated namespaces

List namespaces belonging to this account, project and connection. Use the returned pagination token for further pages; a filtered page may be empty but still have a next token.

- **Logical namespace**: Optional logical name; default default. Use 1–64 letters, digits, underscores or hyphens. The connector adds account/project/connection isolation. Index administration ignores this field.
- **Next-page token**: Optional opaque token returned by the previous matching list action. Leave blank for the first page and keep the same connection and listing filters.
- **Maximum items per page**: Optional integer from 1 to 100; default 100. Repeat the list action with its returned pagination token to fetch another page.

Example input values:

```json
{
  "namespace": "knowledge_base",
  "limit": 100
}
```

## Delete a namespace and its vectors

Delete the selected isolated namespace and all vectors it contains. Requires explicit confirmation; does not delete the index or other namespaces.

- **Logical namespace**: Optional logical name; default default. Use 1–64 letters, digits, underscores or hyphens. The connector adds account/project/connection isolation. Index administration ignores this field.
- **Confirm namespace and vector deletion**: Must be true to delete this isolated namespace and every vector inside it. Verify the logical namespace before enabling.

Example input values:

```json
{
  "namespace": "knowledge_base",
  "confirm": true
}
```

## Count vectors in a namespace

Read vector statistics for the selected logical namespace only. Use to inspect ingestion progress; Pinecone is eventually consistent.

- **Logical namespace**: Optional logical name; default default. Use 1–64 letters, digits, underscores or hyphens. The connector adds account/project/connection isolation. Index administration ignores this field.

Example input values:

```json
{
  "namespace": "knowledge_base"
}
```

## Save or replace vectors by ID

Insert or replace 1–100 vectors with externally generated embeddings and optional metadata in the selected namespace. Reusing an ID replaces that record; dimensions must match the connection.

- **Logical namespace**: Optional logical name; default default. Use 1–64 letters, digits, underscores or hyphens. The connector adds account/project/connection isolation. Index administration ignores this field.
- **Vectors to save (JSON array)**: Supply 1–100 objects with unique id, values and optional flat metadata. Values must be finite and match connection dimensions. Metadata may contain scalars or string lists; _fs_ keys are reserved. The 3-value example needs a 3-dimensional index.

Example input values:

```json
{
  "namespace": "knowledge_base",
  "vectors": [
    {
      "id": "manual_42_part_1",
      "values": [
        0.1,
        0.2,
        0.3
      ],
      "metadata": {
        "text": "Refunds within 30 days.",
        "language": "en"
      }
    }
  ]
}
```

## Read vectors by ID

Fetch 1–100 record IDs from the selected namespace. Use saved IDs to retrieve stored vectors and metadata without a similarity search.

- **Logical namespace**: Optional logical name; default default. Use 1–64 letters, digits, underscores or hyphens. The connector adds account/project/connection isolation. Index administration ignores this field.
- **Vector IDs (JSON array)**: Supply 1–100 explicit nonempty string IDs, each up to 512 UTF-8 bytes without whitespace or control characters. IDs belong to this logical namespace.

Example input values:

```json
{
  "namespace": "knowledge_base",
  "ids": [
    "manual_42_part_1",
    "manual_42_part_2"
  ]
}
```

## List vector IDs by prefix

List vector IDs in the selected namespace, optionally restricted to an ID prefix. Returns explicit pagination for further pages; does not fetch full vector records.

- **Logical namespace**: Optional logical name; default default. Use 1–64 letters, digits, underscores or hyphens. The connector adds account/project/connection isolation. Index administration ignores this field.
- **Vector ID prefix**: Optional prefix for record IDs. Leave blank to list all IDs in this namespace.
- **Next-page token**: Optional opaque token returned by the previous matching list action. Leave blank for the first page and keep the same connection and listing filters.
- **Maximum items per page**: Optional integer from 1 to 100; default 100. Repeat the list action with its returned pagination token to fetch another page.

Example input values:

```json
{
  "namespace": "knowledge_base",
  "prefix": "manual_42_",
  "limit": 100
}
```

## Update an embedding or merge metadata

Update one existing record by ID with new embedding values, metadata fields or both. Metadata uses Pinecone setMetadata and merges supplied fields; provide at least one change.

- **Logical namespace**: Optional logical name; default default. Use 1–64 letters, digits, underscores or hyphens. The connector adds account/project/connection isolation. Index administration ignores this field.
- **Vector ID**: Existing record ID to update in this namespace. Supply embedding values, metadata or both.
- **Replacement embedding (JSON array)**: Finite numeric array from an embedding provider; use exactly the connection dimensions. Match the model used for stored records. The 3-value example is illustrative for a 3-dimensional index.
- **Metadata fields to merge (JSON)**: Optional flat object of scalars or string lists; maximum 40 KiB. Supplied fields merge into the existing record using setMetadata. Keys starting _fs_ are reserved.

Example input values:

```json
{
  "namespace": "knowledge_base",
  "id": "manual_42_part_1",
  "values": [
    0.1,
    0.2,
    0.3
  ],
  "metadata": {
    "language": "en",
    "category": "refunds"
  }
}
```

## Delete vectors by ID

Delete 1–100 explicit record IDs from the selected namespace. Does not delete the namespace or provide an unscoped delete-all operation.

- **Logical namespace**: Optional logical name; default default. Use 1–64 letters, digits, underscores or hyphens. The connector adds account/project/connection isolation. Index administration ignores this field.
- **Vector IDs (JSON array)**: Supply 1–100 explicit nonempty string IDs, each up to 512 UTF-8 bytes without whitespace or control characters. IDs belong to this logical namespace.

Example input values:

```json
{
  "namespace": "knowledge_base",
  "ids": [
    "manual_42_part_1",
    "manual_42_part_2"
  ]
}
```

## Search similar vectors

Search the selected namespace with a numeric embedding and optional Pinecone metadata filter. Returns scores and source metadata; generate the query embedding separately using the ingestion model and dimensions.

- **Logical namespace**: Optional logical name; default default. Use 1–64 letters, digits, underscores or hyphens. The connector adds account/project/connection isolation. Index administration ignores this field.
- **Search embedding (JSON array)**: Finite numeric array from an embedding provider; use exactly the connection dimensions. Match the model used for stored records. The 3-value example is illustrative for a 3-dimensional index.
- **Maximum matching vectors**: Optional integer from 1 to 50; default 10. Scores depend on the index metric and are not percentages.
- **Pinecone metadata filter (JSON)**: Optional Pinecone filter with supported comparison or logical operators. Filters restrict records within this namespace; omit to search all its vectors.

Example input values:

```json
{
  "namespace": "knowledge_base",
  "vector": [
    0.1,
    0.2,
    0.3
  ],
  "top_k": 5,
  "filter": {
    "language": {
      "$eq": "en"
    }
  }
}
```

## Replace a document and its embeddings

Save 1–100 prepared text chunks with embeddings under one document ID, then remove older generations in the namespace. This spans several requests and is not atomic; serialize concurrent replacements of the same document.

- **Logical namespace**: Optional logical name; default default. Use 1–64 letters, digits, underscores or hyphens. The connector adds account/project/connection isolation. Index administration ignores this field.
- **Stable document ID**: Nonempty ID shared by all chunks of one document. Reuse it to replace or delete that document in this namespace.
- **Document chunks and embeddings (JSON array)**: Supply 1–100 objects with text and values, plus optional flat metadata. Generate embeddings first. Replaces all earlier generations of this document after saving new chunks; partial writes can remain on failure. Example uses 3-dimensional vectors.

Example input values:

```json
{
  "namespace": "knowledge_base",
  "document_id": "manual_42",
  "chunks": [
    {
      "text": "Refunds within 30 days.",
      "values": [
        0.1,
        0.2,
        0.3
      ],
      "metadata": {
        "language": "en"
      }
    }
  ]
}
```

## Delete all vectors for a document

Remove the selected document’s chunks from the isolated namespace using its stable document ID. Other documents and the index remain available.

- **Logical namespace**: Optional logical name; default default. Use 1–64 letters, digits, underscores or hyphens. The connector adds account/project/connection isolation. Index administration ignores this field.
- **Stable document ID**: Nonempty ID shared by all chunks of one document. Reuse it to replace or delete that document in this namespace.

Example input values:

```json
{
  "namespace": "knowledge_base",
  "document_id": "manual_42"
}
```

## Set index deletion protection

Enable or disable protection on the entire configured index after confirming its name. Does not change dimensions or metric; disabling protection permits a later explicit index deletion.

- **Logical namespace**: Optional logical name; default default. Use 1–64 letters, digits, underscores or hyphens. The connector adds account/project/connection isolation. Index administration ignores this field.
- **Confirm configured index name**: Enter the exact index name saved in the connection. This operation affects the entire index, including all namespaces.
- **Enable deletion protection**: Required boolean. true protects the entire index; false permits a later Delete an index action. The action does not itself delete any data.

Example input values:

```json
{
  "namespace": "knowledge_base",
  "confirm_index": "knowledge-base",
  "enabled": true
}
```
