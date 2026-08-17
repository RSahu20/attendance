# Ingestion and Normalization

## Implemented flow

```text
authenticated multipart upload
  -> existing AuthorizedScope resolution
  -> entity/module/classification and write-permission check
  -> bounded file read + SHA-256
  -> logical-document advisory lock
  -> document version or idempotent reuse
  -> LocalStorageProvider
  -> format parser / Tesseract fallback
  -> protected ExtractedUnit rows
  -> deterministic normalization and validation
  -> canonical AttendanceRecord rows
  -> lineage-preserving DocumentChunk rows + generated tsvector
  -> final job status/counts/errors
  -> append-only audit events
```

Processing is synchronous for the MVP. The job is committed before parsing and each
stage transition is persisted. Safe failures therefore remain queryable even when a
parser, OCR, or normalization step fails.

## API

`POST /api/v1/documents` accepts a multipart `file` plus `entity_id`, `module`,
`classification`, and optional `logical_name`. Product and tenant are supplied through
the existing protected headers. The caller must have `document:write`,
`attendance:write`, and `audit:write` in the exact requested grant.

`GET /api/v1/ingestion-jobs/{job_id}` returns the status, current stage, document/version
IDs, extracted/normalized/review/error counts, safe errors, and timestamps. Existing RLS
and `document:read` authorization protect the response.

## Parsers and lineage

- CSV: detected header and physical row number.
- XLSX: all non-empty sheets, sheet name, and physical row number.
- DOCX: paragraphs and tables; attendance table rows retain table/row coordinates.
- Text PDF: page extraction with practical delimiter-based attendance row recognition.
- Image/scanned PDF: Tesseract OCR with image/page location and mean word confidence.

All parsers return `ParsedUnit`; none writes attendance records. Normalization is a
separate deterministic step. Source location is stored on extracted units and chunks and
is copied into attendance row metadata.

## OCR review behavior

`OCR_CONFIDENCE_THRESHOLD` defaults to `0.80`. Units below the threshold remain stored,
are normalized when possible, and are marked `review_required`. They are never silently
promoted to accepted evidence or discarded.

## Idempotency and versioning

SHA-256 is calculated from uploaded bytes. A transaction-level PostgreSQL advisory lock
serializes uploads for the same protected logical document. The database additionally
enforces logical-document scope/name uniqueness and document/checksum uniqueness.

- Same logical document and checksum reuses the existing version/job and creates no
  duplicate attendance rows.
- Changed checksum creates a new current version and marks the prior current version
  superseded while preserving its records and lineage.

Files are stored in the Compose `attendance_files` volume. PostgreSQL stores only the
opaque storage key and metadata.

## Validation and errors

The pipeline validates upload size/name, parser support, required date and employee ID,
status mapping, time order, percentage range, non-negative duration, protected scope,
and source lineage. Invalid attendance rows remain as extracted units with structured job
errors; they are not silently discarded. Client-visible failures use stable safe error
codes and do not expose internal exception details.

## Explicit phase boundary

This ingestion module creates retrieval-ready chunks but no embeddings. Retrieval,
generation, exports, and the basic frontend are implemented in separate modules/phases;
cloud deployment remains deferred.
