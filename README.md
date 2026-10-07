# AI Operations Agent

A local, single-user company research workspace. Enter a request, inspect companies and stored source evidence, edit introductions, approve/reject a specific draft revision, and download approved CSV/JSON. Nothing sends messages automatically.

**Current acceptance:** real research completed 50 unique companies, 48 qualified, with 64 checked source snapshots. Native and Linux OpenCode Go runtime gates passed. See [verification](docs/verification/acceptance.md) for test, review and restart evidence, and [demo GIF](docs/verification/demo.gif) for the interface. The existing verification ledger has reached its Firecrawl cap; saved research, human review, exports and offline Demo remain usable. New live runs are rejected before dispatch.

## Run the offline demo

Requirements: Docker with Compose v2 and at least 5 GB of free disk space for builds. No provider keys needed.

```sh
cp .env.example .env
docker compose up --build -d --wait
```

Open http://localhost:3100. Choose Demo dataset, enter `Find 50 European robotics companies for simulation testing.` and start research. Fixtures are explicitly synthetic robotics companies; changing the query does not turn sample data into live web research. The normal default is 20 companies, maximum 50. Companies with a fit verdict and a score at least 70 receive introduction drafts. Review/edit a company and approve it before export.

Stop with `docker compose down`. The database volume retains campaigns, checkpoints and reviewed drafts. Do not use `down -v` to restart: it deletes this project's saved data.

Only the frontend is published, bound to `127.0.0.1`. It joins a bridge network for port publishing and the internal API network. API, worker and database join only the internal network. The browser receives no provider keys or internal agent credentials. If changing the frontend port, set both `APP_PORT` and the matching `APP_ORIGIN` in `.env`, then recreate the services. This is a local product; public server deployment and multi-user authentication are a later phase.

## Native development

Requirements: Python 3.12, uv 0.10.10, Node 24, npm and a local PostgreSQL 16 instance. Create an owned development database, install locked dependencies and launch:

```sh
createdb ai_operations_local
cd backend
uv sync --frozen
cd ../frontend
npm ci
cd ..
python3 scripts/dev.py
```

If the database already exists, reuse it. Set `DATABASE_URL` for another PostgreSQL connection. Open http://localhost:3000. Native default `APP_ORIGIN` is http://localhost:3000; Compose supplies its own value. `scripts/dev.py` terminates its owned process groups on Ctrl+C. It does not restart PostgreSQL or shared services.

## Verify

```sh
cd backend
uv run pytest -q
cd ../frontend
npm run typecheck
npm run build
npx playwright install --with-deps --no-shell chromium
npm run test:e2e
```

Backend tests use real PostgreSQL, each in a fresh owned schema; `TEST_DATABASE_URL` overrides the default development connection. They do not truncate application tables. Browser tests require the running application and worker. Offline browser tests guard every create request against live dispatch; delayed service readiness cannot select Live automatically. `APP_URL=http://localhost:3100 npm run test:e2e` targets Compose. `LIVE_CAMPAIGN_ID=693406f1-671a-4cd2-9d7f-066b2b93fb00 APP_URL=http://localhost:3100 npm run test:e2e` also checks the existing live dataset without creating paid research. CI is configured for offline acceptance with PostgreSQL and Chromium, without provider credentials; remote CI has not been run. Browser screenshots and traces are generated for diagnosis; screenshot inspection verifies layout separately from behavioral assertions.

## Architecture and state

- Next.js/React/TypeScript renders the Paper-designed single prompt/results/review screen and proxies `/api` to FastAPI.
- FastAPI owns human commands, origin checks and exports. All mutating requests require the configured Origin. Internal Authorization headers never grant access to this API. These controls assume a local single user, not an Internet-facing authentication system.
- PostgreSQL owns campaigns, unique domains per campaign, source snapshots, immutable draft revisions, review history, queue jobs, event logs and a shared verification budget. Migrations apply under an advisory transaction lock.
- A separate Python worker claims jobs using `FOR UPDATE SKIP LOCKED`, renews a lease and fences commits with the attempt's lease version. A crashed attempt can be reclaimed; stale responses cannot commit. Three attempts bound automatic retries. Saved successful company results are skipped on restart/manual retry.
- Reviewed source snapshots and drafts do not change during research retries. Editing creates a new pending revision; approval applies only to the current revision. Export joins the saved approved revision, never an unsaved UI field or an agent decision. CSV quotes multiline cells and prevents spreadsheet formula execution.
- OpenCode CLI 1.18.35 is the selected runtime. The supplied English `operations-research` skill is under `runtime-template/agent/.opencode/skills/`. Native structured output uses `info.structured`; global MCPs are excluded by isolated configuration. The private provider gateway and scoped MCP validate the leased job and bound session before research/model dispatch.

