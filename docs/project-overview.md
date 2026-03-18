# Master Project Handoff (Current Repository State)

Updated: March 16, 2026  
Scope: Full repository scan across `frontend`, `backend`, `extension`, `docs`, config/tooling/workflows, planning docs, and prior handoffs.

This is the authoritative onboarding/handoff note for the project as it exists now.
When any prior handoff conflicts with code, treat current code as source of truth.

## Handoff precedence and superseded notes

- Superseded baseline:
  - `docs/dashboard-analysis-handoff.md` is explicitly pre-auth and still references legacy context.
- Current architecture references:
  - `docs/auth-architecture-scrum11.md`
  - `docs/scrum-11-handoff-for-scrum-9.md`
  - `docs/scrum-9-handoff-post-implementation.md`
  - `docs/extraction-analysis-future-work-handoff.md`
- Current code is ahead of some older notes:
  - AI-backed provider path now exists (`backend/app/services/ai_provider.py`), while older notes describe deterministic-only behavior.
  - Extension extraction has had a focused quality pass (`extension/lib/content/extractor.ts`) beyond early scaffold description.
- Documentation drift to watch:
  - `readme.md` still links `docs/dashboard-analysis-handoff.md`; that file is historical context, not current architecture truth.
- Jira XML snapshots (`SCRUM-5.xml`, `SCRUM-9.xml`, `SCRUM-11.xml`) still show `To Do`; those status fields are not reliable implementation status indicators.

---

## 1. Project overview

The project is an AI-assisted Terms and Conditions analyzer with:
- A web dashboard for submitting terms, viewing analysis, and browsing report history.
- A Chrome extension for in-page extraction and quick analysis.
- A FastAPI backend with JWT-authenticated owner-scoped persistence and swappable analysis providers.

Current maturity level:
- Functional vertical slice with shared web + extension backend contracts.
- Authenticated end-to-end flows implemented.
- Extraction/ingestion/analysis seams implemented for future worker/service promotion.
- Still MVP in operational hardening and async infrastructure.

Major capabilities now:
- JWT-authenticated web dashboard login/session and report workflows.
- JWT-authenticated extension runtime auth, extraction, and analysis trigger.
- Backend ingestion boundary supporting direct text and URL fetch/extract paths.
- Deterministic analysis plus AI-backed provider mode (Gemini and OpenAI-compatible).
- Execution-mode seam introduced (sync active, queued not implemented).
- Explicit report lifecycle status model in persistence (`pending`, `running`, `completed`, `failed`), with sync path currently writing `completed`.

---

## 2. Current implementation status

### Fully implemented now

- SCRUM-5 core flow:
  - Submit terms/URL.
  - Generate analysis summary, flagged clauses, trust score.
  - Persist and list reports.
- SCRUM-11 auth model:
  - Supabase JWT bearer auth for protected backend routes.
  - Owner scoping via `subject_type` + `subject_id`.
  - Web login UX with sign-in/sign-up/Google initiation.
- SCRUM-9 extension runtime flow:
  - Popup/background/content script architecture.
  - Background authority for auth/session + backend calls.
  - Content script extraction-only boundary.
  - Shared backend analyze endpoint usage.
  - Popup currently exposes `sign_in_google` and `sign_out` actions only.
- Extraction/analysis architecture phase:
  - Submission preparation boundary.
  - Content ingestion boundary + DTO contracts.
  - Analysis provider seam with deterministic + AI providers.
  - Execution strategy seam (sync mode active).
  - Lifecycle status enum integrated in repositories/storage.

### Partially implemented now

- AI provider path is functionally integrated but operationally fragile under free-tier constraints:
  - Gemini quota/rate limiting (HTTP 429).
  - Read timeouts.
  - Occasional malformed JSON responses requiring parse fallback.
- URL ingestion is implemented but still MVP-level:
  - one sync HTTP fetch attempt, simple extractor, and fallback placeholder text if fetch/extract fails.
- Lifecycle statuses exist in schema/contracts, but synchronous flow mainly produces `completed` reports directly.

### Stubbed / intentionally deferred

- No queued job infrastructure yet.
- No worker process implementation yet.
- Extension token refresh automation is deferred (`extension/lib/runtimeAuthClient.ts` TODO).
- No dedicated extension auth/settings UI beyond current popup flow.
- No robust provider-failure-to-structured-error mapping in routes; some failures still surface as generic 500.

