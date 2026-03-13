# DEPLOYMENT.md

## Purpose

This document defines the deployment strategy for the AI Terms & Conditions Analyzer / Change Tracker.

This is a **student project**, so the deployment approach must remain **completely free**. We will still disclose limitations honestly, but we are not designing around upgrades or assuming we will later move off free services.

Our planned stack is:

- **Cloudflare** for edge delivery, DNS, SSL, CDN, frontend hosting, and future real-time/WebSocket coordination
- **Render** for the Python application layer and internal microservices
- **Supabase** for Postgres and authentication
- **CloudAMQP** for RabbitMQ
- **Upstash Redis** for a single Redis cache node
- **OpenTelemetry SDKs** for instrumentation
- **Sentry Developer plan** for error monitoring and performance visibility

We will also support a **`vault-play`** concept as a separate Render service for learning and demonstration, but with **environment-variable fallback as the real MVP secrets approach**.

---

## Guiding deployment principles

### 1. We deploy the simplest thing that can honestly support the product

The first deployment does **not** need to include every future architecture box. A deployable MVP is more valuable than an overbuilt diagram that never runs.

### 2. We avoid self-hosting infrastructure when a free managed service exists

If a free managed service is good enough, we should use it. Self-hosting adds operational burden, and for a student team that burden is usually architectural vanity disguised as rigor.

### 3. We choose services that map cleanly to the architecture

Each provider should own a clear part of the system. Clean boundaries make the architecture easier to explain, reason about, and evolve.

### 4. We stay inside the free tier on purpose

We are not choosing services because they are “good until we outgrow them.” We are choosing services whose **free tiers are enough for the scope of this project**, while acknowledging that those free tiers come with real constraints.

---

# 1. Why Cloudflare

## What we plan to use from Cloudflare

- **Cloudflare Free plan**
  - DNS
  - SSL/TLS
  - CDN
  - basic edge protection
- **Cloudflare Pages**
  - React frontend hosting
- **Cloudflare Workers Free** *(later / optional)*
  - lightweight edge routing and middleware
- **Cloudflare Durable Objects** *(later / optional)*
  - stateful WebSocket coordination and real-time notification channels
- **Cloudflare API Gateway / API Shield** *(conceptual later fit)*
  - edge-layer API gateway role

## Why we are choosing Cloudflare

### Cloudflare is the right place for the **edge**

Our architecture needs a true edge layer:

- user-facing frontend delivery
- global caching
- DNS
- SSL
- future request routing
- future real-time coordination

Cloudflare is better at this than a generic backend host because this is its core identity. We are not stretching it into a role it was not built for. We are using it exactly where it is strongest.

### Cloudflare Pages is the correct frontend home

The frontend should be static, globally distributed, and cheap to operate. Pages gives us that for free and keeps the React app close to the CDN by design. That makes frontend deployment simpler and reduces the temptation to treat the frontend like a server process when it does not need to be one.

### Cloudflare gives us a believable future for WebSockets and API gateway concerns

We do not need to build the full WebSocket layer immediately, but our architecture does include that ambition. Durable Objects are a strong future fit because they are designed for stateful coordination and multi-client interactions. Likewise, if we later want a more explicit API gateway role at the edge, Cloudflare is the natural place for it conceptually.

## What Cloudflare is **not** responsible for

Cloudflare is **not** our Python backend host.  
Cloudflare is **not** our primary Postgres host.  
Cloudflare is **not** our RabbitMQ broker.  
Cloudflare is **not** our Redis provider.

That separation is deliberate. Cloudflare owns the edge layer, and keeping it in that role makes the system easier to explain and maintain.

---

# 2. Why Render

## What we plan to use from Render

- **Render Web Service**
  - main FastAPI backend
- **Render Background Workers** *(later)*
  - RabbitMQ consumers
  - AI analysis jobs
  - notification jobs
  - retry / recovery jobs
- **Render Private Services** *(later)*
  - internal-only microservices
  - `vault-play` mock Vault service
  - internal helper services
