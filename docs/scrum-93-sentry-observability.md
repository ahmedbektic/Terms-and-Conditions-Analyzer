# SCRUM-93 Sentry Observability

This document is the operator-facing finish for SCRUM-93.

It covers:

- what is instrumented now
- what is explicitly out of scope
- how to configure frontend and backend Sentry
- how to trigger one frontend test event and one backend test event
- how Cloudflare Worker observability relates to Sentry
- a recommended deeper regression suite to add later

## Current Scope

Instrumented now:

- React dashboard frontend
- FastAPI backend
- browser to Cloudflare Worker to FastAPI trace propagation for `/api/*`

Intentionally out of scope:

- browser extension instrumentation
- OpenTelemetry
- Cloudflare OTLP export into Sentry
- future background worker or queue consumer instrumentation
- Cloudflare Worker application-level error export into Sentry

## Service Tagging

Frontend Sentry events use:

- `service=frontend-dashboard`
- `service_surface=react-dashboard`
- `deployment_environment=<VITE_SENTRY_ENVIRONMENT or Vite mode>`
- `release=<VITE_SENTRY_RELEASE when set>`

Backend Sentry events use:

- `service=backend-api`
- `service_surface=fastapi-api`
- `deployment_environment=<SENTRY_ENVIRONMENT or APP_ENV>`
- `release=<SENTRY_RELEASE when set>`

## Scrubbing Rules

Frontend and backend both avoid default PII capture and scrub common sensitive fields before send.

Filtered key patterns include:

- auth or session material such as `authorization`, `cookie`, `token`, `secret`, `password`, `apikey`, `jwt`
- raw policy or agreement text such as `terms_text`, `submitted_text`, `captured_text`, `normalized_text`, `normalized_text_body`, `raw_text_body`, `policy_text`, `raw_input_excerpt`

Additional behavior:

- backend request bodies are disabled with `max_request_body_size="never"`
- `/health` transactions are dropped as noise on the backend
- frontend breadcrumbs and event payloads are scrubbed before send

Residual limitation:

- scrubbing is key-based, so newly introduced sensitive field names must be added to the scrub lists

## Configuration

### Backend env

Use `backend/.env.example` and `backend/.env.production.example`.

Required for real backend Sentry delivery:

- `SENTRY_DSN`

Recommended:

- `SENTRY_ENVIRONMENT`
- `SENTRY_RELEASE`
- `SENTRY_TRACES_SAMPLE_RATE`

Optional verification hook:

- `OBSERVABILITY_ENABLE_TEST_ROUTES=false`

### Frontend env

Use `frontend/.env.example` and `frontend/.env.production.example`.

Required for real browser Sentry delivery:

- `VITE_SENTRY_DSN`

Recommended:

- `VITE_SENTRY_ENVIRONMENT`
- `VITE_SENTRY_RELEASE`
- `VITE_SENTRY_TRACES_SAMPLE_RATE`

For source-map upload during build:

- `SENTRY_AUTH_TOKEN`
- `SENTRY_ORG`
- `SENTRY_PROJECT`
- `VITE_SENTRY_RELEASE`

## Manual Verification Hooks

### Frontend test event

Prerequisites:

- dashboard loaded in a browser
- `VITE_SENTRY_DSN` configured

Trigger:

1. Open browser DevTools on the dashboard page.
2. Run:

```js
setTimeout(() => {
  throw new Error('SCRUM-93 frontend test event');
}, 0);
```

Expected result:

- one browser error event appears in Sentry
- tags include `service=frontend-dashboard`
- release and environment match frontend config
- stack trace resolves cleanly when source maps were uploaded for that release

### Backend test event

Prerequisites:

- backend running with `SENTRY_DSN` configured
- `OBSERVABILITY_ENABLE_TEST_ROUTES=true`

Trigger:

```bash
curl -X POST http://127.0.0.1:8000/api/v1/observability/sentry-test
```

Expected result:

- the request returns a server error because the route raises intentionally
- one backend error event appears in Sentry
- tags include `service=backend-api`
- `/health` traffic does not appear as backend transaction noise

Safety note:

- keep `OBSERVABILITY_ENABLE_TEST_ROUTES=false` in normal shared or production environments

## Trace Propagation Path

Current intended trace path:

- dashboard browser request
- Cloudflare Worker proxy at `/api/*`
- FastAPI backend

What preserves the trace headers:

- frontend Sentry browser tracing sends `sentry-trace` and `baggage` for `/api/*`
- the Worker proxy forwards incoming headers to the backend
- the worker test suite verifies that `sentry-trace` and `baggage` survive the proxy

## Cloudflare Worker vs Sentry

Cloudflare Worker observability is for:

- edge runtime visibility
- request routing and proxy troubleshooting
- Cloudflare-native operational debugging

Sentry observability is for:

- dashboard runtime errors
- backend exceptions and application failures
- browser-to-API correlation using Sentry trace headers

Decision:

- Cloudflare OTLP export into Sentry is deferred and not part of SCRUM-93

## Recommended Regression Suite

The tests below are not all implemented here. They are the high-value suite to add next if you want SCRUM-93 regressions to become difficult.

Backend unit tests:

- verify no-DSN startup is inert
- verify invalid trace sample rate clamps safely
- verify `/health` transactions are dropped
- verify `authorization`, `cookie`, `token`, and policy-text keys are scrubbed recursively
- verify non-sensitive fields such as `source_value` remain intact
- verify release and environment tags are attached to every backend event shape

Backend API tests:

- verification route returns `404` when disabled
- verification route raises when enabled
- a normal report analysis request does not expose `terms_text` in captured event payloads
- tracked-policy capture paths do not expose `captured_text` or normalized policy text

Frontend unit tests:

- Sentry init is inert when `VITE_SENTRY_DSN` is absent
- trace propagation targets include same-origin `/api/*` and local dev backend URLs
- `beforeSend` scrubs `terms_text`, `captured_text`, tokens, cookies, and bearer strings
- common tags are attached to browser error and transaction events

Worker tests:

- `sentry-trace` is forwarded unchanged
- `baggage` is forwarded unchanged
- auth headers are still forwarded
- proxy path rewriting does not strip query strings or trace headers

Build tests:

- production build emits hidden source maps
- Sentry upload plugin stays disabled when build credentials are absent
- Sentry upload plugin activates when `SENTRY_AUTH_TOKEN`, `SENTRY_ORG`, `SENTRY_PROJECT`, and `VITE_SENTRY_RELEASE` are present

Manual smoke tests:

- frontend test event lands in Sentry
- backend verification route lands in Sentry
- one real dashboard API action shows browser and backend entries with matching release/environment expectations

## Developer Checklist

Before calling SCRUM-93 done in a new environment:

- configure backend `SENTRY_*` env vars
- configure frontend `VITE_SENTRY_*` env vars
- configure frontend build-time `SENTRY_*` upload vars if you want readable production stacks
- set matching frontend/backend release values for the deployment
- run one frontend smoke event
- run one backend smoke event
- confirm the worker proxy still preserves `sentry-trace` and `baggage`
