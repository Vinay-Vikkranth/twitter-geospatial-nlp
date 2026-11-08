# Project 53 Twitter pipeline

One working project. Two notebooks and one command-line runner call the same tested implementation.

**Current status:** All 3,578 study incidents and 53 boundaries are present. Local extraction and automated software tests have run. Real Llama inference, human label-accuracy validation, Harvard archive coverage and cluster performance still require the Harvard pilot. Passing software tests is not evidence of scientifically accurate labels.

## Start here

1. Open this `Current` folder in VS Code.
2. Use the Python environment in `.venv`, or create a Python 3.11+ environment and install `requirements.txt`. Harvard must install a CUDA-compatible PyTorch build for its GPU.
3. Run `python run.py doctor`, then `python run.py test`.
4. Run `python run.py filter --mode sample` for real extraction on the bundled 1,646-row local sample.
5. Run `python scripts/verify_outputs.py` to print the verified output locations.

The two `.ipynb` files are optional, readable interfaces to these same commands. Restart old notebook kernels after updating the code. Running the filter notebook does not run the model.

## Where to look

| Location | Purpose |
|---|---|
| `run.py` | Single entry point: doctor, test, filter, label, all |
| `pipeline/study.py` | Exact population, timezones, five-day windows, keywords |
| `pipeline/extract.py` | Chunked archive reading, spatial matching, duplicate quarantine, coverage |
| `pipeline/labels.py` | Prompt, ten emotions, six themes, strict validation, model, summaries |
| `pipeline/common.py` | Fingerprints, verified outputs, atomic publication and locking |
| `data/` | Fixed study inputs, boundaries, lookups and separate local sample |
| `tests/` | Automated regression tests, including explicitly simulated model responses |
| `scripts/` | Output verification and editable Harvard Slurm templates |
| `outputs/sample`, `outputs/pilot`, `outputs/production` | Separate run histories; never mix them |
| `../CHANGES.md` | Before/after comparison and implementation history |

Previous versions remain outside this folder in `../Originals`; earlier tests/backups are in `../Archive`. Do not run those copies or include their credentials in a handoff.

## What the pipeline does

1. Verifies the fixed 3,578 incident IDs and attributes against `data/reference_incidents.csv`. Uses explicit historical city assignments and City + State, not city names alone. Validates all 53 WKT polygons and transforms declared NAD83 coordinates to WGS84.
2. Reads tweets in chunks. Treats naive timestamps according to the explicitly chosen timezone, converts to each incident city's local date, then matches t, t-1, t-2, t-3 and t-4. Window days may precede January 2014. No archive filename date prefilter is used, so adjacent UTC dates are not accidentally skipped.
3. Includes boundary-edge points. Applies the supplied keyword list with whole-word/phrase boundaries by default. `--keyword-policy substring` reproduces the previous broad match strategy for sensitivity checks. Neither strategy establishes keyword precision or recall; broad words such as “piece” remain ambiguous and need human review.
4. Keeps a unique tweet table plus all tweet-to-incident/day links. Tweet IDs stay strings to avoid precision loss. Exact duplicates collapse; differing text/time/coordinates for the same ID are quarantined and reported, even when one variant fails keywords. Existing `matched_incident`/`tag` fields are not trusted or copied as new matches.
5. Labels each unique tweet once with the explicitly selected model and resolved immutable revision. A single JSON response supplies emotion, six thematic intensities and an emotion-preserving summary. There is no automatic model fallback, invented neutral label, default confidence or silent text truncation.
6. Produces incident-day summaries, with separate valid/eligible/failed/low-confidence/unlabelled counts. Means and emotion shares use eligible labels only. Tweet-level labeling is independent of which incident it matches; a city/day link does not prove the tweet discusses that incident.

## Local example

```text
python run.py doctor
python run.py test
python run.py filter --mode sample
python scripts/verify_outputs.py --mode sample
python run.py label --mode sample --max-tweets 10
```

The last command requires real model access and adequate resources. `python run.py all --mode sample` runs extraction and then labeling, stopping if model preflight fails. Default `python run.py` is a read-only readiness check, not an accidental full run.

