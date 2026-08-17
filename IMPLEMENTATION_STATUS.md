# Enterprise RAG Attendance Intelligence — Implementation Status

**Audit date:** 2026-08-15  
**Current implementation boundary:** Foundation, security/tenancy, canonical storage,
ingestion/normalization, authorized retrieval, grounded generation, secure exports, and
the basic evaluator frontend  
**Architecture:** FastAPI modular monolith with PostgreSQL as the only application
database

## Executive summary

The repository currently implements the first four layers required by the
approved architecture:

1. A runnable FastAPI, React/Vite, PostgreSQL, pgvector, Alembic, and Docker Compose
   application stack.
2. Authentication validation, server-resolved tenant/RBAC/classification scope,
   PostgreSQL row-level-security context, and append-only audit storage.
3. Canonical attendance validation and protected PostgreSQL storage for documents,
   versions, extraction lineage, attendance facts, full-text-search chunks, and vector
   embeddings.
4. Authenticated multi-format upload, local storage, checksum/versioning, deterministic
   parsing and normalization, Tesseract OCR, lineage, chunking, status, and ingestion
   audit events.
5. Deterministic structured/document/hybrid routing, allowlisted SQL aggregates,
   PostgreSQL FTS, local embeddings, authorized pgvector search, fusion, evidence
   lineage, controlled unavailable results, and retrieval audit events.
6. Scope-revalidated context, mock/OpenAI provider abstractions, prompt-injection and PII
   controls, citation validation, confidence gating, controlled unavailable answers, and
   generation audit events.
7. Authorized JSON/XLSX/PDF rendering, requester-bound artifact access, formula-injection
   protection, expiration cleanup, and export audit events.
8. A basic React evaluator flow covering upload, processing, question, grounded result,
   citations/confidence, unavailable evidence, and three-format download.

The system now ingests evidence, produces grounded answers from authorized facts/context,
and exports authorized canonical records through a working evaluator-facing UI. Stored
query history and advanced product UI remain future work.

## Status legend

| Status | Meaning |
|---|---|
| Implemented | Working code exists and is covered by relevant tests. |
| Foundation only | Models, interfaces, or storage exist, but the end-to-end feature does not. |
| Not implemented | No functional implementation exists yet. |

## Assignment goal coverage

| # | Assignment goal | Status | Current evidence |
|---:|---|---|---|
| 1 | Accept attendance evidence in multiple formats | Implemented | Authenticated CSV, XLSX, DOCX, text-PDF, image, and scanned-PDF upload works. |
| 2 | Normalize inputs into a canonical model | Implemented | Deterministic alias, date/time/status/percentage/duration normalization produces validated canonical records. |
| 3 | Store structured attendance in PostgreSQL | Implemented | Ingestion persists protected attendance records, extraction lineage, chunks, versions, and job state. |
| 4 | Semantic retrieval with PostgreSQL + pgvector | Implemented | Local MiniLM embeddings, authorized cosine retrieval, and HNSW indexing use PostgreSQL only. |
| 5 | PostgreSQL full-text keyword retrieval | Implemented | Authorized PostgreSQL FTS retrieval uses the generated `tsvector` and GIN index. |
| 6 | Structured/document/hybrid routing | Implemented | A deterministic router selects allowlisted SQL, document, or combined retrieval. |
| 7 | Pre-LLM product/tenant/entity/module/RBAC/classification enforcement | Implemented | Operation checks, explicit predicates, and RLS run before facts or evidence leave PostgreSQL. |
| 8 | Grounded answers with validated citations | Implemented | Typed provider output is checked against server-issued evidence IDs, source locators, and claim/answer support. |
| 9 | Confidence and controlled unavailable responses | Implemented | Deterministic scoring includes retrieval/extraction/citation quality and gates low-quality or invalid answers. |
| 10 | JSON, XLSX, and PDF export | Implemented | All formats use one authorized record selection; XLSX sanitizes formulas and artifacts expire. |
| 11 | Audit logging | Implemented for MVP | Upload/version/ingestion, retrieval, generation, and export outcomes use append-only audit events. |
| 12 | Security and integration tests | Implemented for current scope | PostgreSQL, pgvector, JWT, scope, RLS, cross-tenant/entity, constraints, FTS, and vector storage are tested. |
| 13 | Basic React frontend | Implemented | The documented single-page evaluator flow supports upload, status, query, answer/citations/confidence, unavailable responses, and exports. |
| 14 | Docker Compose runtime | Implemented | `postgres`, `api`, and `frontend` run through Compose with persistent PostgreSQL storage. |