- **Render Cron Jobs** *(later)*
  - scheduled policy re-checks
  - scheduled cleanup tasks

## Why we are choosing Render

### Render is the right place for the **application layer**

The backend is not just a CRUD API. It will eventually coordinate AI analysis, queue-driven work, notifications, retries, and microservice boundaries. That is exactly the kind of application-layer work Render is good at hosting.

### Render is the easiest free host for FastAPI that still respects the future architecture

The biggest reason to choose Render is that it works now **and** supports the architectural direction we want without forcing us into serverless edge-only compromises. We can start with one web service and later break out workers, internal services, and cron-triggered tasks using the same platform primitives. That is a much stronger story than “we chose the simplest host and will figure out the rest later.”

### Render gives us the right service model for microservices

If we later split the backend, we already know where each part goes:

- public HTTP API → **Web Service**
- queue consumers → **Background Workers**
- internal-only APIs → **Private Services**
- scheduled scans → **Cron Jobs**

That makes Render a convincing choice because it matches the architecture instead of fighting it.

## Render free-tier limitations

We should be clear that Render free services are not production-grade in the enterprise sense. Free services can have cold starts, limited resources, and free-tier operational constraints. That is acceptable here because this is a student project. The point is not to simulate an enterprise SLA; the point is to deploy something real for zero cost.

### `vault-play` on Render

We will support a `vault-play` service as a separate Render service for experimentation and architectural demonstration only. It should not be described as production-grade secrets management. The real secrets strategy for this project remains environment variables managed by the hosting platforms. That is the honest and technically responsible choice on a zero-dollar budget.

---

# 3. Why Supabase

## What we plan to use from Supabase

- **Supabase Postgres**
  - one shared Postgres database
- **Supabase Auth**
  - user authentication and account management
- **JWT-based authentication**
  - access tokens issued by Supabase Auth as JWTs
  - backend verification of authenticated user context
  - optional custom claims later if needed

## Why we are choosing Supabase

### Supabase solves both persistence and identity at once

The fastest way to make an MVP harder than it needs to be is to separately self-manage a database and an auth system. Supabase collapses both problems into one free managed platform. That is a strategic win, not just a convenience win.

### Postgres is the right primary datastore

Our domain is relational:

- users
- analyses
- tracked policies
- snapshots
- notification preferences
- audit records

Postgres fits this naturally, and Supabase gives us managed Postgres without forcing us to become database operators.

### Supabase Auth supports our JWT plan cleanly

This matters a lot.

We plan to use JWTs. Supabase already does that for us:

- user signs in
- Supabase issues an **access token JWT**
- the frontend includes that token when calling the backend
- the backend verifies the JWT and uses its claims to identify the user
- Supabase can also use those claims for Row Level Security on the database side

That means JWT is not a separate bolt-on choice — it is already aligned with how Supabase Auth works.

### This is better than building our own JWT auth for this project

Could we issue our own JWTs from FastAPI? Yes. Should we? No.

That would create extra work around:

- login flows
- refresh tokens
- token expiry
- token signing keys
- password storage
- account lifecycle

Supabase already provides this, and its auth model is compatible with the backend architecture we want. The correct engineering choice is to use the managed auth layer that already speaks JWT natively.

## How the backend uses Supabase JWTs

Planned flow:

1. User signs in with Supabase Auth.
2. Supabase issues an access token JWT.
3. Frontend stores session state and sends the JWT with API requests.
4. FastAPI verifies the JWT and extracts claims such as user identity.
5. Backend uses that identity to authorize access and associate data correctly.
6. Supabase-side RLS can later reinforce database-level access if we use direct data access patterns.

This is a clean design because:

- identity is centralized
- JWT is standard and stateless
- backend remains decoupled from password/auth implementation details
- auth works across frontend and backend consistently

## Table-per-microservice model

We are using **one Supabase database** with **table ownership by service** rather than database-per-service.

Example ownership:

