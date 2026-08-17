# Enterprise RAG Attendance Intelligence — Completed Work

**Status date:** 2026-08-15  
**Architecture:** FastAPI modular monolith  
**Application database:** PostgreSQL only  
**Current test result:** 61 backend + 4 frontend tests passed

## 1. Current outcome

The repository contains a runnable attendance intelligence MVP backend that can:

1. Authenticate a user and resolve access from PostgreSQL.
2. Accept CSV, XLSX, DOCX, text PDF, image, and scanned PDF attendance evidence.
3. Calculate SHA-256 checksums and preserve document versions.
4. Parse, normalize, validate, and store canonical attendance records.
5. Preserve file/page/sheet/table/row lineage and OCR confidence.
6. Create PostgreSQL full-text-search chunks.
7. Create local sentence-transformer embeddings and store them in pgvector.
8. Route questions to structured, document, or hybrid retrieval.
9. Apply product, tenant, entity, module, RBAC, and classification controls before data
   reaches answer generation.
10. Produce grounded answers with validated citations and confidence bands.
11. Return controlled unavailable responses when evidence cannot be validated.
12. Record ingestion, retrieval, and generation activity in append-only audit events.
13. Run with PostgreSQL, API, and a basic evaluator-facing React/Vite workflow through Docker Compose.
14. Export the same authorized canonical record set as JSON, XLSX, or PDF.
15. Protect export creation, status, download, expiration, and audit at the existing
    authorization/RLS boundary.

Advanced product UI and production cloud deployment are not implemented yet.

## 2. Completed phases

### Phase 1 — Application foundation

- Python 3.11 FastAPI backend.
- SQLAlchemy 2.x database engine and request-scoped sessions.
- Pydantic v2 environment configuration.
- Alembic migration infrastructure.
- PostgreSQL with pgvector as the only application database.
- React, TypeScript, and Vite frontend foundation.
- Docker Compose services for PostgreSQL, API, and frontend.
- Persistent PostgreSQL, uploaded-file, and embedding-model-cache volumes.
- Liveness and PostgreSQL/pgvector readiness checks.
- Ruff and pytest infrastructure.
- No SQLite, MongoDB, external vector database, Redis, Kafka, Celery, or Kubernetes.

### Phase 2 — Authentication, authorization, RLS, and audit

- Signed JWT validation with configured issuer, audience, expiration, and algorithm.
- The token establishes identity only; it does not decide tenant or data access.
- Server-resolved `AuthorizedScope` loaded from PostgreSQL assignments.
- Product, tenant, entity, module, permission, role, and classification enforcement.
- Indivisible grants prevent privilege composition across separate assignments.
- Transaction-local PostgreSQL authorization context.
- PostgreSQL row-level-security policies on protected tables.
- Separate migration-owner and restricted runtime database roles.
- Non-disclosing authorization errors.
- Append-only audit events protected by RLS and database triggers.

### Phase 3 — Canonical attendance and protected storage

- Protected logical documents and immutable document versions.
- Ingestion jobs and extracted source units.
- Canonical attendance records.
- Lineage-preserving document chunks.
- Generated PostgreSQL `tsvector` search representation and GIN index.
- pgvector `vector(384)` embedding storage.
- Composite foreign keys that preserve protected scope through child tables.
- Database constraints for status, confidence, percentages, durations, and time ordering.

Canonical records contain:

- Attendance date.
- Employee/subject external ID and display name.
- Department or group.
- Canonical attendance status.
- Check-in and check-out times.
- Attended/scheduled duration.
- Attendance percentage.
- Product, tenant, entity, module, and classification.
- Source document, version, extracted unit, file location, extraction method, confidence,
  review status, and normalization warnings.

### Phase 4 — Ingestion and normalization

Implemented upload-to-storage flow:

```text
authenticated upload
  -> AuthorizedScope validation
  -> bounded file read
  -> SHA-256 checksum
  -> logical-document advisory lock
  -> idempotency/version resolution
  -> local file storage
  -> parser/OCR
  -> extracted units
  -> deterministic normalization
  -> canonical attendance records
  -> lineage-preserving chunks and PostgreSQL FTS
  -> job status and counts
  -> append-only audit events
```

Supported inputs:

- CSV with header detection, common aliases, and row numbers.
- XLSX with multiple sheets, sheet names, headers, and row numbers.
- DOCX paragraphs and tables with table/row coordinates.
- Text PDF extraction page by page.
- Images and scanned PDFs through Tesseract OCR.

OCR behavior:

- OCR confidence is preserved.
- The default review threshold is configurable.
- Low-confidence extraction remains available for review.
- Uncertain evidence is marked `review_required`; it is not silently treated as certain.

