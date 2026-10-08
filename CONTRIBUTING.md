# Contributing

Read [product scope](docs/product.md), [architecture](docs/architecture.md) and the applicable `AGENTS.md` before changing behavior. Preserve the single prompt workflow, verified evidence, immutable draft revisions and human-only approval. Maintained documentation and skills use English.

## Install

Follow [setup](docs/setup.md). Use the committed Python/npm lockfiles. Do not update dependencies incidentally; record purpose, resolved version, license and verification in [dependencies](docs/dependencies.md) when adding or changing a runtime dependency.

## Backend checks

Use a reachable PostgreSQL 16 database. From the repository root:

```sh
cd backend
uv sync --frozen
TEST_DATABASE_URL='dbname=ai_operations_local' uv run pytest -q
cd ..
```

Set the connection string to your local test database. The test role needs permission to create schemas. Each test creates and removes a unique schema; the fixtures do not truncate application tables. Tests exercise state/readback, domain duplicates, competing workers, lease expiry, retry/cancellation, agent denial, evidence, draft approval and budget/accounting failure cases. They mock outbound providers and require no paid calls.

## Frontend checks

```sh
cd frontend
npm ci
npm run typecheck
npm run build
npx playwright install --no-shell chromium
cd ..
```

On Linux, use `npx playwright install --with-deps --no-shell chromium` to install browser system dependencies. Chromium is the configured desktop/mobile browser; these checks do not establish Safari or physical-device behavior.

Run the native application in a separate terminal:

```sh
LIVE_ENABLED=false python3 scripts/dev.py
```

Then run the browser workflow from the repository root:

```sh
cd frontend
APP_URL=http://localhost:3000 npm run test:e2e
cd ..
```

For a running Compose installation, use `APP_URL=http://localhost:3100`. The tests use the actual UI, API and worker and save synthetic runs in the application's database. They cover prompt → progress → 50 results → source inspection → editing → approval/rejection → CSV/JSON → reload, plus cancellation/retry, create idempotency, delayed live readiness and usage display. Synthetic create requests are guarded against accidental paid dispatch. A fresh database runs 10 desktop/mobile cases and skips the two historical live-dataset cases.

The optional `LIVE_CAMPAIGN_ID` enables a test tied to the historical accepted 50-company dataset, its exact title, MiR/FANUC drafts and Savant review. It reads evidence and exercises human review/export, including updating reviews in that dataset; it is not a generic test for an arbitrary campaign and never creates paid research. Run it only against the documented dataset you intend to review. Without this explicit opt-in it stays skipped.

Playwright reports/traces are ignored. Tests also write delivery screenshots under `docs/verification/`; inspect any resulting tracked changes before committing, rather than silently replacing historical evidence.

## CI and live verification

[Offline acceptance](.github/workflows/ci.yml) installs locked dependencies, runs PostgreSQL tests, builds/typechecks the UI and runs browser tests against a native offline application with PostgreSQL 16.13. It requires no provider secrets and does not claim live validation. The browser step stops its owned development process groups on both success and failure before setup-uv prunes the cache. The [Actions page](https://github.com/66dplus/ai-operations-agent/actions/workflows/ci.yml) reports the current remote result; [publication evidence](docs/github.md) and local acceptance records distinguish their environments.

For live integration changes, verify the real pinned runtime, selected model, structured output and tool restrictions before dispatch. Confirm Go **Use balance OFF**, credentials and the owner's remaining authorized budget. Retain ledger history, uncertain reservations and existing approvals. An offline mock cannot establish a new provider/model contract.

Record the tested code/environment and distinguish **PASS**, **FAIL** and **NOT RUN**. Reuse [acceptance](docs/verification/acceptance.md) and [current measurement](docs/verification/uncapped-acceptance.md); do not relabel old live results as a fresh run. A missing live check does not invalidate completed offline checks and must remain visible.

## Change review

Keep one owner for each business rule. Validate changed interfaces through their actual consumers and persisted readback. A meaningful UI change also needs an ordinary-user pass through the affected visible flow. Queue, budget, lease and approval boundary changes require the FULL route and independent read-only review, as specified in project guidance.

Review the complete diff, failures/recovery, dependencies, behavioral evidence and documentation impact. Update README for changed setup/public behavior and the product reference for confirmed owner decisions. Do not expand documentation-only work into a runtime rewrite.

## Secrets and data

Keep `.env`, credentials, agent attempts, database dumps, browser storage and private logs out of commits. `runtime/` and common build/test directories are ignored; `.env.example` contains placeholders/defaults only. Treat commit history as part of publication review. Do not upload a real credential just because its current working-tree file is ignored.

Use a dedicated branch and preserve other sessions' changes and services. Never reset the shared ledger, remove database volumes or restart unrelated infrastructure to make a check pass.
