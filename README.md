# Enterprise RAG Attendance Intelligence

A self-contained MVP for an **Attendance Intelligence Agent** that accepts attendance
reports in multiple formats, normalizes them into a canonical model, answers
business questions through a retrieval-augmented pipeline, and provides grounded
citations, confidence scoring, and controlled unavailable responses — all within
mandatory product/tenant/entity/module/RBAC/classification isolation.

## Architecture

The system follows the reference architecture with seven clearly separated layers.
See [index.html](./index.html) for the full diagrams showing
isolation enforcement points, database role separation, and technology substitutions.

```
┌───────────────────────────────────────────────────────────────────┐
│  Client Layer          React/Vite evaluator UI · External APIs   │
├───────────────────────────────────────────────────────────────────┤
│  API Gateway           CORS · JWT · X-Product-ID · X-Tenant-ID   │
│                        → AuthorizedScope + PostgreSQL RLS context │
├───────────────────────────────────────────────────────────────────┤
│  Query Orchestration   Deterministic router: structured │        │
│                        document │ hybrid │ unsupported            │
├───────────────────────────────────────────────────────────────────┤
│  Ingestion             CSV · XLSX · DOCX · text-PDF · image-OCR  │
│                        · scanned-PDF OCR → canonical model       │
│                        SHA-256 idempotency · advisory locks      │
├───────────────────────────────────────────────────────────────────┤
│  Knowledge Stores      PostgreSQL 16 + pgvector                  │
│                        Structured facts · tsvector FTS · vector  │
│                        embeddings · 28 RLS policies              │
├───────────────────────────────────────────────────────────────────┤
│  Retrieval             Allowlisted SQL · keyword FTS · cosine    │
│                        vector · reciprocal-rank fusion            │
│                        Scope predicates BEFORE retrieval          │
├───────────────────────────────────────────────────────────────────┤
│  Generation            Mock (deterministic) or OpenAI provider   │
│                        Context receives only approved evidence   │
├───────────────────────────────────────────────────────────────────┤
│  Post-processing       Prompt-injection detection · PII redact   │
│                        Citation validation · confidence scoring  │
│                        Controlled unavailable responses           │
│                        Append-only audit events                   │
├───────────────────────────────────────────────────────────────────┤
│  Export                JSON · XLSX · PDF with same authorized     │
│                        records · formula-injection protection     │
│                        Requester-bound · TTL expiration           │
└───────────────────────────────────────────────────────────────────┘
```

**Non-negotiable design rule:** The model never decides access. All isolation filters
are enforced by explicit SQL predicates and PostgreSQL RLS policies *before* any context
is sent to the generation layer.

## Technology Choices

| Component | Technology | Why |
|---|---|---|
| API framework | FastAPI 0.115 | Async, auto-generated OpenAPI, Pydantic-native validation |
| Database | PostgreSQL 16 (pgvector image) | Single store for structured data, FTS, and vector search |
| Vector search | pgvector 0.8 + HNSW index | Eliminates separate vector DB; cosine similarity in PostgreSQL |
| Full-text search | PostgreSQL tsvector + GIN | Integrated with RLS; no Elasticsearch needed |
| Embeddings | sentence-transformers/all-MiniLM-L6-v2 | Free, local, 384-dimensional, no API key required |
| LLM generation | Mock (default) / OpenAI (optional) | Mock enables deterministic testing; OpenAI for real answers |
| OCR | Tesseract via pytesseract | Free, local, handles scanned images and PDFs |
| Authentication | PyJWT HS256 | Lightweight for MVP; production would use RS256 + JWKS |
| Migrations | Alembic | Standard SQLAlchemy migration tool |
| Frontend | React 18 + TypeScript + Vite 6 | Minimal evaluator UI; backend is the primary deliverable |
| PDF export | ReportLab 4 | Professional table rendering with landscape A4 |
| XLSX export | openpyxl 3 | Built-in formula-injection sanitization |
| Containers | Docker Compose v2 | One-command local startup |

## Prerequisites

