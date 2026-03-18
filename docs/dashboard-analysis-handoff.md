# Developer Handoff

> Note: this document captures the baseline before auth integration.
> For current auth/session ownership architecture, see `docs/auth-architecture-scrum11.md`.

## 1. Current feature status

is implemented end-to-end for a single anonymous user session:

- User can submit terms text and/or source URL from the dashboard.
- Backend generates deterministic AI-style analysis (`summary`, `flagged_clauses`, `trust_score`).
- Report is persisted and shown in saved history.
- User can reopen a previously saved report from history.
- Persistence works in `memory` mode by default and `postgres` mode when configured.

## 2. Frontend architecture

Primary files/layers:

- Feature container: `frontend/src/features/dashboard/DashboardPage.tsx`
- State orchestration: `frontend/src/features/dashboard/hooks/useDashboardReports.ts`
- Presentational components:
  - `components/AgreementSubmissionForm.tsx`
  - `components/AnalysisSummaryCard.tsx`
  - `components/FlaggedClausesList.tsx`
  - `components/ReportHistoryList.tsx`
- Transport boundary: `frontend/src/lib/api/client.ts`
- API contracts: `frontend/src/lib/api/contracts.ts`
- API-to-UI mapping: `frontend/src/features/dashboard/mappers.ts`
- Session owner key (historical auth seam): `frontend/src/lib/session/sessionId.ts` (removed in JWT-only cleanup)

Frontend flow:

1. `DashboardPage` builds `DashboardApiClient` and calls `useDashboardReports`.
2. Hook loads history on mount (`listReports`).
3. Submit calls `submitAndAnalyze`, then refreshes history from backend source-of-truth.
4. Selecting history item calls `getReport` and updates detail panel.

## 3. Backend architecture

Primary files/layers:

- App/bootstrap: `backend/app/main.py`
- Router composition: `backend/app/api/router.py`
- Route handlers (thin): `backend/app/api/routes/reports.py`, `backend/app/api/routes/agreements.py`
- Dependency wiring + subject resolution: `backend/app/api/deps.py`
- Service/business orchestration: `backend/app/services/analysis_service.py`
- Analyzer interface + implementation: `backend/app/services/ai_provider.py`
- Schema contracts: `backend/app/schemas/agreements.py`, `backend/app/schemas/reports.py`
- Repository boundary: `backend/app/repositories/interfaces.py`
- Repository models: `backend/app/repositories/models.py`

Backend flow:

1. Route validates request schema and resolves request subject.
2. Route delegates to `AnalysisOrchestrationService`.
3. Service normalizes input, persists agreement, calls analysis provider, persists report.
4. Route maps stored models to response contracts.

## 4. Persistence/data model

Backend mode is selected by `PERSISTENCE_BACKEND` in `backend/.env`:

- `memory`: `backend/app/repositories/in_memory.py`
- `postgres`: `backend/app/persistence/postgres.py`

Postgres tables:

- `agreements`
  - `id`, `subject_type`, `subject_id`, `title`, `source_url`, `agreed_at`, `terms_text`, `created_at`
- `reports`
  - `id`, `agreement_id`, `subject_type`, `subject_id`, `source_type`, `source_value`, `raw_input_excerpt`, `status`, `summary`, `trust_score`, `model_name`, `flagged_clauses` (JSONB), `created_at`, `completed_at`

Ownership is currently session-scoped through `subject_type` + `subject_id`.

## 5. API contract summary

Current dashboard-used endpoints:

- `POST /api/v1/reports/analyze`
  - Input: `title?`, `source_url?`, `agreed_at?`, `terms_text?` (at least one of URL/text required)
  - Output: full `ReportResponse`
- `GET /api/v1/reports`
  - Output: list of `ReportListItemResponse` (newest first)
- `GET /api/v1/reports/{report_id}`
  - Output: full `ReportResponse`

Additional staged flow endpoints:

- `POST /api/v1/agreements`
- `POST /api/v1/agreements/{agreement_id}/analyses` with `{"trigger":"manual"}`

## 6. Known limitations / temporary decisions

- Analyzer is deterministic keyword-based (`deterministic-keyword-v1`), not an LLM.
- Auth is not implemented; owner identity comes from `X-Session-Id`.
- Session ID is stored in browser localStorage and used as ownership boundary.
- Schema is auto-created in Postgres mode when enabled; no migration framework yet.
- Some route-level response mapping is duplicated and can be centralized later.

## 7. Recommended next story integration points

(Auth) first:

- Replace `get_request_subject` in `backend/app/api/deps.py` to derive subject from auth token/JWT.
- Keep service/repository signatures (`subject_type`, `subject_id`) stable to minimize churn.
- Provide token getter in frontend and pass via `DashboardApiClientConfig.getAccessToken`.
- Decide ownership migration strategy for existing session-owned rows (optional backfill or keep anonymous history separate).

SCRUM-9 (Extension) after auth:

- Reuse existing endpoints from extension:
  - quick flow: `POST /reports/analyze`
  - staged flow: `POST /agreements` -> `POST /agreements/{id}/analyses`
- Add optional metadata fields (capture context, page URL/source) at schema layer first, then map in service.
- Keep extension-specific parsing outside core service to avoid coupling dashboard and extension ingestion logic.

## 8. Suggested first files to inspect for

1. `backend/app/api/deps.py`
2. `backend/app/services/analysis_service.py`
3. `backend/app/repositories/interfaces.py`
4. `backend/app/persistence/postgres.py`
5. `frontend/src/lib/api/client.ts`
6. `frontend/src/lib/session/sessionId.ts` (historical; removed in )
7. `frontend/src/features/dashboard/hooks/useDashboardReports.ts`

## Do not break these assumptions

- Routes stay thin; business logic belongs in `AnalysisOrchestrationService`.
- Repository abstraction remains the persistence boundary; route/service code must not depend on Postgres directly.
- API contracts in `frontend/src/lib/api/contracts.ts` remain the only frontend transport source.
- Components remain presentational; network/state orchestration stays in dashboard hook and API client.
- `subject_type` + `subject_id` ownership fields remain intact until auth migration is complete.
- `reports` listing stays newest-first; dashboard UX and tests depend on this ordering.