### Still missing (relative to planned future architecture)

- Retry/backoff/circuit-breaker strategy for provider invocation.
- Structured-output robustness loop for malformed AI responses.
- Async status endpoints / accepted-job workflow.
- Tracking/version diff pipeline, scheduled monitoring, and notification system from broader roadmap.
- Observability integrations (Sentry/OpenTelemetry) are planned in docs but not implemented in runtime code.

---

## 3. Repository structure overview

High-level map:
- `backend/`: FastAPI API, auth, services, repository contracts, persistence implementations, tests.
- `frontend/`: React web app (auth + dashboard), shared API/auth contracts, tests.
- `extension/`: MV3 extension runtime (popup/background/content), runtime auth adapter, extraction, tests.
- `docs/`: architecture/handoff/style docs and setup guides.
- `.github/workflows/ci.yml`: CI for frontend/backend/extension lint-test-build checks.
- `scripts/`: local bootstrap and run scripts.

Major responsibility split:
- Backend owns auth verification, ownership enforcement, ingestion, analysis, and persistence.
- Frontend owns authenticated dashboard UX and uses shared transport contracts.
- Extension owns extraction and runtime orchestration, reusing shared auth/API contract shapes.

Tightly related areas:
- Shared API seam between frontend and extension:
  - `frontend/src/lib/api/contracts.ts`
  - `frontend/src/lib/api/client.ts`
  - `extension/lib/apiClient.ts`
  - note: extension imports frontend transport/contracts directly by relative path, which intentionally prevents drift but increases cross-package coupling.
- Shared auth contract seam:
  - `frontend/src/lib/auth/contracts.ts`
  - extension runtime adapter implements this contract.

Intentionally separated areas:
- Extension content extraction is isolated from backend analysis logic.
- Backend orchestration is separated from ingestion details and provider specifics.
- Persistence concerns are behind repository interfaces.

---

## 4. Frontend/web app architecture

Major modules:
- App shell and auth gate:
  - `frontend/src/App.tsx`
  - `frontend/src/features/auth/AuthProvider.tsx`
  - `frontend/src/features/auth/AuthEntryPoint.tsx`
  - `frontend/src/features/auth/hooks/useAuthSession.ts`
- Auth provider adapter:
  - `frontend/src/lib/auth/supabaseClient.ts`
  - `frontend/src/lib/auth/contracts.ts`
  - `frontend/src/lib/auth/providerErrors.ts`
- Dashboard feature:
  - `frontend/src/features/dashboard/DashboardPage.tsx`
  - `frontend/src/features/dashboard/hooks/useDashboardReports.ts`
  - `frontend/src/features/dashboard/components/*`
  - `frontend/src/features/dashboard/mappers.ts`
- API transport seam:
  - `frontend/src/lib/api/client.ts`
  - `frontend/src/lib/api/createDashboardApiClient.ts`
  - `frontend/src/lib/api/contracts.ts`

Auth/session flow:
1. `AuthProvider` boots auth state through `useAuthSession`.
2. `AuthEntryPoint` renders loading, login, or dashboard.
3. Authenticated state injects bearer-token getter into `DashboardApiClient`.
4. Dashboard remains auth-agnostic and consumes only API client methods.
5. API bearer header injection happens only in `DashboardApiClient.request`.

Dashboard/report flow:
1. `DashboardPage` mounts and loads report history.
2. Submit form calls `POST /reports/analyze`.
3. Selected report detail fetched via `GET /reports/{id}`.
4. History list remains backend source-of-truth ordered newest-first.

Important reusable seams:
- `DashboardApiClient` as transport boundary for both web and extension.
- `AuthClient` contract that extension runtime reuses.
- Presentational component separation from API/orchestration logic.

---

## 5. Extension architecture

Entrypoints:
- `extension/background.service-worker.ts`
- `extension/contentScript.ts`
- `extension/popup/index.ts`

Responsibilities by runtime:
- Popup:
  - Thin UI state machine only.
  - Sends intent messages to background.
  - No token ownership, no direct backend calls.
- Background:
  - Single authority for auth/session reads and actions.
  - Coordinates active-tab extraction + backend analyze submission.
  - Maps errors into typed protocol envelopes.
- Content script:
  - Extraction-only.
  - No auth logic, no network calls, no analysis logic.

Core extension boundaries:
- Protocol contract:
  - `extension/lib/contract.ts`
