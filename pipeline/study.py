"""Validate the fixed study population and build all five incident-day windows."""
import csv
import json
import re
from zoneinfo import ZoneInfo
import pandas as pd
from boundary53 import read_registry, read_incident_city_aliases, city_state_key, load_city_polygons
from .common import ROOT

def load_study():
    registry=read_registry(ROOT/'data/city_registry_53.csv')
    aliases=read_incident_city_aliases(ROOT/'data/incident_city_aliases.csv',registry)
    frame=pd.read_csv(ROOT/'data/latLong.csv',dtype={'Incident ID':str},keep_default_na=False)
    reference=pd.read_csv(ROOT/'data/reference_incidents.csv',dtype={'Incident ID':str},keep_default_na=False)
    from rebuild_incidents import reconcile
    # Reconcile uses integer IDs, never floating tweet identifiers.
    check=frame.copy(); ref=reference.copy()
    check['Incident ID']=pd.to_numeric(check['Incident ID'],errors='raise')
    ref['Incident ID']=pd.to_numeric(ref['Incident ID'],errors='raise')
    if len(frame)!=3578 or frame['Incident ID'].duplicated().any() or frame['Incident ID'].eq('').any():
        raise ValueError('Study must contain 3578 unique incident IDs.')
    reconcile(check,ref)
    tz={city_state_key(r['City'],r['State']):r['timezone'] for r in json.loads((ROOT/'data/city_timezones.json').read_text())}
    if set(tz)!=set(registry): raise ValueError('Timezone mapping does not match 53-city registry.')
    polygons=load_city_polygons(ROOT/'data/cities boundary',ROOT/'data/city_registry_53.csv')
    windows=[]
    for row in frame.to_dict('records'):
        key=city_state_key(row['City Or County'],row['State']); key=aliases.get(key,key)
        if key not in registry: raise ValueError(f'Unregistered incident: {row["Incident ID"]}')
        date=pd.Timestamp(row['Incident Date'])
        if not pd.Timestamp('2014-01-01')<=date<=pd.Timestamp('2023-12-31'): raise ValueError('Incident date outside study.')
        ZoneInfo(tz[key])
        for offset in range(0,-5,-1):
            day=(date+pd.Timedelta(days=offset)).strftime('%Y-%m-%d')
            windows.append((str(row['Incident ID']),date.strftime('%Y-%m-%d'),registry[key][0],registry[key][1],tz[key],day,offset))
    return registry,polygons,tz,windows

def keyword_regex(policy='word'):
    with (ROOT/'data/Twitter_GunViolence_Keywords_List.xlsx - Sheet1.csv').open(encoding='utf-8-sig') as f:
        terms=sorted({r['Keyword'].strip() for r in csv.DictReader(f) if r['Keyword'].strip()})
    patterns=[re.escape(t).replace(r'\ ',r'\s+') for t in terms]
    if policy=='word': patterns=[r'(?<!\w)'+p+r'(?!\w)' for p in patterns]
    elif policy!='substring': raise ValueError('Keyword policy must be word or substring.')
    return re.compile('|'.join(patterns),re.IGNORECASE)

def utc_times(values,naive_tz):
    # Explicit offsets are respected. Naive values use the declared input timezone.
    def parse(value):
        try:
            if not str(value).strip(): return pd.NaT
            if re.fullmatch(r'\d+(\.\d+)?',str(value).strip()): return pd.NaT
            t=pd.Timestamp(value)
            if t.tzinfo is None: t=t.tz_localize(naive_tz,ambiguous='raise',nonexistent='raise')
            return t.tz_convert('UTC')
        except (ValueError,TypeError,OverflowError): return pd.NaT
    return pd.to_datetime(values.map(parse),utc=True)
