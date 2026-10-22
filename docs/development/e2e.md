# End-to-end tests (Playwright)

`frontend/e2e/pilot-journey.spec.ts` drives the pilot journey through the real UI against
a running stack:

sign up → create organization → onboarding → generate a marketing plan (mock AI) and
make it active → add a Facebook **simulation** account → generate a post with AI → submit
→ approve → publish now (the Celery worker publishes through the simulation adapter) →
see "Published · Simulation" → switch automation to semi-automatic → Operations shows
background processing healthy.

Nothing external is called: the AI provider is the labelled mock, and simulation accounts
never post anywhere. Each run creates a new user and organization (`e2e.<timestamp>@example.com`)
in the database it runs against. Don't point it at shared or production data.

## Run locally

Start the stack (`make up`, `make backend`, `make worker`, `make beat`, `make frontend`),
then:

```bash
make e2e
```

To use an installed Chrome instead of Playwright's bundled browser:

```bash
cd frontend && E2E_BROWSER_CHANNEL=chrome npm run e2e
```

`E2E_BASE_URL` targets another frontend (default `http://localhost:3000`). Failures keep a
trace, screenshot and page snapshot under `frontend/test-results/`; open the HTML report with
`npx playwright show-report`.

## In CI

The `e2e` job in `.github/workflows/ci.yml` runs the same spec against Postgres and Redis
services, Django, a Celery worker and beat, and the **production standalone build** of the
frontend.

**Status:** the identical sequence (production build, standalone server, real worker and
beat) passed locally on 2026-10-20. The workflow itself has not run on GitHub yet: the
repository has no remote or commits.
