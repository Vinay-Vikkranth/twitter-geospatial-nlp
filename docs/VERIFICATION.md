# Verification record

Prepared November 7, 2026. See the commit history for subsequent changes.

The public sample was freshly executed on Python 3.11 with NumPy 2.2.5, Pandas 3.0.3, scikit-learn 1.7.0 and Matplotlib 3.10.1. Its output image is `docs/assets/demo.png`; machine-readable outputs are generated under ignored `outputs/demo/`. This validates the documented sample entry point, not the entire historical research experiment.

Run locally:

```bash
python scripts/demo.py
python -m unittest discover -s tests -v
```

GitHub Actions repeats those commands on a clean Ubuntu runner. Workflow status must be checked on GitHub rather than inferred from local success. Notebook outputs were cleared for public sharing; historical saved outputs and original data remain in the untouched source folders. ArcGIS exports need a licensed ArcGIS Pro Python environment, and real LLM inference needs approved model access and adequate compute. No model download or archive processing is triggered by the sample or tests.

## Completed publication checks

All 50 preserved research regression tests were freshly rerun successfully in the isolated local workspace with authorized copied inputs and simulated model backends. This is separate from the five public regression tests. Real Llama inference and the full archive remain pending.

The initial uploaded commit passed GitHub Actions on a clean Ubuntu runner. The final commit is checked again after the documentation update. No raw research input is part of either commit.

## ArcGIS README galleries

November 7: two native ArcGIS maps added with project-specific captions, retained basemap attribution and visual inspection. Homelessness reuses the existing paper exports; gun violence and Twitter use newly exported ArcGIS Pro 3.6 layouts from verified source layers. See MAP_PROVENANCE.md for counts, CRS and prototype versus final-study distinctions. No analysis/model code changed.
