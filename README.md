# Yorisoi 寄り添い

**An AI copilot that helps care workers write individual evacuation plans for people who cannot evacuate on their own.**

Japan requires every municipality to keep a register of residents who need help evacuating and to *endeavour* to make each
of them an individual evacuation plan (個別避難計画). On 1 April 2026, 1,014,017 of 6,696,718 registered people had one
(15.1%), according to the [Cabinet Office and FDMA survey](https://www.fdma.go.jp/mission/prepare/assistant/items/assistant002_tyousa1_260401.pdf).
Every plan is written by hand: a conversation, a hazard check of the home, a suitable shelter, a route and named helpers.

Yorisoi does the slow parts and keeps a person in charge:

1. **Hazard brief:** reads the flood depth at the home from the national hazard-map tiles, finds shelters certified for floods, and checks the path.
2. **Conversation:** recorded audio (Gemini transcribes it) or a typed transcript.
3. **Draft:** Gemini extracts facts *with the exact words that support them* (code drops any quote not found in the transcript), then drafts the plan in the fields of the Cabinet Office sample form, citing evidence for every line.
4. **Checks:** safety rules in code (shelter certified for the hazard, two helpers with phone numbers, power for medical devices, consent, transport…) plus a Gemini review that can only add notes.
5. **Copies and approval:** easy-read Japanese (やさしい日本語), a helper card and a translation; the care worker confirms with the resident, a supervisor approves (blocked while a must-fix check remains), and the plan is stamped.

**Links:** [demo video (3:00)](https://github.com/nityam02/yorisoi/releases/download/v1.0/yorisoi-demo.mp4) ·
live prototype: Cloud Run URL added at deployment · pitch deck built from the organiser's template by [`tools/deck`](tools/deck).

> **All residents and interviews in this repository are fictional.** Coordinates are district centre points, not homes.
> Hazard and shelter data are real public data. Outputs are drafts that require human approval.

## Run locally

Requirements: Python 3.12 with [uv](https://docs.astral.sh/uv/), Node 22.

```bash
cp .env.example .env            # add GEMINI_API_KEY
cd apps/web && npm install && npm run build && cd ../..
cd services/api && uv sync && uv run uvicorn app.main:app --port 8080
# open http://localhost:8080
```

For frontend work, run `npm run dev` in `apps/web` (it proxies `/api` to port 8080).

Tests (no network, no Gemini): `cd services/api && uv run pytest`

## Deploy to Cloud Run

```bash
PROJECT=your-gcp-project ./infra/deploy.sh               # Gemini API key from .env → Secret Manager
PROJECT=your-gcp-project USE_VERTEX=1 ./infra/deploy.sh  # or Vertex AI billed to the project
```

The script enables the APIs, creates a Firestore database in `asia-northeast1`, and deploys one Cloud Run service that
serves the API at `/api` and the web app at `/`. Free-tier Gemini keys have small daily quotas; use a billed key or
Vertex AI for anything people will test.

## How it is built

| Part | What it does | Where |
| --- | --- | --- |
| Hazard tools | Flood depth from the pixel colour of the Hazard Map Portal tile (legend verified against live tiles); GSI designated emergency evacuation sites by hazard type; GSI address search; Google Routes API walking route when `MAPS_API_KEY` is set, otherwise straight-line distance (labelled as such) | `services/api/app/tools` |
| Extractor | Gemini structured output; every fact, person and need carries a verbatim quote that code verifies | `app/agents/extractor.py` |
| Planner | Gemini drafts the reasoning fields and must cite evidence ids; the shelter can only come from the tool's list; factual fields are filled by code | `app/agents/planner.py` |
| Critic | Deterministic safety rules on every save; optional Gemini review that adds notes only | `app/agents/critic.py` |
| Rewriter | Easy-read Japanese, helper card, translation | `app/agents/rewriter.py` |
| Models | `gemini-3.5-flash` by default, falling back to `gemini-3.1-flash-lite` and `gemini-2.5-flash` on overload or quota limits; the model that actually answered is recorded on each plan | `app/llm.py` |
| Web app | React + Vite, tablet-first; map with GSI tiles via Leaflet | `apps/web` |
| Storage | JSON files locally; Firestore on Cloud Run | `app/store.py` |

Not built yet: a live (streaming) interview copilot using the Gemini Live API, landslide and tsunami layers, and an
Agent Development Kit wrapper around the agents.

## Evaluation

`eval/run_eval.py` scores extraction on the three sample interviews against hand-written answers. See
[`eval/RESULTS.md`](eval/RESULTS.md); treat it as a smoke test, not a benchmark.

## Demo video

`tools/demo` rebuilds the demo video from the running app: `tts.py` (Gemini TTS narration), `record.mjs` (Playwright),
`cards.mjs` (title cards), `build.py` (ffmpeg assembly with captions).

## Data sources and attribution

- Flood depth: ハザードマップポータルサイト（国土交通省）, 洪水浸水想定区域（想定最大規模） — [open data terms](https://disaportal.gsi.go.jp/hazardmapportal/hazardmap/copyright/opendata.html)
- Shelters: 国土地理院 指定緊急避難場所データ — [GSI](https://www.gsi.go.jp/bousaichiri/hinanbasho.html)
- Base map: 地理院タイル — [GSI](https://maps.gsi.go.jp/development/ichiran.html)
- Plan fields: Cabinet Office, 避難行動要支援者の避難行動支援に関する取組指針（様式例）

Built for the Google Cloud AI Builder Cup 2026 (Sustainability and Social Impact). License: to be decided by the team.
