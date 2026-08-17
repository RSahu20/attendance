# Enterprise RAG Attendance Intelligence Microservice

## Architecture and Implementation Plan

**Status:** Planning only  
**Architecture style:** Modular monolith  
**Authoritative requirements:** The assignment text supplied in the conversation

## Repository inspection

The workspace was inspected before producing this plan. At that time it contained no application source files, README, configuration, assignment attachment, or valid Git history. Therefore, the assignment text supplied in the conversation is treated as the authoritative specification.

The recommended MVP is a modular monolith with one FastAPI codebase, one PostgreSQL database, and an optional worker process built from the same backend package. PostgreSQL remains the sole system of record and retrieval engine.

## Key architectural decisions

- PostgreSQL handles relational data, full-text search, pgvector, job state, and audit records.
- Retrieval never relies on the LLM for authorization.
- Every retrieval branch applies authorization predicates directly in its database query.
- PostgreSQL row-level security provides defense in depth, while application authorization remains explicit and testable.
- Structured questions use a safe, allowlisted query model, not arbitrary LLM-generated SQL.
- Evidence identifiers are created by the application. The LLM may reference them but cannot create valid citations.
- OCR and embedding work can run in a separate worker process for operational isolation while remaining part of the same modular monolith.
- Local filesystem storage is acceptable for the MVP; its interface allows later replacement by S3-compatible storage.
- Redis is not required. PostgreSQL-backed ingestion jobs are sufficient for the assignment.

## A. Architecture diagram

```text
                         React frontend
                               |
                         HTTPS / JSON API
                               |
                   +-----------v------------+
                   | FastAPI modular monolith|
                   |                         |
Identity/JWT ----->| Authentication          |
                   | Authorization resolver  |
                   | Ingestion API           |
                   | Query orchestrator      |
                   | Export API              |
                   | Audit/diagnostics API   |
                   +----+----------+---------+
                        |          |
              authorized|          | ingestion jobs
                 queries|          |
                        v          v
              +--------------------------+
              | PostgreSQL + pgvector    |
              |                          |
              | Canonical records        |
              | Document versions        |
              | Chunks + embeddings      |
              | tsvector indexes         |
              | Access-control metadata  |
              | Audit/events/jobs        |
              +--------------------------+
                        ^
                        |
              +---------+----------+
              | Backend worker     |  Same codebase/image
              |                    |
              | Parsing            |
              | OCR/Tesseract      |
              | Normalization      |
              | Chunking           |
              | Embedding          |
              +---------+----------+
                        |
              +---------v----------+
              | StorageProvider    |
              | Local volume (MVP) |
              | Object store later |
              +--------------------+

Query path:

Request
  -> authenticate
  -> resolve AuthorizedScope from trusted server-side state
  -> authorize requested operation
  -> classify structured/document/hybrid
  -> execute only pre-filtered retrieval
  -> revalidate evidence provenance
  -> construct minimal authorized context
  -> invoke LLM provider
  -> validate citations and grounding
  -> compute confidence
  -> answer or controlled unavailable response
  -> append audit event
```

The worker is a separate process only because OCR and embeddings are CPU- and memory-intensive. It is not a separately owned service and shares the backend domain modules, migrations, configuration, and database.

## B. Repository tree