## Implemented backend foundation

- Python 3.11 application package.
- FastAPI application factory and lifecycle cleanup.
- Pydantic v2 environment configuration.
- PostgreSQL-only URL validation; there is no SQLite fallback.
- Minimum 32-byte JWT secret validation.
- Fixed embedding schema dimension validation at 384.
- Configurable CORS origins.
- SQLAlchemy 2.x engine and per-request session dependency.
- Alembic migrations executed automatically before API startup.
- Liveness endpoint that does not depend on external services.
- Readiness endpoint that verifies both PostgreSQL connectivity and pgvector.
- Ruff linting/formatting and pytest configuration.

### Implemented API endpoints

| Method | Endpoint | Purpose | Authentication |
|---|---|---|---|
| `GET` | `/health/live` | Confirms the FastAPI process is serving requests. | None |
| `GET` | `/health/ready` | Confirms PostgreSQL and pgvector availability. | None |
| `GET` | `/api/v1/auth/context` | Returns the caller's server-resolved grants for the requested product and tenant. | Bearer JWT plus `X-Product-ID` and `X-Tenant-ID` |
| `POST` | `/api/v1/documents` | Uploads, parses, normalizes, chunks, and stores attendance evidence. | Bearer JWT, protected headers, and scoped write permissions |
| `GET` | `/api/v1/ingestion-jobs/{job_id}` | Returns protected ingestion status, counts, and safe errors. | Bearer JWT, protected headers, and scoped read permission |
| `POST` | `/api/v1/queries` | Produces a grounded answer from authorized structured/document/hybrid evidence. | Bearer JWT, protected headers, scoped read permissions, and audit write permission |
| `POST` | `/api/v1/exports` | Requests a JSON, XLSX, or PDF export of authorized attendance records. | Bearer JWT, protected headers, and scoped read/export/audit permissions |
| `GET` | `/api/v1/exports/{export_id}` | Returns the status of a requester-bound export job. | Bearer JWT, protected headers, and scoped export permission |
| `GET` | `/api/v1/exports/{export_id}/download` | Downloads the completed export artifact. | Bearer JWT, protected headers, and scoped read/export/audit permissions |

User-management, stored-query, and audit-query APIs are not implemented.

## Implemented authentication and authorization foundation

### JWT validation

- Accepts bearer tokens through FastAPI's HTTP bearer dependency.
- Uses the configured HS256 secret, issuer, and audience.
- Requires `sub`, `iat`, `exp`, `iss`, and `aud` claims.
- Returns a minimal immutable `Principal` containing only the authenticated subject.
- Does not trust token claims to grant tenant, role, entity, module, or classification
  access.

Token issuance, refresh tokens, identity-provider discovery, JWKS, and user-management
APIs are not implemented.

### Server-resolved authorization

- Resolves the authenticated subject to an active database user.
- Verifies the requested product and tenant are active.
- Loads only active, currently valid role assignments for that exact product and tenant.
- Resolves permissions from database role-permission relationships.
- Preserves every assignment as an indivisible `ScopeGrant`.
- Supports tenant-wide or entity-restricted grants.
- Supports all-module or module-restricted grants.
- Enforces ordered classification ceilings:
  - `PUBLIC = 0`
  - `INTERNAL = 1`
  - `CONFIDENTIAL = 2`
  - `RESTRICTED = 3`
