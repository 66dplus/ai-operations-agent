# Recorded product demonstration

Recorded on 2026-10-08 through Computer Use in the actual local application. Product runtime source: `659669c`; the repository at recording start was `b4e562f` with documentation-only changes since that runtime version. This replaces the previous three-still GIF with an edited walkthrough. Product behavior and provider configuration were not changed.

## Assets

| File | Use |
| --- | --- |
| [demo.mp4](demo.mp4) | Full 64.5-second video, 1920×1080, 30fps, H.264/yuv420p, faststart, silent; 3,381,579 bytes |
| [demo.gif](demo.gif) | 12-second, 960×540 looping README teaser from the MP4 |
| [demo-poster.jpg](demo-poster.jpg) | Preview image showing the company review panel |
| [demo-preview.html](demo-preview.html) | Local video player with chapter navigation and MP4 download |

The README embeds the GIF and links to the MP4. These are static files suitable for repository publication; they do not require a hosted research API. The selected GitHub repository and remote rendering/publication remain pending. GitHub's native attachment player can also be used by uploading the MP4 when editing the eventual README.

The previous [live still-image GIF](demo-live-stills.gif) is preserved for the historical acceptance report. Current media checks are recorded in [demo-verification.json](demo-verification.json).

## Actual recorded flow

The query was:

> Find 50 European robotics companies. I offer simulation testing tools for robotics teams.

The operator typed through the browser UI, started **Demo dataset**, watched progress, opened Lumen Machines, expanded its saved source text, replaced the introduction, approved revision 2, filtered approved results, downloaded CSV and reloaded the campaign.

The data is explicitly synthetic in both the application and a persistent video badge. The offline fixture returns its sample companies; it does not perform a new web search for this request. The recorded output was 50 processed / 40 qualified / 1 approved, with one exact saved draft in the exported CSV.

Capture used a task-owned empty PostgreSQL database and localhost-only native processes. `LIVE_ENABLED`, `GO_BALANCE_DISABLED` and `RUNTIME_VERIFIED` were false; no provider credentials or gateway were supplied. The recording database had **0 provider requests** after the flow. Existing native/container live data, approvals and shared infrastructure were not altered.

The source material is 332 actual browser screenshots, including real intermediate typing and processing states. The editor changes timing and adds camera movement, captions, chapter indicators, cursor/click annotations and a downloaded-file callout. It does not regenerate product UI or invent results. Processing is accelerated and labeled; this video is not a latency benchmark. English captions match the shipped English UI. No external music or voice assets are included.

## Verification

| Criterion | Observed | Status |
| --- | --- | --- |
| Ordinary user flow | Request → 50 results → saved source → edit → approval → real CSV download → restored approval | PASS |
| Export readback | One Lumen Machines row, approved revision 2, exact human-edited body | PASS |
| Paid dispatch | Health reports live unavailable; recording database provider receipts count 0 | PASS |
| Video structure and decoding | 64.5 seconds, 1920×1080, 30fps H.264; full FFmpeg decode succeeds | PASS |
| Browser playback | In-app browser decodes the MP4, plays and seeks chapters with no media error | PASS |
| Visual review | Title/end cards, typing, results, evidence, editing, approval and export frames inspected | PASS |
| GitHub rendering/publication | Repository destination not yet selected | NOT RUN |

Backend behavior tests and live-provider gates were not repeated for this media-only change; prior results remain in the dated acceptance reports. The recording is a new offline user-flow check, not another live acceptance run.

## Local preview and editing

Open the MP4 in a video player, or start the byte-range-capable preview server using existing backend dependencies:

```sh
cd backend
uv run uvicorn preview_demo:app --app-dir ../scripts --host 127.0.0.1 --port 3111
```

Open http://localhost:3111/demo-preview.html. The helper serves static verification assets and has no research API. Stop it with Ctrl+C.

[render_demo.py](../../scripts/render_demo.py) accepts a capture folder containing `capture.json` and `frames/*.jpg`, recorded through Computer Use. Raw captures and the recording database are kept outside Git. To rerender on the recording host:

```sh
python3 scripts/render_demo.py --captures /path/to/capture-folder --output docs/verification/demo.mp4
python3 scripts/demo_gif.py
```

Editing was checked on macOS with Python 3.12+, Pillow 12.3.0 with WOFF2 support, FFmpeg 9.0.1 with libx264 and the existing frontend Inter font package (`npm ci` in `frontend`). The optional tools and licenses are recorded in [dependencies](../dependencies.md). `--stills /path/to/previews` renders chapter samples for visual review instead of encoding the full video. This editor targets the named stages of this recording; a new scenario must update the storyboard and preview/teaser times together. The shipped final video does not depend on those editing tools to play.