```text
attendance/
├── README.md
├── .env.example
├── .gitignore
├── Makefile
├── docker-compose.yml
├── docker-compose.test.yml
├── docs/
│   ├── architecture.md
│   ├── security-model.md
│   ├── api-examples.md
│   ├── deployment.md
│   └── threat-model.md
├── backend/
│   ├── Dockerfile
│   ├── pyproject.toml
│   ├── alembic.ini
│   ├── alembic/
│   │   ├── env.py
│   │   └── versions/
│   ├── src/attendance/
│   │   ├── main.py
│   │   ├── config.py
│   │   ├── api/
│   │   │   ├── dependencies.py
│   │   │   ├── errors.py
│   │   │   └── routes/
│   │   │       ├── auth.py
│   │   │       ├── documents.py
│   │   │       ├── ingestion.py
│   │   │       ├── queries.py
│   │   │       ├── exports.py
│   │   │       ├── audit.py
│   │   │       └── health.py
│   │   ├── domain/
│   │   │   ├── attendance.py
│   │   │   ├── documents.py
│   │   │   ├── security.py
│   │   │   ├── retrieval.py
│   │   │   ├── citations.py
│   │   │   └── exports.py
│   │   ├── db/
│   │   │   ├── session.py
│   │   │   ├── models/
│   │   │   ├── repositories/
│   │   │   ├── rls.py
│   │   │   └── types.py
│   │   ├── security/
│   │   │   ├── authentication.py
│   │   │   ├── authorization.py
│   │   │   ├── scopes.py
│   │   │   ├── classification.py
│   │   │   └── redaction.py
│   │   ├── ingestion/
│   │   │   ├── service.py
│   │   │   ├── jobs.py
│   │   │   ├── validation.py
│   │   │   ├── checksum.py
│   │   │   ├── normalization.py
│   │   │   ├── chunking.py
│   │   │   └── parsers/
│   │   │       ├── base.py
│   │   │       ├── csv_parser.py
│   │   │       ├── xlsx_parser.py
│   │   │       ├── docx_parser.py
│   │   │       ├── pdf_parser.py
│   │   │       ├── image_parser.py
│   │   │       └── ocr.py
│   │   ├── retrieval/
│   │   │   ├── orchestrator.py
│   │   │   ├── router.py
│   │   │   ├── structured.py
│   │   │   ├── keyword.py
│   │   │   ├── vector.py
│   │   │   ├── hybrid.py
│   │   │   └── context_builder.py
│   │   ├── providers/
│   │   │   ├── llm/
│   │   │   │   ├── base.py
│   │   │   │   ├── mock.py
│   │   │   │   └── openai.py
│   │   │   ├── embeddings/
│   │   │   │   ├── base.py
│   │   │   │   └── sentence_transformer.py
│   │   │   ├── ocr/
│   │   │   │   ├── base.py
│   │   │   │   └── tesseract.py
│   │   │   └── storage/
│   │   │       ├── base.py
│   │   │       └── local.py
│   │   ├── generation/
│   │   │   ├── service.py
│   │   │   ├── prompts.py
│   │   │   ├── grounding.py
│   │   │   ├── confidence.py
│   │   │   └── citation_validator.py
│   │   ├── exports/
│   │   │   ├── service.py
│   │   │   ├── json_export.py
│   │   │   ├── xlsx_export.py
│   │   │   └── pdf_export.py
│   │   ├── audit/
│   │   │   └── service.py
│   │   └── worker.py
│   └── tests/
│       ├── unit/
│       ├── integration/
│       ├── security/
│       ├── fixtures/
│       └── conftest.py
├── frontend/
│   ├── Dockerfile
│   ├── package.json
│   ├── vite.config.ts
│   └── src/
│       ├── api/
│       ├── components/
│       ├── pages/
│       └── types/
├── samples/
│   ├── csv/
│   ├── xlsx/
│   ├── docx/
│   ├── pdf/
│   └── images/
└── scripts/
    ├── bootstrap.sql
    ├── seed_demo.py
    └── smoke_test.sh
```

## C. PostgreSQL table design

All protected domain tables include `product_id`, `tenant_id`, `entity_id`, `module`, and `classification`. Role access is resolved from assignments and grants rather than copied into every attendance row.