Sample timestamps are assumed UTC for this test; confirm archive semantics with Harvard before production. The sample is not a complete archive and must not be used to infer city-wide zero activity. Sample mode does not silently use a configured production archive.

## Harvard: pilot before production

Supply your approved Hugging Face login privately using `hf auth login` or `HF_TOKEN`. Never paste credentials into notebooks, Slurm scripts, screenshots or the shared ZIP. `harvard_settings.env.example` contains no token; the real `.env` is excluded from the handoff.

```bash
python run.py doctor
python run.py test
python run.py filter --mode pilot --archive /path/to/archive --naive-timezone UTC --max-files 5
python run.py label --mode pilot --max-tweets 100
```

`UTC` is an example to confirm, not evidence of the archive's convention. The five files are a smoke test, not a representative accuracy sample. Review schema, date boundaries, GPS/spatialerror, conflict report, memory, disk and throughput. Select a representative multi-city/multi-year pilot separately. All languages and location types are retained; validate their quality and any desired research exclusions before scaling.

For production, prepare a **verified archive coverage file** and remove pilot limits:

```bash
python run.py filter --mode production --archive /path/to/archive --naive-timezone UTC --coverage /path/to/verified_coverage.csv
python run.py label --mode production
python scripts/verify_outputs.py --mode production --stage LABELS
```

Production rejects local sample inputs and tweet/file limits. The supplied Slurm scripts are templates: Harvard must set its allocation/account/partition and environment. They have not been submitted to Harvard. Extraction uses one process and on-disk SQLite checkpoints, rather than notebook multiprocessing and unbounded in-memory concatenation. It scans and hashes all selected files; plan sufficient local/scratch disk for the full archive identity index and benchmark I/O before production. A restart re-hashes inputs and resumes completed files; an interrupted file is reread from its start.

If compute nodes cannot reach the Hub, download the licensed model to a shared Hugging Face cache on a network-enabled node first. Record the exact 40-character commit SHA. Then run labeling with `--offline-model --revision <that-commit-SHA>` and the same shared cache (HF_HOME). Offline mode refuses `main`/tags and does not query the Hub. It still requires all tokenizer/weights files in the cache and sufficient GPU/RAM; it does not bypass model access or licence requirements.

### Coverage file contract

CSV columns are `utc_date,status`; one unique ISO date per row:

| Status | Meaning |
|---|---|
| `complete` | Harvard confirms all expected files for this UTC day are available; the run also requires successfully read timestamp-date evidence (or filename-date evidence for an empty file) |
| `verified_empty` | Independently confirmed no archived tweets for the entire UTC day; not a substitute for missing files |
| `missing` | Missing/unavailable archive day |

An undeclared date is unknown, not complete. A local calendar day can require two UTC dates. Actual UTC dates read from records are logged in source_files.csv. For empty files only, filename-date evidence recognizes `YYYY-MM-DD` or `YYYY_MM_DD`. If Harvard's naming differs, confirm empty-day evidence separately. Read files alone do not prove completeness. Do not copy a hypothetical coverage template and mark all dates complete. Conflicting tweet IDs prevent complete-coverage status until reviewed. No hardcoded July 2023 cutoff is treated as established archive coverage.

## Outputs and interpretation

Use `scripts/verify_outputs.py` or the `LATEST_*.json` pointers, not the newest-looking CSV. They reject changed inputs, code, relevant package versions, archive inventories, modified output files, failed latest attempts and labels tied to an older extraction.

| File | Contents |
|---|---|
| `tweets.csv` | Unique IDs, UTC timestamps, text, coordinates, language and source/place/location metadata |
| `tweet_incident_matches.csv` | All IDs, incident IDs/dates, assigned city/state, local day, offset/tag |
| `incident_days.csv` | All 17,890 incident-day windows, coverage status and observed matching tweet counts |
| `conflicting_tweets.csv` | Conflicting IDs and original variants, for source review |
| `source_files.csv`, `source_inventory.json` | File hashes, processing counts and inventory |
| `tweet_sources.csv` | Files contributing each retained tweet |
| `tweets_labeled_research.csv` | One labeled row per attempted tweet, status, eligible flag, model/revision and six scores |
| `tweet_incident_labels.csv` | Incident links with label status, emotion, six scores and summary |
| `incident_day_summary.csv` | Coverage, counts, six means and ten separate emotion proportions |
| `qc.json`, `manifest.json` | Quality thresholds, emotion-column mapping, fingerprints and exact run settings |

