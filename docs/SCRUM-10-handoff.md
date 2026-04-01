# SCRUM-10 Handoff

Updated: March 25, 2026  
Scope: Abuse protection, edge/deployment shaping, Gemini input budgeting, dashboard UX fixes, Docker support, helper scripts, CI/tooling verification, and associated documentation.

This handoff is the implementation-oriented reference for the SCRUM-10 work completed in this repository. When this document conflicts with older notes, current code wins.

## 1. Executive summary

SCRUM-10 was a hardening pass across the full stack rather than a single isolated feature. The completed work covers:

- Input validation and sanitization across backend, frontend, and extension entry points.
- Abuse protection through backend rate limiting and client-side auth attempt throttling.
- Gemini free-tier prompt-budget enforcement and a matching dashboard character-limit UX.
- Cloudflare Worker edge routing in front of the Render backend.
- Dockerized local development support, helper scripts, CI/tooling validation, and expanded documentation.
- Dashboard layout regression fixes for analysis cards and saved report history containment.

The system remains a Cloudflare + Render + Supabase architecture:

- Cloudflare Workers: frontend static asset serving plus `/api/*` edge proxy.
- Render: FastAPI backend origin.
- Supabase: auth and Postgres persistence.

## 2. Architectural outcomes

### 2.1 Security/input boundary

Before SCRUM-10, the application had multiple input paths that were functional but not uniformly hardened. This pass centralized and propagated sanitization rules so they run before data reaches persistence, remote-fetch logic, or provider calls.

Primary backend boundary:

- `backend/app/core/input_validation.py`

Primary frontend boundary:

- `frontend/src/lib/security/inputValidation.ts`

These boundaries are now reused by:

- backend request schemas and submission preparation
- frontend API payload creation
- frontend auth credential normalization
- extension runtime auth client credential handling

### 2.2 Abuse-protection model

Protection is intentionally layered:

- App-level backend limits:
  - always enforceable at the FastAPI layer
  - protect the API even if a caller bypasses the frontend
- Client-side auth throttling:
  - slows repeated login/signup attempts in shipped clients
  - not a replacement for backend or edge controls
- Cloudflare edge:
  - proxies deployed API traffic
  - preserves the forwarding metadata needed for backend limits
  - still the right place to add WAF or bot controls later

### 2.3 Deployment model clarification

One of the most important clarifications from this work is that Cloudflare and Render do not play the same role:

- Cloudflare Worker code runs at the edge.
- Render does not execute the Worker code.
- Render remains the long-running backend origin service.

This means "using edge functions" in this repo really means:

1. browser requests hit the Cloudflare-hosted frontend
2. `/api/*` requests are intercepted by the Worker
3. the Worker proxies to `API_BACKEND_ORIGIN`
4. the Render FastAPI service handles the real business logic

## 3. Detailed implementation areas

### 3.1 Input validation and sanitization

#### Backend

Core normalization and rejection rules live in:

- `backend/app/core/input_validation.py`

This module now handles:

- single-line normalization for titles and emails
- terms-text normalization
- unsafe HTML/script-like block stripping
- control-character rejection/cleanup
- public-hostname URL validation for external fetch inputs
- length and blank-value enforcement
- agreement timestamp validation

These validators are applied in:

- `backend/app/schemas/agreements.py`
- `backend/app/schemas/reports.py`
- `backend/app/services/submission_preparation.py`

Practical impact:

- malformed or hostile input is rejected early
- source URLs cannot target local/private hosts
- oversized terms input is rejected consistently
- backend storage and provider calls receive normalized text instead of raw untrusted strings

#### Frontend

Matching client-side validation lives in:

- `frontend/src/lib/security/inputValidation.ts`

This file now sanitizes:

- report-analysis payloads
- agreement-create payloads
- terms text
- optional single-line inputs
- source URLs
- email/password credentials

The frontend uses those rules in:

- `frontend/src/lib/api/client.ts`
- `frontend/src/lib/auth/supabaseClient.ts`
- `frontend/src/features/dashboard/components/AgreementSubmissionForm.tsx`

#### Extension