| Table | Important fields and purpose |
|---|---|
| `products` | `id`, `code`, `name`, timestamps |
| `tenants` | `id`, `product_id`, `code`, `name`, status |
| `entities` | `id`, `product_id`, `tenant_id`, `parent_id`, `entity_type`, `name`, hierarchy path |
| `users` | `id`, identity-provider subject, email/status |
| `roles` | `id`, `product_id`, optional `tenant_id`, name |
| `permissions` | Resource/action pairs such as `attendance:read`, `document:export` |
| `role_permissions` | Role-to-permission association |
| `user_role_assignments` | User, role, product, tenant, optional entity/module scope, classification ceiling |
| `access_grants` | Optional explicit allow/deny grants and effective date range |
| `documents` | Stable logical document identity and protected scope |
| `document_versions` | `document_id`, version number, SHA-256, MIME type, storage key, parser status, metadata |
| `ingestion_jobs` | Job state, requested scope, version, error summary, counts, requester |
| `extracted_units` | Page/sheet/table/row/block text, source locator, OCR confidence, review status |
| `attendance_records` | Canonical structured attendance facts |
| `document_chunks` | Text, provenance, protected scope, token count, generated `tsvector` |
| `chunk_embeddings` | `chunk_id`, embedding model/version/dimension, `vector(n)` |
| `query_requests` | Question, resolved scope snapshot, route, requester, request ID |
| `retrieval_evidence` | Query/evidence relationship, retrieval method and score |
| `generated_answers` | Answer, provider/model, confidence, grounding status |
| `citations` | Answer, evidence ID, source locator, validated status |
| `export_jobs` | Format, authorized scope snapshot, status, storage key, expiry |
| `audit_events` | Append-only event, actor, action, resource, scope snapshot, request ID, outcome |
| `schema_mappings` | Saved tenant/file-format column mappings where needed |

### Canonical attendance model

```text
id
product_id, tenant_id, entity_id, module, classification

subject_external_id
subject_display_name          nullable/minimized according to permission
attendance_date
session_external_id           nullable
session_name                  nullable
course_or_group               nullable

status                        present/absent/late/excused/partial/unknown
scheduled_start/end           nullable
check_in/check_out            nullable
scheduled_minutes             nullable
attended_minutes              nullable
attendance_percentage         nullable
late_minutes                  nullable

source_document_id
source_version_id
source_unit_id
source_record_key
raw_row_metadata              JSONB, carefully access-controlled

extraction_method             native/csv/xlsx/pdf_text/ocr/manual
extraction_confidence
review_status                 accepted/review_required/rejected
normalization_warnings        JSONB
recorded_at
created_at, updated_at
```

### Important constraints and indexes

- Unique document version checksum within logical document scope.
- Unique canonical source record per `document_version_id + source_record_key`.
- Composite indexes beginning with `product_id, tenant_id, entity_id`.
- B-tree indexes on date, status, subject ID, module, and classification.
- GIN index on `document_chunks.search_vector`.
- HNSW or IVFFlat pgvector index, depending on dataset size and operational needs.
- Unique embedding per `chunk_id + model_name + model_version`.
- Scope-consistency constraints or triggers prevent a chunk from claiming a different tenant than its document version.
- Append-only protection for audit events.
- Row-level security policies use transaction-local trusted scope values.
- No SQLite fallback in tests because RLS, pgvector, and PostgreSQL FTS are essential behavior.

Classification should be an ordered server-side policy, for example:

```text
public < internal < confidential < restricted
```

A role assignment carries a classification ceiling. Classification is never accepted directly from an untrusted query request.

## D. API endpoint list

Suggested `/api/v1` endpoints follow.

### Documents and ingestion

- `POST /documents` — multipart upload plus entity/module/classification metadata.
- `GET /documents` — authorized document listing.
- `GET /documents/{document_id}` — authorized metadata and versions.
- `POST /documents/{document_id}/versions` — upload changed content.
- `POST /documents/{document_id}/reprocess` — explicit reprocessing.
- `GET /ingestion-jobs/{job_id}` — ingestion state and review counts.
- `GET /ingestion-jobs/{job_id}/review-items` — low-confidence items.
- `PATCH /review-items/{item_id}` — accept, correct, or reject extracted data.

### Attendance

- `GET /attendance` — authorized filtered record list.
- `GET /attendance/summary` — safe structured aggregates.
- `GET /attendance/{record_id}` — authorized record and provenance.

### Query

- `POST /queries` — answer a question.
- `GET /queries/{request_id}` — retrieve an authorized prior result.

Core query request:

