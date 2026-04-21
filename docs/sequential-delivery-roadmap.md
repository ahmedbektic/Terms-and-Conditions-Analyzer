# Sequential Delivery Roadmap

## Purpose

This document explains the implementation sequence for the current backlog plan and, more importantly, the exact conditions each story should leave behind so the next story can begin smoothly instead of reopening architecture questions.

The sequence assumed here is:

1. `SCRUM-93` - Sentry observability
2. `SCRUM-104` - Async-ready monolith
3. `SCRUM-115` - Background tracked policy re-check
4. `SCRUM-38` - AI analysis orchestration
5. `SCRUM-126` - Policy change notifications and email
6. `SCRUM-76` - Redis transient state and caching
7. `SCRUM-137` - RabbitMQ adoption
8. `SCRUM-148` - OpenTelemetry tracing
9. `SCRUM-159` - Notification delivery microservice extraction

This order is not arbitrary. It is designed to prevent the team from adding infrastructure before the application has:

- stable execution boundaries
- runtime visibility
- durable state models
- one proven async workflow
- one proven notification path
- a concrete reason to introduce heavier infrastructure

## Current Architectural Baseline

At the time this plan was written, the repo is effectively a modular monolith:

- Cloudflare Worker in front of `/api/*`
- one Render-hosted FastAPI API
- synchronous execution for analysis and policy check flows
- tracked policy storage, snapshotting, change detection, and diff support already present at the monolith layer
- no first-class Sentry instrumentation yet
- no OpenTelemetry wiring yet
- no RabbitMQ-backed execution path yet
- Redis planned but not yet positioned as a supporting optimization layer

That baseline matters because the plan intentionally grows complexity only after each lower layer is real and observable.

## Delivery Philosophy

The key rule for this roadmap is: every story must leave behind a reusable seam, not just a feature.

In practice that means each story should finish with:

- one exact workflow clearly implemented
- stable interfaces and ownership boundaries
- durable state where needed
- observability for that workflow
- explicit out-of-scope decisions
- a clean handoff to the next story

If a story ends with "we kind of support several paths" or "the next story can decide which variant to use," that story is not actually done from a sequencing perspective.

## Story 1: SCRUM-93 - Sentry Observability

### Why this is first

Before the team adds background execution, broker transport, or service extraction, it needs evidence when things fail. Without that, every later story turns into blind debugging across more moving parts.

This story is not a generic observability initiative. It should be scoped to the currently deployed surfaces:

- React dashboard frontend
- FastAPI backend
- the browser-to-API path through the Cloudflare Worker proxy

The story should not expand into:

- browser extension instrumentation
- future worker-process instrumentation
- Cloudflare OTLP export into Sentry
- OpenTelemetry

### What this story should concretely deliver

- Sentry frontend SDK initialized in the dashboard entrypoint
- Sentry backend SDK initialized in the FastAPI bootstrap path
- environment and release tagging
- trace propagation across dashboard requests to `/api/*`
- source maps for frontend production errors
- scrubbing rules for secrets, auth headers, and raw policy content
- a documented way to fire one frontend and one backend test event
- a documented division between Cloudflare native observability and Sentry

### What "done enough to start the next story" looks like

The important exit state is not just "Sentry sends events." The important exit state is:

- the team can reliably see backend exceptions with route and environment context
- the team can reliably see frontend runtime failures with readable source maps
- the browser-to-API path supports request tracing headers
- Sentry can be turned off safely in local or unset-DSN environments
- the current deployment config has a documented place for Sentry-related env vars

### Why this enables SCRUM-104

`SCRUM-104` introduces execution-status models and later queue seams. Those changes affect routing, persistence, error handling, and status transitions. Without baseline Sentry visibility, the team will not know whether failures are:

- route-level bugs
- persistence bugs
- state transition bugs
- timeout handling bugs

### Smooth handoff checklist from SCRUM-93 to SCRUM-104

- Backend startup supports optional Sentry initialization without crashing when DSN is absent.
- Frontend startup supports optional Sentry initialization without breaking local development.
- Trace headers survive the current dashboard -> Worker -> API path.
- Release and environment tags are stable and documented.
- Sensitive data filtering rules are already in place so later async stories do not accidentally widen telemetry exposure.
- Health endpoints and other noisy paths are already filtered so later status polling does not flood telemetry.