- `analysis_*` → analysis service
- `policy_*` → tracking/snapshot service
- `notification_*` → notification service
- `audit_*` → audit/compliance service

Rules:

1. Each service owns its tables.
2. Other services should prefer API/event boundaries over direct writes.
3. Shared direct access should be minimized and documented.
4. Cross-service joins should be treated as a warning sign.

This gives us the best practical version of decoupling we can achieve on a strict free budget.

---

# 4. Why CloudAMQP

## What we plan to use from CloudAMQP

- **CloudAMQP free RabbitMQ plan**
  - one managed RabbitMQ broker for the entire application

## Why we are choosing RabbitMQ and CloudAMQP

### RabbitMQ is the right level of complexity

At our stage, we need:

- task queues
- retries
- decoupled async work
- consumers for background processing

RabbitMQ is a strong fit for that. It is simpler and more directly aligned with operational workflows than Kafka for this project.

### CloudAMQP is the right way to consume RabbitMQ on a free budget

If we hosted RabbitMQ ourselves, we would spend time managing the broker instead of building the product. CloudAMQP gives us the broker as a service, which is exactly what a student MVP should want.

## Limitations

We should be realistic: the free plan is appropriate for development, demos, and hobby-scale usage. It is not intended for high-throughput production messaging. That is acceptable for this project because our expected traffic and queue volume are modest.

---

# 5. Why Upstash Redis

## What we plan to use from Upstash

- **One Upstash Redis database**
  - single Redis cache node
  - not distributed
  - not clustered

## Why we are choosing one Redis node

### Because we need Redis’s behavior, not Redis architecture theater

Our intended Redis use cases are small:

- cache recent summaries
- store transient analysis status
- support basic rate limiting
- keep short-lived coordination data

A single managed Redis instance is enough.

### Redis is deliberately not our source of truth

- Postgres = source of truth
- RabbitMQ = async job transport
- Redis = speed and transient state

That distinction keeps the system clean.

## Limitations

This is a single-node free-tier Redis instance. It is not a highly available distributed cache. That is fine for our purposes because Redis is not carrying permanent business-critical state.

---

# 6. Why Sentry

## What we plan to use from Sentry

- **Sentry Developer plan**
- **React/browser SDK**
- **Python/FastAPI SDK**

## Why we are choosing Sentry

### Sentry gives the fastest debugging payoff

The project includes a frontend, extension-adjacent UI flows, a backend, async jobs, and third-party services. Failures are inevitable. Sentry gives us useful error visibility immediately, with very low setup cost.

### Sentry belongs in both frontend and backend

That is non-negotiable if we want meaningful debugging:

- frontend SDK catches UI/runtime problems
- backend SDK catches API exceptions and worker failures

### Hosted Sentry is the right free choice

Self-hosting Sentry would be infrastructure vanity. The free hosted plan is much more appropriate for our budget and team size.

## Limitations

The free plan is enough for a student project, but it still comes with event-volume and retention limits. That is acceptable because our goal is developer visibility, not enterprise observability coverage.

---

# 7. Why OpenTelemetry SDKs

## What we plan to use from OpenTelemetry

- **OpenTelemetry SDKs in backend services**
  - main FastAPI service
  - worker services later
- optional instrumentation for:
  - RabbitMQ interactions
  - Redis interactions
  - database calls
  - external AI calls

## Why we are choosing OpenTelemetry

### Because tracing and error monitoring are not the same thing

Sentry is excellent for crashes and exceptions. OpenTelemetry is what makes distributed behavior visible:

- where a request spent time
- which service called which dependency
- whether RabbitMQ, Redis, Supabase, or AI calls are a bottleneck

### SDKs only, not a collector service

For this project, we will use **OpenTelemetry SDKs**, not a separately hosted collector. That keeps the observability story free and lightweight while still showing that we understand the correct instrumentation pattern.

### OpenTelemetry keeps the architecture honest

As soon as we have a public API, background jobs, and broker-driven work, we need a way to explain the flow across services. OpenTelemetry is the right conceptual and technical tool for that.

