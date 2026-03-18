# SCRUM-11 Developer Handoff (Preparing SCRUM-9)

## 1. Current feature status after SCRUM-11

- Web app now uses Supabase Auth for sign-up/sign-in (email/password + Google initiation flow).
- Backend access is JWT-only for protected endpoints.
- Dashboard history/analysis requests are authenticated and owner-scoped by user identity.
- Legacy `X-Session-Id` ownership flow has been removed from runtime code paths.
- Existing SCRUM-5 report workflows still work for authenticated users:
  - submit + analyze
  - list saved reports
  - open prior report details

## 2. Frontend auth architecture

Primary boundaries:

- Auth contracts/provider adapter:
  - `frontend/src/lib/auth/contracts.ts`
  - `frontend/src/lib/auth/supabaseClient.ts`
- Auth state orchestration:
  - `frontend/src/features/auth/hooks/useAuthSession.ts`
  - `frontend/src/features/auth/AuthProvider.tsx`
- Auth screen + app-level auth gate:
  - `frontend/src/features/auth/components/LoginScreen.tsx`
  - `frontend/src/features/auth/AuthEntryPoint.tsx`
- Transport client factory (shared seam for web/extension):
  - `frontend/src/lib/api/createDashboardApiClient.ts`

Flow:

1. `AuthProvider` boots and subscribes auth session state.
2. `AuthEntryPoint` chooses login vs dashboard.
3. In authenticated state, `AuthEntryPoint` injects an API client built with `getAccessToken`.
4. Dashboard feature remains auth-agnostic and uses only `DashboardApiClient`.

## 3. Backend auth architecture

Primary boundaries:

- JWT verification:
  - `backend/app/auth/supabase_jwt.py`
- Request subject resolution (Bearer -> ownership tuple):
  - `backend/app/auth/subject_resolver.py`
- Auth runtime wiring (config -> verifier/resolver):
  - `backend/app/auth/runtime.py`
- API dependency seam:
  - `backend/app/api/deps.py`

Flow:

1. Route depends on `get_request_subject`.
2. Dependency resolves owner from `Authorization: Bearer <token>`.
3. Resolved subject is passed to service layer (`RequestSubject`).
4. Services/repositories filter data by ownership fields (`subject_type`, `subject_id`).

## 4. Ownership and persistence model

- Ownership remains modeled as:
  - `subject_type`
  - `subject_id`
- SCRUM-11 canonical authenticated ownership:
  - `subject_type = "supabase_user"`
  - `subject_id = <JWT sub>`
- No implicit migration/backfill was added for historical anonymous rows.
- Repository/service contracts were intentionally preserved for future flexibility.

## 5. API contract summary relevant to extension reuse

JWT-protected endpoints to reuse:

- `POST /api/v1/reports/analyze`
  - one-shot extension flow candidate
- `GET /api/v1/reports`
  - authenticated history list
- `GET /api/v1/reports/{report_id}`
  - report detail
- `POST /api/v1/agreements`
  - staged flow (store extracted terms first)
- `POST /api/v1/agreements/{agreement_id}/analyses` (`{"trigger":"manual"}`)
  - staged analysis trigger

Auth requirement:

- `Authorization: Bearer <supabase_access_token>`

## 6. Known limitations / temporary decisions

- Analyzer remains deterministic keyword logic (`deterministic-keyword-v1`), not LLM-backed.
- Historical anonymous data is not automatically reassigned to authenticated users.
- Response mapping for reports is centralized, but broader route mapping consolidation is still possible later.
- No extension-specific ingestion/parsing logic exists yet (intentionally).

## 7. Recommended SCRUM-9 integration points

Reuse, do not reimplement:

- Frontend auth/session abstraction (`AuthClient` + `useAuthSession` pattern).
- API transport seam (`createDashboardApiClient` / `DashboardApiClient`).
- Existing protected backend endpoints and ownership enforcement.

Extension should add:

- T&C extraction/capture logic in extension code only.
- Popup UX state for extraction + analysis trigger + summary display.
- Token retrieval/injection in extension runtime using the same bearer-token contract.

Backend APIs for SCRUM-9:

- Start by reusing existing endpoints directly.
- Only add new APIs if extension needs additional metadata fields that current schemas cannot carry.

## 8. Suggested first files to inspect for SCRUM-9

1. `frontend/src/lib/api/createDashboardApiClient.ts`
2. `frontend/src/lib/api/client.ts`
3. `frontend/src/lib/auth/contracts.ts`
4. `frontend/src/features/auth/hooks/useAuthSession.ts`
5. `backend/app/api/deps.py`
6. `backend/app/auth/subject_resolver.py`
7. `backend/app/services/analysis_service.py`
8. `backend/app/api/routes/reports.py`
9. `backend/app/api/routes/agreements.py`

## 9. Do not break these assumptions

- Routes stay thin; auth parsing stays in dependency/auth layers.
- Service layer remains auth-provider agnostic.
- Repository interface remains the persistence boundary.
- Ownership checks continue to be enforced through `subject_type + subject_id`.
- Dashboard/extension should share backend contracts, not fork endpoint behavior.
- Extension-specific extraction/parsing logic must stay outside core backend analysis orchestration.

## SCRUM-9 Preflight Note

- Extension should reuse the current auth/session stack contracts, not build a second auth abstraction.
- Extension should call existing analyze/report endpoints directly first.
- New APIs are only justified for extension-specific metadata/capture context not representable today.
- Keep extraction, DOM parsing, and popup orchestration in extension modules; do not push that logic into dashboard components or core backend services.
- Main coupling risks to avoid:
  - duplicating bearer-token injection logic in multiple places
  - adding Supabase-specific checks inside service/repository layers
  - branching backend behavior by client type (web vs extension) when shared contracts are sufficient
