# Architecture

The application is a local, single-user research and review tool. The backend owns durable state and product rules. OpenCode supplies research reasoning; it does not own the queue, approvals or exports. The [product reference](product.md) records the approved scope, and [the runtime decision](decisions/0001-opencode-runtime.md) explains this separation.

## Components and ownership

| Component | Owns | Main implementation |
| --- | --- | --- |
| Next.js / React | Prompt, progress, company panel, human review controls and downloads | `frontend/app/` |
| FastAPI | Human API, Origin checks, request validation and readback | `backend/operations/api.py` |
| Product service | Domain normalization, evidence checks, qualification, draft revisions and approved export | `backend/operations/service.py` |
| PostgreSQL | Campaigns, companies, sources, jobs, checkpoints, caches, reviews and provider receipts | `backend/migrations/`, `backend/operations/db.py` |
| Python worker | Leased task execution, heartbeat, recovery and settlement | `backend/operations/worker.py`, `queue.py` |
| OpenCode adapter | Isolated runtime lifecycle, sessions, JSON Schema output and one semantic repair | `backend/operations/agent.py` |
| Private gateway / MCP | Scoped research tools, actual model request accounting and provider credentials | `backend/operations/gateway.py`, `providers.py` |

The offline worker uses synthetic fixtures in `demo.py`. It follows the same persistence, validation, review and export rules without making provider calls. The standard Compose network has no provider gateway. The live override adds a gateway with outbound access; only the web service publishes a localhost port.

## Pipeline

1. **Create:** the UI submits a query and mode with an idempotency key. The backend derives the target count from supported English/Russian count phrases, defaults to 20 and rejects counts outside 1–50. It checks live readiness and, when enabled, the shared budget before creating work.
2. **Plan:** the model returns a `CampaignPlan`. Criteria and discovery queries are persisted before the next job is queued. The backend retains ownership of the requested count.
3. **Discover:** the agent uses scoped Firecrawl search and returns candidate websites. Domains are normalized and deduplicated with a unique `(campaign_id, domain)` constraint. Search snippets are discovery hints; they are not qualification evidence.
4. **Collect and research:** the worker obtains company landing pages through the gateway, then the agent may fetch more pages for assigned companies. Up to three distinct URLs per domain are allowed. Research runs in batches of up to five, returning enrichment, qualification and drafts together as `ResearchBatch`.
5. **Validate and save:** Pydantic rejects invalid schemas. Every assigned company must appear exactly once; evidence must refer to that company's stored source and contain an exact quotation after whitespace normalization. Qualified companies need a draft; other companies cannot have one. A fit requires a score of at least 70 and a `strong_fit` or `possible_fit` verdict.
6. **Review and export:** the human opens evidence, edits drafts and approves or rejects a specific revision. Export reads only the approved saved revision.

For live requests larger than five companies, a five-company pilot commits first. With caps enabled, measured usage projects the remaining work against the shared budget before releasing it. With caps explicitly disabled, the checkpoint and accounting remain while the budget projection cannot block dispatch. A shortage of verified companies produces a visible partial result; it is never filled with invented companies.

## Runtime and capability boundary

Each live job attempt starts its own pinned `opencode serve --pure` process, directory, XDG state, server password and session. Global user configuration and MCPs are excluded. Provider secrets and the database connection are absent from the agent's allowlisted subprocess environment. The process receives a temporary task capability for the gateway.

Runtime permissions deny tools by default and allow only the project skill, `StructuredOutput` and the connected `research_*` MCP. The gateway enforces the active lease and binds model traffic to its OpenCode session. The three research tools are:

| Tool | Scope |
| --- | --- |
| `task_context` | Current campaign criteria and the current task's assigned companies/sources |
| `search` | Discovery jobs only; public web search with bounded limits |
| `fetch_page` | Research jobs only; assigned company ID, same normalized domain, public HTTP(S) URL and page limit |

The agent cannot use shell/file tools, other tasks, review or export endpoints. The [skill](../runtime-template/agent/.opencode/skills/operations-research/SKILL.md) treats website instructions as untrusted source material. Backend membership, URL, lease and evidence checks enforce the relevant rules even when model output is wrong. Exact quotations establish a source match, not independent truth or perfect relevance.