`observed_match_count=0` alone does **not** mean no tweets existed. `complete_coverage_tweet_count` is populated only for verified complete days. Zero valid labels yields blank means, not six zeros. A real accepted thematic score of zero remains numeric zero.

By default, model-reported confidence below 50 excludes **all** emotion/thematic results for that tweet from summaries, while preserving raw emotion, confidence and summary for inspection. `--confidence-policy flag` explicitly includes them instead. Both exports and aggregates use the same eligibility flag. The default required valid-schema rate is 98%; low-confidence labels are schema-valid but may not be eligible. Neither confidence nor schema success measures actual accuracy. Have humans review stratified outputs and assess category/score reliability before research use.

Emoji sentiment uses the original small lexicon with proper Unicode tokenization. Unknown emojis are unscored, not neutral evidence. The former “emoji confidence” heuristic was removed because it is not a calibrated probability. Lexicon sentiment is not equivalent to the tweet's emotional meaning (e.g. prayer or sarcasm).

### Restart and failure handling

- Configuration, inputs, code, package versions, prompt and resolved model revision determine run identities. Changed inputs produce separate results/checkpoints.
- SQLite commits one extraction file or one label at a time. Truncated JSONL append recovery is no longer needed. Failed model responses are retried on a later invocation; valid matching checkpoints are reused.
- A process lock prevents simultaneous writers per mode. After a hard kill, a lock may remain: **first verify no job/process is active**, then remove only that mode's `RUNNING.lock`. Never delete a running job's lock.
- Malformed/corrupt files, invalid required rows or conflicting timestamp columns fail the extraction and block publication. Check `LAST_EXTRACT_ATTEMPT.json` and the named source file; completed files remain resumable.
- Label QC failure leaves diagnostic exports in that run folder but no new published result. Readers refuse an older success after a failed latest attempt.
- Empty valid input produces typed header-only tweet/label exports and complete window/status tables without loading a model.

## Rebuilding incidents

Harvard can run the prepared input without the Excel workbook. To rebuild deliberately, use `python rebuild_incidents.py --master /path/to/MasterDataALL-mod.xlsx` to validate; add `--write` only after archiving active outputs. The whole master sheet is filtered by actual date and approved city/state. The bundled fixed reference is used for exact ID and attribute reconciliation. Originals remain untouched.

## Boundaries of this handoff

This is the two-stage Harvard extraction/labeling package, plus incident-day summaries. It does not add the older project's ArcGIS/hex-grid or predictive-model stages. Fixed 2024 city boundaries are used for all study years, and historical parenthetical incident assignments are preserved; neither is a claim that municipal boundaries or surrounding suburbs were identical throughout 2014–2023. Review these study-design assumptions with the research team.

The shared ZIP excludes secrets, `.venv`, previous versions, test outputs and run databases. Handle tweet text/IDs according to your archive/data-sharing agreement. Do not call this pipeline production-validated until the cluster pilot, real model outputs and scientific validation are complete.

The ZIP includes the comparison log as `CHANGES.md` alongside this README. References to `../Originals`, `../Archive` and `../CHANGES.md` describe the owner's local workspace; those private historical folders are deliberately not distributed. The packaged code and prepared inputs do not depend on them.

## Implementation references

- [pandas chunked CSV reading](https://pandas.pydata.org/pandas-docs/stable/reference/api/pandas.read_csv.html) and [timezone-aware date parsing](https://pandas.pydata.org/pandas-docs/stable/reference/api/pandas.to_datetime.html).
- [Shapely covers semantics](https://shapely.readthedocs.io/en/2.1.0/reference/shapely.covers.html) for the explicit boundary-edge rule.
- [Unicode emoji tokenization](https://emoji-python.readthedocs.io/en/stable/).
- [Hugging Face chat templates](https://huggingface.co/docs/transformers/v5.20.0/chat_templating) and the [Llama 3.2 model card](https://huggingface.co/meta-llama/Llama-3.2-3B-Instruct).

These references informed implementation behavior; they do not validate this study's model scores or archive coverage.
