# Architecture

This document maps the implementation to the reference architecture layers and shows
where isolation is enforced.

## System Architecture

```mermaid
graph TB
    subgraph CLIENT["Client Layer"]
        FE["React/Vite<br/>Evaluator UI"]
        EXT["External API<br/>Consumer"]
    end

    subgraph GATEWAY["API Gateway Layer"]
        direction LR
        CORS["CORS<br/>Middleware"]
        JWT["JWT Validation<br/>HS256 · issuer · audience"]
        HEADERS["Header Validation<br/>X-Product-ID · X-Tenant-ID"]
        SCOPE["Scope Resolution<br/>AuthorizationService"]
    end

    subgraph ORCHESTRATION["Query Orchestration Layer"]
        ROUTER["QueryRouter<br/>structured │ document │ hybrid"]
        PERM["Permission Check<br/>attendance:read · document:read · audit:write"]
    end

    subgraph INGESTION["Ingestion & Preprocessing Layer"]
        UPLOAD["Upload Handler<br/>multipart · size validation"]
        CHECKSUM["SHA-256<br/>Idempotency"]
        LOCK["Advisory Lock<br/>Logical Document"]

        subgraph PARSERS["Format Parsers"]
            CSV_P["CSV"]
            XLSX_P["XLSX<br/>multi-sheet"]
            DOCX_P["DOCX<br/>paragraph + table"]
            PDF_P["PDF<br/>text + OCR fallback"]
            OCR_P["Image OCR<br/>Tesseract"]
        end

        NORM["Attendance<br/>Normalizer"]
        CHUNK["Document<br/>Chunker"]
    end

    subgraph STORES["Knowledge Stores — PostgreSQL"]
        direction TB

        subgraph STRUCTURED_DB["Structured Store"]
            ATT_TBL["attendance_records<br/>canonical facts"]
            DOC_TBL["documents · document_versions<br/>ingestion_jobs · extracted_units"]
        end

        subgraph SEARCH_DB["Search Stores"]
            FTS["tsvector + GIN index<br/>PostgreSQL FTS"]
            VEC["vector 384 + HNSW index<br/>pgvector cosine"]
        end

        subgraph SECURITY_DB["Security & Audit"]
            RBAC_TBL["products · tenants · entities<br/>users · roles · permissions<br/>user_role_assignments"]
            AUDIT_TBL["audit_events<br/>append-only · trigger-protected"]
            RLS["28 RLS Policies<br/>4 per protected table"]
        end

        EXPORT_TBL["export_jobs<br/>requester-bound · TTL"]
    end

    subgraph RETRIEVAL["Retrieval & Context Building Layer"]
        STRUCT_R["Structured Retriever<br/>allowlisted SQL aggregates"]
        KW_R["Keyword Retriever<br/>websearch_to_tsquery · ts_rank_cd"]
        VEC_R["Vector Retriever<br/>cosine distance · score threshold"]
        FUSION["Reciprocal Rank<br/>Fusion"]
        CTX["Context Builder<br/>scope revalidation"]
    end

    subgraph GENERATION["Generation Layer"]
        LLM_MOCK["MockProvider<br/>deterministic"]
        LLM_OPENAI["OpenAIProvider<br/>configurable model"]
    end

    subgraph POSTPROCESSING["Post-processing & Governance Layer"]
        INJECT["Prompt-Injection<br/>Detection & Redaction"]
        PII["PII Minimization<br/>email · phone redaction"]
        CITE_V["Citation Validator<br/>evidence ID · claim overlap · grounding"]
        CONF["Confidence Scorer<br/>extraction · coverage · method agreement"]
        UNAVAIL["Unavailable Response<br/>Controller"]
        AUDIT_W["Audit Writer<br/>append-only events"]
    end

    subgraph EXPORT["Export Layer"]
        EXP_SVC["Export Service<br/>authorized record selection"]
        JSON_R["JSON<br/>Renderer"]
        XLSX_R["XLSX Renderer<br/>formula protection"]
        PDF_R["PDF<br/>Renderer"]
        EXP_DL["Download Handler<br/>requester-bound · TTL"]
    end

    FE --> CORS
    EXT --> CORS
    CORS --> JWT --> HEADERS --> SCOPE

    SCOPE -->|"AuthorizedScope<br/>+ RLS context"| ORCHESTRATION
    SCOPE -->|"AuthorizedScope"| INGESTION
    SCOPE -->|"AuthorizedScope"| EXPORT

    ROUTER --> STRUCT_R
    ROUTER --> KW_R
    ROUTER --> VEC_R

    UPLOAD --> CHECKSUM --> LOCK --> PARSERS --> NORM --> CHUNK

    NORM --> ATT_TBL
    CHUNK --> FTS
    CHUNK --> VEC

    STRUCT_R --> ATT_TBL
    KW_R --> FTS
    VEC_R --> VEC
    KW_R --> FUSION
    VEC_R --> FUSION

    FUSION --> CTX

    CTX --> INJECT --> PII
    PII --> LLM_MOCK
    PII --> LLM_OPENAI
    LLM_MOCK --> CITE_V
    LLM_OPENAI --> CITE_V
    CITE_V --> CONF --> UNAVAIL

    EXP_SVC --> ATT_TBL
    EXP_SVC --> JSON_R
    EXP_SVC --> XLSX_R
    EXP_SVC --> PDF_R

    AUDIT_W --> AUDIT_TBL
    RLS -.->|"enforced on every<br/>SELECT · INSERT · UPDATE · DELETE"| STRUCTURED_DB
    RLS -.->|"enforced"| SEARCH_DB
    RLS -.->|"enforced"| EXPORT_TBL

    style GATEWAY fill:#1a365d,color:#fff
    style STORES fill:#1a472a,color:#fff
    style RETRIEVAL fill:#4a2040,color:#fff
    style GENERATION fill:#3d3d00,color:#fff
    style POSTPROCESSING fill:#5a1a1a,color:#fff
    style INGESTION fill:#2d3748,color:#fff
    style EXPORT fill:#2a4365,color:#fff
    style RLS fill:#c53030,color:#fff,stroke:#c53030,stroke-width:3px
```

