# Setup and operation

Run all root-level commands from the cloned repository. The default installation uses synthetic offline fixtures. Live research requires provider credentials and a verified runtime.

## Docker: offline

Use Docker with Compose v2 and at least 5 GB of free build space:

```sh
cp .env.example .env
docker compose up --build -d --wait
```

Open http://localhost:3100. PostgreSQL migrations run automatically. Only the frontend is published, bound to localhost; the API, worker and database use the private network.

```sh
docker compose ps
docker compose logs --tail=100 api worker web
docker compose down
```

The named `database` volume retains campaigns, sources and draft reviews. Do not add `-v` when stopping unless you intend to delete those records.

To change the frontend port, set both `APP_PORT` and its matching `APP_ORIGIN` in `.env`, then recreate the services. Origin validation depends on the exact configured address.

## Native development

Requirements: Python 3.12, uv 0.10.10, Node 24, npm and PostgreSQL 16. The tested patch versions are recorded in [dependencies](dependencies.md).

```sh
createdb ai_operations_local
cd backend
uv sync --frozen
cd ../frontend
npm ci
cd ..
python3 scripts/dev.py
```

Reuse the database if it already exists. Set `DATABASE_URL` for a different connection. Open http://localhost:3000. The launcher terminates its own process groups on Ctrl+C; PostgreSQL remains independently managed.

Native processes inherit exported environment variables. The launcher does not load `.env`; Compose loads that file for variable substitution. Native `APP_ORIGIN` defaults to http://localhost:3000. The Next.js proxy uses `API_URL` at build/config time, defaulting to http://127.0.0.1:8000 for native development; the web image builds against http://api:8000.

## Live research gate

The selected integration is OpenCode CLI 1.18.35 and Go DeepSeek V4.1 Flash. On the verified installation, actual streaming, JSON Schema output and restricted tools passed native/Linux gates. A different host or a changed CLI/model needs its own real gate before setting `RUNTIME_VERIFIED=true`; setting a flag is not a substitute for verification.

Live readiness requires `LIVE_ENABLED`, `GO_BALANCE_DISABLED` and `RUNTIME_VERIFIED`, plus a reachable gateway with configured credentials. Confirm Go **Use balance OFF** in the provider console before setting its confirmation flag. There is no automatic fallback or top-up.