There is no Redis, email-sending service, team management or SaaS billing layer. See [product reference](docs/product.md), [dependency inventory](docs/dependencies.md) and [Paper exports](docs/design/README.md).

## Budget and live gate

All live acceptance—including probes, retries, repairs and auxiliary model calls—must share **250 Firecrawl credits and 100 actual DeepSeek HTTP requests**. Atomic PostgreSQL reservations happen before external dispatch. Ambiguous outcomes retain the reservation. A worker crash cannot prove that a provider did not receive a request. Exhaustion blocks further sends for that provider; new live campaigns are rejected when either cap is reached. Manual retry does not replenish the budget.

Do not enable Go paid fallback, top up or switch to a paid provider. The owner confirmed Use balance OFF; Go usage was checked read-only as well. `.env.example` leaves `LIVE_ENABLED=false`, `GO_BALANCE_DISABLED=false` and `RUNTIME_VERIFIED=false` for safe offline startup. Flags alone do not prove a different host's live runtime is ready; the gateway must also have configured credentials and the real runtime gate must pass.

Live acceptance starts with five companies that remain in the final 50. Remaining jobs do not exist until those five succeed and the measured cost projection fits the remaining shared budget. Every claimed result contains a checked quote from a stored public source. An incomplete live run stays NOT RUN/FAIL in acceptance, even if the demo passes. The completed50 native run used56 model reservations and167 Firecrawl credits across all probes/retries to that point. One Linux runtime probe raised the model count to57. A subsequently detected asynchronous mode-selection bug launched unintended live test runs: the retained total is87 model reservations (86 received,1 uncertain) and250 Firecrawl credits. The bug is fixed, all such tasks are fenced, and the cap was never reset. Those runs do not replace the verified original50. Another live budget requires separate owner authorization; no refill, new scope or paid fallback was used.

## Enable live research

The owner confirmed Go **Use balance OFF** on 2026-10-07. The selected CLI/model passed a real streaming/JSON Schema gate. Credentials remain gateway-only; OpenCode receives a temporary job capability, never the provider keys. Each job starts an isolated `opencode serve --pure` process with only the research skill, StructuredOutput and three scoped MCP tools. Its session is bound to a fenced PostgreSQL lease. The gateway checks authority again before every physical external request, including OpenCode retries and repairs.

For native live development, install the pinned CLI and use your existing credential file paths:

```sh
cd runtime-template/node && npm ci && cd ../..
export LIVE_ENABLED=true GO_BALANCE_DISABLED=true RUNTIME_VERIFIED=true
export GO_KEY_FILE="$HOME/.local/share/opencode/auth.json"
export FIRECRAWL_KEY_FILE="$HOME/Library/Application Support/firecrawl-cli/credentials.json"
python3 scripts/dev.py
```

Alternatively the gateway accepts `OPENCODE_GO_API_KEY` and `FIRECRAWL_API_KEY` environment variables. Do not paste them into tracked files or browser code. A different host's model/configuration needs its own runtime gate before setting `RUNTIME_VERIFIED=true`.

For Linux Compose live mode, import only the existing selected-provider keys into ignored files, then enable the explicit override:

```sh
python3 scripts/import_local_credentials.py
export LOCAL_UID=$(id -u) LOCAL_GID=$(id -g)
export GO_BALANCE_DISABLED=true RUNTIME_VERIFIED=true
docker compose -f compose.yaml -f compose.live.yaml up --build -d --wait
```

On another OS, set `GO_AUTH_SOURCE` and `FIRECRAWL_AUTH_SOURCE` to the existing credential JSON files before importing. The import script prints no keys and sets private file permissions. Only the gateway mounts those files, read-only, running as the file owner's UID/GID. It has outbound networking and no published port; API and workers remain on the private network. Default `compose.yaml` stays offline and needs no credentials.

Use one active database/ledger for a verification budget. Switching native/container environments must stop live dispatch first and preserve the spent/reserved totals; a new database is not permission to reset the authorized cap. Normal cancellation and retries cannot replenish it. Successful plans/discovery/results are durable checkpoints; source caching lasts24 hours and research caching binds company, source URLs/content hashes, criteria, provider/model and skill version. Fetching is limited to three public HTML pages on the assigned company domain, with global Firecrawl concurrency2. Arbitrary files, shell, other campaigns, human review and exports are unavailable to the agent.