## Story 2: SCRUM-104 - Async-Ready Monolith

### Why this comes before any background runner

The first workflow selected for asynchronous preparation is fixed:

- manual tracked policy re-check
- triggered by `POST /api/v1/tracked-policies/{id}/check`

This story should not background anything yet. It should prepare the monolith to support queued execution later without rewriting the tracked policy logic a second time.

This is where the team creates the seam between:

- request handling
- execution status tracking
- core re-check business logic
- future execution transport

### What this story should concretely deliver

- durable execution or job status model for tracked policy re-checks
- valid lifecycle states such as pending, running, succeeded, failed, timed out
- structured failure metadata
- status query API contract
- idempotency or deduplication rules for repeated manual re-check requests
- clear service boundary so the same re-check executor can run sync now and async later

### What must explicitly remain out of scope

- report analysis redesign
- agreement submission redesign
- scheduled scans
- RabbitMQ
- email notifications

### What "done enough to start the next story" looks like

The team should be able to say:

- "A tracked policy re-check has a durable execution record."
- "The API no longer relies on the HTTP request as the only source of status truth."
- "The core tracked policy re-check logic is callable through a reusable execution seam."
- "If we background this tomorrow, we do not need to rediscover what the input, output, or terminal states are."

### Why this enables SCRUM-115

`SCRUM-115` is the first true background workflow. It should be implementation work, not architecture discovery. The previous story should already answer:

- what gets executed
- what execution status looks like
- how duplicate submissions are handled
- what failure metadata looks like
- how the client checks status

### Smooth handoff checklist from SCRUM-104 to SCRUM-115

- There is one exact executor for manual tracked policy re-checks.
- Status records include enough fields for enqueue, start, finish, failure, and result correlation.
- The API contract for status retrieval is stable enough for dashboard polling.
- Duplicate manual re-check behavior is defined, not left to "best effort."
- Timeouts and retry boundaries are documented for the tracked policy re-check path.
- The story documentation explicitly says report analysis is not part of the first async seam.

## Story 3: SCRUM-115 - Background Tracked Policy Re-Check

### Why this is the first async pilot

The team needs one real background workflow before it talks seriously about brokers, tracing across runtimes, or service splits.

The chosen workflow is fixed and should not drift:

- the dashboard triggers `POST /api/v1/tracked-policies/{id}/check`
- the request returns quickly with execution metadata
- the monolith completes the re-check in the background

For this first pass, the transport is intentionally lightweight:

- in-process background runner
- same deployment
- no RabbitMQ yet

### What this story should concretely deliver

The workflow step order should be explicit and preserved:

1. fetch current policy text
2. normalize text
3. persist a snapshot only if meaningfully changed
4. run change detection
5. update tracked policy status fields
6. persist resulting change event seed for later notification and AI use

The story should also deliver:

- background execution status progression
- safe handling of duplicate or overlapping manual checks
- dashboard-visible completion state
- reliable local demo path

### What should not be added here

- scheduled recurring scans
- RabbitMQ
- email delivery
- broad AI pipeline changes

### What "done enough to start the next story" looks like

The team should have a real end-to-end async path that proves:

- execution records work
- background processing works
- tracked policy state updates correctly after background completion
- change events are persisted in a machine-usable way

That last point matters because both `SCRUM-38` and `SCRUM-126` depend on it.

### Why this enables SCRUM-38

`SCRUM-38` should not guess what changed. It should consume the result of an already completed policy re-check flow:

- previous snapshot reference
- new snapshot reference
- normalized content
- change event seed
- latest tracked policy metadata

This means the AI story can focus on interpretation, not scraping or transport.

### Smooth handoff checklist from SCRUM-115 to SCRUM-38

- Completed re-check executions persist references to the old and new snapshots when applicable.
- Change detection leaves behind a machine-usable change event seed rather than only a boolean flag.
- Background completion reliably updates tracked policy metadata.
- Failures are durable and inspectable rather than hidden in logs only.
- Manual re-check execution is stable enough that AI analysis can be layered on top instead of compensating for transport instability.