This is application-level isolation with private container networks and restricted tools, not an operating-system sandbox against a compromised runtime. Origin checks serve the local human UI; they are not multi-user authentication. Public deployment requires a separate security and hosting design.

## Persistence, cancellation and recovery

PostgreSQL owns job eligibility and leases. Claims lock the campaign and use `SKIP LOCKED`; heartbeats extend only active, unexpired leases. Commits require the current lease version and database wall-clock expiry. The common mutation lock order is campaign → job → company.

Temporary provider errors can retry a job up to three attempts with backoff. A malformed or semantically invalid structured response gets one application repair; runtime schema retries are disabled. Model/tool activity can involve several physical provider requests per job, and every dispatched attempt is counted. This does not promise exactly-once external execution.

Planning/discovery checkpoints, stored pages and successful research results survive restarts. Committed company research is immutable under research retry. Cancellation and explicit retry increment lease versions and invalidate old capabilities; late workers cannot overwrite saved state. Retry requeues unfinished work, not completed results. Budget-stopped campaigns require explicit human retry after an authorized mode change.

Source snapshots are immutable once the company result is verified. Before that point, successful source retrieval can populate the snapshot. The URL source cache has a 24-hour lifetime; each snapshot is capped at 24,000 characters. Research cache keys include company/domain, source URLs and content hashes, saved criteria, provider/model and skill version. Cached evidence is rebound to the current company source IDs and validated before saving.

Editing creates a new immutable human draft revision, marks it pending and clears its approval. Review must name the current revision; stale edits/reviews return 409. Research retries cannot replace human drafts. CSV/JSON export joins the approved revision, and CSV cells that could be interpreted as spreadsheet formulas are guarded.

## Accounting

The private gateway reserves each physical model request before forwarding it. Firecrawl calls reserve credits before dispatch. Reservations and the scope totals are updated transactionally; retries and repairs use the same ledger. When enforcement is enabled, a request beyond a cap is rejected before outbound dispatch. Missing or malformed enforcement settings keep caps on; only explicit `BUDGET_LIMITS_ENABLED=false` opts out.

Uncertain delivery retains the reservation. Valid provider token/credit metadata is recorded separately from estimates. The gateway observes fragmented streaming usage while forwarding the original stream bytes. Campaign statistics join receipts through that campaign's jobs, while the shared scope retains global totals. Neither missing credit reports nor rounded subscription percentages mean zero cost. See [the measured live run](verification/uncapped-acceptance.md).

## Human API

The Next.js proxy exposes the following relative routes. Mutations require the configured `Origin`; any Authorization header is rejected by the human API, so an agent credential cannot authorize review. Native development also exposes FastAPI's generated `/docs` on localhost:8000.

| Method and route | Contract |
| --- | --- |
| `GET /api/health` | Runtime readiness, model and enforcement mode |
| `POST /api/campaigns` | `{query, mode}` plus `Idempotency-Key` of 8–120 characters; same key/body returns the original run, conflicting body returns 409 |
| `GET /api/campaigns` | Recent runs, including older history |
| `GET /api/campaigns/{id}` | Campaign, companies, sources, review state, logs, budget and usage readback |
| `GET /api/campaigns/{id}/events` | SSE snapshots on changes and heartbeat comments; closes on terminal state |
| `POST /api/campaigns/{id}/cancel` | Stops unfinished work while retaining saved results |
| `POST /api/campaigns/{id}/retry` | Explicitly requeues unfinished steps |
| `PATCH /api/leads/{id}/draft` | `{subject, body, expected_revision}`; creates the next pending revision |
| `POST /api/leads/{id}/review` | `{revision, decision: "approved" \| "rejected"}` |
| `GET /api/campaigns/{id}/export?format=csv` or `format=json` | Downloads approved revisions; other formats return 422 |

Campaign states are `queued`, `running`, `completed`, `partial`, `cancelled` and `budget_exhausted`. Failures remain visible in campaign errors, company errors and run logs. The frontend restores the selected campaign from browser storage and reads persisted state after reload.

## Verification scope

[Original acceptance](verification/acceptance.md) and [the current uncapped measurement](verification/uncapped-acceptance.md) distinguish actual native/Linux live execution, offline tests, restart evidence and checks not run. [Contributing](../CONTRIBUTING.md) describes reproducible local checks. Remote CI and public deployment are not established by local test success.
