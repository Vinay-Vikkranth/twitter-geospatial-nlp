#!/usr/bin/env python3
"""Single supported entry point. See README.md before running production."""
import argparse
import importlib.metadata
import json
import os
from pathlib import Path
import sys
from pipeline.common import ROOT

def load_settings():
    path=ROOT/'harvard_settings.env'
    if not path.exists(): return
    allowed={'HF_TOKEN','GV_RAW_TWEETS_DIR','TWEETS_PATH'}
    for line in path.read_text(encoding='utf-8').splitlines():
        if line.lstrip().startswith('#') or '=' not in line: continue
        key,value=line.split('=',1); key=key.strip(); value=value.strip().strip('"').strip("'")
        if key in allowed and value: os.environ.setdefault(key,value)

def doctor():
    import psutil
    import torch
    from pipeline.study import load_study
    registry,polygons,tz,windows=load_study()
    result={'study_incidents':len(windows)//5,'cities':len(registry),'incident_days':len(windows),
            'cuda_available':torch.cuda.is_available(),'available_ram_gib':round(psutil.virtual_memory().available/1024**3,2),
            'hf_token_in_environment':bool(os.environ.get('HF_TOKEN')),
            'archive_configured':bool(os.environ.get('GV_RAW_TWEETS_DIR')),
            'packages':{p:importlib.metadata.version(p) for p in ['pandas','numpy','shapely','pyproj','torch','transformers','huggingface-hub','emoji','openpyxl','tzdata','psutil']}}
    print(json.dumps(result,indent=2)); return result

def main(argv=None):
    load_settings()
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('stage',choices=['doctor','filter','extract','label','emotion','all','test'],nargs='?',default='doctor')
    parser.add_argument('--mode',choices=['sample','pilot','production'],default='sample')
    source=parser.add_mutually_exclusive_group()
    source.add_argument('--input',type=Path,help='Local CSV/TSV, sample or pilot only')
    source.add_argument('--archive',type=Path,help='Archive folder with *.csv.gz files')
    parser.add_argument('--naive-timezone',help='Required explicit timezone for naive production/pilot timestamps; e.g. UTC')
    parser.add_argument('--coverage',type=Path,help='Independently verified UTC-day archive coverage CSV')
    parser.add_argument('--chunk-rows',type=int,default=50000)
    parser.add_argument('--max-files',type=int)
    parser.add_argument('--keyword-policy',choices=['word','substring'],default='word')
    parser.add_argument('--model',default='meta-llama/Llama-3.2-3B-Instruct')
    parser.add_argument('--revision',default='main')
    parser.add_argument('--offline-model',action='store_true',help='Use cached model only; requires --revision with immutable commit SHA')
    parser.add_argument('--confidence-threshold',type=float,default=50)
    parser.add_argument('--confidence-policy',choices=['exclude','flag'],default='exclude')
    parser.add_argument('--min-label-success',type=float,default=.98)
    parser.add_argument('--max-tweets',type=int)
    args=parser.parse_args(argv)
    if args.stage=='doctor': return doctor()
    if args.stage=='test':
        import subprocess
        raise SystemExit(subprocess.call([sys.executable,'-m','unittest','discover','-s',str(ROOT/'tests'),'-v'],cwd=ROOT))
    if args.stage in {'filter','extract','all'}:
        if args.mode!='sample' and not args.naive_timezone:
            parser.error('Specify --naive-timezone after confirming archive timestamp semantics with Harvard.')
        if args.mode=='production' and args.input: parser.error('Production must read the archive, not a local sample.')
        if args.mode=='production' and not args.coverage: parser.error('Production requires --coverage; missing days must be declared, never assumed observed.')
        path=args.input or args.archive
        if path is None:
            if args.mode=='sample': path=ROOT/'data/sample/tweets.tsv'
            else:
                configured=os.environ.get('GV_RAW_TWEETS_DIR')
                if not configured: parser.error('Set --archive or GV_RAW_TWEETS_DIR.')
                path=Path(configured)
        from pipeline.extract import extract
        run,_=extract(path,args.mode,args.naive_timezone or 'UTC',args.coverage,args.keyword_policy,args.chunk_rows,args.max_files)
        print('Extraction output:',run)
    if args.stage in {'label','emotion','all'}:
        from pipeline.labels import label
        limit=args.max_tweets if args.max_tweets is not None else (10 if args.mode=='sample' else None)
        run,_=label(args.mode,args.model,args.revision,args.confidence_threshold,args.confidence_policy,args.min_label_success,limit,local_files_only=args.offline_model)
        print('Label output:',run)

if __name__=='__main__':
    if hasattr(sys.stdout,'reconfigure'): sys.stdout.reconfigure(encoding='utf-8')
    try: main()
    except Exception as exc:
        print(f'ERROR [{type(exc).__name__}]: {exc}',file=sys.stderr)
        sys.exit(1)
