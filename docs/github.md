# GitHub publication

The repository is prepared as a source project with documentation, a key-free offline demo and local verification evidence. GitHub hosts the code and documentation; pushing this repository does not deploy the application or expose the local services.

The project is published at [66dplus/ai-operations-agent](https://github.com/66dplus/ai-operations-agent), created on 2026-10-08 as a private repository. Its default branch is `codex/ai-operations-agent-mvp`. The owner's request authorized repository creation and publication; private visibility was the stated default while awaiting an optional preference.

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

## Clone and update

Authenticated users with repository access can clone the project:

```sh
gh repo clone 66dplus/ai-operations-agent
cd ai-operations-agent
```

Follow the root [README](../README.md) for the offline local installation. The README embeds the GIF teaser and links to the full 64.5-second MP4. Both media files are committed with the code. A separate GitHub Pages site is unnecessary for this documentation and has not been configured.

For subsequent authorized updates, inspect the remote and push the current dedicated branch:

```sh
git remote -v
git push origin HEAD
gh run list --workflow ci.yml --limit 3
```

Inspect the **Offline acceptance** Actions run after each push. A local PASS is not evidence that the remote job passed. Keep a failed job visible, diagnose it and fix required checks.

## Before publication

At documentation preparation on 2026-10-08, the local repository had no configured remote. Local runtime source `659669c` had 62 backend tests, 12 desktop/mobile browser cases and a measured Linux live5 pass. Remote GitHub Actions, a new live50 repeat and public server deployment remained **NOT RUN**. See [current acceptance](verification/uncapped-acceptance.md) for exact evidence and [README](../README.md) for installation.

The documentation-only change checked 43 local links/images, syntax in 12 shell examples, and offline/live Compose resolution from `.env.example`. Known Go/Firecrawl credential bytes were absent from 81 candidate worktree files and 98 historical Git blobs. These checks passed without starting services or sending paid requests. Commands and API descriptions were reviewed against their implementations; application tests were not rerun for this documentation-only change. This known-key scan does not claim detection of every possible secret.

## Publication verification

Before the first upload of `8e149b8`, 89 tracked files and 119 historical Git blobs were checked. Known local credential bytes and common GitHub/Firecrawl/model-token/private-key patterns were absent; credentials, runtime data and the owner's Word document were not tracked. This is a scoped publication check, not a guarantee that every possible secret format is detectable.

GitHub's authenticated README HTML API renders the GIF and full-video link. Remote Git blob hashes and sizes match the local README, GIF and 3,381,579-byte MP4. Large MP4 API readback attempts were truncated and a fresh clone timed out through the local network; those helper checks remain FAIL. Authenticated browser inspection remains NOT RUN because both available browser sessions were signed out. Git blob integrity and README rendering are separate successful checks.

The [initial Actions run](https://github.com/66dplus/ai-operations-agent/actions/runs/37766030786) failed before tests because the runner parsed single quotes in `--health-cmd` incorrectly. Double quotes fixed service startup. The [next run](https://github.com/66dplus/ai-operations-agent/actions/runs/37766310650), at `35b08ac`, passed its backend, typecheck/build and browser steps but failed during cache cleanup. Background `uv run` processes retained the shared cache lock. An isolated local probe reproduced the blocked prune and its immediate completion after stopping the owned process.

The workflow now traps shell exit, terminates the known development PID and waits for its process-group cleanup before setup-uv prunes. A focused check confirms that cleanup removes the owned child and preserves both success and a nonzero exit status; all six CI shell blocks parse. Test requirements and application state/authorization behavior are unchanged. The [current Actions result](https://github.com/66dplus/ai-operations-agent/actions/workflows/ci.yml), also shown by the README badge, is the authority for the latest combined commit. Earlier failed runs remain visible.
