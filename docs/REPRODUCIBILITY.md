# Public and research execution

## Public clone

Install requirements.txt, run scripts/demo.py, then unittest discover under tests. All inputs are synthetic and self-contained. No network inference occurs.

## Authorized research execution

The Desktop copy retains ignored data/private inputs. Run scripts/prepare_research.py to build outputs/research_workspace with the original expected data layout, then install requirements-research.txt in an isolated research environment. This deliberately keeps the full CLI separate from the public sample.

```bash
python scripts/prepare_research.py
cd outputs/research_workspace
python run.py doctor
python -m unittest discover -s research/tests -v
python run.py filter --mode sample
```

The private historical sample is available only in the local Desktop copy. A GitHub clone must supply authorized inputs first. Expected data includes latLong.csv, reference_incidents.csv, city_registry_53.csv, incident_city_aliases.csv, city_timezones.json, the keyword CSV, emoji_lexicon.json and all boundary WKT CSVs. The fixed population validation intentionally rejects a mismatched replacement dataset.

For labeling, follow RESEARCH_WORKFLOW.md: privately set HF_TOKEN or sign into Hugging Face, obtain model permission, record an immutable revision and confirm resources. No real GPU/model run is claimed by this packaging. For production extraction, confirm timestamp semantics and independently verified daily archive coverage. Do not turn an unknown or incomplete archive day into a zero count. Full production must not use the public synthetic example.

The original detailed operational guide predates public packaging; its bundled-real-sample commands refer to the authorized workspace, not a public clone. Historical code and results remain separate from the new seven-row demo.