## Story 4: SCRUM-38 - AI Analysis Orchestration

### Why it belongs here

This story becomes much more valuable after background re-checks already produce durable change artifacts. At that point the AI layer can explain:

- what changed
- why it matters
- which clauses are risky
- how confident the system is

Without that base workflow, the AI story risks becoming a broad rewrite of every analysis path at once.

### The correct first application of this story

The first operational focus should be:

- change-aware analysis for tracked policy changes

That means the orchestration pipeline should primarily use:

- old snapshot
- new snapshot
- diff context
- clause extraction
- structured stage outputs
- final human-readable explanation

The existing acceptance criteria support this direction through:

- multi-step orchestration
- JSON schema validation
- diff-context retrieval
- fallback behavior
- consistency checks

### What this story should concretely deliver

- multi-stage analysis pipeline instead of one prompt / one response
- structured stage outputs with validation
- change-aware reasoning using diff context
- final explanation artifact that can be consumed by both dashboard views and notifications
- fallback to a simpler deterministic or reduced explanation if advanced stages fail
- tests for invalid AI payloads and partial pipeline failures

### What "done enough to start the next story" looks like

The team should have a stable machine-readable and human-readable output for a changed tracked policy, such as:

- key changed clauses
- why the changes matter
- confidence caveats
- explanation fallback when AI cannot complete all stages

### Why this enables SCRUM-126

Once notifications start, the product should ideally send more than "a policy changed." It should send:

- a concise impact summary
- the most important changed clauses
- a fallback message if rich AI analysis is unavailable

That means the notification story can stay small if the AI story already exposes a stable explanation artifact.

### Smooth handoff checklist from SCRUM-38 to SCRUM-126

- The AI pipeline can consume diff-aware inputs from tracked policy changes.
- There is one stable summary artifact suitable for user-facing notification content.
- The pipeline exposes clear fallback behavior when advanced analysis fails.
- Structured outputs are validated before downstream consumers use them.
- Notification consumers do not need to understand the internal AI stage graph; they only need the final summary artifact plus confidence/fallback metadata.

## Story 5: SCRUM-126 - Policy Change Notifications and Email

### Why it comes after AI orchestration

Email is much more useful if it can include:

- what changed
- why it matters
- a safe fallback if analysis is unavailable

Notifications should be a consumer of the background and AI pipeline outputs, not a forcing function that makes those systems less clean.

### What this story should concretely deliver

One exact notification path only:

- send a policy-change email
- to the owner of the tracked policy
- after successful background re-check
- when a meaningful change event exists

This story should also include:

- notification records and lifecycle states
- suppression rules
- duplicate prevention
- one user preference flag for this notification category
- retry-safe provider abstraction

### What should stay out of scope

- in-app notifications
- SMS
- batch digest systems
- multi-channel preference center
- generalized communication platform work

### What "done enough to start the next story" looks like

The team should have:

- a stable notification record model
- a proven email delivery path
- clear suppression and dedupe rules
- one concrete hot path that can later benefit from Redis

### Why this enables SCRUM-76

Once notifications and background status paths are real, the team can see where transient state is actually needed:

- dedupe locks
- recent execution status lookups
- cached explanation payloads
- short-lived notification coordination state

That makes Redis an optimization layer for known hot paths instead of speculative infrastructure.

### Smooth handoff checklist from SCRUM-126 to SCRUM-76

- Notification creation and delivery have durable source-of-truth records in Postgres or existing persistence.
- Email retries and failure states are explicit.
- Duplicate suppression logic exists at the durable domain level before Redis is added as a performance helper.
- The team can identify one or two real transient-state pain points from the implemented flow.
- Notification and background flows continue to function correctly even without Redis.

## Story 6: SCRUM-76 - Redis Transient State and Caching

### Why Redis belongs here

Redis should support proven workflows, not define them.

By this point, the system already has:

- a background re-check flow
- a notification path
- durable source-of-truth persistence
- enough operational knowledge to identify high-value transient-state opportunities

