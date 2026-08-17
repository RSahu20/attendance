# Basic Evaluator Frontend

The React/Vite frontend intentionally implements one linear demonstration:

```text
connect authorized demo scope
  -> upload evidence
  -> inspect ingestion status
  -> ask a question
  -> inspect answer, confidence, and validated citations
  -> download JSON, XLSX, or PDF
```

It does not implement dashboards, analytics, administration, or authorization logic.
Every protected request sends the bearer token plus product and tenant headers. The
frontend service proxies same-origin `/api` and `/health` requests to the existing API
container, avoiding browser-hostname/CORS fragility. The backend resolves grants and
remains the source of truth.

## Start and connect

Start the existing stack:

```bash
docker compose up --build
```

In another terminal, generate a short-lived local demo scope and token:

```bash
docker compose run --rm \
  -e PYTHONPATH=/workspace/backend/src:/workspace/scripts \
  -v ./:/workspace -w /workspace api python scripts/demo_frontend_auth.py
```

Open <http://localhost:5173> and paste `bearer_token`, `product_id`, and `tenant_id` into
the Demo connection form. The helper verifies the token against the running API before
printing it. The token is signed from the configured local environment, contains identity
only, and expires after two hours. No secret or token is committed to the repository.

The context endpoint supplies authorized grants. Select the provided entity, module, and
classification before uploading or querying.

## Evaluator flow

1. Click **Use built-in demo CSV** (or select a fictional file in `samples/tenant-a`),
   then click **Upload and process**. The built-in option avoids local file-picker or
   browser sandbox restrictions during evaluation.
2. Review stage, status, extracted units, normalized records, review count, and safe errors.
3. Ask a structured or document/hybrid question. Example: `What was the average attendance percentage?`
4. Review the exact backend answer, status, retrieval mode, confidence, scope IDs, request/audit IDs, and any validated citations.
5. Ask an unsupported question to see the controlled unavailable state.
6. Use **Export JSON**, **Export XLSX**, and **Export PDF**. React requests and downloads
   artifacts; all selection, rendering, expiration, and authorization remain backend-owned.

## Error behavior

The interface distinguishes backend unavailability, invalid authentication, authorization
denial, upload or processing failure, query failure, controlled unavailable evidence, and
export failure. It displays safe API messages and never renders stack traces.

## Frontend checks

```bash
docker compose run --rm frontend npm test
docker compose run --rm frontend npm run build
```

The focused component tests cover upload, processing status, query submission, answered
and unavailable results, citations, confidence, all three export actions, and API errors.

For a non-interactive verification of the same live frontend/API journey:

```bash
docker compose run --rm \
  -e PYTHONPATH=/workspace/backend/src:/workspace/scripts \
  -v ./:/workspace -w /workspace api python scripts/demo_frontend_flow.py
```