- Uses the same non-disclosing `Requested scope is unavailable` response for inaccessible
  scopes.

Preserving individual grants prevents a permission from one assignment being combined
with the entity or classification ceiling from a different assignment.

### PostgreSQL RLS context

- Serializes trusted server-resolved grants into transaction-local PostgreSQL settings.
- Sets user, product, tenant, and authorization grants with `set_config(..., true)`.
- Uses the PostgreSQL `app_scope_allows` function to evaluate product, tenant, entity,
  module, permission, and classification together.
- Uses a dedicated non-owner application database role.
- The application role is neither a superuser nor permitted to bypass RLS.
- The separate migration role owns and migrates the schema.

Retrieval repositories add explicit protected-scope predicates; RLS remains the database
defense-in-depth layer.

## Implemented database schema

### Identity and RBAC tables

| Table | Implemented purpose |
|---|---|
| `products` | Product identity and active status. |
| `tenants` | Product-owned tenant identity and active status. |
| `entities` | Tenant-scoped entities with protected parent relationships. |
| `users` | External identity subjects and active status. |
| `permissions` | Named application permissions. |
| `roles` | Product/tenant-scoped roles. |
| `role_permissions` | Role-to-permission association. |
| `user_role_assignments` | Time-bounded entity/module/classification role grants. |

### Audit table

| Table | Implemented purpose |
|---|---|
| `audit_events` | Actor, role IDs, request ID, protected scope, action, resource, outcome, and metadata. |

Audit events are protected by read/write RLS policies. A database trigger rejects updates
and deletes, making application audit rows append-only.

### Document and canonical attendance tables

| Table | Implemented purpose |
|---|---|
| `documents` | Stable logical document identity and protected scope. |
| `document_versions` | Ordered versions, SHA-256 checksum, file metadata, storage key, parser state, and current-version marker. |
| `ingestion_jobs` | Ingestion execution stage, outcome, counters, and safe structured errors. |
| `extracted_units` | Parsed page/sheet/row/block text, source locator, extraction method/confidence, and review state. |
| `attendance_records` | Canonical structured attendance facts with complete source lineage. |
| `document_chunks` | Protected text chunks with provenance and a generated search vector. |
| `chunk_embeddings` | Protected embedding metadata and pgvector values. |

### Canonical attendance fields

The canonical model and table include:

- Product, tenant, entity, module, and classification.
- External subject ID and optional display name.
- Attendance date, session identifiers, session name, and course/group.
- Status: present, absent, late, excused, partial, or unknown.
- Optional scheduled, check-in, and check-out timestamps.
- Optional scheduled minutes, attended minutes, attendance percentage, and late minutes.
- Source document, document version, extracted unit, and source record key.
- Raw row metadata.
- Extraction method and confidence.
- Review status and normalization warnings.
- Optional recorded timestamp plus database creation/update timestamps.

Pydantic and PostgreSQL constraints validate percentage/confidence ranges, non-negative
durations, valid status values, and timestamp ordering.

### Idempotency and versioning

- A logical document version is unique by `(document_id, sha256)`.
- Version numbers are unique per logical document and must be positive.
- A partial unique index permits at most one current version per document.
- Extracted source keys are unique within a document version.
- Attendance source record keys are unique within a document version.

Uploads compute SHA-256, serialize the protected logical-document operation with an
advisory lock, reuse the same version for matching content, and create/supersede versions
for changed content. Long-term storage retention/orphan cleanup remains deferred.

### Search-ready storage

- `document_chunks.search_vector` is a stored, non-null generated PostgreSQL `tsvector`.
- It uses the PostgreSQL `english` text-search configuration.
- A GIN index exists on the generated search vector.
- `chunk_embeddings.embedding` uses pgvector `vector(384)`.
- Embedding model and version metadata are stored with each embedding.

Text querying/ranking, semantic cosine distance, explicit authorized embedding backfill,
HNSW indexing, and reciprocal-rank fusion are implemented. Reranking and final LLM
context construction are deferred.