Idempotency behavior:

- Same logical document and checksum reuses the existing version/job.
- No duplicate attendance rows are created.
- Changed content creates a new current version.
- Previous versions remain preserved and are marked superseded.

### Phase 5 — PostgreSQL retrieval

- Local `sentence-transformers/all-MiniLM-L6-v2` embedding provider.
- Explicit writer-authorized embedding backfill.
- Persistent Hugging Face model cache in Docker Compose.
- Cosine pgvector retrieval with configurable minimum score.
- Cosine HNSW index on stored embeddings.
- PostgreSQL keyword retrieval using `websearch_to_tsquery` and `ts_rank_cd`.
- Deterministic structured/document/hybrid query router.
- Cleaned hybrid search text so routing words do not dilute domain retrieval.
- Allowlisted SQLAlchemy aggregate operations.
- Current-document-version filtering.
- Reciprocal-rank fusion and candidate deduplication.
- Controlled unsupported/no-evidence responses.
- Retrieval audit events.

Structured metrics include:

- Count.
- Average attendance percentage.
- Total attended hours.
- Highest attendance percentage.
- Lowest attendance percentage.
- Status breakdown.

Supported deterministic filters include date range, employee ID, department, and status.

Every retrieval branch applies explicit product, tenant, entity, module, classification,
and current-version predicates. Existing PostgreSQL RLS remains defense in depth.

### Phase 6 — Grounded answer generation

- `LLMProvider` abstraction.
- Deterministic offline `MockProvider`, used by default.
- Optional `OpenAIProvider` using typed structured output.
- Deterministic server-generated answers for structured-only queries.
- Context builder that independently revalidates retrieved chunks before generation.
- Context contains only already-authorized evidence.
- Email and phone-like PII minimization before provider invocation.
- Detection, marking, and redaction of common prompt-injection instructions in evidence.
- No database, retrieval, export, or authorization tools are exposed to the model.
- Application-generated opaque evidence IDs.
- Citation validation against the current request's authorized evidence registry.
- Source-locator validation.
- Claim-to-evidence and answer-to-citation lexical grounding checks.
- One bounded correction retry for invalid provider citations.
- Controlled `INVALID_CITATIONS`, `LOW_CONFIDENCE`, `PROVIDER_UNAVAILABLE`, and
  `INSUFFICIENT_AUTHORIZED_EVIDENCE` outcomes.
- Sanitized generation audit events that do not store questions or document content.

Confidence is deterministic quality scoring rather than statistical probability. It
uses retrieval coverage, keyword/vector agreement, extraction/OCR confidence, review
status, citation coverage, structured-result availability, and prompt-injection flags.
The bands are high (`>= 0.80`), medium (`0.55–0.79`), and low (`< 0.55`); the default
answer threshold is `0.55` and is configurable.

### Phase 7 — Secure exports

- One authorization-scoped canonical attendance selection shared by all renderers.
- Explicit product, tenant, entity, module, classification, filters, and current-version
  predicates before records enter application memory; PostgreSQL RLS remains active.
- Native JSON export with canonical fields and source lineage.
- Readable XLSX attendance and metadata sheets using openpyxl.
- Formula-injection protection for cells beginning with `=`, `+`, `-`, or `@`.
- Readable ReportLab PDF with scope metadata, records, lineage, confidence, and review state.
- Requester-owned protected export jobs and download-time permission revalidation.
- Configurable one-hour default expiration and simple physical artifact cleanup.
- Append-only requested/completed/failed/downloaded audit events without attendance content.

### Phase 8 — Basic evaluator frontend

- One linear upload → processing → question → answer/citations/confidence → export flow.
- Short-lived local demo-token connection without committed credentials.
- Server-resolved authorization context and entity/module/classification selection.
- Multipart evidence upload with filename/type/status/job display.
- Ingestion-job polling with stage, counts, review state, and safe errors.
- Exact backend answer, availability, retrieval mode, confidence, scope, request, and audit display.
- Validated citation filename/page/sheet/row rendering without frontend-generated evidence.
- Backend-owned JSON/XLSX/PDF export creation and authenticated artifact download.
- Friendly backend-unavailable, authentication, authorization, upload, query, processing,
  unavailable-evidence, and export errors.
- Responsive, intentionally simple single-page React layout with no dashboards or analytics.

## 3. Current API endpoints

There are **9 API operations**:

