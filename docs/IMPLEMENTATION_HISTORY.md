# Archived implementation history

Paths below refer to the original private research layout, not files distributed by this public repository.

# Pipeline changes — simple summary

**Updated: October 23, 2026**

This summarizes changes to Avantika's Harvard pipeline, including corrections made during our review. **Local software tests passed; the full Harvard run and real AI labeling still need testing.**

## What changed?

| Area | Before | Current version |
|---|---|---|
| **City boundaries** | Only 31 study cities, plus 5 extras | All **53 required cities**; checks reject missing, extra or invalid boundaries. City/state matching and explicit coordinate conversion prevent location mix-ups. |
| **Incident records** | Supplied input omitted 9 required incidents and had no IDs | Rebuilt from the full master workbook: **3,578 unique study incidents**, checked against the project reference. |
| **Neighborhood names** | Our initial strict filter excluded 83 records such as Chicago (Englewood) | Restored the project's approved city assignments while keeping state checks. |
| **Dates and incident links** | Calendar dates could put tweets on the wrong day; incident links were unclear | Uses city-local dates and **T0 through T0−4**. Keeps tweet IDs and links each tweet to every matching incident. |
| **Keywords and duplicates** | Substring matches could select unrelated words; conflicting duplicates could be silently kept | Matches whole words/phrases, removes exact repetition and sets conflicting tweet IDs aside for review. |
| **Missing or bad data** | Missing archive data or failed processing could look like empty results | Validates inputs, blocks partial results from failed runs, and separates missing coverage from verified zeros. |
| **AI labels** | Invalid responses could become neutral/zero; confidence handling was inconsistent | Validates responses; keeps **10 emotion categories separate from 6 thematic scores**. Consistently excludes confidence below 50 by default and reports valid, failed and excluded counts. |
| **Empty inputs and emojis** | Empty labeling input could crash; unknown emojis could be misrepresented | Produces structured empty outputs without loading the model. Counts known and unknown emojis separately. |
| **Safe restarts** | Old checkpoints/results could be reused after inputs changed | Checks inputs, code, settings and model version before reuse; safely saves progress and prevents competing runs. |
| **Running and sharing** | Large notebook implementations; limited automated checks | Shared code behind both notebooks, chunked processing, 50 automated tests, readiness checks and a handoff ZIP excluding credentials. |

## What was tested?

- **50 automated tests passed.**
- **53 cities, 3,578 unique incidents and 17,890 incident-day windows** verified.
- The supplied **1,646-row sample** produced **303 unique tweets and 303 incident links**.
- Extraction restarted successfully. The unpacked handoff package produced the same sample results on this computer.

**Why did 316 unique tweets become 303?**  
46 failed the corrected keyword matching, 1 had conflicting text, and 34 were added after correcting local dates: **316 − 46 − 1 + 34 = 303**. Two conflicting IDs exist in the full sample; only one was previously selected.

## What is still pending?

1. **Real AI labeling:** This computer had insufficient available memory and no CUDA GPU. The model did not run, and no real emotion/thematic results were produced here.
2. **Harvard archive checks:** Confirm its format, timezone and available dates. Missing days must not count as zero tweets.
3. **Research review:** Check label quality, keywords, confidence threshold, revised labeling prompt, historical city assignments and use of fixed 2024 boundaries.
4. **Harvard pilot:** Test a small real dataset for accuracy, runtime, disk use and restarts before the full run. Local tests do not establish cluster performance.

## Where to look

- Current (original path: Current/) — the only working pipeline.
- Sample results (original path: Current/outputs/sample/RESULTS.md) — actual outputs and run status.
- Instructions (original path: Current/README.md) — how to run and verify it.
- Originals (original path: Originals/) — supplied versions, unchanged.
- Detailed history (original path: Archive/Change_04_Full_Review/CHANGES_detailed_2026-10-23.md) — preserved investigations and file-level changes; optional reading.

**For future changes:** Update the relevant row and test status here; keep detailed evidence in `Archive`. This rewrite changes documentation only, not pipeline behavior.
