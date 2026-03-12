# Code Style

## General

- Prefer simple, readable code over clever code.
- Keep functions small and focused.
- Write code that is easy to test.
- Add comments only when intent is not obvious from the code.

## TypeScript / React

- Use TypeScript for all frontend code.
- Use functional React components.
- Prefer named exports for shared utilities; default exports are acceptable for page-level components.
- Keep component files focused on one component.
- Use Prettier for formatting and ESLint for linting.
- Avoid `any` unless there is a clear reason.

## Python / FastAPI

- Follow PEP 8.
- Use type hints for public functions and API code.
- Keep route handlers thin; move business logic into services.
- Use Black for formatting.
- Prefer explicit return values and clear exception handling.

## Testing

- Add or update tests for behavior changes.
- Test user-visible behavior and service logic.
- Do not merge failing CI.

## Pull Requests

- Keep PRs focused and reasonably small.
- Link each PR to an issue/story.
- Ensure acceptance criteria are addressed before merge.
