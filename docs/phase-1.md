# Phase 1 Foundation

Phase 1 establishes a runnable application and verifies that PostgreSQL and pgvector are available. It intentionally contains no attendance-domain behavior.

## Runtime components

```text
Browser -> React/Vite -> FastAPI -> PostgreSQL + pgvector
```

PostgreSQL is the only application database. The database volume is persistent, and the API waits for the PostgreSQL health check before applying Alembic migrations and starting.

## Health semantics

- `/health/live` proves the API process can serve requests. It does not contact dependencies.
- `/health/ready` returns HTTP 200 only when PostgreSQL is reachable and the `vector` extension is installed.
- A dependency failure returns HTTP 503 with non-sensitive component state.

## Security boundary for this phase

`JWT_SECRET` is accepted as required configuration so later authentication work does not introduce a new secret-loading mechanism. Authentication, RBAC, tenant scoping, and row-level security are explicitly outside Phase 1.

