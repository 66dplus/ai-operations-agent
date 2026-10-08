# Decision 0001: use OpenCode for MVP research reasoning

Date: 2026-10-08. Status: retain the implemented OpenCode runtime for the local MVP; production provider suitability and an alternative cost benchmark remain open. This records the current implementation and recommendation, not authorization to rewrite the runtime or change providers.

## Context

The owner selected OpenCode with a project skill because it already provides an agent runtime. The product has a defined workflow: interpret a request, discover companies, collect evidence, qualify and draft, then let a human review and export. The question is whether reusing a coding-agent runtime is sound engineering or whether to build a custom agent.

OpenCode officially supports a headless HTTP server, session/message APIs and programmatic clients ([server documentation](https://opencode.ai/docs/server/)). Using its CLI as an internal runtime is therefore a supported integration mechanism. Its general tool permissions need explicit configuration; their defaults are not the application's authorization policy ([permissions documentation](https://opencode.ai/docs/permissions/)).

The existing application already implements the parts that a skill cannot supply: durable tasks, checkpoints, fenced leases, evidence validation, accounting, draft revision control and human approval. Reusing OpenCode saves model/tool-loop and session integration work; it does not eliminate backend engineering.

## Decision

Keep the pinned, isolated OpenCode runtime for the current local MVP. Preserve the backend as owner of product state and rules. Do not build a universal autonomous agent merely to replace a working runtime.

If the workflow remains fixed, the next useful comparison is a bounded backend pipeline with direct structured model calls. The backend would choose when to search/fetch and supply saved pages to plan/discovery/research calls. This is smaller than building a general agent and offers explicit control over context and call counts. Adopt it only after an equivalent quality, failure and cost benchmark.

| Option | Useful here because | Tradeoff / decision |
| --- | --- | --- |
| OpenCode + scoped MCP + skill | Working tool loop, sessions, provider integration and native structured output; adaptable research | Runtime startup/context/tool-step costs and version coupling. Retain for MVP. |
| Bounded backend + direct model calls | Known stages, existing durable state and validators; explicit context and requests | Need provider transport and limited step/repair logic. Best alternative to benchmark for a stable product workflow. |
| General custom agent | Could support substantially more open-ended actions or specialized agent behavior | Need to own tool loop, history, permissions, structured output and runtime failures. No current requirement justifies this scope. |

## What the measurement proves

The real Linux five-company run produced five qualified companies, nine saved sources and 19 validated quotations. The gateway recorded 13 model HTTP requests and 189,439 provider-reported tokens:

| Stage | Physical model requests | Input tokens | Output tokens | Total tokens |
| --- | ---: | ---: | ---: | ---: |
| Plan | 4 | 6,205 | 1,138 | 7,343 |
| Discovery | 4 | 18,562 | 1,911 | 20,473 |
| Research | 5 | 146,865 | 14,758 | 161,623 |
| Total | 13 | 171,632 | 17,807 | 189,439 |

Source: [run report](../verification/uncapped-acceptance.md) and [request receipts](../verification/uncapped-live.json), campaign `c0f7106e-dc6b-431a-b577-15bbb83a6131`, runtime source `659669c`.

Most tokens were in research. This identifies where to inspect source/context volume and repeated tool exchanges. It does not prove that all those tokens are OpenCode overhead, that a direct pipeline would be cheaper at equal quality, or that reported tokens equal a dollar invoice. A baseline with the same evidence and output requirements has not been run.

## Runtime and subscription are separate decisions

OpenCode is the runtime. OpenCode Go is the selected model service. The official [Go documentation](https://opencode.ai/docs/go/) describes support for OpenCode and other coding agents generating similar request types, and asks clients to send typical coding-agent traffic. Company prospect research is a different workload.

The local tests establish that this integration works technically. They do not establish that Go is an appropriate subscription for a production research service. Before using it for that purpose, confirm this workload with the provider or use a regular API service that supports the intended application. Replacing OpenCode with a custom agent while continuing to use the same Go service would leave this provider question unchanged.

The documented Go usage windows and paid-balance fallback are also separate from application caps. The owner confirmed **Use balance OFF** before existing live work. The temporary local uncapped mode removes internal admission gates only; it neither removes provider quotas nor authorizes top-ups or paid fallback. No provider change is implemented by this decision.

## Implementation boundary and limitations

`worker.run_job` delegates live work to `agent.run_live_job`. The adapter creates a disposable runtime per attempt, checks its effective MCP/configuration, posts native JSON Schema messages, validates results and performs one semantic repair. PostgreSQL remains the checkpoint and review owner.

A replacement can retain the UI, human API, migrations, job leases, saved evidence, validators, caches, reviews and export. It would replace reasoning/transport inside that live execution boundary. The current `AI_PROVIDER` and `AI_MODEL` settings do not make the integration provider-agnostic: the gateway's upstream endpoint and credential format are Go-specific and also need a transport adapter for a different provider.

Current material limitations are the process/session startup per job attempt, runtime API/version coupling, variable model/tool exchanges and context size. These are reasons to measure and keep the adapter bounded, not evidence that the whole application should be rewritten.

## Next comparison, not yet executed

Use the same accepted requests, companies, saved pages, model where permitted, schemas and validation rules. Compare cold and warm cache cases separately. Record:

- Exact evidence validity, useful qualification and drafts faithful to the user's offering.
- Missing-company behavior, invalid-output repair, timeout/retry and rejected tool access.
- Physical requests including retries, reported input/output tokens, cache metadata when available and provider account usage.
- End-to-end wall time and engineering complexity.
- Identical approval/export behavior through the unchanged backend.

One direct model call per batch is not an acceptance criterion if it loses evidence or result quality. A cheaper approach must still meet the product requirements. Benchmark status: **NOT RUN**. The recommendation is to keep the current MVP and benchmark a bounded alternative when predictable production cost becomes the next objective.
