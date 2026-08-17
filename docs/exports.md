# Secure Attendance Exports

## Flow

```text
authenticated request
  -> existing AuthorizedScope
  -> attendance:read + attendance:export + audit:write check
  -> transaction-local PostgreSQL RLS context
  -> explicit product/tenant/entity/module/classification SQL predicates
  -> current-version canonical attendance rows only
  -> JSON, XLSX, or PDF renderer
  -> local expiring artifact storage
  -> protected export job + append-only audit events
  -> authorization revalidation on status/download
```

Records are restricted in SQL before they enter application memory. PostgreSQL RLS is
the defense-in-depth layer. The service never loads a global dataset and filters it
afterward.

## API

- `POST /api/v1/exports` creates a synchronous MVP export job.
- `GET /api/v1/exports/{export_id}` returns status only to the requesting user while the
  exact protected scope remains authorized.
- `GET /api/v1/exports/{export_id}/download` revalidates read/export/audit permissions,
  requester ownership, scope, status, and expiry before reading the artifact.

Creation accepts format, attendance dataset, entity, module, classification, optional
date range, optional employee ID, and optional status. Unsupported stored-query-result
exports are not simulated because query history is not currently persisted.

## Formats

All three formats use the same typed authorized record collection and deterministic
ordering.

- JSON contains minimal canonical fields, source lineage, extraction confidence, and
  review status.
- XLSX contains attendance and export-metadata sheets, readable widths/filtering, and
  formula-injection protection. String values beginning with `=`, `+`, `-`, or `@` are
  prefixed with an apostrophe before being written.
- PDF contains title/timestamp, permitted tenant/entity/module/classification context,
  attendance rows, source references, confidence, and review status.

## Storage and expiration

Artifacts are stored through the existing `StorageProvider` under opaque export keys.
`EXPORT_TTL_SECONDS` defaults to one hour. Create, status, and download operations run a
simple caller-scoped cleanup: expired files are physically deleted and their protected
jobs become `expired`. No Redis, Celery, or worker service is used.

`EXPORT_MAX_RECORDS` defaults to 10,000. Oversized datasets fail safely with a structured
job error rather than producing an unbounded in-memory artifact.

## Audit

Append-only events cover requested, completed, failed, and downloaded outcomes. Metadata
contains request/export IDs, format, protected product/tenant/module scope, and outcome;
raw attendance content is not logged.

## Security verification

Integration tests cover cross-tenant, cross-entity, classification, module, RBAC, and
different-user denials; download reauthorization; lineage; format consistency; formula
injection; audit metadata; expiration; and physical cleanup.
