# Phase 3 Canonical Domain and Storage

Phase 3 establishes the persistence contracts needed by later ingestion and retrieval
work. It does not expose upload APIs, parse files, run OCR, generate embeddings, retrieve
context, or call an LLM.

## Protected scope

Every document, version, ingestion job, extracted unit, attendance fact, text chunk, and
embedding stores:

- `product_id`
- `tenant_id`
- `entity_id`
- `module`
- `classification`

Composite foreign keys require child records to retain the exact protected scope of
their parent. Each table has operation-specific PostgreSQL RLS policies. Reads require
the applicable `document:read` or `attendance:read` permission; mutations require the
corresponding write permission. The API runtime role remains a non-owner so these
policies cannot be bypassed through ordinary application access.

## Storage graph

```text
Document
  -> DocumentVersion (unique document + SHA-256, ordered versions)
       -> IngestionJob
       -> ExtractedUnit
            -> AttendanceRecord
            -> DocumentChunk
                 -> ChunkEmbedding
```

`DocumentVersion.is_current` has a partial unique index that permits at most one current
version for a document. Re-upload behavior is implemented in a later ingestion phase;
the database already prevents the same checksum from creating duplicate versions of the
same logical document.

## Canonical attendance model

`CanonicalAttendanceRecord` is the format-neutral validation boundary. It contains the
protected scope, subject and session identifiers, attendance status and date, optional
schedule/check-in timing and derived metrics, complete source lineage, extraction method
and confidence, review status, normalization warnings, and source metadata.

The `attendance_records` table persists that model with database checks for valid enum
values, confidence and percentage ranges, non-negative durations, valid time ordering,
and unique source record identity per document version.

## Search-ready storage

`document_chunks.search_vector` is a stored generated PostgreSQL `tsvector` built with
the `english` text-search configuration and indexed with GIN. The authorized keyword
retriever now queries this column.

`chunk_embeddings.embedding` uses pgvector `vector(384)`. The application setting is
required to match 384 because changing vector dimensions is a schema migration, not a
runtime-only configuration change. The retrieval phase adds a cosine HNSW index.

## Phase boundary

The ingestion job and extracted-unit tables are storage contracts only. Phase 3 has no
parsers, upload endpoint, background worker, provider implementation, retrieval path,
generation, citation construction, or export behavior.