```json
{
  "question": "What was the attendance rate for Entity X last month?",
  "entity_ids": ["optional-requested-subset"],
  "date_from": "2026-07-01",
  "date_to": "2026-07-31"
}
```

The server intersects requested filters with the caller's resolved scope.

Core response:

```json
{
  "answer": "...",
  "tenant_context": {"tenant_id": "..."},
  "entity_context": {"entity_ids": ["..."]},
  "role_context": {"roles": ["..."]},
  "citations": [],
  "confidence": {"score": 0.91, "band": "high"},
  "retrieval_mode": "structured",
  "request_id": "...",
  "audit_id": "...",
  "status": "answered"
}
```

Controlled failure uses `status: "unavailable"` with a safe reason such as `INSUFFICIENT_AUTHORIZED_EVIDENCE`. It does not reveal whether inaccessible evidence exists.

### Exports

- `POST /exports` — create JSON, XLSX, or PDF export from authorized filters/query.
- `GET /exports/{export_id}` — export status.
- `GET /exports/{export_id}/download` — short-lived authorized download.

### Audit and diagnostics

- `GET /audit-events` — restricted audit search.
- `GET /health/live`
- `GET /health/ready`
- `GET /diagnostics` — admin-only checks for database, extensions, provider configuration, model availability, and storage.

## E. Security flow

```text
1. Validate token and identify user.
2. Load active roles and grants from PostgreSQL.
3. Resolve immutable AuthorizedScope:
   product, tenant, allowed entities, allowed modules,
   actions, role IDs, classification ceiling.
4. Validate requested product/tenant against that scope.
5. Intersect requested entity/date/module filters with authorized scope.
6. Reject an empty or unauthorized scope without querying protected data.
7. Set transaction-local RLS context.
8. Pass AuthorizedScope, not raw claims, to repositories.
9. Apply scope predicates inside every SQL/FTS/vector branch.
10. Perform aggregation only over the pre-filtered relation.
11. Revalidate every returned evidence item against AuthorizedScope.
12. Build context only from validated evidence.
13. Invoke the LLM with that context and no data-access tools.
14. Accept only citations referencing supplied evidence IDs.
15. Revalidate citations before returning them.
16. Apply the same authorization service to exports and stored query results.
17. Write a sanitized audit event containing the resolved scope and outcome.
```

### Defense-in-depth requirements

- PostgreSQL RLS on attendance, documents, chunks, embeddings through chunk joins, query history, exports, and audit views.
- `SET LOCAL` inside each transaction to prevent pooled-connection scope leakage.
- Deny by default when scope data is missing or malformed.
- Entity hierarchy expansion occurs server-side.
- Cache keys, if Redis is later enabled, include the full authorization scope fingerprint.
- Error messages do not disclose cross-tenant record existence.
- Raw prompts and document text are not written to normal logs.
- Export downloads reauthorize the caller; possession of an export ID is insufficient.
- Spreadsheet exports neutralize CSV/XLSX formula injection.
- Uploads enforce MIME/type checks, size/page/row limits, archive limits, safe filenames, and timeouts.

## F. Retrieval flow

### Routing

A deterministic router first classifies common intents:

- **Structured:** counts, totals, averages, extrema, comparisons, and date filters.
- **Document:** policies, narratives, source explanations, and evidence wording.
- **Hybrid:** a computed result requiring supporting source evidence.
- **Unsupported or ambiguous:** controlled unavailable or clarification response.

An LLM may assist classification later, but its output must validate against a strict `QueryPlan` schema. It cannot supply SQL, authorization predicates, tenant IDs, or arbitrary columns.

### Structured retrieval

- Parse the question into allowlisted metric, dimensions, filters, and aggregation.
- Validate against Pydantic query-plan models.
- Compile with SQLAlchemy expressions.
- Start from an already authorized attendance relation.
- Use parameterized queries.
- Reject unsupported calculations instead of generating arbitrary SQL.
- Return both the result and provenance IDs/source coverage needed for citation.

### Keyword retrieval