- Orchestration:
  - `extension/lib/background/orchestrator.ts`
- Chrome runtime gateway:
  - `extension/lib/background/chromeRuntimeGateway.ts`
- Background auth session store:
  - `extension/lib/background/authSessionStore.ts`
- Runtime auth adapter:
  - `extension/lib/runtimeAuthClient.ts`
  - `extension/lib/runtimeAuth/*`
- Shared backend transport adapter:
  - `extension/lib/apiClient.ts`
- Extraction strategy:
  - `extension/lib/content/extractor.ts`

Auth/session reuse model:
- Extension implements shared `AuthClient` contract.
- Session persisted in `chrome.storage.local`.
- Background hydrates and caches session as authority for popup/analysis requests.

Message flow:
1. Popup requests auth state or sends action.
2. Background handles auth action through runtime auth adapter.
3. Popup analysis intent triggers background extraction request to content script.
4. Background sends extracted payload to shared backend analyze contract.
5. Popup receives summary/result envelope.

Extension-specific vs shared:
- Extension-specific: chrome runtime plumbing, extraction heuristics, popup UI state.
- Shared: auth contract shape, API payload schema, backend endpoints, bearer token model.

Operational caveat:
- `Could not establish connection. Receiving end does not exist.` is typically a runtime messaging/injection condition (for example restricted tabs like `chrome://*`, or content script context not available yet), not a backend contract mismatch.

---

## 6. Backend architecture

### Routes (thin transport layer)

- Router composition:
  - `backend/app/api/router.py`
- Report routes:
  - `backend/app/api/routes/reports.py`
- Agreement routes:
  - `backend/app/api/routes/agreements.py`
- Dependency wiring:
  - `backend/app/api/deps.py`
- Response mappers:
  - `backend/app/api/mappers/reports.py`

### Services and orchestration boundaries

- Orchestration service:
  - `backend/app/services/analysis_service.py`
  - Workflow coordination, owner-scoped operations, no provider internals.
- Submission/source preparation:
  - `backend/app/services/submission_preparation.py`
  - Normalization + ingestion request shaping.
- Content ingestion boundary:
  - `backend/app/services/content_ingestion.py`
  - URL fetch/extract + submitted text handling behind interfaces.
- Extraction DTO contracts:
  - `backend/app/services/extraction_contracts.py`
- Execution mode seam:
  - `backend/app/services/analysis_execution.py`
  - Strategy abstraction with sync implementation active.
- Analysis provider seam:
  - `backend/app/services/ai_provider.py`
  - Deterministic + AI providers + fallback wrapper.

Provider selection and fallback behavior (current code):
- Config source: `backend/app/core/config.py`.
- Runtime builder: `build_analysis_provider(...)` in `backend/app/services/ai_provider.py`.
- `ANALYSIS_PROVIDER_MODE=deterministic` (default) -> deterministic provider only.
- `ANALYSIS_PROVIDER_MODE=ai` -> provider kind from `ANALYSIS_AI_PROVIDER_KIND` (`gemini` default, `openai_compatible` supported).
- Missing/invalid AI config -> warning + deterministic provider.
- `ANALYSIS_AI_FALLBACK_TO_DETERMINISTIC=true` -> AI provider wrapped by `FallbackAnalysisProvider`; invocation/parsing failures degrade to deterministic result with warning metadata.

### Repositories and persistence boundaries

- Repository interfaces:
  - `backend/app/repositories/interfaces.py`
- Domain models/status:
  - `backend/app/repositories/models.py`
  - `backend/app/repositories/analysis_status.py`
- In-memory implementation:
  - `backend/app/repositories/in_memory.py`
- Postgres implementation:
  - `backend/app/persistence/postgres.py`

### Schemas/contracts

- API schemas:
  - `backend/app/schemas/reports.py`
  - `backend/app/schemas/agreements.py`
- External contracts remain stable for web + extension:
  - `POST /api/v1/reports/analyze`
  - `GET /api/v1/reports`
  - `GET /api/v1/reports/{report_id}`
  - `POST /api/v1/agreements`
  - `POST /api/v1/agreements/{agreement_id}/analyses`

### Execution mode seam (sync-vs-queued)

- Controlled by `ANALYSIS_EXECUTION_MODE`.
- Unknown modes currently log warning and fall back to sync strategy.
- This is internal only; route contracts unchanged.
- Sync mode executes provider invocation inline in request path (`SyncAnalysisExecutionStrategy.execute`), so provider latency/timeouts directly affect HTTP latency.

