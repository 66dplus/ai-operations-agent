# GitHub publication

The repository is prepared as a source project with documentation, a key-free offline demo and local verification evidence. GitHub hosts the code and documentation; pushing this repository does not deploy the application or expose the local services.

## Included

- Next.js frontend, FastAPI backend, PostgreSQL migrations and worker.
- Pinned runtime/lockfiles, scoped research skill, Dockerfiles and Compose definitions.
- `.env.example` with offline, capped defaults.
- README, setup, architecture, runtime decision, contribution guide and dependency record.
- Approved Paper reference, recorded MP4/GIF demo, screenshots and dated acceptance/usage records.
- Offline GitHub Actions workflow using PostgreSQL and Chromium; no paid-provider secrets required.

The repository has no selected distribution license. Choosing to publish source does not itself choose an open-source license. Decide the project's license before presenting it as open source; dependency licenses are already recorded separately in [dependencies](dependencies.md).

## Publication review

Inspect both the current tree and committed history. Confirm that no `.env`, keys, credential files, database/agent state or private logs are tracked. The [contribution guide](../CONTRIBUTING.md) lists relevant checks. Keep the shipped defaults offline/capped; the owner's ignored local uncapped setting is not a publication default.

Useful local checks:

```sh
git status --short
git diff --check
git ls-files
git check-ignore .env runtime/credentials/go.json runtime/credentials/firecrawl.json
git remote -v
```

These commands show tracked/ignored paths, not a complete secret audit. Check file contents and history without printing secret values. Review screenshots/GIFs and acceptance metadata as material that will become visible at the selected repository visibility. Do not attach the owner's original Word document or credentials automatically.

## Upload to the chosen repository

Select an existing repository URL, or a new repository name and **private/public** visibility. Create a new destination empty, without an auto-generated README or unrelated history. After that destination and publication are authorized, add the real URL from the repository root:

```sh
git remote add origin https://github.com/OWNER/REPOSITORY.git
git push -u origin HEAD
```

`OWNER/REPOSITORY` is a placeholder; do not run it literally. If `origin` already exists, inspect it rather than overwriting another destination. This uploads the current dedicated branch (`codex/ai-operations-agent-mvp` at documentation preparation time); it does not merge or rewrite another branch. For an existing repository with unrelated code, choose the appropriate integration path rather than force-pushing.

For a new repository, choose its default branch in GitHub after the first push if needed. The root README renders on GitHub, including Mermaid and relative documentation/media links. A separate GitHub Pages site is unnecessary for this documentation and has not been configured.

After pushing, inspect the **Offline acceptance** Actions run. A local PASS is not evidence that the remote job passed. Keep a failed job visible, diagnose it and fix required checks. Add a repository-specific CI badge only after the actual URL and workflow status are known.

## Prepared state

At documentation preparation on 2026-10-08, the local repository had no configured remote. Local runtime source `659669c` had 62 backend tests, 12 desktop/mobile browser cases and a measured Linux live5 pass. Remote GitHub Actions, a new live50 repeat and public server deployment remained **NOT RUN**. See [current acceptance](verification/uncapped-acceptance.md) for exact evidence and [README](../README.md) for installation.

The documentation-only change checked 43 local links/images, syntax in 12 shell examples, and offline/live Compose resolution from `.env.example`. Known Go/Firecrawl credential bytes were absent from 81 candidate worktree files and 98 historical Git blobs. These checks passed without starting services or sending paid requests. Commands and API descriptions were reviewed against their implementations; application tests were not rerun for this documentation-only change. This known-key scan does not claim detection of every possible secret.