- Use `websearch_to_tsquery` or `plainto_tsquery`.
- Filter product, tenant, entity, module, and classification in the SQL query.
- Rank with `ts_rank_cd`.
- Preserve page/sheet/row provenance.

### Vector retrieval

- Embed the question using the configured provider/model version.
- Apply all authorization predicates within the nearest-neighbor query.
- Join embeddings to chunks and verify scope consistency.
- Never retrieve globally and filter only afterward.

### Hybrid retrieval

- Run authorized structured, keyword, and vector branches.
- Fuse document candidates with weighted reciprocal-rank fusion.
- Keep structured facts separate from narrative evidence.
- Deduplicate by evidence ID.
- Apply diversity and context-size limits after authorization.
- Return a typed evidence bundle to the context builder.

### Context, grounding, and citations

Each context item receives an opaque application-generated evidence ID:

```text
[EVIDENCE ev_123]
source: attendance.xlsx / Sheet1 / row 18
content: ...
```

The provider returns structured output containing answer claims and evidence IDs. Citation validation checks that:

- The evidence ID was present in the authorized context.
- The evidence belongs to the same request and scope.
- The source locator exists.
- Cited text supports the claim sufficiently.
- No unsupported citation identifier was invented.

If citation validation fails, the system may retry once with a correction prompt, then return unavailable or a reduced deterministic answer.

Confidence is a reproducible quality score, not a claim of statistical probability. Inputs include:

- Retrieval rank and agreement between keyword/vector results.
- Structured data completeness.
- Citation coverage of material claims.
- OCR/extraction confidence and review status.
- Source/version validity.
- Conflicts between sources.
- Whether the result was deterministic or generative.

Example bands:

- High: `>= 0.80`
- Medium: `0.55-0.79`
- Low: `< 0.55`
- Below the answer threshold or without sufficient authorized citations: unavailable.

### Prompt-injection resistance

- Treat retrieved text as untrusted evidence, not instructions.
- Delimit evidence and explicitly prohibit obeying embedded commands.
- Do not expose retrieval, database, or export tools to the answer-generation model.
- Use structured provider output.
- Limit context fields to what the caller may view.
- Detect and flag likely injection text for audit/review.
- Ignore document content asking to change security scope or reveal system prompts.
- Validate all outputs independently of the prompt.

## G. Ingestion flow

```text
Upload
  -> authenticate and authorize document:create
  -> validate scope, type, size, and filename
  -> stream to temporary storage while calculating SHA-256
  -> lock/check logical document and checksum
  -> same checksum: return existing version/job, create no records
  -> changed checksum: create immutable document version
  -> select parser
  -> extract source units with provenance
  -> normalize into canonical candidate records
  -> validate business rules
  -> persist accepted records and review-required candidates
  -> construct document chunks
  -> create tsvector automatically
  -> generate embeddings
  -> finalize version/job atomically where practical
  -> audit outcome
```

### Parser behavior

- **CSV:** Encoding detection with bounded fallback, delimiter/header validation, safe column mapping, row provenance, and date/time normalization.
- **XLSX:** `openpyxl` read-only/data-only mode, selected sheets, header detection, merged-cell handling, formulas treated as data, and row provenance.
- **DOCX:** `python-docx`, paragraphs and tables in document order, and section/table/row provenance.
- **Text PDF:** Native extraction first, preserving page numbers and text blocks.
- **Scanned PDF/image:** Render safely, preprocess, run Tesseract, and retain word/block/page confidence.
- **Handwriting:** Tesseract output is best-effort only. Low-confidence handwritten extraction must be marked `review_required`; the MVP must not silently present it as reliable canonical data.

### Normalization pipeline

1. Parser output becomes a format-neutral `ExtractedUnit`.
2. Header/field aliases map to canonical fields.
3. Dates, time zones, durations, status labels, identifiers, and percentages normalize.
4. Required fields and semantic constraints validate.
5. A stable `source_record_key` is derived from source location and normalized identity.
6. Confidence and warnings propagate.
7. Accepted records persist; ambiguous records enter review state.
8. Chunks retain exact version and page/sheet/row lineage.