### Best first Redis use in this sequence

The best first Redis use should be tied to the tracked policy workflow, for example:

- short-lived lock or dedupe state for active tracked policy re-checks
- recent execution-status caching for dashboard polling
- short-lived notification send coordination state

The story text also mentions:

- health checks
- cache abstraction
- fallback behavior
- first wired cache path

Those should all be implemented in a way that preserves the rule:

- Postgres remains source of truth
- Redis remains optional support

### What this story should concretely deliver

- one shared Redis client module
- cache abstraction layer
- namespaces and TTL rules
- one exact first wired path
- health-check or connectivity visibility
- graceful no-Redis fallback
- tests proving fallback assumptions

### What "done enough to start the next story" looks like

The team should be able to say:

- "Redis improves one real path."
- "The app still works without Redis."
- "Redis state is clearly transient."
- "We now have enough supporting coordination state to evaluate whether a broker is worth it."

### Why this enables SCRUM-137

When RabbitMQ adoption is evaluated, the team should already understand:

- how transient coordination works
- how optional infrastructure is handled
- how fallback behavior is implemented

Redis also provides patterns the team can reuse around:

- health checks
- env wiring
- graceful degradation
- operational visibility

### Smooth handoff checklist from SCRUM-76 to SCRUM-137

- One first Redis path is actually wired to the tracked policy workflow or notification workflow.
- Redis fallback behavior is tested and documented.
- Health or startup connectivity signals exist.
- The domain model still works correctly without Redis.
- The team has clear evidence about where current async pain remains even after adding a transient-state layer.

## Story 7: SCRUM-137 - RabbitMQ Adoption

### Why broker adoption is delayed this long

RabbitMQ is justified only when the team can point to a specific pain in a proven workflow. The chosen first broker-backed workflow is fixed:

- tracked policy re-check enqueue and execution

Notification sending remains downstream. That is important because it prevents this story from trying to solve every async use case at once.

### What this story should concretely deliver

- documented adoption decision
- if yes, publisher path from `POST /api/v1/tracked-policies/{id}/check`
- tracked policy re-check message contract
- queue or routing-key naming
- consumer for tracked policy re-check messages
- retries, dead-letter handling, poison-message policy
- idempotency protections
- broker health visibility

### What "done enough to start the next story" looks like

The team should end this story with one stable producer-consumer boundary that can be traced and reasoned about:

- request publishes message
- message contract is durable and versioned
- consumer executes tracked policy re-check
- retries and failures are explicit

### Why this enables SCRUM-148

OpenTelemetry becomes much more valuable once the flow crosses:

- frontend
- Cloudflare Worker
- API
- broker publish
- broker consume
- background execution
- notification creation
- email provider call

Before that, Sentry and local logs carry most of the value.

### Smooth handoff checklist from SCRUM-137 to SCRUM-148

- Producer and consumer boundaries are stable and named.
- Message contracts are documented and versioned.
- Publish and consume code paths have explicit success and failure branches.
- Broker env vars and deployment assumptions are finalized enough for tracing setup.
- Correlation IDs or equivalent execution identifiers exist or can be added consistently.

## Story 8: SCRUM-148 - OpenTelemetry Tracing

### Why tracing is here instead of earlier

The representative traced workflow is fixed and should stay fixed:

- dashboard manual tracked policy re-check
- Cloudflare Worker proxy
- FastAPI API
- approved background execution transport
- snapshot persistence
- change detection
- notification record creation
- optional email send

If RabbitMQ is adopted, the trace includes publish and consume. If not, it traces the approved in-process background seam instead.

### What this story should concretely deliver

- service naming and resource attributes
- trace propagation across the exact workflow
- spans for policy fetch, persistence, change detection, notification creation, and email send
- edge trace participation through the Worker
- OTLP exporter wiring
- clear boundary between Sentry responsibilities and OTel responsibilities

### What "done enough to start the next story" looks like

The team should be able to open one trace and answer:

- where latency is occurring
- where failures occur
- which component owns the failing segment
- whether the service boundary for notification delivery is strong enough to extract

### Why this enables SCRUM-159

