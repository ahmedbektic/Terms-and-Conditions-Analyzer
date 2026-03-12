# Naming Conventions

## General

- Use descriptive names.
- Avoid abbreviations unless they are widely understood.
- Be consistent across frontend, backend, and docs.

## Files

- React components: `PascalCase.tsx`
  - Example: `PolicySummaryCard.tsx`
- Hooks: `useSomething.ts`
  - Example: `useTrackedPolicies.ts`
- Utility files: `camelCase.ts` or `kebab-case.ts`
  - Example: `formatDate.ts`
- Python modules: `snake_case.py`
  - Example: `policy_analyzer.py`

## Code

- Classes / React components: `PascalCase`
- Variables / functions: `camelCase` in TypeScript, `snake_case` in Python
- Constants: `UPPER_SNAKE_CASE`
- Booleans should read like questions:
  - `isLoading`
  - `hasChanges`
  - `canRetry`

## API and Database

- API routes should be resource-oriented:
  - `/policies`
  - `/analyses`
  - `/notifications`
- Database tables/columns: `snake_case`

## Events

Use dot-separated lowercase event names.

Examples:

- `policy.tracking_requested`
- `policy.snapshot_created`
- `policy.changed_detected`
- `policy.change_analyzed`
- `notification.sent`

## Branches

Use short, readable branch names:

- `feature/policy-dashboard`
- `fix/login-error`
- `chore/add-ci`

## Pull Requests

Use a concise title:

- `Add Chrome extension policy extraction`
- `Implement backend snapshot comparison`