### Versioning and idempotency

- SHA-256 is computed from original bytes.
- The same logical document and checksum is idempotent.
- A changed checksum creates a new immutable version.
- Reprocessing the same bytes with a newer parser/model records a processing run without duplicating the document version.
- Concurrent duplicate uploads use a database unique constraint and transaction handling, not only an application pre-check.
- Previous versions remain auditable; one version is marked current.

## H. Ordered implementation phases

1. **Foundation**
   - Project scaffolding, configuration, FastAPI, PostgreSQL connection, Alembic, Docker Compose, and health endpoints.

2. **Security and tenancy**
   - Identity model, roles, permissions, assignments, classifications, `AuthorizedScope`, RLS, and audit foundations.

3. **Canonical domain and storage**
   - Document/version, ingestion job, extracted unit, attendance record, chunk, and embedding schemas.

4. **Native structured ingestion**
   - CSV and XLSX parsers, normalization, checksum/versioning, and review state.

5. **Document ingestion**
   - DOCX and native PDF parsing, chunking, provenance, and FTS.

6. **OCR**
   - Image/scanned PDF path, Tesseract provider, confidence, and review handling.

7. **Embedding and semantic retrieval**
   - sentence-transformers provider, pgvector indexes, and authorized vector queries.

8. **Query orchestration**
   - Intent routing, safe structured query plans, and keyword/vector/hybrid retrieval.

9. **Generation and evidence controls**
   - Mock/OpenAI providers, context builder, prompts, citation validation, grounding, confidence, and unavailable responses.

10. **Exports**
    - Authorized JSON, XLSX, and PDF generation and download controls.

11. **Frontend**
    - Upload, job status/review summary, query UI, citations, confidence, and export controls.

12. **Hardening and delivery**
    - Security/integration tests, diagnostics, seed data, documentation, Compose smoke test, and deployment guide.

## I. Dependencies between phases

```text
Foundation
  -> Security and tenancy
      -> Canonical domain
          -> CSV/XLSX ingestion
          -> Document ingestion -> OCR
          -> Embeddings
              -> Query orchestration
                  -> Generation/citations/confidence
                      -> Exports
                      -> Frontend

Audit logging begins in Security and tenancy and extends through every phase.
Security tests begin with the schema and run against every retrieval/export feature.
Deployment hardening depends on all mandatory application paths being complete.
```

The security layer must precede retrieval implementation. Adding tenancy filters afterward is particularly risky and would make meaningful isolation tests harder.

## J. Mandatory assignment features

- Modular-monolith FastAPI backend.
- PostgreSQL, pgvector, and PostgreSQL full-text search.
- SQLAlchemy, Pydantic, and Alembic.
- Canonical attendance model.
- CSV, XLSX, DOCX, text PDF, and scanned image/PDF ingestion.
- Tesseract OCR with confidence/review status.
- SHA-256 idempotency and immutable versioning.
- Structured, document, and hybrid query routing.
- Safe structured aggregation without arbitrary LLM SQL.
- Pre-retrieval product/tenant/entity/module/RBAC/classification enforcement.
- Defense-in-depth isolation for citations, aggregation, generation, and export.
- Local sentence-transformer embeddings.
- `MockProvider` and `OpenAIProvider`.
- Validated citations, grounding checks, confidence bands, and unavailable responses.
- JSON, XLSX, and PDF exports.
- Audit logging.
- Security and PostgreSQL integration tests.
- Basic React frontend.
- Docker Compose.
- Documentation and demo/seed evidence proving Tenant A cannot access Tenant B.

## K. Features that can be deferred

- Redis and distributed caching.
- Celery or an external queue system.
- Cloud object storage.
- External embedding providers.
- Advanced handwriting models beyond Tesseract.
- SSO/OIDC administration UI; a simple JWT/dev identity adapter is enough for MVP.
- Rich policy-authoring UI.
- Automatic schema mapping learned per tenant.
- Streaming LLM answers.
- Reranker or cross-encoder.
- Sophisticated confidence calibration from production feedback.
- Antivirus service integration, while retaining upload-hardening hooks.
- Partitioning, replicas, autoscaling, and multi-region deployment.
- OpenTelemetry stack, SIEM integration, key-management service, and immutable external audit archive.
- Kubernetes and independently deployed microservices.