| Method | Endpoint | Purpose |
|---|---|---|
| `GET` | `/health/live` | Confirms the API process is running. |
| `GET` | `/health/ready` | Checks PostgreSQL connectivity and pgvector availability. |
| `GET` | `/api/v1/auth/context` | Returns the caller's server-resolved authorized grants. |
| `POST` | `/api/v1/documents` | Uploads, parses, normalizes, stores, chunks, and audits attendance evidence. |
| `GET` | `/api/v1/ingestion-jobs/{job_id}` | Returns authorized ingestion state, counts, and safe errors. |
| `POST` | `/api/v1/queries` | Produces an authorized grounded answer with citations and confidence. |
| `POST` | `/api/v1/exports` | Creates an authorized JSON, XLSX, or PDF attendance export. |
| `GET` | `/api/v1/exports/{export_id}` | Returns requester-owned authorized export status. |
| `GET` | `/api/v1/exports/{export_id}/download` | Revalidates authorization and downloads an unexpired artifact. |

Protected endpoints require:

```text
Authorization: Bearer <JWT>
X-Product-ID: <UUID>
X-Tenant-ID: <UUID>
```

The query response contains:

- Answer.
- Tenant context.
- Entity context.
- Role context.
- Validated citations.
- Confidence score and band.
- Retrieval mode.
- Request ID.
- Audit ID.
- Answered/unavailable status.
- Safe unavailable reason where applicable.

## 4. Security flow

```text
JWT validation
  -> authenticated subject
  -> PostgreSQL user and role assignments
  -> immutable AuthorizedScope
  -> requested entity/module/classification validation
  -> transaction-local PostgreSQL RLS context
  -> operation-specific permission check
  -> explicit SQL/FTS/vector scope predicates
  -> authorized aggregation/evidence only
  -> context revalidation
  -> PII/injection sanitization
  -> provider invocation without tools
  -> citation and grounding validation
  -> confidence gate
  -> optional authorized export selection/rendering
  -> sanitized audit event
  -> final response
```

The model never decides access. Tenant A cannot retrieve, aggregate, cite, generate from,
or infer Tenant B through the implemented query path. Entity and classification denials
use the same non-disclosing security boundary.

## 5. PostgreSQL and migration status

Applied Alembic revisions:

| Revision | Purpose |
|---|---|
| `20260815_0001` | Enable and verify pgvector. |
| `20260815_0002` | Identity, tenancy, RBAC, classification, RLS context, and audit. |
| `20260815_0003` | Documents, versions, canonical attendance, FTS chunks, embeddings, constraints, and RLS. |
| `20260815_0004` | Ingestion status/error fields and safe logical-document idempotency. |
| `20260815_0005` | Cosine HNSW index for semantic retrieval. |
| `20260815_0006` | Protected export jobs, export permission, constraints, indexes, and RLS. |

Current migration head: `20260815_0006`.

Latest Alembic verification:

```text
No new upgrade operations detected.
```

## 6. Test and quality results

Latest packaged Docker verification:

```text
61 backend tests passed
4 frontend interaction tests passed
Frontend TypeScript/Vite production build passed
Frontend npm audit: 0 vulnerabilities
Ruff lint passed
Ruff formatting check passed
Alembic schema check passed
```

Coverage includes:

- Application startup, liveness, readiness, PostgreSQL, and pgvector.
- Configuration loading and invalid configuration rejection.
- JWT validation and authorization resolution.
- Cross-tenant, cross-entity, module, permission, and classification denial.
- Prevention of cross-grant privilege composition.
- PostgreSQL RLS and restricted runtime role behavior.
- Append-only audit enforcement.
- Canonical model and database constraints.
- CSV, XLSX, DOCX, text PDF, image OCR, and scanned-PDF parsing.
- Normalization, validation errors, source lineage, and OCR review status.
- Upload authorization, persistence, ingestion status, and failure visibility.
- Checksum idempotency and changed-content versioning.
- Structured, keyword, vector, and hybrid retrieval.
- pgvector embedding persistence and FTS behavior.
- Retrieval tenant/entity/classification isolation.
- Context revalidation, PII minimization, and prompt-injection redaction.
- Mock/OpenAI typed provider contracts without a real external API call.
- Invented citation rejection and bounded retry behavior.
- Citation grounding and review-aware confidence scoring.
- Final answer and controlled unavailable response contracts.
- JSON, XLSX, and PDF exports with consistent logical authorized records.
- Cross-tenant/entity/classification/module/RBAC and different-user export denials.
- Source lineage, XLSX formula-injection protection, export audit, expiry, and cleanup.
- Upload interaction and completed processing-status rendering.
- Query submission, answer/context/citation/confidence rendering, and unavailable state.
- JSON/XLSX/PDF button creation/download behavior and safe API errors.

## 7. Latest live demonstration

The running Compose stack was verified with synthetic data:

```text
PostgreSQL: healthy
pgvector version: 0.8.4
stored embeddings: 14
API operations: 9
```