- **Docker** with Docker Compose v2
- Optional for local development: Python 3.11+ and Node.js 20+

## Quick Start

The complete stack starts from a clean checkout in one command:

```bash
docker compose up --build
```

This uses the explicitly non-secret, local-only placeholder values from `.env.example`.

### Services

| Service | URL |
|---|---|
| Frontend (evaluator UI) | http://localhost:5173 |
| API documentation (Swagger) | http://localhost:8000/docs |
| OpenAPI spec (JSON) | http://localhost:8000/openapi.json |
| Liveness probe | http://localhost:8000/health/live |
| Readiness probe | http://localhost:8000/health/ready |

### Custom Environment

For persistent development, create a local environment file:

```bash
cp .env.example .env
```

At minimum, change these values:

- `POSTGRES_PASSWORD` and its matching value in `MIGRATION_DATABASE_URL`
- `POSTGRES_APP_PASSWORD` and its matching value in `DATABASE_URL`
- `JWT_SECRET` — replace with a random value of at least 32 bytes

The `.env` file is gitignored and overrides `.env.example` in Compose.

## Environment Variables

| Variable | Default | Purpose |
|---|---|---|
| `DATABASE_URL` | `postgresql+psycopg://...` | Runtime PostgreSQL connection (non-owner role) |
| `MIGRATION_DATABASE_URL` | `postgresql+psycopg://...` | Schema owner connection for Alembic |
| `APP_ENV` | `development` | Environment flag |
| `JWT_SECRET` | *(must change)* | HS256 signing key (≥32 bytes) |
| `JWT_ISSUER` | `attendance-intelligence` | Expected JWT issuer claim |
| `JWT_AUDIENCE` | `attendance-api` | Expected JWT audience claim |
| `CORS_ORIGINS` | `http://localhost:5173,...` | Comma-separated allowed browser origins |
| `LLM_PROVIDER` | `mock` | `mock` (deterministic) or `openai` |
| `OPENAI_API_KEY` | *(empty)* | Required when `LLM_PROVIDER=openai` |
| `OPENAI_MODEL` | `gpt-4o-mini` | OpenAI model identifier |
| `ANSWER_CONFIDENCE_THRESHOLD` | `0.55` | Minimum confidence to return an answer |
| `EMBEDDING_MODEL` | `sentence-transformers/all-MiniLM-L6-v2` | Local embedding model |
| `EMBEDDING_DIMENSION` | `384` | Must match migrated vector schema |
| `RETRIEVAL_LIMIT` | `8` | Maximum evidence items per retrieval |
| `SEMANTIC_SCORE_THRESHOLD` | `0.25` | Minimum cosine similarity for vector results |
| `OCR_PROVIDER` | `tesseract` | OCR engine for images and scanned PDFs |
| `OCR_CONFIDENCE_THRESHOLD` | `0.80` | Below this → `review_required` status |
| `STORAGE_PROVIDER` | `local` | File storage backend |
| `STORAGE_ROOT` | `/data/attendance` | Local storage root path |
| `EXPORT_TTL_SECONDS` | `3600` | Export artifact expiration (seconds) |
| `EXPORT_MAX_RECORDS` | `10000` | Maximum records per export |
| `MAX_UPLOAD_BYTES` | `26214400` | Maximum upload file size (25 MB) |
| `VITE_API_BASE_URL` | *(empty)* | Frontend API proxy; leave empty for Docker |

## API Endpoints

All authenticated endpoints require a Bearer JWT token plus `X-Product-ID` and
`X-Tenant-ID` headers. The server resolves the authorization scope from the database;
token claims do not grant access.

### Health

| Method | Path | Auth | Purpose |
|---|---|:---:|---|
| `GET` | `/health/live` | None | Process liveness |
| `GET` | `/health/ready` | None | PostgreSQL + pgvector availability |

### Authentication

| Method | Path | Auth | Purpose |
|---|---|:---:|---|
| `GET` | `/api/v1/auth/context` | JWT | Server-resolved grants for the requested scope |

