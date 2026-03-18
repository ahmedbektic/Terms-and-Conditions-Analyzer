# Dashboard Analysis Flow Handoff

## End-to-end flow

1. `DashboardPage` creates `DashboardApiClient` and invokes `useDashboardReports`.
2. `useDashboardReports` handles submit/list/select actions and UI state transitions.
3. `DashboardApiClient` sends typed requests to FastAPI routes under `/api/v1`.
4. Route handlers (`api/routes/reports.py`, `api/routes/agreements.py`) validate transport concerns and delegate to `AnalysisOrchestrationService`.
5. `AnalysisOrchestrationService` normalizes input, coordinates agreement persistence, calls the analysis provider, and persists report outputs.
6. Repository implementations persist/read data either in-memory (`repositories/in_memory.py`) or Postgres (`persistence/postgres.py`) based on config.

## Where to change what

- Frontend state orchestration:
  - `frontend/src/features/dashboard/hooks/useDashboardReports.ts`
- Frontend API boundary and contracts:
  - `frontend/src/lib/api/client.ts`
  - `frontend/src/lib/api/contracts.ts`
- Backend business logic:
  - `backend/app/services/analysis_service.py`
- Backend analyzer implementation seam:
  - `backend/app/services/ai_provider.py`
- Backend persistence seam:
  - Interfaces: `backend/app/repositories/interfaces.py`
  - In-memory: `backend/app/repositories/in_memory.py`
  - Postgres: `backend/app/persistence/postgres.py`

## Auth extension point (future login)

- Current owner scoping uses `X-Session-Id` and `RequestSubject`.
- Replace `get_request_subject` in `backend/app/api/deps.py` with token/JWT subject extraction.
- Keep service/repository signatures (`subject_type`, `subject_id`) unchanged for minimal churn.
- Frontend can provide bearer tokens through `DashboardApiClientConfig.getAccessToken` without rewriting components.

## Browser-extension extension point

- Extension ingestion can call existing backend endpoints directly:
  - one-shot: `POST /reports/analyze`
  - staged/manual: `POST /agreements` then `POST /agreements/{id}/analyses`
- If extension needs extra metadata (origin tab, capture timestamp), add optional fields to agreement/report schemas and keep mapper updates isolated in `frontend/src/features/dashboard/mappers.ts`.