Once the team can trace the end-to-end path, it has evidence for service extraction instead of opinions. Since the first microservice target is fixed to notification delivery, the traces should help confirm:

- notification work is operationally distinct
- notification failures are separable from the public API
- notification delivery has a clean enough contract to move out

### Smooth handoff checklist from SCRUM-148 to SCRUM-159

- The tracked policy re-check plus notification path is fully traceable.
- Notification creation and email send segments are distinct and observable.
- Service naming conventions are stable enough to extend to a new service.
- The team understands which notification data must remain durable and which interactions can move to a separate runtime.
- The current monolith already emits enough telemetry to compare pre- and post-extraction behavior.

## Story 9: SCRUM-159 - Notification Delivery Microservice Extraction

### Why notification delivery is the first extraction target

The roadmap fixes the first extraction target for clarity:

- notification delivery capability only

It should not reopen the choice between:

- scraper service
- diff service
- AI analysis service

Notification delivery is the best first extraction because, after the earlier stories, it should already have:

- one bounded responsibility
- one downstream provider integration
- one clear contract
- separate failure modes
- strong observability

### What this story should concretely deliver

- explicit service boundary for notification delivery
- contract between monolith and notification service
- deployment definition for the new service
- service-to-service configuration and auth assumptions
- observability and tracing from first deploy
- rollback plan
- documentation of what stays in the monolith

### What the monolith should continue to own

- public API routes
- tracked policy re-check orchestration
- snapshotting
- change detection
- durable domain truth for tracked policies and change events

### What "done" really means here

This story is not done when "a second process exists." It is done when:

- notification ownership is clear
- service contract is stable
- rollout is reversible
- traces and errors remain understandable after extraction
- the monolith no longer has an ambiguous split-brain relationship with notification delivery

## Recommended Transitional Artifacts Across the Whole Plan

To keep story-to-story handoffs smooth, the team should preserve a few artifacts consistently across the entire sequence:

### Stable identifiers

- tracked policy ID
- execution or job ID
- change event ID
- notification record ID
- correlation or trace context where applicable

### Durable state models

- tracked policy execution status
- change event seed or change artifact
- notification lifecycle state

### Reusable interfaces

- tracked policy re-check executor
- notification provider abstraction
- cache abstraction
- broker publisher abstraction
- tracing and observability config seams

### Documentation that must not drift

- env var names and ownership
- source-of-truth vs transient-state rules
- out-of-scope decisions per story
- workflow trigger and step order
- fallback behavior when optional infrastructure is unavailable

## Common Failure Modes If the Sequence Is Ignored

### If SCRUM-38 is done too early

The AI layer ends up compensating for transport and state gaps instead of focusing on interpretation.

### If SCRUM-76 is done too early

Redis becomes architecture theater and starts carrying business meaning it should not own.

### If SCRUM-137 is done before SCRUM-115 is stable

The broker becomes a transport for an unstable workflow, which multiplies debugging difficulty without proving value.

### If SCRUM-148 is done before a real multi-runtime path exists

The team spends time wiring tracing around a workflow that is still mostly monolithic and not yet worth the operational overhead.

### If SCRUM-159 is done before tracing and stable contracts

The service split is driven by diagram ambition rather than operational evidence.

## Final Practical Summary

If the team wants this roadmap to work, each story should answer one exact question:

- `SCRUM-93`: Can we see failures and request behavior clearly?
- `SCRUM-104`: Do we have a durable execution seam for manual tracked policy re-checks?
- `SCRUM-115`: Can that exact re-check run in the background reliably?
- `SCRUM-38`: Can we explain meaningful tracked policy changes well and safely?
- `SCRUM-126`: Can we notify the user about those changes through one trustworthy email path?
- `SCRUM-76`: Can we optimize transient state without corrupting the domain model?
- `SCRUM-137`: Is a broker now justified for the tracked policy re-check flow?
- `SCRUM-148`: Can we trace the exact cross-runtime workflow end to end?
- `SCRUM-159`: Is notification delivery now proven enough to extract as the first microservice?

If a story finishes without answering its question in a reusable and observable way, the next story will start with avoidable ambiguity.