### Protected storage enforcement

Every Phase 3 protected table carries:

- `product_id`
- `tenant_id`
- `entity_id`
- `module`
- `classification`

Composite foreign keys prevent child records from changing the protected scope inherited
from their parent. The seven Phase 3 protected tables each have separate select, insert,
update, and delete RLS policies, for 28 policies total.

## Implemented audit foundation

The audit append service can create an event with:

- Request and actor IDs.
- Product, tenant, optional entity, module, and classification.
- Resolved role IDs.
- Action, resource type/ID, outcome, and metadata.

This service leaves transaction ownership to its caller. Upload/version/ingestion,
retrieval, generation, and export paths all use it.

## Implemented frontend

- React 18 with TypeScript and Vite 6.
- Environment-configured API base URL.
- Browser request to `/health/live`; visible checking, available, and unavailable API states.
- Local demo connection through the authorization-context endpoint.
- File upload with entity/module/classification selection.
- Polling-based ingestion status with counts and error display.
- Question submission with grounded answer, citation, confidence, and context display.
- Controlled unavailable-evidence display with reason codes.
- JSON, XLSX, and PDF export buttons with download-and-save behavior.
- Focused Vitest/Testing Library interaction tests covering the full evaluator flow.
- Dockerized development startup.

Advanced analytics dashboard, product navigation, and production frontend packaging are
not yet implemented.

## Implemented Docker and operations foundation

### Compose services

| Service | Implementation |
|---|---|
| `postgres` | `pgvector/pgvector:pg16`, persistent named volume, health check, initialization script. |
| `api` | Python 3.11 FastAPI image; waits for healthy PostgreSQL, migrates to head, starts Uvicorn, and retains its local embedding-model cache. |
| `frontend` | Node 20/Vite development server connected to the API health endpoint. |

- PostgreSQL is the only application database.
- The initialization script creates the restricted runtime database role.
- `.env.example` contains local placeholders only; no real secrets are stored.
- `.env` is optional and ignored by Git.
- No Redis, MongoDB, external vector database, Kafka, Celery, or Kubernetes component has
  been added.

### Available Make targets

- `make setup`
- `make up`
- `make down`
- `make logs`
- `make test`
- `make lint`
- `make format`
- `make migrate`

## Alembic migrations

| Revision | Purpose |
|---|---|
| `20260815_0001` | Enable and verify the PostgreSQL `vector` extension. |
| `20260815_0002` | Add product/tenant/entity/user, RBAC, classification, RLS context, and append-only audit foundations. |
| `20260815_0003` | Add protected documents, versions, ingestion/extraction storage, canonical attendance, FTS chunks, vector embeddings, constraints, and RLS policies. |
| `20260815_0004` | Add ingestion progress/error fields and logical-document uniqueness for safe idempotency. |
| `20260815_0005` | Add a cosine HNSW index for authorized semantic retrieval. |
| `20260815_0006` | Add protected export jobs, export permission, constraints, indexes, and RLS policies. |

Current verified migration head: `20260815_0006`.

## Test coverage and latest results

Latest packaged verification result:

```text
61 tests collected
61 passed
4 frontend interaction tests passed
Frontend production build passed
Frontend npm audit: 0 vulnerabilities
Ruff lint passed
Ruff format check passed
Alembic check: No new upgrade operations detected
```

Current tests cover:

- Application creation and OpenAPI startup.
- Liveness and readiness success/failure behavior.
- PostgreSQL connectivity and pgvector availability.
- Environment configuration validation.
- Valid JWT claims and wrong-audience rejection.
- Missing bearer-token rejection.
- Cross-tenant authorization denial.
- Tenant-scoped authorization-context responses.
- Prevention of cross-grant privilege composition.
- Runtime database role ownership and RLS-bypass restrictions.
- Authorized versus missing-RLS-context audit access.
- Append-only audit-event enforcement.
- Canonical attendance validation.
- Full-text-search and vector column operation.
- Attendance database constraints.
- Document checksum uniqueness.
- Presence of operation-specific RLS policies.
- Cross-entity protected-row isolation.
- Rejection of cross-scope document versions.
- CSV, multi-sheet XLSX, DOCX, text-PDF, and OCR parsing.
- Deterministic normalization, structured invalid-record issues, and source lineage.
- Authenticated upload, persistence, chunks, and queryable ingestion status.
- Same-checksum idempotency and changed-checksum versioning.
- Upload authorization and tenant isolation during ingestion.
- Low-confidence OCR review propagation.
- Deterministic structured, document, hybrid, and unsupported query routing.
- Authorized SQL aggregation, PostgreSQL FTS, pgvector retrieval, and reciprocal-rank fusion.
- Retrieval tenant/entity/classification denial and controlled unavailable responses.
- Retrieval evidence lineage and explicit writer-authorized embedding persistence.
- Context revalidation, PII minimization, and prompt-injection redaction.
- Mock/OpenAI typed provider contracts and provider-failure handling.
- Invented/unsupported citation rejection with one bounded correction retry.
- Grounding validation, review-aware confidence scoring, and answer threshold gating.
- Final tenant/entity/role context and generation audit responses.
- JSON/XLSX/PDF export rendering and logical record consistency.
- Export tenant/entity/classification/module/RBAC and requester isolation.
- Export source lineage, XLSX formula protection, audit metadata, expiration, and cleanup.
- Frontend upload/status, query/answer, citations/confidence, unavailable state, all export
  buttons, and safe API error behavior.

Direct database verification also confirmed:

```text
embedding_type: vector(384)
search_vector: generated ALWAYS, NOT NULL
protected Phase 3 RLS policies: 28
FTS GIN indexes: 1
pgvector HNSW indexes: 1
runtime role superuser/BYPASSRLS: false/false
pgvector version: 0.8.4
live API operations: 9
live export jobs: JSON/XLSX/PDF completed with 12 records each
live export logical record consistency: true
live frontend/API/Swagger responses: 200/200/200
live frontend evaluator flow: upload, structured/cited/unavailable query, and all exports passed
```

## Remaining implementation work

### Ingestion production hardening

- Optional asynchronous/PostgreSQL-backed worker for large files; MVP processing is
  synchronous and records each stage.
- Content-signature/MIME inspection beyond extension, parser, and corruption validation.
- Better complex PDF table extraction and human review workflow.
- Storage retention/orphan reconciliation and optional cloud storage provider.

### Generation production hardening

- More sophisticated claim decomposition and semantic entailment validation.
- Provider-specific rate limits, retry policy, cost controls, and production evaluations.
- Stored query/answer history with protected retention controls.

### Privacy, advanced UI, and deployment

- Optional dashboard, analytics, admin, and product navigation.
- Security headers, rate limits, production identity provider, and secret manager.
- Production frontend build/server and TLS ingress.
- Backup/restore, observability, immutable external audit archive, and cloud deployment.

## Current runnable commands

Start the complete stack:

```bash
docker compose up --build
```

Run all backend tests:

```bash
docker compose run --rm api pytest
```

Run quality checks:

```bash
docker compose run --rm api ruff check src tests alembic
docker compose run --rm api ruff format --check src tests alembic
docker compose run --rm api alembic check
```

Runtime URLs:

- Frontend: <http://localhost:5173>
- API documentation: <http://localhost:8000/docs>
- Liveness: <http://localhost:8000/health/live>
- Readiness: <http://localhost:8000/health/ready>

## Overall conclusion

The repository implements tested, runnable, authorized ingestion, retrieval, grounded
generation, and secure JSON/XLSX/PDF export pipelines with strong database-level scope
isolation. All 13 mandatory assignment test scenarios are covered. Remaining work is
limited to production hardening, advanced UI, and cloud deployment infrastructure.