---

## 7. Auth and identity model

Authority and flow:
- Supabase is auth issuer.
- Backend is token verifier and ownership enforcer.
- Frontend/extension are token presenters via `Authorization: Bearer <token>`.

Backend auth modules:
- `backend/app/auth/supabase_jwt.py`
- `backend/app/auth/subject_resolver.py`
- `backend/app/auth/runtime.py`
- `backend/app/api/deps.py`

Ownership model:
- Canonical authenticated ownership:
  - `subject_type = "supabase_user"`
  - `subject_id = <jwt sub>`
- Ownership enforcement remains in service/repository calls via `subject_type + subject_id`.
- Legacy `X-Session-Id` path is not active runtime behavior.

Web vs extension differences:
- Web auth uses Supabase browser SDK adapter in frontend.
- Extension auth uses runtime adapter with PKCE OAuth + storage-backed session.
- Both converge on same backend JWT bearer contract.

Assumptions that must not break:
- Routes must not parse JWT internals directly.
- Services/repositories remain auth-provider agnostic.
- Owner scoping must continue at persistence boundary.

---

## 8. Extraction and analysis architecture

What exists now:
- Backend-internal extraction/ingestion DTOs (`ExtractionIngestionRequest`, `ExtractionIngestionResult`, metadata).
- Ingestion service handles:
  - Direct submitted text.
  - URL fetch/extract path.
  - Extension text source kind support.
- Submission preparation resolves source identity and normalizes values before orchestration persists.

Current URL-only behavior (important):
- If request has `source_url` and no `terms_text`, ingestion attempts URL fetch/extract.
- If URL fetch/extract fails, ingestion returns fallback placeholder text plus metadata warnings/errors (`url_fetch_fallback_placeholder`) to keep sync request path functional.
- If request has both `source_url` and `terms_text`, ingestion uses submitted text and does not fetch URL (`url_with_submitted_text` strategy).

Deterministic vs provider-backed behavior:
- Deterministic provider:
  - `DeterministicAnalysisProvider` (`deterministic-keyword-v1`).
- AI-backed providers:
  - `GeminiAnalysisProvider` (native `generateContent`).
  - `OpenAICompatibleAnalysisProvider` (chat completions style).
- Fallback:
  - `FallbackAnalysisProvider` can wrap AI provider and degrade to deterministic.

How ingestion/extraction/analysis/persistence interact:
1. Route validates request.
2. Orchestration calls submission preparation.
3. Preparation calls ingestion service.
4. Agreement is persisted.
5. Execution strategy adapts ingestion result to provider input.
6. Provider returns structured analysis result.
7. Report repository persists report with lifecycle status.

Where state lands today:
- API responses still expose status as string (`ReportResponse.status`), mapped from enum via `report.status.value`.
- Current sync flow writes `completed` reports; `pending/running/failed` are present for future async/worker execution.

Upgrade-ready design elements already in place:
- Swappable URL fetcher/extractor protocols in ingestion.
- Explicit provider runtime config + provider builder registry.
- Execution strategy seam for sync now and queued later.
- Repository interfaces preserving persistence boundary.

Potential worker/private-service promotion candidates:
- Content ingestion and extraction internals.
- Provider invocation/gateway.
- Analysis execution strategy as queued worker consumer.

---

## 9. Shared contracts and important seams

API transport seam:
- Shared payload/response contract for web + extension analyze path:
  - `terms_text`, optional `source_url`, optional `title`, optional `agreed_at`.
- No endpoint forking by client type.

Auth seam:
- Shared bearer-token transport.
- Shared auth contract concept (`AuthClient`) across web + extension, with runtime-specific adapters.

Provider seam:
- `AnalysisProvider` protocol and provider input/output DTOs in `ai_provider.py`.
- Provider identity and execution metadata included in provider result.

Extraction/analysis contracts:
- Backend-internal DTOs in `extraction_contracts.py` separate preparation/ingestion from orchestration.

Persistence seam:
- Repository interfaces isolate services/routes from storage implementation.
- In-memory and Postgres implementations satisfy same interfaces.

Execution seam:
- `AnalysisExecutionStrategy` separates orchestration from sync/queued implementation specifics.

Protocol seam (extension runtime):
- `extension/lib/contract.ts` centralizes popup/background/content message contract and guards.

---