### Ingestion

| Method | Path | Auth | Purpose |
|---|---|:---:|---|
| `POST` | `/api/v1/documents` | JWT | Upload and process a file (multipart) |
| `GET` | `/api/v1/ingestion-jobs/{job_id}` | JWT | Ingestion status, counts, and errors |

### Query

| Method | Path | Auth | Purpose |
|---|---|:---:|---|
| `POST` | `/api/v1/queries` | JWT | Ask a question → grounded answer with citations |

### Export

| Method | Path | Auth | Purpose |
|---|---|:---:|---|
| `POST` | `/api/v1/exports` | JWT | Request a JSON, XLSX, or PDF export |
| `GET` | `/api/v1/exports/{export_id}` | JWT | Export job status |
| `GET` | `/api/v1/exports/{export_id}/download` | JWT | Download the export artifact |

## API Examples

### 1. Upload attendance evidence

```bash
curl -X POST http://localhost:8000/api/v1/documents \
  -H "Authorization: Bearer $TOKEN" \
  -H "X-Product-ID: $PRODUCT_ID" \
  -H "X-Tenant-ID: $TENANT_ID" \
  -F "file=@samples/tenant-a/attendance.csv" \
  -F "entity_id=$ENTITY_ID" \
  -F "module=attendance" \
  -F "classification=1"
```

Response:

```json
{
  "job_id": "...",
  "document_id": "...",
  "document_version_id": "...",
  "checksum": "a1b2c3...",
  "status": "completed",
  "idempotent": false
}
```

### 2. Check ingestion status

```bash
curl http://localhost:8000/api/v1/ingestion-jobs/$JOB_ID \
  -H "Authorization: Bearer $TOKEN" \
  -H "X-Product-ID: $PRODUCT_ID" \
  -H "X-Tenant-ID: $TENANT_ID"
```

Response:

```json
{
  "job_id": "...",
  "status": "completed",
  "current_stage": "completed",
  "extracted_unit_count": 5,
  "normalized_record_count": 4,
  "review_required_count": 0,
  "error_count": 0,
  "errors": []
}
```

### 3. Ask a question

```bash
curl -X POST http://localhost:8000/api/v1/queries \
  -H "Authorization: Bearer $TOKEN" \
  -H "X-Product-ID: $PRODUCT_ID" \
  -H "X-Tenant-ID: $TENANT_ID" \
  -H "Content-Type: application/json" \
  -d '{
    "question": "How many employees were present on 2026-08-01?",
    "entity_id": "'$ENTITY_ID'",
    "module": "attendance",
    "classification": 1
  }'
```

Response:

```json
{
  "answer": "The authorized count is 2.",
  "tenant_context": { "tenant_id": "..." },
  "entity_context": { "entity_ids": ["..."] },
  "role_context": { "roles": ["..."] },
  "citations": [
    {
      "evidence_id": "ev_1",
      "source_locator": { "source_file": "attendance.csv", "row": 2 },
      "claim": "..."
    }
  ],
  "confidence": { "score": 0.95, "band": "high" },
  "retrieval_mode": "structured",
  "request_id": "...",
  "audit_id": "...",
  "status": "answered",
  "unavailable_reason": null
}
```

### 4. Request an export

```bash
curl -X POST http://localhost:8000/api/v1/exports \
  -H "Authorization: Bearer $TOKEN" \
  -H "X-Product-ID: $PRODUCT_ID" \
  -H "X-Tenant-ID: $TENANT_ID" \
  -H "Content-Type: application/json" \
  -d '{
    "entity_id": "'$ENTITY_ID'",
    "module": "attendance",
    "classification": 1,
    "format": "xlsx",
    "dataset": "attendance"
  }'
```

### 5. Download an export

```bash
curl -OJ http://localhost:8000/api/v1/exports/$EXPORT_ID/download \
  -H "Authorization: Bearer $TOKEN" \
  -H "X-Product-ID: $PRODUCT_ID" \
  -H "X-Tenant-ID: $TENANT_ID"
```

