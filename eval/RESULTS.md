# Evaluation results

Extraction of the three fictional sample interviews (`services/api/app/data/interviews`) against hand-written
answers (`ground_truth.json`). Run with `cd services/api && uv run python ../../eval/run_eval.py <runs>`.

**Read these as a smoke test, not a benchmark:** 3 interviews written by the team, small n, and on 2026-10-10 the
answering model was the fallback `gemini-3.1-flash-lite` because the free-tier daily quota for `gemini-3.5-flash`
was used up. Re-run on the production model before quoting numbers.

| Date | Model | Runs | People found | Phones right | Needs found | Key facts | Consent right | Dropped (no verbatim quote) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 2026-10-10 | gemini-3.1-flash-lite | 2 | 14/14 | 14/14 | 4/6 | 38/40 | 4/6 | 4 of 71 |
| 2026-10-10, after multi-sentence quote fix | gemini-3.1-flash-lite | 1 | 7/7 | 7/7 | 3/3 | 20/20 | 3/3 | 0 of 36 |

The two consent misses in the first row were safe failures: the model's quote spanned two speakers and did not match
the transcript verbatim, so consent was set to "unclear", which blocks approval until a person confirms it.

Deterministic safety rules are covered by unit tests (`services/api/tests`), not by this script.

## Still to do (see the plan in the proposal doc)

- Hazard check: compare `flood_depth()` with a manual reading of https://disaportal.gsi.go.jp for 30 addresses.
- Planted-error test for the Gemini review (contradictions the rules cannot see).
- Timed role-play: minutes to an approved plan, manual vs. Yorisoi.
