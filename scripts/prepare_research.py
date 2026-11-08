from pathlib import Path
import shutil
ROOT=Path(__file__).resolve().parents[1]
source=ROOT/'data/private';target=ROOT/'outputs/research_workspace'
files=[p for p in source.rglob('*') if p.is_file()]
if not files:raise SystemExit('Authorized research data is not bundled in GitHub. See docs/REPRODUCIBILITY.md.')
target.mkdir(parents=True,exist_ok=True)
kind='twitter-geospatial-nlp'
for p in files:
    rel=p.relative_to(source)
    if kind=='gun-violence-geospatial-ml':dest=target/rel
    elif kind=='homelessness-spatial-modeling' and rel.parts[0] in ['recorded_outputs','arcgis_evidence']:
        dest=target/('outputs' if rel.parts[0]=='recorded_outputs' else 'Paper/ArcGIS_Figures')/Path(*rel.parts[1:])
    else:dest=target/'data'/rel
    dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,dest)
for p in (ROOT/'research').glob('*.ipynb'):shutil.copy2(p,target/p.name)
if kind=='gun-violence-geospatial-ml':
    shutil.copytree(ROOT/'digital_twin',target/'digital_twin',dirs_exist_ok=True,ignore=shutil.ignore_patterns('__pycache__','artifacts'))
    shutil.copy2(ROOT/'research/run_kfold.py',target/'run_kfold.py')
if kind=='twitter-geospatial-nlp':
    for directory in ['pipeline','scripts','research/tests']:
        shutil.copytree(ROOT/directory,target/directory,dirs_exist_ok=True,ignore=shutil.ignore_patterns('__pycache__'))
    for p in ROOT.glob('*.py'):shutil.copy2(p,target/p.name)
    shutil.copy2(ROOT/'requirements-research.txt',target/'requirements.txt')
print('Prepared isolated authorized workspace:',target)
