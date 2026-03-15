# Extension Scaffold (SCRUM-9)

This folder contains the browser extension scaffold only.
It follows the SCRUM-11 seams: shared auth contract + shared dashboard API
transport, with extension-only logic isolated to extraction and runtime wiring.

## What Is Implemented vs Stubbed

- Implemented:
  - popup/background/content-script message flow
  - extraction -> analyze orchestration
  - shared backend contract reuse (`terms_text`, bearer token transport)
  - runtime auth adapter with:
    - Google OAuth sign-in via `chrome.identity.launchWebAuthFlow` + PKCE code exchange
    - password sign-in/sign-up via Supabase auth REST endpoints
    - persisted extension session storage in `chrome.storage.local`
    - no manual `auth_session` seeding required for normal runtime flow
- Not yet implemented:
  - token refresh automation in extension runtime
  - dedicated in-popup auth settings/config UI

## Build

Run from repository root:

```powershell
npm install --prefix extension
npm run --prefix extension build
npm run --prefix extension typecheck
npm run --prefix extension test
```

The build outputs runtime assets under `extension/dist/`.

## Environment configuration

- `extension/.env.example`: optional extension build-time auth + API config.
- `frontend/.env.local`: if extension auth env vars are not explicitly set,
  extension build falls back to frontend `VITE_SUPABASE_*` and `VITE_API_BASE_URL`.
- `backend/.env`: should include local API/CORS settings; add extension origin
  to `CORS_ALLOWED_ORIGINS` only if your browser/backend combo requires it.

API base URL resolution order used by the extension build/runtime:

1. `EXTENSION_API_BASE_URL` (process env)
2. `VITE_API_BASE_URL` (process env)
3. `EXTENSION_API_BASE_URL` / `VITE_API_BASE_URL` from `extension/.env` or `.env.local`
4. `VITE_API_BASE_URL` from frontend env files
5. fallback default: `http://127.0.0.1:8000/api/v1`

If you point to a different backend host, ensure it is listed in extension
`manifest.json` `host_permissions`.

## Local Runtime Test (End-to-End)

### 1. Prepare backend + frontend

From repository root (PowerShell):

```powershell
.\scripts\run-backend.ps1
```

In a second terminal:

```powershell
.\scripts\run-frontend.ps1
```

Default expected endpoints:

- frontend: `http://127.0.0.1:5173`
- backend API: `http://127.0.0.1:8000/api/v1`

### 2. Build and load in Chrome (developer mode)

1. Open `chrome://extensions`.
2. Enable **Developer mode**.
3. Click **Load unpacked**.
4. Select the `extension/` folder (not `extension/dist`).
5. Pin the extension icon so popup access is always visible.

### 3. Ensure Supabase OAuth redirect is allowed

1. In Chrome, open extension details and copy extension id.
2. Expected redirect URI format:
   - `https://<extension-id>.chromiumapp.org/supabase-auth`
3. Add that redirect URI to your Supabase auth provider redirect allow list.
4. Ensure Google provider is enabled in Supabase Auth for this environment.
5. Full setup matrix: `docs/google-auth-setup-matrix.md`.

### 4. Sign in from extension popup

1. Open any normal web page in a tab.
2. Click extension icon.
3. Click `Log in`.
4. Complete Google OAuth flow.
5. Popup should return with `Signed in.` state.

### 5. Run extension flow

1. Open a page with visible policy text (or any long text page).
2. Click the extension icon.
3. Confirm popup shows `Signed in.` and `Analyze page`.
4. Click `Analyze page`.
5. Confirm summary appears in popup output.

### 6. Optional runtime overrides for auth/backend config

For local debugging, you can override runtime values in service-worker console:

```javascript
await chrome.storage.local.set({
  auth_supabase_url: "https://your-project-ref.supabase.co",
  auth_supabase_anon_key: "your-anon-key",
  api_base_url: "http://127.0.0.1:8000/api/v1",
  extraction_min_length: 160,
});
```

These overrides are for endpoint/config debugging only.
Do not manually write `auth_session`; sign in through popup `Log in`.

`extraction_min_length` is optional and should stay a positive integer.
Use it only when local pages are short/noisy and you need a lower threshold.

### 7. Reset local extension auth state (optional)

In service-worker console:

```javascript
await chrome.storage.local.remove("auth_session");
```

Use reset only for logout/troubleshooting scenarios.
Normal auth lifecycle should always be driven by popup `Log in` / `Log out`.

## Current scaffold boundaries