## Limitations

Without a separately hosted collector or full observability backend, our telemetry setup will be lighter than a full production tracing stack. That is a conscious tradeoff to remain fully free.

---

# 8. Secrets management: `vault-play` and environment-variable fallback

## Planned approach

### Real MVP approach

Secrets live in:

- **Render environment variables** for backend services
- **Cloudflare environment/config variables** where needed for frontend/edge logic

### Learning / demonstration approach

We will also support a **`vault-play`** service:

- separate Render service
- clearly marked as mock/experimental
- not treated as real production secrets infrastructure

## Why this is the right choice

### Because a fake “secure” solution is worse than an honest simple one

HashiCorp Vault is a real secrets platform. Running a serious Vault deployment on a fragile all-free setup would give the appearance of sophistication without the operational guarantees that make Vault meaningful.

### Environment variables are the correct free-tier answer

They are:

- built into our hosts
- simple
- stable
- sufficient

The right engineering decision is the one that reduces risk and complexity while staying honest about scope.

---

# 9. Planned deployment topology

## MVP topology

### Cloudflare

- DNS
- SSL
- CDN
- Cloudflare Pages for React frontend

### Render

- one **web service** for main FastAPI backend
- optional `vault-play` service

### Supabase

- one Postgres project/database
- one auth system using JWT access tokens

### CloudAMQP

- one RabbitMQ broker

### Upstash

- one Redis database

### Sentry

- hosted project(s) for frontend and backend monitoring

### OpenTelemetry

- SDKs embedded in backend code

---

## Later microservice topology

### Public edge

- Cloudflare Free + Pages
- optional Workers/API edge logic
- optional Durable Objects for WebSocket coordination

### Render

- `api-service` → public web service
- `analysis-worker` → background worker
- `notification-worker` → background worker
- `policy-diff-service` → private service
- `vault-play` → private service or isolated internal demo service
- `policy-recheck-cron` → cron job

### Supabase

Single Postgres instance with service-owned tables:

- `analysis_*`
- `policy_*`
- `notification_*`
- `audit_*`

### CloudAMQP

RabbitMQ as the async backbone

### Upstash

Redis as cache / status / rate-limiting store

### Sentry + OpenTelemetry

Cross-cutting observability in every relevant service

---

# 10. Service-to-architecture mapping

## Global CDN

**Cloudflare Free + Pages**

## Frontend hosting

**Cloudflare Pages**

## Public backend API

**Render Web Service**

## Background jobs

**Render Background Workers + CloudAMQP**

## Internal microservices

**Render Private Services**

## Scheduled policy checks

**Render Cron Jobs**

## Database / auth / JWT

**Supabase**

- Postgres for persistence
- Auth for identity
- JWT access tokens for authenticated API calls
- optional RLS support driven by JWT claims

## Messaging

**CloudAMQP**

## Cache / transient state

**Upstash Redis**

## Real-time / WebSockets (future)

**Cloudflare Workers + Durable Objects**

## Error monitoring

**Sentry Developer plan**

## Tracing / instrumentation

**OpenTelemetry SDKs**

---

# 11. Why this stack is convincing

This deployment strategy is convincing because it is disciplined.

It is **fully free**.  
It is **deployable**.  
It is **architecturally coherent**.  
It is **honest about limitations**.

But it also does not undersell the system. We still have:

- a real global edge layer
- a real Python backend host
- a real managed Postgres database
- a real JWT-based auth system
- a real broker
- a real cache
- real observability tooling

Most importantly, every service has a clear reason to exist:

- **Cloudflare** owns the edge
- **Render** owns the application layer
- **Supabase** owns data and identity
- **CloudAMQP** owns async brokered workflows
- **Upstash** owns transient caching/state
- **Sentry** owns actionable error visibility
- **OpenTelemetry** owns trace-level observability

That is exactly what a good deployment design should look like:  
**simple enough to run, clear enough to defend, and structured enough to feel like real engineering.**