The extension now reuses the same auth/input rules through:

- `extension/lib/runtimeAuthClient.ts`

This keeps credential validation consistent between web auth and extension auth instead of maintaining a second set of rules.

### 3.2 Rate limiting and bot resistance

Primary backend rate-limiting implementation:

- `backend/app/security/rate_limit.py`

Wiring:

- `backend/app/api/deps.py`
- `backend/app/main.py`

Configuration:

- `backend/app/core/config.py`
- `backend/.env.example`
- `backend/.env.production.example`

Current default policy families include:

- general API request budget
- agreement creation budget
- analysis request budget
- hourly analysis budget

The design uses policy objects and a sliding-window store so limits can be tuned without changing route code.

Why this matters:

- repeated report listing, submission, or analysis requests can now be throttled
- abuse is limited even when requests do not come from the browser UI
- responses include rate-limit headers that make operator debugging easier

Client-side auth throttling:

- `frontend/src/lib/security/authAttemptThrottle.ts`
- `frontend/src/lib/auth/supabaseClient.ts`
- `frontend/tests/supabaseClient.rateLimit.test.ts`

This protects sign-in/sign-up flows in the shipped frontend, and similar auth normalization exists in the extension runtime adapter. It is additive protection, not a substitute for backend enforcement.

### 3.3 Gemini free-tier prompt budgeting

Backend runtime/config side:

- `backend/app/core/config.py`
- `backend/app/services/ai_provider.py`

Important defaults:

- model target: `gemini-2.5-flash`
- configured free-tier budget: `250000` input tokens
- conservative estimate: `3` characters per token

The implementation estimates prompt size before making a provider request and raises a structured input error when the configured budget would be exceeded. This avoids wasting a network round trip on obviously too-large requests.

Covered by tests in:

- `backend/tests/test_ai_provider_contract.py`
- `backend/tests/test_reports_api.py`
- `backend/tests/test_agreements_api.py`

### 3.4 Dashboard character-limit UX

The backend guard alone was not enough because users could still paste a huge terms document and only discover the failure after submit.

UI changes live in:

- `frontend/src/features/dashboard/components/AgreementSubmissionForm.tsx`
- `frontend/src/styles/global.css`
- `frontend/tests/dashboard.test.tsx`

What the dashboard now does:

- shows a live `typed / max` character counter under the terms textarea
- highlights the counter and textarea when the cap is reached/exceeded
- disables `Analyze and save report` while the input is oversized
- shows a tooltip reason on the disabled action wrapper
- displays inline limit-state messaging explaining the exact overage

Current UI cap:

- `200000` characters

Reasoning:

- it is conservative relative to the backend token estimator and keeps the user-facing limit understandable

### 3.5 Cloudflare Worker edge proxy

Worker implementation:

- `frontend/worker/index.ts`

Worker configuration:

- `frontend/wrangler.jsonc`

Frontend routing behavior:

- `frontend/src/lib/api/createDashboardApiClient.ts`

The Worker currently does three things:

1. intercepts `/api/*`
2. forwards requests to the configured Render backend origin
3. serves SPA assets for non-API traffic through `env.ASSETS.fetch(request)`

Important design boundaries:

- the Worker does not duplicate backend business rules
- backend auth, validation, persistence, and analysis still live in FastAPI
- forwarded IP/host/proto metadata is preserved so backend rate limiting stays meaningful

Important deployment rule:

- if `VITE_API_BASE_URL` points directly to Render in production, you bypass the Worker
- the intended deployed default is the same-origin `/api/v1` path so the Cloudflare edge proxy is used

### 3.6 Dashboard layout regression fixes

This hardening work also surfaced several desktop overflow issues in the dashboard.

Fixed areas:

- analysis summary panel overlap
- flagged clauses panel overlap
- saved reports history rows extending past the panel edge

Relevant files:

- `frontend/src/styles/global.css`
- `frontend/src/features/dashboard/components/AgreementSubmissionForm.tsx`
- `frontend/src/features/dashboard/components/ReportHistoryList.tsx`

Key fixes:

- rebalanced two-column dashboard grid
- increased dashboard container width modestly
- earlier single-column collapse breakpoint
- stronger `min-width: 0` handling on panels, history rows, and truncated content
- explicit flex-shrink control for status chips and long URLs

### 3.7 Docker support and local developer ergonomics

Added:

- `backend/Dockerfile`
- `frontend/Dockerfile`
- `docker-compose.yml`

Design intent:

- mirror the existing local development flow instead of inventing a separate production-like container stack

Current compose/dev behavior:

- backend runs reloadable FastAPI/Uvicorn
- frontend runs the Vite dev server
- frontend dependencies are preserved in a volume-compatible way for local iteration

Supporting scripts added/updated:

- `scripts/dev.ps1`
- `scripts/dev.sh`
- `scripts/bootstrap.ps1`
- `scripts/bootstrap.sh`

These helpers now cover:

- running backend/frontend/preview/docker
- rebuilding backend/frontend/extension/all/docker
- installing extension dependencies during bootstrap

### 3.8 CI and documentation updates

CI:

- `.github/workflows/ci.yml`

Documentation:

- `README.md`
- `docs/render-cloudflare-deploy.md`
- `SCRUM-10-PR.md`
- `docs/SCRUM-10-handoff.md`

Tooling validation now includes:

- docker compose config validation
- helper-script validation
- updated command references for development, testing, and deployment

## 4. Key file map

Use this as the quickest code-navigation index for SCRUM-10:

- Backend validation:
  - `backend/app/core/input_validation.py`
  - `backend/app/schemas/agreements.py`
  - `backend/app/schemas/reports.py`
  - `backend/app/services/submission_preparation.py`
- Backend rate limiting:
  - `backend/app/security/rate_limit.py`
  - `backend/app/api/deps.py`
  - `backend/app/main.py`
  - `backend/tests/test_rate_limiting.py`
- Gemini budgeting:
  - `backend/app/core/config.py`
  - `backend/app/services/ai_provider.py`
  - `backend/tests/test_ai_provider_contract.py`
  - `backend/tests/test_reports_api.py`
  - `backend/tests/test_agreements_api.py`
- Frontend validation and UX:
  - `frontend/src/lib/security/inputValidation.ts`
  - `frontend/src/lib/security/authAttemptThrottle.ts`
  - `frontend/src/lib/api/client.ts`
  - `frontend/src/features/dashboard/components/AgreementSubmissionForm.tsx`
  - `frontend/src/styles/global.css`
  - `frontend/tests/dashboard.test.tsx`
- Extension:
  - `extension/lib/runtimeAuthClient.ts`
- Edge/deployment:
  - `frontend/worker/index.ts`
  - `frontend/wrangler.jsonc`
  - `frontend/src/lib/api/createDashboardApiClient.ts`
  - `docs/render-cloudflare-deploy.md`
- Docker/dev:
  - `backend/Dockerfile`
  - `frontend/Dockerfile`
  - `docker-compose.yml`
  - `scripts/dev.ps1`
  - `scripts/dev.sh`

## 5. Verification history

The following commands were run during the SCRUM-10 implementation sequence:

Backend/API/provider coverage:

```bash
./.venv/Scripts/python.exe -m pytest backend/tests/test_reports_api.py backend/tests/test_agreements_api.py -q
./.venv/Scripts/python.exe -m pytest backend/tests/test_ai_provider_contract.py backend/tests/test_reports_api.py backend/tests/test_agreements_api.py -q
./.venv/Scripts/python.exe -m pytest backend/tests/test_rate_limiting.py -q
```

Frontend and dashboard coverage:

```bash
npm run test:frontend
npm run build:frontend
```

Extension coverage:

```bash
npm --prefix extension test -- --pool=threads runtimeAuthClient.test.ts
npm run typecheck:extension
npm run test:extension
```

Tooling verification:

```bash
docker compose config
npm run verify:docker
./scripts/dev.ps1 help
```

Not fully completed in the sandbox:

- `bash -n scripts/dev.sh`
  - blocked by local Bash access issues in this environment
- `npm run build:extension`
  - hit `spawn EPERM` from esbuild in the sandbox