- `background.service-worker.ts`: runtime bootstrap + one message listener
- `lib/background/orchestrator.ts`: background flow authority (auth/extraction/analysis)
- `lib/background/chromeRuntimeGateway.ts`: chrome API runtime plumbing boundary
- `contentScript.ts`: extraction message endpoint only
- `lib/content/extractor.ts`: extraction strategy and text normalization
- `popup/index.ts`: popup UI state only
- `lib/popup/backgroundClient.ts`: popup-to-background transport/protocol wrapper
- `lib/runtimeAuthClient.ts`: thin extension auth orchestrator that implements shared `AuthClient`
- `lib/runtimeAuth/*`: runtime auth internals (config, oauth flow, HTTP, session codec/store)
- `lib/apiClient.ts`: extension adapter that reuses shared `DashboardApiClient`
- `lib/contract.ts`: shared message types, envelopes, and protocol guards
- `lib/config.ts`: shared runtime defaults and storage keys

## Message protocol

- Popup -> Background:
  - `auth.state.request` -> `auth.state.result`
  - `auth.action.request` -> `auth.action.result`
  - `analysis.request` -> `analysis.result`
- Background -> Content:
  - `extraction.request` -> `extraction.result`
- Any flow can return `error` with an explicit `area` (`auth`, `extraction`, `analysis`, `protocol`).

## Runtime flow (happy path)

1. Popup asks background for auth state (`auth.state.request`).
2. User clicks analyze; popup sends `analysis.request`.
3. Background requests extraction from content script (`extraction.request`).
4. Background submits extracted `terms_text` through shared `DashboardApiClient`.
5. Background returns `analysis.result`; popup renders summary.

## Shared seams and extension-only boundaries

- Shared seam reuse:
  - `lib/runtimeAuthClient.ts` implements the shared `AuthClient` contract.
  - `lib/apiClient.ts` reuses shared `DashboardApiClient` and backend payload contract.
- Extension-only logic:
  - DOM extraction (`contentScript.ts`, `lib/content/extractor.ts`)
  - Chrome runtime plumbing (`lib/background/chromeRuntimeGateway.ts`)
  - popup UI state transitions (`popup/index.ts`)

## Safe extension points for future stories

- Add richer extraction heuristics in `lib/content/extractor.ts`.
- Add new popup intents by extending `lib/contract.ts` and `lib/background/orchestrator.ts`.
- Add token refresh/re-auth behavior in `lib/runtimeAuthClient.ts` without changing popup/content boundaries.
  - expected split point: keep orchestration in `runtimeAuthClient.ts`, add internals in `runtimeAuth/*`

## Intentional stubs

- No automatic token refresh mechanism is implemented yet.
- No dedicated popup settings flow for runtime Supabase config overrides.

## Troubleshooting

- Popup says `Not signed in...`:
  - OAuth sign-in failed or session is expired.
  - Re-run `Log in` flow and verify Supabase redirect allow list.
- If you manually seeded `auth_session` during earlier debugging:
  - remove it and use popup `Log in` so background/runtime auth controls session lifecycle.
- Popup shows `Google sign-in is not enabled for this environment...`:
  - Google provider is disabled in current Supabase project.
  - Enable provider and re-check `docs/google-auth-setup-matrix.md`.
- Popup login action fails with auth config error:
  - set `EXTENSION_SUPABASE_URL` / `EXTENSION_SUPABASE_ANON_KEY` at build time
    or set runtime `auth_supabase_url` / `auth_supabase_anon_key` in storage.
- Popup shows `Google sign-in failed. Authorization page could not be loaded.`:
  - verify `auth_supabase_url` or `EXTENSION_SUPABASE_URL` uses project root URL:
    - `https://<project-ref>.supabase.co`
    - not `https://<project-ref>.supabase.co/auth/v1`
  - re-run popup login after correcting runtime/build auth config.
- Popup shows `Google sign-in failed because Supabase rejected the OAuth callback...`:
  - verify Supabase redirect allow-list contains the exact extension callback:
    - `https://<extension-id>.chromiumapp.org/supabase-auth`
  - reload the extension so latest background auth runtime is active.
- Popup analysis fails with network/permission-style errors:
  - ensure backend host matches extension `host_permissions` in `manifest.json`
  - set `api_base_url` runtime override when backend is not at local default
  - if backend still blocks origin, append extension origin to backend CORS list
- Popup shows analysis error about no extracted text:
  - target page does not have enough extractable text; try a longer policy page.
  - for local testing only, you can lower `extraction_min_length` in storage.
- Backend returns 401:
  - token is expired/invalid for backend auth settings.
  - run extension `Log in` flow again to refresh extension session.
- Possible CORS issue (environment-dependent):
  - add `chrome-extension://<your-extension-id>` to backend `CORS_ALLOWED_ORIGINS`
    and restart backend.