## L. Deployment plan

### Local and evaluator deployment

Docker Compose services:

- `postgres`: PostgreSQL with pgvector extension, persistent volume, and health check.
- `api`: FastAPI/uvicorn backend.
- `worker`: Same backend image, running the ingestion worker command.
- `frontend`: React build served by a lightweight web server.
- Optional `redis` profile, disabled by default.

Startup order:

1. PostgreSQL becomes healthy.
2. Alembic migrations run as a one-shot release/init task.
3. API and worker start.
4. Frontend connects through a configured API base URL.
5. A seed command optionally creates demo tenants, roles, and evidence.

### Portfolio/cloud deployment

- Build separate frontend and backend images from the same repository.
- Use a managed PostgreSQL offering that explicitly supports pgvector.
- Run API and worker from the same backend image with different commands.
- Use persistent object storage rather than container-local uploads.
- Store secrets in the platform secret manager.
- Enforce HTTPS, restricted CORS, database TLS, backups, and migration-on-release.
- Keep a mock-provider demo mode so the project is demonstrable without paid LLM access.
- Select a current free or low-cost host at deployment time; provider free tiers change frequently.

## M. Risks and likely failure points

| Risk | Mitigation |
|---|---|
| Cross-tenant leakage from a missed predicate | Central authorized repositories, RLS, immutable scope object, and adversarial isolation tests |
| Connection-pool RLS scope leakage | Transaction-scoped `SET LOCAL`, mandatory transaction boundary, and reset tests |
| LLM-generated unsafe SQL | Typed allowlisted query plans and SQLAlchemy compiler; no raw SQL generation |
| Vector retrieval filtered after nearest-neighbor search | Include authorization predicates inside candidate SQL and test query behavior |
| Scope mismatch between document, chunk, and embedding | Redundant protected fields plus consistency constraints and validation |
| Hallucinated citations | Opaque evidence IDs, structured output, citation allowlist, and claim validation |
| Weak handwritten OCR | Review-required threshold and explicit confidence propagation |
| Duplicate uploads under concurrency | Unique checksum constraints and transactional upsert behavior |
| Parser variability and malformed files | Bounded parsing, representative fixtures, and row/page-level error reporting |
| Embedding dimension/model changes | Store model/version/dimension; re-embed as a versioned operation |
| OpenAI data egress or PII exposure | Provider policy, minimization/redaction, explicit configuration, and local/mock default |
| Prompt injection in uploaded evidence | Treat evidence as data, no model tools, output validation, and audit flags |
| PII in logs and audit records | Structured metadata logging, hashing/redaction, and restricted audit access |
| Export bypasses retrieval controls | Exports use the same authorization/query services and reauthorize downloads |
| Spreadsheet formula injection | Prefix or escape dangerous cell values in XLSX/CSV-like content |
| FTS language/tokenization mismatch | Configurable PostgreSQL text-search configuration and multilingual test fixtures |
| Long OCR/embedding requests | PostgreSQL-backed job worker, timeouts, size limits, and observable job states |
| Confidence presented as certainty | Document it as a heuristic quality score and prefer unavailable below threshold |
| Local storage loss in cloud | Persistent volume for MVP; object-storage provider before public deployment |
| Empty starting repository | Establish conventions and baseline tests during Phase 1 |

## Recommended next step

Begin Phase 1 only after this plan is approved:

1. Initialize the repository structure.
2. Scaffold FastAPI and React applications.
3. Configure PostgreSQL with pgvector through Docker Compose.
4. Add Alembic, configuration handling, health endpoints, and test infrastructure.
5. Verify the empty application stack end to end.
6. Implement security and tenancy before adding ingestion or retrieval.