## 10. Build, tooling, and developer workflow

Top-level tooling:
- Node workspace currently includes `frontend`.
- Python dependencies in `backend/requirements.txt`.
- Formatting/linting:
  - Python: Black.
  - Frontend: ESLint + Vitest.
  - Extension: TypeScript + esbuild + Vitest.

CI (`.github/workflows/ci.yml`):
- Frontend: lint, build, test.
- Backend: `black --check`, pytest.
- Extension: typecheck, test, build.

Run/build reality check:
- Frontend dev runtime uses Vite (`scripts/run-frontend.ps1`), but `frontend/package.json` `build` script is currently a placeholder message.
- Extension is not part of root npm workspaces; it is built/tested via `--prefix extension` commands and its own `package-lock.json`.

Important config files:
- `backend/.env.example`
- `frontend/.env.example`
- `extension/.env.example`
- `backend/app/core/config.py`
- `extension/scripts/build.mjs`

Extension build assumptions:
- Build outputs under `extension/dist/`.
- Unpacked extension loaded from `extension/` root.
- `manifest.json` points to `dist/*` assets.
- Env precedence and fallback implemented in `extension/scripts/build.mjs`.

Non-obvious/fragile areas:
- `frontend/package.json` currently has a placeholder build command, not a real production bundle pipeline.
- Local extension behavior can fail with runtime messaging errors if content script is unavailable in active tab context.
- AI provider behavior is sensitive to free-tier quotas/timeouts and strict JSON adherence.
- Postgres schema is created from SQL in `backend/app/persistence/postgres.py` at startup when enabled (`POSTGRES_AUTO_CREATE_SCHEMA=true`), not via migration tooling.

---

## 11. Deployment alignment

Alignment with `DEPLOYMENT.md`:
- Auth + DB direction aligns with Supabase-based design.
- Monorepo still in single-service stage but with clean seams for future service split.
- Current backend supports memory and Postgres modes, consistent with incremental deployment path.
- Planned Cloudflare/Render/RabbitMQ/Redis observability stack is architectural direction only; this repo currently runs as local/dev monolith plus extension.

Already aligned:
- JWT-based auth model.
- Postgres-backed persistence option.
- Internal seams for future worker/service extraction.

Still local/dev-oriented:
- No queue broker integration yet (CloudAMQP path not implemented in code).
- No Redis integration yet.
- No Sentry/OpenTelemetry integration in runtime.
- Frontend build/deploy pipeline not production-ready in repository scripts.

Intentionally future-ready:
- Execution strategy seam for worker migration.
- Ingestion and provider abstractions suitable for private service boundaries.
- Repository boundaries decoupled from route/service layers.

---

## 12. Key technical debt and limitations

Real issues to track:
- AI provider reliability:
  - Gemini free-tier rate limits (429).
  - Read timeouts.
  - Occasional non-parseable model JSON responses.
- Error surfacing:
  - Some provider failures can still bubble as HTTP 500 in sync path.
- Ingestion quality:
  - URL extraction is simple tag stripping; quality varies by site structure.
  - Fetch timeout is fixed and short by default in ingestion (`DEFAULT_INGEST_TIMEOUT_SECONDS = 8.0`), so slow legal pages often hit fallback.
- Extension runtime stability:
  - `Could not establish connection. Receiving end does not exist.` can occur in tab/runtime edge cases (restricted schemes, not-yet-injected content scripts, stale extension context).
- Deferred token refresh in extension runtime auth adapter.
- Sync-only execution path may become bottleneck for large inputs and unstable provider latency.
- No migration framework yet; Postgres schema is created directly in code.
- Frontend build script is placeholder, limiting production deployment realism.

Architecture is good but implementation remains thin in:
- Async job lifecycle.
- AI invocation resilience.
- Robust structured-output enforcement.
- Monitoring/observability.

---

## 13. Do not break these assumptions

- Keep web and extension on shared backend contracts; no client-type endpoint branching.
- Keep popup thin; keep content script extraction-only.
- Keep background as extension auth/session + orchestration authority.
- Keep backend routes thin and transport-focused.
- Keep orchestration focused on workflow coordination, not ingestion/provider internals.
- Keep ingestion logic separate from provider and persistence logic.
- Keep provider-specific details isolated inside provider modules.
- Keep repository interfaces as persistence boundaries.
- Keep deterministic provider always available as fallback/safe mode.
- Keep JWT bearer flow and `subject_type + subject_id` ownership enforcement intact.
- Preserve execution-mode seam so queued/worker mode can be added without contract churn.