## Sample Data

The `samples/` directory contains synthetic attendance data:

| Directory | Contents | Purpose |
|---|---|---|
| `samples/tenant-a/` | CSV, XLSX, DOCX, text-PDF, scanned-PNG, scanned-PDF | Six-format ingestion demonstration |
| `samples/tenant-b/` | CSV | Tenant isolation testing |
| `samples/attendance_test_documents/` | CSV, XLSX, DOCX, PDF, scanned images, non-attendance files | Extended test corpus |

All people and employee identifiers are fictional. Regenerate binary samples:

```bash
docker compose run --rm -v .:/workspace -w /workspace api \
  python samples/generate_samples.py
```

## Run Tests

With the Compose stack running:

```bash
# Backend: 61 unit, integration, and security tests
docker compose run --rm api pytest

# Frontend: 4 interaction tests + production build
docker compose run --rm frontend npm test
docker compose run --rm frontend npm run build

# Linting and formatting
docker compose run --rm api ruff check src tests alembic
docker compose run --rm api ruff format --check src tests alembic
```

There is deliberately no SQLite fallback — all tests run against the real PostgreSQL
database with pgvector and RLS enabled.

### Test Coverage Summary

| Category | Count | What is tested |
|---|:---:|---|
| Application & config | 5 | Factory startup, Pydantic validation, environment parsing |
| Health | 4 | Liveness, readiness success/failure, pgvector check |
| Authentication | 3 | Valid JWT, wrong audience, missing bearer |
| Authorization & RLS | 7 | Cross-tenant denial, scope resolution, RLS context, grant composition |
| Security schema | 4 | Runtime role restrictions, RLS policies, append-only audit |
| Canonical storage | 7 | FTS/vector operation, constraints, checksum uniqueness, cross-entity/scope isolation |
| Ingestion parsers | 6 | CSV, multi-sheet XLSX, DOCX, text-PDF, OCR parsing |
| Normalization | 4 | Status mapping, date/time parsing, invalid records, lineage |
| Ingestion API | 6 | Upload, persistence, idempotency, versioning, authorization, OCR confidence |
| Query routing | 4 | Structured, document, hybrid, unsupported classification |
| Retrieval API | 5 | SQL aggregates, FTS, vector search, tenant isolation, unavailable response |
| Generation controls | 4 | Context revalidation, injection detection, citation validation, confidence |
| Exports API | 7 | JSON/XLSX/PDF rendering, access control, record consistency, TTL, formula protection |
| Frontend | 4 | Upload flow, query/answer/citations, unavailable response, all three exports |
| **Total** | **61 + 4** | |

### Mandatory Scenario Coverage

| # | Assignment Test Scenario | Status | Test Evidence |
|:---:|---|:---:|---|
| 1 | Mixed-format ingestion (≥4 types) | ✅ | 6 parsers tested |
| 2 | Extraction traceability | ✅ | Source locator and lineage verified |
| 3 | OCR/handwriting confidence handling | ✅ | Low-confidence → review_required |
| 4 | Idempotency | ✅ | Re-upload returns same version |
| 5 | Structured answers | ✅ | Allowlisted SQL aggregates |
| 6 | Evidence-grounded answers | ✅ | Citation validation with overlap checks |
| 7 | Unavailable answer | ✅ | Controlled response with reason code |
| 8 | Tenant isolation | ✅ | Cross-tenant denial in auth + RLS |
| 9 | RBAC/entity isolation | ✅ | Entity-scoped grants + RLS |
| 10 | Prompt injection | ✅ | Pattern detection → redaction + penalty |
| 11 | PII/data leakage | ✅ | Email/phone redaction; RLS |
| 12 | Provider failure | ✅ | Exception → PROVIDER_UNAVAILABLE |
| 13 | Export consistency | ✅ | Same authorized record set for all formats |

## Database Migrations

The API container runs `alembic upgrade head` before starting. To run manually:

```bash
docker compose run --rm api alembic upgrade head
```

