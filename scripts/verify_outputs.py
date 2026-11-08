"""Print only published, current, hash-verified output paths."""
import argparse
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from pipeline.common import ROOT, latest
parser=argparse.ArgumentParser()
parser.add_argument('--mode',choices=['sample','pilot','production'],default='sample')
parser.add_argument('--stage',choices=['EXTRACT','LABELS'],default='EXTRACT')
args=parser.parse_args()
run,manifest=latest(ROOT/'outputs'/args.mode,args.stage)
print('VERIFIED:',run)
for name in manifest['files']: print(run/name)
