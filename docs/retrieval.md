# Authorized Retrieval

## Implemented flow

```text
authenticated query
  -> existing AuthorizedScope resolution
  -> entity/module/classification + operation permission check
  -> deterministic structured/document/hybrid routing
  -> explicit protected-scope predicates + PostgreSQL RLS
  -> allowlisted SQL aggregate and/or FTS + pgvector retrieval
  -> reciprocal-rank fusion
  -> lineage-preserving evidence IDs
  -> controlled unavailable response
  -> append-only retrieval audit event
```

The query path is read-only except for its audit event. It never creates embeddings.
Embedding backfill is an explicit writer-authorized operation performed after ingestion,
so a read request cannot turn into a hidden write or broaden its own scope.

## API

`POST /api/v1/queries` accepts `question`, `entity_id`, `module`, `classification`, and
optional deterministic filters for date range, employee, department, and status.
Product and tenant come from the existing protected headers. The caller needs
`attendance:read` for structured retrieval, `document:read` for document retrieval,
both for hybrid retrieval, and `audit:write` for every route.

The response contains a request ID, append-only audit ID, selected retrieval mode,
availability state, optional structured result, and authorized evidence. Evidence
contains an application-generated evidence ID, chunk/version IDs, content, source
locator, retrieval methods, fused score, extraction confidence, and review status.
No LLM is called in this phase.

## Retrieval modes

- Structured retrieval supports allowlisted count, average percentage, total hours,
  highest/lowest percentage, and status-breakdown aggregates with deterministic filters.
- Keyword retrieval uses PostgreSQL `websearch_to_tsquery`, `ts_rank_cd`, the generated
  `tsvector`, and its GIN index.
- Semantic retrieval uses local `sentence-transformers/all-MiniLM-L6-v2` embeddings,
  pgvector cosine distance, and a cosine HNSW index.
- Hybrid retrieval combines an allowlisted aggregate with document evidence.
- Keyword and semantic candidates are deduplicated and fused with reciprocal-rank fusion.

Only current document versions participate. Every query includes product, tenant,
entity, module, and classification predicates before aggregation or ranking.

## Security properties

The API verifies the exact operation permission before any retriever runs. Each retriever
independently applies explicit protected-scope predicates. The existing transaction-local
authorization context and RLS policies remain defense in depth. The embedding indexer
requires `document:write` and indexes only rows visible in the exact authorized scope.

Tests cover tenant, entity, and classification denial, authorized keyword/vector
retrieval, structured aggregation, hybrid routing, unavailable behavior, evidence
lineage, and PostgreSQL persistence.

## Downstream boundary

Retrieval itself still produces evidence rather than natural-language answers. The
generation layer consumes this contract and adds context revalidation, providers,
citations, grounding, and confidence. Secure exports are implemented separately; advanced
frontend work remains deferred.
See [generation.md](./generation.md).