| Revision | Purpose |
|---|---|
| `20260815_0001` | Enable pgvector extension |
| `20260815_0002` | Identity, RBAC, classification, RLS context, append-only audit |
| `20260815_0003` | Documents, versions, extraction, canonical attendance, FTS chunks, vector embeddings, 28 RLS policies |
| `20260815_0004` | Ingestion progress fields, logical-document uniqueness |
| `20260815_0005` | Cosine HNSW index for vector retrieval |
| `20260815_0006` | Protected export jobs, export permission, RLS policies |

## Make Targets

```bash
make setup     # Copy .env.example to .env
make up        # docker compose up --build
make down      # docker compose down
make logs      # docker compose logs -f
make test      # docker compose run --rm api pytest
make lint      # Ruff lint check
make format    # Ruff format
make migrate   # Alembic upgrade head
```

## Security Model

The two-role PostgreSQL pattern separates schema ownership from runtime access:

- **`attendance_admin`** — Owns tables, runs migrations (Alembic). Can bypass RLS.
- **`attendance_app`** — Runtime role used by the API. No superuser, no `BYPASSRLS`.
  Subject to all 28 RLS policies.

This separation prevents the application from accidentally bypassing row-level security.


## Project Structure

```
attendance/
├── backend/
│   ├── src/attendance/
│   │   ├── api/              # FastAPI routes and dependencies
│   │   ├── audit/            # Append-only audit service
│   │   ├── db/               # SQLAlchemy models, session, RLS
│   │   ├── domain/           # Pure Pydantic domain models
│   │   ├── exports/          # JSON/XLSX/PDF renderers and service
│   │   ├── generation/       # LLM context, citations, confidence
│   │   ├── ingestion/        # Parsers, normalization, chunking
│   │   ├── providers/        # Pluggable LLM, embedding, OCR, storage
│   │   ├── retrieval/        # Structured, keyword, vector retrieval
│   │   └── security/         # JWT auth, authorization service
│   ├── tests/
│   │   ├── unit/             # 11 unit test files
│   │   └── integration/      # 8 PostgreSQL integration test files
│   └── alembic/              # 6 migration scripts
├── frontend/
│   └── src/                  # React evaluator UI + tests
├── docs/                     # Architecture, security, ingestion, retrieval docs
├── samples/                  # Synthetic tenant-a/tenant-b data
├── scripts/                  # Demo scripts and DB init
├── docker-compose.yml        # One-command startup
├── .env.example              # Local placeholder configuration
└── Makefile                  # Convenience targets
```

## Known Limitations and Production Roadmap

### Implemented (MVP)

- ✅ All 13 mandatory test scenarios pass
- ✅ Six input formats (CSV, XLSX, DOCX, text-PDF, image-OCR, scanned-PDF-OCR)
- ✅ Canonical attendance normalization with traceability
- ✅ Structured, document, and hybrid retrieval modes
- ✅ Mock and OpenAI LLM providers
- ✅ Grounded answers with validated citations and confidence
- ✅ JSON, XLSX, and PDF exports with consistent authorized records
- ✅ 28 PostgreSQL RLS policies for defense-in-depth isolation
- ✅ Append-only audit trail
- ✅ React evaluator UI with full workflow
- ✅ Docker Compose one-command startup

### Simulated / Configured for MVP

- JWT tokens are self-issued for demo purposes; production would use an external identity
  provider with RS256/JWKS
- The `MockProvider` generates deterministic answers from the first evidence item; switch
  to `LLM_PROVIDER=openai` for real generative answers
- OCR uses Tesseract locally; production could use cloud OCR for higher accuracy
- File storage is local disk; configurable for cloud object storage

### Deferred to Production

- Asynchronous ingestion worker (current processing is synchronous per request)
- Advanced PDF table extraction and human review workflow
- Rate limiting, security headers, TLS termination
- Stored query/answer history
- Advanced analytics dashboard
- External audit log archival
- Backup/restore and observability infrastructure
- Cloud deployment (Kubernetes, managed PostgreSQL)
