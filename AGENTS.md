# Project Working Agreement

Read docs/product.md before behavior changes. The approved reference is the supplied AI Operations Agent MVP specification plus the owner's accepted plan and Paper design linked there.

Keep the single prompt entry point and all research, evidence, review and approved-export behavior. Python owns persisted state, validation, permissions and cost budgets; OpenCode owns research reasoning. Agents must never approve drafts or reach user review endpoints. Reviews refer to immutable draft revisions.

Required checks: Python pytest against real PostgreSQL; frontend typecheck/build; browser end-to-end workflow; isolated OpenCode permission/structured-output probe. Live acceptance requires 50 evidence-backed companies within the task-wide cap of 250 Firecrawl credits and 100 actual DeepSeek requests. Never enable paid fallback or lower acceptance to hide a failure. Use the FULL route for queue, budget, lease or approval boundaries and an independent read-only review.

Do not change shared databases, global agent configuration or other sessions' services. Runtime credentials/data are ignored. Read README for the supported commands. Keep maintained project instructions and role prompts in English.