## Isolation Enforcement Points

The diagram below shows where the mandatory isolation context
(`product_id`, `tenant_id`, `entity_id`, `module`, RBAC, classification) is enforced.
The non-negotiable rule — **the model never decides access** — is satisfied by enforcing
all filters before context reaches the generation layer.

```mermaid
flowchart LR
    REQ["Incoming<br/>Request"] --> GW["Gateway<br/>JWT + Headers"]

    GW -->|"Principal"| AUTH["Authorization<br/>Service"]
    AUTH -->|"AuthorizedScope<br/>grants resolved<br/>from database"| RLS_CTX["PostgreSQL<br/>RLS Context<br/>set_config()"]

    RLS_CTX --> LAYER{"Retrieval<br/>Layer"}

    LAYER -->|"product_id<br/>tenant_id<br/>entity_id<br/>module<br/>classification ≤ ceiling"| SQL["SQL<br/>Predicates"]
    SQL -->|"defense in depth"| PG_RLS["PostgreSQL<br/>RLS Policies"]

    PG_RLS -->|"only permitted<br/>rows returned"| CTX_BUILD["Context<br/>Builder"]
    CTX_BUILD -->|"re-validates scope<br/>sanitizes content"| LLM["LLM<br/>Provider"]

    LLM -->|"raw output"| POST["Post-processing<br/>citation validation<br/>confidence gating"]

    POST -->|"validated answer<br/>or controlled<br/>unavailable"| RESP["Response"]

    style GW fill:#1a365d,color:#fff
    style AUTH fill:#2a4365,color:#fff
    style RLS_CTX fill:#c53030,color:#fff
    style PG_RLS fill:#c53030,color:#fff
    style SQL fill:#9b2c2c,color:#fff
    style CTX_BUILD fill:#4a2040,color:#fff
    style POST fill:#5a1a1a,color:#fff
```

### Enforcement summary

| Layer | Mechanism | What it prevents |
|---|---|---|
| Gateway | JWT validation, `X-Product-ID` / `X-Tenant-ID` headers | Unauthenticated or unscoped requests |
| Authorization | `AuthorizationService.resolve_scope()` from database | Forged or expired role claims |
| Application predicates | Explicit `WHERE` clauses on every query | Broad retrieval before filtering |
| PostgreSQL RLS | 28 row-level policies + `app_scope_allows()` function | Application bugs leaking rows |
| Context builder | Re-validates chunk ownership + scope | Stale or manipulated evidence IDs |
| Post-processing | Citation validation, confidence gating, unavailable controller | Hallucinated citations, low-confidence answers |

## Database Role Separation

```mermaid
graph LR
    ADMIN["attendance_admin<br/>Schema Owner<br/>Runs Alembic migrations<br/>Can bypass RLS"]
    APP["attendance_app<br/>Runtime Role<br/>No superuser · No BYPASSRLS<br/>Subject to all 28 RLS policies"]
    PG["PostgreSQL<br/>pgvector/pgvector:pg16"]

    ADMIN -->|"DDL · migrations"| PG
    APP -->|"DML only · RLS enforced"| PG

    style ADMIN fill:#b7791f,color:#fff
    style APP fill:#276749,color:#fff
    style PG fill:#2d3748,color:#fff
```

## Technology Stack

| Responsibility | Technology | Substitution rationale |
|---|---|---|
| API framework | FastAPI 0.115 | Async-capable, auto-generated OpenAPI, Pydantic-native |
| Database | PostgreSQL 16 via pgvector image | Single store for structured data, full-text search, and vector embeddings |
| Vector search | pgvector 0.8 | Eliminates separate vector DB; HNSW indexing in PostgreSQL |
| Full-text search | PostgreSQL `tsvector` + GIN | No Elasticsearch needed; integrated with RLS |
| Embeddings | sentence-transformers/all-MiniLM-L6-v2 | Free, local, no API key required; 384-dimensional |
| LLM generation | Configurable: Mock (default) or OpenAI | Mock enables deterministic testing; OpenAI for production |
| OCR | Tesseract via pytesseract | Free, local; no cloud dependency |
| Authentication | PyJWT (HS256) | Lightweight; production would use RS256 + JWKS |
| Migrations | Alembic | Standard SQLAlchemy migration tool |
| Frontend | React 18 + TypeScript + Vite 6 | Minimal evaluator UI; not the primary deliverable |
| PDF export | ReportLab 4 | Professional table rendering |
| XLSX export | openpyxl 3 | Formula-injection protection built in |
| Container | Docker Compose v2 | One-command local startup |
