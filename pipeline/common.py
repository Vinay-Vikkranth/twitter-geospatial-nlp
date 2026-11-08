"""Run identity, exclusive execution, verified publication, disk-backed state."""
import contextlib
import csv
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import sys
import importlib.metadata
from datetime import datetime, timezone
ROOT = Path(__file__).resolve().parent.parent

def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''): h.update(block)
    return h.hexdigest()

def identity(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,default=str,allow_nan=False).encode()).hexdigest()

def atomic_json(path, value):
    path=Path(path); path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_name(path.name+'.tmp')
    with tmp.open('w',encoding='utf-8') as f:
        json.dump(value,f,indent=2,ensure_ascii=False,allow_nan=False,default=str)
        f.flush(); os.fsync(f.fileno())
    os.replace(tmp,path)

def code_hash():
    paths=[*sorted((ROOT/'pipeline').glob('*.py')),ROOT/'boundary53.py',ROOT/'rebuild_incidents.py',ROOT/'run.py',ROOT/'requirements.txt']
    versions={name:importlib.metadata.version(name) for name in ['pandas','numpy','shapely','pyproj','emoji','tzdata','transformers','torch']}
    return identity({'files':{str(p.relative_to(ROOT)):sha(p) for p in paths},'packages':versions,'python':sys.version})

def data_hash():
    paths=[ROOT/'data/latLong.csv',ROOT/'data/reference_incidents.csv',ROOT/'data/city_registry_53.csv',ROOT/'data/incident_city_aliases.csv',ROOT/'data/city_timezones.json',ROOT/'data/emoji_lexicon.json',ROOT/'data/Twitter_GunViolence_Keywords_List.xlsx - Sheet1.csv',*sorted((ROOT/'data/cities boundary').glob('*.csv'))]
    return identity({str(p.relative_to(ROOT)):sha(p) for p in paths})

@contextlib.contextmanager
def lock(root):
    root=Path(root); root.mkdir(parents=True,exist_ok=True)
    path=root/'RUNNING.lock'
    try: fd=os.open(path,os.O_CREAT|os.O_EXCL|os.O_WRONLY)
    except FileExistsError: raise RuntimeError(f'Another run or interrupted run holds {path}. Verify no process is running before removing that lock.')
    try:
        os.write(fd,json.dumps({'pid':os.getpid(),'started':datetime.now(timezone.utc).isoformat()}).encode())
        os.close(fd); yield
    finally: path.unlink(missing_ok=True)

def connect(path):
    db=sqlite3.connect(path)
    db.execute('PRAGMA foreign_keys=ON')
    db.execute('PRAGMA journal_mode=WAL')
    db.execute('PRAGMA synchronous=FULL')
    return db

def export_query(db,query,path,params=()):
    path=Path(path); tmp=path.with_name(path.name+'.tmp')
    cursor=db.execute(query,params)
    with tmp.open('w',encoding='utf-8',newline='') as f:
        writer=csv.writer(f); writer.writerow([c[0] for c in cursor.description])
        for rows in iter(lambda:cursor.fetchmany(10000),[]): writer.writerows(rows)
    os.replace(tmp,path)

def publish(root,stage,run,outputs,info):
    manifest={**info,'status':'complete','run_id':run.name,'code_hash':code_hash(),'data_hash':data_hash(),
              'python':sys.version,'finished_utc':datetime.now(timezone.utc).isoformat(),
              'files':{p.name:sha(p) for p in outputs}}
    atomic_json(run/'manifest.json',manifest)
    atomic_json(root/f'LATEST_{stage}.json',{'run':str(run.resolve()),'manifest_hash':sha(run/'manifest.json')})
    atomic_json(root/f'LAST_{stage}_ATTEMPT.json',{'status':'complete','run_id':run.name})
    return manifest

def latest(root,stage):
    root=Path(root)
    attempt=json.loads((root/f'LAST_{stage}_ATTEMPT.json').read_text())
    if attempt['status']!='complete': raise RuntimeError(f'Latest {stage} attempt did not complete; refusing stale output.')
    pointer=json.loads((root/f'LATEST_{stage}.json').read_text())
    run=Path(pointer['run'])
    if sha(run/'manifest.json')!=pointer['manifest_hash']: raise RuntimeError('Manifest changed.')
    manifest=json.loads((run/'manifest.json').read_text())
    if manifest['code_hash']!=code_hash() or manifest['data_hash']!=data_hash():
        raise RuntimeError('Code or study inputs changed. Rerun extraction and labeling.')
    for name,digest in manifest['files'].items():
        if sha(run/name)!=digest: raise RuntimeError(f'Published file modified: {name}')
    for source in manifest.get('sources',[]):
        if not Path(source['path']).is_file() or sha(source['path'])!=source['sha256']:
            raise RuntimeError('Tweet source changed or disappeared. Rerun extraction.')
    archive=manifest.get('config',{}).get('source')
    if archive and Path(archive).is_dir():
        current=sorted(str(p.resolve()) for p in Path(archive).rglob('*.csv.gz'))
        limit=manifest['config'].get('max_files')
        expected=[s['path'] for s in manifest['sources'] if s['path'].endswith('.csv.gz')]
        if len(current)!=manifest['config']['total_discovered_files'] or (current[:limit] if limit else current)!=expected:
            raise RuntimeError('Archive inventory changed. Rerun extraction.')
    if stage=='LABELS':
        upstream,upstream_manifest=latest(root,'EXTRACT')
        if manifest.get('extract_manifest_sha256')!=sha(upstream/'manifest.json'):
            raise RuntimeError('Labels belong to an older extraction. Rerun labeling.')
    return run,manifest
