"""Create a clean source/data ZIP; never include credentials or execution outputs."""
from pathlib import Path
import hashlib
import json
import re
import zipfile
ROOT=Path(__file__).resolve().parents[1]
def package(destination):
    allowed_files={'run.py','boundary53.py','verify_boundaries.py','rebuild_incidents.py','requirements.txt',
                   'requirements-tested.txt','README.md','harvard_settings.env.example',
                   'filter_tweets_by_gv_dates.ipynb','gun_violence_tweet_emotion_pipeline.ipynb'}
    files=[p for p in ROOT.iterdir() if p.is_file() and p.name in allowed_files]
    for directory in ['pipeline','tests','scripts','data']:
        files.extend(p for p in (ROOT/directory).rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.suffix not in {'.pyc','.env'})
    change_log=ROOT.parent/'CHANGES.md'
    if not change_log.is_file(): change_log=ROOT/'CHANGES.md'
    for p in [*files,*([change_log] if change_log.is_file() else [])]:
        if p.suffix in {'.py','.md','.txt','.json','.ipynb','.csv','.tsv','.example'}:
            if re.search(r'hf_[A-Za-z0-9]{20,}',p.read_text(encoding='utf-8')):
                raise RuntimeError('Credential-like value found; refusing to package. Inspect locally without sharing it.')
    destination=Path(destination)
    with zipfile.ZipFile(destination,'w',compression=zipfile.ZIP_DEFLATED) as z:
        for p in sorted(files): z.write(p,Path('Project53_Harvard')/p.relative_to(ROOT))
        if change_log.is_file(): z.write(change_log,Path('Project53_Harvard')/'CHANGES.md')
    with zipfile.ZipFile(destination) as z:
        if z.testzip() is not None: raise RuntimeError('ZIP integrity check failed')
        if any('/outputs/' in name or '/.venv/' in name or name.endswith('.env') for name in z.namelist()):
            raise RuntimeError('Unsafe file included')
    print(json.dumps({'zip':str(destination),'files':len(files)+int(change_log.is_file()),'sha256':hashlib.sha256(destination.read_bytes()).hexdigest()},indent=2))

if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser(); parser.add_argument('destination',type=Path)
    package(parser.parse_args().destination)
