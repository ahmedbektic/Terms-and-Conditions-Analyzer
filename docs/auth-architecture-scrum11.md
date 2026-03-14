# SCRUM-11 Auth Architecture (Supabase JWT)

This document describes where authentication lives after SCRUM-11 and how ownership is enforced without coupling auth to business services.

## 1) Scope and Intent

- Auth provider: Supabase Auth (frontend sign-in/up/OAuth) + Supabase-issued JWT access tokens.
- Backend authorization model: owner scoping through existing `subject_type` + `subject_id`.
- Non-goal in SCRUM-11: automatic migration of anonymous session-owned rows to authenticated users.

## 2) Frontend Boundaries

Auth modules:

- `frontend/src/lib/auth/contracts.ts`
- `frontend/src/lib/auth/supabaseClient.ts`
- `frontend/src/lib/api/createDashboardApiClient.ts`
- `frontend/src/features/auth/hooks/useAuthSession.ts`
- `frontend/src/features/auth/AuthProvider.tsx`
- `frontend/src/features/auth/AuthEntryPoint.tsx`
- `frontend/src/features/auth/components/LoginScreen.tsx`

Dashboard modules remain auth-agnostic:

- `frontend/src/features/dashboard/*`
- `frontend/src/lib/api/client.ts` (Bearer-token transport seam only)

### Frontend Request/Auth Flow

1. `AuthProvider` initializes `useAuthSession`.
2. `useAuthSession` boots persisted session via `AuthClient.getSession()` and listens to auth-state changes.
3. `AuthEntryPoint` decides UI:
   - `loading` -> session bootstrap screen
   - `unauthenticated` -> `LoginScreen`
   - `authenticated` -> `DashboardPage`
4. `AuthEntryPoint` builds an authenticated API client via `createDashboardApiClient`.
5. `DashboardPage` consumes the injected client and remains auth-agnostic.
6. `DashboardApiClient` injects `Authorization: Bearer <token>` on API requests.

## 3) Backend Boundaries

Auth modules:

- `backend/app/auth/supabase_jwt.py` (JWT verification)
- `backend/app/auth/runtime.py` (provider-aware resolver construction)
- `backend/app/auth/subject_resolver.py` (header -> ownership subject policy)
- `backend/app/api/deps.py` (FastAPI dependency wiring and error mapping)

Business/persistence modules remain auth-agnostic:

- `backend/app/services/analysis_service.py`
- `backend/app/repositories/interfaces.py` + repository implementations

### Backend Request/Auth Flow

1. Route depends on `get_request_subject` (`backend/app/api/deps.py`).
2. Dependency calls `AuthSubjectResolver.resolve(...)`.
3. Resolver verifies Bearer token via `SupabaseJwtVerifier` and maps to:
   - `("supabase_user", <jwt sub>)` for authenticated calls.
4. Dependency maps result to `RequestSubject`.
5. Service/repository calls filter strictly by `subject_type` + `subject_id`.

Routes remain thin: they never parse JWTs and never decide ownership policy directly.

## 4) Ownership Semantics After SCRUM-11

Canonical authenticated ownership:

- `subject_type = "supabase_user"`
- `subject_id = <Supabase JWT sub claim>`

Important rule:

- No implicit row migration occurs at request time.
- Existing historical anonymous rows remain unmigrated unless an explicit
  migration/backfill story is implemented.

## 5) SCRUM-9 Extension Reuse Seams

Frontend:

- Extension UI can reuse `AuthClient` contract and `useAuthSession` orchestration, with a runtime-specific auth adapter if needed.
- API transport already supports token injection via `DashboardApiClientConfig.getAccessToken`.

Backend:

- Extension can call the same authenticated API endpoints and dependency chain (`Authorization` header + `get_request_subject`).
- No extension-specific auth logic is required in services/repositories.

## 6) Configuration Footnotes

Backend JWT verification uses either:

- `SUPABASE_JWT_SECRET` (HS256 secret mode), or
- `SUPABASE_JWT_JWKS_URL` / derived JWKS from issuer.

Common production-like setup uses:

- `SUPABASE_JWT_ISSUER=https://<project-ref>.supabase.co/auth/v1`
- `SUPABASE_JWT_JWKS_URL=https://<project-ref>.supabase.co/auth/v1/.well-known/jwks.json`

## 7) Current Known Constraints

- Route-level response mapping has some duplication outside auth scope.
- Ownership migration tooling is not implemented yet.
- `subject_type` remains generic for repository compatibility, even though
  request auth currently resolves to `supabase_user` only.
