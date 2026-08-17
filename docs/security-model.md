# Phase 2 Security and Tenancy Foundation

## Trust boundary

The access token establishes only the external identity subject. Product, tenant, entity, module, role, permission, and classification access are loaded from PostgreSQL. Claims or request values cannot grant access by themselves.

Authenticated scoped requests provide:

```text
Authorization: Bearer <JWT>
X-Product-ID: <UUID>
X-Tenant-ID: <UUID>
```

JWT validation requires an HS256 signature, `sub`, `iat`, `exp`, the configured issuer, and the configured audience. Production deployments should replace the development HMAC adapter with their identity-provider integration while retaining the `Principal` boundary.

## Authorization scope

`AuthorizationService` resolves active database assignments for exactly one product and tenant. Missing users, inactive records, expired assignments, and cross-tenant requests receive the same unavailable response.

Each assignment becomes a separate `ScopeGrant` containing:

- Role ID
- Entity restriction or tenant-wide access
- Module restriction or all-module access
- Classification ceiling
- Permissions supplied by that role

Grants are never flattened. This prevents a confidential ceiling for Entity A from being combined with an Entity B assignment that only permits public records.

## PostgreSQL RLS context

The server serializes the already-resolved grants into transaction-local PostgreSQL settings with `set_config(..., true)`. The `app_scope_allows` database function checks product, tenant, entity, module, classification, and required permission against the same indivisible grant.

Future protected tables must define operation-specific RLS policies using this function. Application repositories must still add explicit authorization predicates; RLS is defense in depth.

The Compose database creates two roles:

- `POSTGRES_USER`: schema owner used only by Alembic.
- `POSTGRES_APP_USER`: non-owner role used by the API and tests.

## Audit foundation

Audit events carry product, tenant, optional entity, module, classification, actor, role IDs, request ID, action, resource, outcome, and metadata. PostgreSQL policies protect reads and writes using `audit:read` and `audit:write` grants.

A database trigger rejects updates and deletes, making events append-only within the application database. External immutable archival remains a future production enhancement.

## Phase boundary

Phase 2 does not provide user-management APIs, token issuance, attendance tables, ingestion, retrieval, LLM access, or exports. Those capabilities must reuse the authorization scope and RLS context introduced here.

