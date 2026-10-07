# Resolved dependencies

Lockfiles are authoritative. Metadata was read from installed distributions and npm package manifests on 2026-10-07. These direct dependencies serve concrete product boundaries; no Redis or extra queue framework is used.

| Dependency | Resolved version | License | Purpose / verification |
| --- | --- | --- | --- |
| Next.js | 16.4.0 | MIT | UI and same-origin API proxy; production build and browser flow |
| React / React DOM | 19.3.0 | MIT | Interactive research/review screen; browser flow |
| TypeScript | 5.9.3 | Apache-2.0 | Strict UI types; typecheck/build |
| Inter / @fontsource/inter | 5.3.0 | OFL-1.1 | Locally served Paper font; screenshot inspection |
| FastAPI | 0.142.2 | MIT | Typed human API; origin and request/readback tests |
| Uvicorn | 0.54.0 | BSD-3-Clause | ASGI server; native startup/health |
| HTTPX | 0.28.1 | BSD-3-Clause | External HTTP with explicit timeouts; runtime probe |
| Psycopg | 3.3.6 | LGPL-3.0-only | Real PostgreSQL transactions; concurrency/recovery tests |
| Pydantic | 2.13.5 | MIT | Structured result/evidence contracts; backend tests |
| MCP Python SDK | 2.3.0 | MIT | Scoped agent tools; actual native research and Linux runtime gate passed |
| OpenCode CLI | 1.18.35 | MIT | Isolated headless agent; actual native/Linux streaming/schema and native live50 passed |
| Pytest | 9.1.1 | MIT | PostgreSQL behavior tests |
| pytest-asyncio | 1.4.0 | Apache-2.0 | Async integration tests |
| Playwright | 1.63.0 | Apache-2.0 | Chromium desktop/mobile entry-to-export tests |
| Pillow (optional preview tool) | 12.3.0 | MIT-CMU | Encodes the delivery GIF from verified screenshots; bundled tool runtime, absent from app containers |

Runtime images currently pin Python 3.12.13, Node 24.14.1 and PostgreSQL 16.13. uv 0.10.10 installs the Python lockfile. Docker verifies published image manifests during build; clean-container verification is recorded separately.