---

## 14. Recommended next implementation opportunities

1. AI reliability hardening in provider layer.
   - Add retries with backoff, explicit timeout strategy, and bounded failure handling.
   - Improve failure-to-fallback behavior and error mapping so provider instability does not cause avoidable 500s.
2. Structured output robustness.
   - Tighten JSON contract enforcement and parse recovery.
   - Add safer fallback path when AI output is malformed (including provider-returned near-JSON).
3. Queued execution strategy (first async slice).
   - Implement `queued` strategy behind `AnalysisExecutionStrategy`.
   - Persist lifecycle transitions (`pending` -> `running` -> `completed`/`failed`) and keep current route payload shape stable.
4. API error contract stabilization for provider failures.
   - Map upstream/provider failures to predictable client-facing responses.
5. Ingestion quality upgrades behind existing boundary.
   - Improve HTML extraction quality without changing route contracts.
6. Extension runtime resiliency.
   - Add targeted recovery for content-script unavailability and clearer retry UX.
7. Production readiness of web build/deploy.
   - Replace frontend placeholder build command with real Vite build path and deployment-ready outputs.
8. Observability foundation.
   - Add structured logging + initial Sentry/OpenTelemetry hooks at provider/ingestion/execution boundaries.

---

## 15. Files a future developer should inspect first

Prioritized reading list:

1. `backend/app/api/deps.py`  
Why: Central runtime wiring for persistence, provider selection, execution mode, and auth subject resolver.

2. `backend/app/core/config.py`  
Why: Environment-controlled runtime behavior (provider mode, provider kind, fallback, execution mode, auth and CORS).

3. `backend/app/services/analysis_service.py`  
Why: Orchestration center and entrypoint for agreement/report workflows.

4. `backend/app/services/submission_preparation.py`  
Why: Source normalization and ingestion request adaptation boundary.

5. `backend/app/services/content_ingestion.py`  
Why: Actual text acquisition logic and URL/direct text behavior.

6. `backend/app/services/analysis_execution.py`  
Why: Sync-vs-queued seam and provider input adaptation point.

7. `backend/app/services/ai_provider.py`  
Why: Deterministic + AI provider implementations, fallback behavior, output parsing.

8. `backend/app/auth/subject_resolver.py` and `backend/app/auth/supabase_jwt.py`  
Why: Ownership/auth authority and JWT verification model.

9. `frontend/src/features/auth/AuthEntryPoint.tsx` and `frontend/src/features/auth/hooks/useAuthSession.ts`  
Why: Web auth session orchestration and dashboard gate.

10. `frontend/src/lib/api/client.ts`  
Why: Shared transport seam used by web and extension.

11. `extension/lib/background/orchestrator.ts`  
Why: Extension runtime decision flow and boundary discipline.

12. `extension/lib/content/extractor.ts`  
Why: Extraction-only strategy and likely evolution hotspot.

13. `extension/lib/runtimeAuthClient.ts`  
Why: Runtime auth behavior, PKCE flow integration, and deferred token refresh seam.

14. `extension/manifest.json` and `extension/scripts/build.mjs`  
Why: Runtime permission/host assumptions and build-time config injection order.

15. `backend/tests/test_reports_api.py`, `backend/tests/test_ai_provider_contract.py`, `extension/tests/background.service-worker.test.ts`, `extension/tests/contentScript.test.ts`, `DEPLOYMENT.md`, and `CSCI3300ProjectPlanning.txt`  
Why: Architectural direction and staged evolution constraints that future changes should respect.

---

## Executive summary

Current codebase status is a working authenticated monolith with strong internal seams: routes are thin, orchestration is separated from ingestion and provider internals, provider selection is runtime-configured, and persistence remains behind repository interfaces. The main near-term risk is operational reliability of AI mode (429/timeouts/malformed JSON) under sync request-path execution; architecture is ahead of operational hardening.

## Recommended first actions for the next engineer

1. Implement provider reliability hardening and malformed-output fallback so AI mode fails gracefully.
2. Add first queued execution strategy behind `AnalysisExecutionStrategy`, keeping current endpoints stable.
3. Improve URL ingestion quality behind `ContentIngestionService` protocols without touching orchestration/routes.
4. Replace frontend placeholder build script with a real production build path to align with deployment goals.