OpenCode supports programmatic headless operation ([server reference](https://opencode.ai/docs/server/)). Go is a separate service with usage windows and a documented coding-agent traffic focus ([Go reference](https://opencode.ai/docs/go/)). Company research working in a local test does not establish provider approval for a production research service. See [the runtime decision](decisions/0001-opencode-runtime.md).

### Existing credentials: native

The gateway reads the existing Go and Firecrawl credential files; it does not pass them to the agent:

```sh
cd runtime-template/node
npm ci
cd ../..
export LIVE_ENABLED=true GO_BALANCE_DISABLED=true RUNTIME_VERIFIED=true
export GO_KEY_FILE="$HOME/.local/share/opencode/auth.json"
export FIRECRAWL_KEY_FILE="$HOME/Library/Application Support/firecrawl-cli/credentials.json"
python3 scripts/dev.py
```

These credential paths match the tested macOS tools; use your actual file paths on another host. Alternatively, the native gateway accepts `OPENCODE_GO_API_KEY` and `FIRECRAWL_API_KEY` from the process environment. Never put keys in tracked files or browser code. OpenCode receives only a temporary leased task capability.

### Existing credentials: Linux containers

Import only the selected provider credentials into ignored private runtime files:

```sh
python3 scripts/import_local_credentials.py
export LOCAL_UID=$(id -u) LOCAL_GID=$(id -g)
export GO_BALANCE_DISABLED=true RUNTIME_VERIFIED=true
docker compose -f compose.yaml -f compose.live.yaml up --build -d --wait
```

The import script defaults to the same macOS credential paths. On another OS, export `GO_AUTH_SOURCE` and `FIRECRAWL_AUTH_SOURCE` with the actual existing JSON paths first. It prints no keys, sets directory mode 0700/file mode 0600 and changes no global provider configuration. Only the gateway mounts the files, read-only, under the owner's UID/GID. The live override enables live flags for API/workers and adds the outbound gateway network; it publishes no additional port.

To run two workers, append `--scale worker=2`. Firecrawl concurrency stays globally limited to two through PostgreSQL advisory locks.

## Configuration and accounting

| Setting | Default / scope | Meaning |
| --- | --- | --- |
| `APP_PORT` | 3100, Compose | Published frontend port |
| `APP_ORIGIN` | localhost:3100 Compose; localhost:3000 native | Required Origin for human mutations |
| `DATABASE_URL` | Native connection; Compose supplies its internal connection | PostgreSQL state owner |
| `LIVE_ENABLED` | false; live override enables it | Allows live dispatch |
| `GO_BALANCE_DISABLED` | false | Operator confirmation that Go paid fallback is OFF |
| `RUNTIME_VERIFIED` | false | Operator confirmation of a completed actual runtime gate |
| `BUDGET_LIMITS_ENABLED` | true | Only explicit `false` disables internal budget enforcement |
| `MAX_MODEL_CALLS` / `MAX_FIRECRAWL_CREDITS` | 100 / 250 | Native settings; current Compose files pin these values |
| `BUDGET_SCOPE` | acceptance | Shared durable ledger; changing scope is not a budget refill |
| `GO_KEY_FILE` / `FIRECRAWL_KEY_FILE` | Native file paths; Compose mounts imported files | Gateway-only credentials |
| `AI_PROVIDER` / `AI_MODEL` | opencode-go / deepseek-v4.1-flash, native settings | Selected runtime configuration; gateway transport is currently Go-specific |

The original capped acceptance was followed by an owner-authorized temporary uncapped measurement. To use that mode, set `BUDGET_LIMITS_ENABLED=false` in Compose's ignored `.env` or export it for native processes, then recreate/restart API, workers and gateway together. Restore `true` the same way to enforce caps against retained totals. Missing or malformed values keep enforcement on.

Every physical provider attempt reserves usage atomically before dispatch. Unknown delivery outcomes retain the reservation. Disabling enforcement never resets the ledger. Old budget-stopped campaigns require **Retry unfinished steps**; the application does not restart them automatically.

Keep one active accounting database for a verification budget. Before moving live execution between native and container environments, stop dispatch and preserve spent/reserved totals. Creating a fresh database or changing `BUDGET_SCOPE` does not authorize another budget.

Under **This run**, requests, tokens and credit reports are campaign-scoped. Token totals cover only requests with valid provider metadata. Firecrawl reserved credits are estimates; missing per-response billing metadata stays unknown. Account balance readback is separate. Go subscription percentages and token counts are not an invoice.

## Troubleshooting

| Symptom | Check / action |
| --- | --- |
| Live web is disabled | Read `/api/health`, confirm all three live opt-ins and gateway readiness. Check credential paths/permissions. |
| Start returns budget exhausted | Check cumulative counters and enforcement mode. Retain the ledger; use an explicitly authorized configuration change or continue Demo/saved review. |
| A run is partial or stopped | Open run logs. Retry unfinished steps; successful sources/results and approvals are retained. |
| A human action returns 403 | Open the app at exactly `APP_ORIGIN`; provider/agent Authorization credentials cannot use the human API. |
| Credentials cannot be read in containers | Confirm imported file permissions and `LOCAL_UID`/`LOCAL_GID`; only the gateway owns credential access. |
| The build runs out of disk | Free task-owned regenerable build/cache space, retain the database volume and runtime evidence. |
| Go or Firecrawl returns 429/5xx | Inspect request receipts and provider quotas. Automatic retries are bounded; internal uncapped mode does not remove provider quotas. |

For validation commands and fresh-database behavior, see [Contributing](../CONTRIBUTING.md). For historical live evidence and current measurements, see [acceptance](verification/acceptance.md) and [uncapped measurement](verification/uncapped-acceptance.md).
