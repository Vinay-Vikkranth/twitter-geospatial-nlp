"""Rebuild the fixed study input from the FULL master sheet, with ID reconciliation.

Default is validation only. --write replaces data/latLong.csv after all checks,
preserving its prior bytes in Archive. Existing outputs block replacement.
Requires pandas and openpyxl. Never writes the master workbook or Originals.
"""
import argparse
import hashlib
import json
from pathlib import Path
import pandas as pd
from boundary53 import city_state_key, read_registry, read_incident_city_aliases

HERE = Path(__file__).resolve().parent
FIELDS = ['Incident ID', 'Incident Date', 'State', 'City Or County', 'Address', 'City_std']

def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def select_incidents(raw, registry, aliases):
    required = set(FIELDS) - {'City_std'}
    if not required <= set(raw):
        raise ValueError(f'Missing master columns: {required - set(raw)}')
    dates = pd.to_datetime(raw['Incident Date'], errors='coerce')
    if dates.isna().any():
        raise ValueError('Master contains missing or invalid incident dates.')
    selected = raw.loc[dates.between('2014-01-01', '2023-12-31 23:59:59.999999')].copy()
    keys = [city_state_key(c, s) for c, s in zip(selected['City Or County'], selected['State'])]
    keys = [aliases.get(k, k) for k in keys]
    selected['City_std'] = [registry[k][0] if k in registry else None for k in keys]
    selected = selected.loc[selected['City_std'].notna(), FIELDS].copy()
    ids = pd.to_numeric(selected['Incident ID'], errors='raise')
    if ids.isna().any() or (ids % 1 != 0).any() or ids.duplicated().any():
        raise ValueError('Incident IDs must be nonmissing, integral and unique.')
    selected['Incident ID'] = ids.astype('int64')
    selected['Incident Date'] = pd.to_datetime(selected['Incident Date']).dt.strftime('%Y-%m-%d')
    return selected.sort_values(['Incident Date', 'Incident ID']).reset_index(drop=True)

def reconcile(selected, reference):
    if len(selected)!=3578 or selected['Incident ID'].isna().any() or selected['Incident ID'].duplicated().any():
        raise ValueError('Selected incidents must contain 3578 unique IDs.')
    expected = pd.to_numeric(reference['Incident ID'], errors='raise')
    if expected.isna().any() or expected.duplicated().any() or len(expected) != 3578:
        raise ValueError('Reference must contain 3578 unique incident IDs.')
    missing = set(expected) - set(selected['Incident ID'])
    extra = set(selected['Incident ID']) - set(expected)
    if missing or extra:
        raise ValueError(f'ID mismatch: missing={sorted(missing)}, extra={sorted(extra)}')
    # IDs alone are insufficient: verify the incident attributes as well.
    import re
    def clean(v):
        value = re.sub(r'\s+', ' ', '' if pd.isna(v) else str(v).strip()).casefold()
        return '' if value == 'nan' else value
    ref = reference.set_index('Incident ID')
    for _, row in selected.iterrows():
        other = ref.loc[row['Incident ID']]
        if pd.to_datetime(row['Incident Date']).strftime('%Y-%m-%d') != pd.to_datetime(other['Incident Date']).strftime('%Y-%m-%d'):
            raise ValueError(f'Date disagreement for {row["Incident ID"]}')
        for field in ['State', 'City Or County', 'Address', 'City_std']:
            if clean(row[field]) != clean(other[field]):
                raise ValueError(f'{field} disagreement for {row["Incident ID"]}')

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--master', type=Path, default=HERE.parent.parent / 'MasterDataALL-mod.xlsx')
    parser.add_argument('--reference', type=Path, default=HERE / 'data/reference_incidents.csv')
    parser.add_argument('--write', action='store_true')
    args = parser.parse_args()
    master_hash = digest(args.master)
    raw = pd.read_excel(args.master, sheet_name='Master Data (wide)', engine='openpyxl')
    registry = read_registry(HERE / 'data/city_registry_53.csv')
    aliases = read_incident_city_aliases(HERE / 'data/incident_city_aliases.csv', registry)
    selected = select_incidents(raw, registry, aliases)
    reference = pd.read_csv(args.reference)
    reconcile(selected, reference)
    if selected[['City_std', 'State']].drop_duplicates().shape[0] != 53:
        raise ValueError('Expected all 53 cities.')
    report = dict(master_rows=len(raw), selected_incidents=len(selected), unique_ids=selected['Incident ID'].nunique(), cities=53, missing_ids=0, extra_ids=0, attributes_match=True, master_sha256=master_hash, reference_sha256=digest(args.reference))
    if args.write:
        if any(p.is_file() for p in (HERE / 'outputs').rglob('*')):
            raise ValueError('Existing outputs detected. Archive them before rebuilding; do not reuse old labels/checkpoints.')
        archive = HERE.parent / 'Archive/Change_03_Rebuild_Incidents'
        archive.mkdir(parents=True,exist_ok=True)
        target = HERE / 'data/latLong.csv'
        backup = archive / 'latLong.before.csv'
        if not backup.exists():
            backup.write_bytes(target.read_bytes())
        candidate = selected.to_csv(index=False, lineterminator='\n')
        import os
        temporary=target.with_name('latLong.pending.csv')
        temporary.write_text(candidate, encoding='utf-8', newline='')
        reconcile(pd.read_csv(temporary), reference)
        if digest(args.master) != master_hash:
            raise RuntimeError('Master workbook unexpectedly changed.')
        os.replace(temporary,target)
        report['input_sha256'] = digest(target)
        (archive / 'rebuild_results.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report, indent=2))

if __name__ == '__main__':
    main()