- `docker compose build backend frontend`
  - blocked by Docker buildx lock-file access in this environment
- Black / ESLint / other formatting or lint checks
  - intentionally not run during implementation because the user explicitly forbade those checks

## 6. Local runbook

### Standard local app run

From the repo root:

```bash
./scripts/dev.sh run backend
./scripts/dev.sh run frontend
```

### Dockerized local run

```bash
./scripts/dev.sh run docker
```

### Useful rebuild flows

```bash
./scripts/dev.sh rebuild backend
./scripts/dev.sh rebuild frontend
./scripts/dev.sh rebuild extension
./scripts/dev.sh rebuild all
./scripts/dev.sh rebuild docker
```

## 7. Deployment and runtime notes

### Render

Render is the backend origin runtime.

Important backend environment families:

- Supabase database/auth configuration
- CORS allow-list
- abuse-protection rate-limit settings
- AI provider settings

Important abuse-protection knobs:

- `API_RATE_LIMIT_REQUESTS_PER_WINDOW`
- `API_RATE_LIMIT_WINDOW_SECONDS`
- `AGREEMENT_CREATE_RATE_LIMIT_REQUESTS`
- `AGREEMENT_CREATE_RATE_LIMIT_WINDOW_SECONDS`
- `ANALYSIS_RATE_LIMIT_REQUESTS`
- `ANALYSIS_RATE_LIMIT_WINDOW_SECONDS`
- `ANALYSIS_HOURLY_RATE_LIMIT_REQUESTS`
- `ANALYSIS_HOURLY_RATE_LIMIT_WINDOW_SECONDS`
- `ANALYSIS_GEMINI_MAX_INPUT_TOKENS`
- `ANALYSIS_GEMINI_ESTIMATED_CHARS_PER_TOKEN`

### Cloudflare Workers

Cloudflare is the edge runtime and frontend host.

Required runtime variable:

- `API_BACKEND_ORIGIN=https://<your-render-service>.onrender.com`

Important reminder:

- do not set a deployed `VITE_API_BASE_URL` to the Render origin unless you intentionally want to bypass the Worker proxy

### Supabase

Supabase remains:

- auth issuer/JWT source
- database backing store

Make sure its redirect allow-list includes:

- local frontend origin(s)
- deployed Cloudflare Worker origin
- any custom domain you place in front of Cloudflare

## 8. Risks, limitations, and follow-up work

Current limitations:

- client-side auth throttling is helpful but not authoritative
- no dedicated WAF/bot-management rules are encoded in repo config yet
- no queued async analysis infrastructure exists yet
- dashboard character limits are conservative and based on the current Gemini free-tier assumptions
- Docker support still needs a full non-sandbox browser smoke test

Recommended follow-ups:

- add Cloudflare WAF / bot / challenge rules once traffic patterns are known
- add visual regression coverage for dashboard layout containment
- consider a provider-side `countTokens` path if tighter Gemini sizing becomes necessary
- add production observability for rate-limit violations and provider rejections
- consider per-authenticated-user auth-attempt protections on the backend if login abuse remains a concern

## 9. Suggested reviewer/operator checklist

Before calling SCRUM-10 fully done in a live environment:

- confirm deployed frontend requests use `/api/v1` on the Cloudflare origin
- confirm `API_BACKEND_ORIGIN` points to the correct Render backend
- confirm backend rate-limit settings are not accidentally zeroed/disabled
- confirm Supabase redirect origins and CORS values match the live frontend host
- confirm the terms-text limit UX is visible and the disabled submit state behaves as expected
- confirm long saved-report URLs truncate cleanly in the dashboard
- run a real local or deployed Docker smoke test outside this sandbox

## 10. Bottom line

SCRUM-10 materially improved the project's operational baseline. The codebase now has:

- stricter trust boundaries
- meaningful rate limiting
- clearer Cloudflare/Render architecture
- explicit Gemini-size protection
- better dashboard resilience
- a documented Docker/dev path

It is still an MVP, but it is a far safer and more operable MVP than the pre-SCRUM-10 state.