Observed answers:

| Mode | Result |
|---|---|
| Structured | Count `12.0`, answered, confidence `0.95/high`. |
| Document | Validated text-PDF row citation, confidence `0.7333/medium`. |
| Hybrid | Structured count plus validated evidence, confidence `0.8333/high`. |
| Unsupported | Controlled unavailable, confidence `0.0/low`. |

Observed audit events from the demonstration:

```text
retrieval.completed / available: 3
retrieval.completed / unavailable: 1
generation.completed / answered: 3
generation.completed / unavailable: 1
```

Observed secure export demonstration:

| Format | Records | Artifact size |
|---|---:|---:|
| JSON | 12 | 6,974 bytes |
| XLSX | 12 | 6,981 bytes |
| PDF | 12 | 3,607 bytes |

The JSON, XLSX, and PDF artifacts contained the same four logical synthetic employee
identifiers across 12 attendance rows. Live export audit counts were three requested,
three completed, and three downloaded events.

Observed basic frontend journey:

```text
frontend served: 200
authorized grants resolved: 1
CSV upload/job: completed, 4 normalized records
structured answer: answered, 0.95/high
cited answer: answered, 1 validated citation, 0.7333/medium
citation source: attendance-text.pdf, page 1, row 5
unsupported question: controlled unavailable
JSON/XLSX/PDF: completed, 12 permitted records each
```

All sample employees and tenants are fictional.

## 8. Runtime commands

Start the stack:

```bash
docker compose up --build
```

Run all backend tests:

```bash
docker compose run --rm api pytest -q
```

Run quality checks:

```bash
docker compose run --rm api ruff format --check src tests alembic
docker compose run --rm api ruff check src tests alembic
docker compose run --rm api alembic check
```

Run the synthetic ingestion demonstration:

```bash
docker compose run --rm \
  -e PYTHONPATH=/workspace/backend/src:/workspace/scripts \
  -v ./:/workspace -w /workspace api python scripts/demo_ingestion.py
```

Run the retrieval and grounded-answer demonstration:

```bash
docker compose run --rm \
  -e PYTHONPATH=/workspace/backend/src:/workspace/scripts \
  -v ./:/workspace -w /workspace api python scripts/demo_retrieval.py
```

Run the secure export demonstration:

```bash
docker compose run --rm \
  -e PYTHONPATH=/workspace/backend/src:/workspace/scripts \
  -v ./:/workspace -w /workspace api python scripts/demo_exports.py
```

Runtime URLs:

- Frontend: <http://localhost:5173>
- OpenAPI/Swagger: <http://localhost:8000/docs>
- Liveness: <http://localhost:8000/health/live>
- Readiness: <http://localhost:8000/health/ready>

## 9. Important operational notes

- `MockProvider` is the default and requires no external LLM/network request.
- `OpenAIProvider` is implemented and adapter-tested, but no real OpenAI call was made
  because no API key was supplied.
- To use OpenAI, set `LLM_PROVIDER=openai`, `OPENAI_API_KEY`, and optionally
  `OPENAI_MODEL` in the ignored local `.env` file.
- Semantic embedding backfill is an explicit writer-authorized operation. The query path
  remains read-only except for append-only retrieval/generation audit events.
- File processing is synchronous for the MVP; large-file worker orchestration is deferred.
- Citation support validation is deterministic lexical grounding suitable for the MVP.
  Production semantic entailment evaluation remains future hardening.

## 10. Remaining assignment work

- Advanced dashboard, analytics, admin, and product navigation if later required.
- Stored query/answer history if required.
- Stored query-result export if protected query history is later added; the current export
  dataset is normalized canonical attendance.
- Production identity-provider/JWKS integration.
- Rate limiting, provider retries, cost controls, and production evaluations.
- Cloud object storage and deployment.
- TLS ingress, secret management, observability, backup/restore, and external immutable
  audit archival.

## 11. Supporting documentation

- `README.md` — setup and current repository scope.
- `IMPLEMENTATION_PLAN.md` — approved full architecture and ordered plan.
- `IMPLEMENTATION_STATUS.md` — audited implementation status.
- `docs/security-model.md` — authentication, authorization, RLS, and audit boundary.
- `docs/canonical-storage.md` — protected canonical persistence contract.
- `docs/ingestion.md` — ingestion and normalization behavior.
- `docs/retrieval.md` — structured, keyword, vector, and hybrid retrieval.
- `docs/generation.md` — context, providers, grounding, citations, and confidence.
- `docs/exports.md` — secure JSON/XLSX/PDF exports and artifact lifecycle.
- `docs/frontend.md` — basic evaluator flow, demo connection, tests, and live verification.
