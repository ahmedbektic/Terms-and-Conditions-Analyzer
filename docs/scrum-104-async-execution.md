# Tracked Policy Async Execution (SCRUM-104)

This document outlines the architecture introduced in SCRUM-104, transforming the tracked-policy manual re-check flow into a durable, explicitly tracked execution model.

## What Is Async-Ready Now

The manual tracked-policy check endpoint has been migrated to the new async-ready execution model:
- `POST /api/v1/tracked-policies/{id}/check`

This endpoint no longer returns a bare `TrackedPolicyResponse`. Instead, it routes through an async-ready orchestration layer (`TrackedPolicyCheckExecutionService`) and returns a response envelope that tracks the status of the check run:

```json
{
  "execution": {
    "status": "pending | running | succeeded | failed | timed_out"
  },
  "tracked_policy": { "...": "present for inline results or deduped active executions" }
}
```

The frontend client fully supports this envelope and polls `GET /api/v1/tracked-policies/executions/{id}`.

## Synchronous and Out of Scope

The following flows were deliberately not refactored in SCRUM-104 and remain on synchronous or external-scheduler tracks:
- Report analysis
- Agreement submission
- Scheduled scans
- RabbitMQ / generic background workers

## Future Queue Handoff Point

Currently, `TrackedPolicyCheckExecutionService.execute_check()` invokes the synchronous business logic (`PolicySnapshotService.check_tracked_policy()`) inline on the web-server thread.

The cleanly defined handoff point for SCRUM-115 is `execute_check()` or a hook immediately after execution creation. When a queue is introduced, the web thread should create the execution, leave it in `pending`, and publish a message. A background worker would then transition the execution to `running`, execute the core check logic, and apply the terminal transition (`succeeded`, `failed`, or `timed_out`).

## Dedupe Rule

A strict active-execution deduplication rule exists to prevent multiple overlapping scrapes for the same policy.
- An execution is active if it is in the `pending` or `running` state.
- In-memory repositories enforce this via programmatic lookups plus create-time conflict checks.
- Postgres enforces this via a partial unique index on `(tracked_policy_id, subject_type, subject_id)` where `status IN ('pending', 'running')`.

Repeated requests to `POST /check` while an execution is active will not trigger a new run. Instead, the orchestrator returns the existing active execution record so the frontend can poll it.

## Execution Lifecycle States

The execution model supports strict, valid transitions to prevent silent failures and invalid jumps:

1. `pending`: The execution record has been created and may later be queued.
2. `running`: The execution has begun evaluating the source policy.
3. `succeeded`: The scrape and comparison completed successfully.
4. `failed`: An application error, missing dependency, or structured failure occurred.
5. `timed_out`: The underlying dependency explicitly timed out.

Rules:
- State should progress forward as `pending -> running -> (succeeded | failed | timed_out)`.
- Direct `pending -> terminal` completion is still allowed for failure paths that complete before a running transition is recorded.
- No invalid or silent jump transitions are permitted. Failure metadata is preserved through structured fields such as `failure_message`.

## Timeout and Retry Expectations

Expectations for tracked-policy checks:
- Timeout extraction: timeout-like exceptions from lower layers are explicitly classified into the `timed_out` state so infrastructure congestion is distinguishable from persistent bad-data or application failures (`failed`).
- Failure delivery: the execution status endpoint returns terminal failures as JSON with `status: failed | timed_out`; the frontend converts those terminal states into user-visible errors locally instead of relying on non-2xx HTTP responses.
- Retries: under the current monolith implementation, retries are manual. Users can click the check button again after an execution fails or times out. In a queued deployment, exhausted automatic retries would eventually transition to `failed` or `timed_out` with structured fallback detail.
