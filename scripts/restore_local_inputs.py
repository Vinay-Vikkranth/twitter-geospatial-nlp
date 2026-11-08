from pathlib import Path
import shutil
root=Path(__file__).resolve().parents[1]
source=root/'data/private';target=root/'data/research'
files=[p for p in source.rglob('*') if p.is_file()]
if not files:raise SystemExit('Research inputs are not distributed. See docs/REPRODUCIBILITY.md for provenance and required access.')
for p in files:
    dest=target/p.relative_to(source);dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,dest)
print(f'Restored {len(files)} local input files to ignored data/research. No downloads or publication performed.')
