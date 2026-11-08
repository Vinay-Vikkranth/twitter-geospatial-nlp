"""Chunked extraction with transactional file checkpoints and auditable coverage."""
import csv
import gzip
import json
import math
from pathlib import Path
import re
import sqlite3
import pandas as pd
import shapely
from .common import ROOT, atomic_json, code_hash, data_hash, identity, sha, lock, connect, export_query, publish
from .study import load_study, keyword_regex, utc_times

SCHEMA='''
CREATE TABLE IF NOT EXISTS tweets(message_id TEXT PRIMARY KEY, tweet_date_utc TEXT NOT NULL, text TEXT NOT NULL,
 latitude REAL, longitude REAL, tweet_lang TEXT, place TEXT, data_source TEXT, gps TEXT, spatialerror TEXT,
 content_hash TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS windows(incident_id TEXT,incident_date TEXT,city TEXT,state TEXT,timezone TEXT,
 local_date TEXT,day_offset INTEGER,coverage_status TEXT,PRIMARY KEY(incident_id,day_offset));
CREATE TABLE IF NOT EXISTS matches(message_id TEXT REFERENCES tweets(message_id),incident_id TEXT,day_offset INTEGER,
 PRIMARY KEY(message_id,incident_id,day_offset),FOREIGN KEY(incident_id,day_offset) REFERENCES windows(incident_id,day_offset));
CREATE TABLE IF NOT EXISTS sources(message_id TEXT REFERENCES tweets(message_id),source_file TEXT,PRIMARY KEY(message_id,source_file));
CREATE TABLE IF NOT EXISTS files(path TEXT PRIMARY KEY,sha256 TEXT,status TEXT,rows_read INTEGER,invalid_rows INTEGER,matched_rows INTEGER,utc_dates TEXT);
CREATE TABLE IF NOT EXISTS rejected(source_file TEXT,row_number INTEGER,reason TEXT);
CREATE TABLE IF NOT EXISTS conflicts(message_id TEXT,source_file TEXT,variant_json TEXT,PRIMARY KEY(message_id,source_file,variant_json));
CREATE TABLE IF NOT EXISTS observations(message_id TEXT PRIMARY KEY,content_hash TEXT,variant_json TEXT,source_file TEXT);
'''

def read_chunks(path,chunk_rows):
    opener=gzip.open if str(path).endswith('.gz') else open
    with opener(path,'rt',encoding='utf-8-sig',newline='') as f:
        header=f.readline()
    delimiter='\t' if '\t' in header else ','
    yield from pd.read_csv(path,sep=delimiter,dtype=str,keep_default_na=False,chunksize=chunk_rows,on_bad_lines='error')

def process_file(db,path,digest,polygons,tz,window_lookup,regex,naive_tz,chunk_rows):
    read=invalid=matched=0; utc_dates=set()
    for chunk in read_chunks(path,chunk_rows):
        required={'message_id','text','latitude','longitude'}
        if not required<=set(chunk) or not ({'tweet_date','date'}&set(chunk)):
            raise ValueError('Tweet source requires message_id, text, latitude, longitude and tweet_date/date.')
        timestamps=chunk['tweet_date'].copy() if 'tweet_date' in chunk else chunk['date'].copy()
        if 'date' in chunk: timestamps=timestamps.mask(timestamps.str.strip().eq(''),chunk['date'])
        times=utc_times(timestamps,naive_tz)
        if 'tweet_date' in chunk and 'date' in chunk:
            other=utc_times(chunk['date'],naive_tz)
            both=chunk['tweet_date'].str.strip().ne('')&chunk['date'].str.strip().ne('')
            if (both&times.notna()&other.notna()&times.ne(other)).any():
                raise ValueError('Conflicting date and tweet_date columns; confirm timestamp semantics.')
        lat=pd.to_numeric(chunk['latitude'],errors='coerce'); lon=pd.to_numeric(chunk['longitude'],errors='coerce')
        valid=times.notna()&lat.between(-90,90)&lon.between(-180,180)&chunk.message_id.str.strip().ne('')&chunk.text.str.strip().ne('')
        for idx in chunk.index[~valid]:
            db.execute('INSERT INTO rejected VALUES(?,?,?)',(str(path),int(idx)+2,'invalid_timestamp_coordinates_id_or_text'))
        invalid+=int((~valid).sum()); read+=len(chunk)
        utc_dates.update(times[valid].dt.strftime('%Y-%m-%d').unique())
        # Check identity before keyword/spatial filtering: a changed variant may no
        # longer contain a keyword, but must still invalidate its selected twin.
        for idx in chunk.index[valid]:
            row=chunk.loc[idx]; mid=str(row.message_id).strip()
            core=[times.loc[idx].isoformat(),str(row.text),float(lat.loc[idx]),float(lon.loc[idx])]
            fingerprint=identity(core); encoded=json.dumps(core,ensure_ascii=False)
            seen=db.execute('SELECT content_hash,variant_json,source_file FROM observations WHERE message_id=?',(mid,)).fetchone()
            if seen is None:
                db.execute('INSERT INTO observations VALUES(?,?,?,?)',(mid,fingerprint,encoded,str(path)))
            elif seen[0]!=fingerprint:
                db.execute('INSERT OR IGNORE INTO conflicts VALUES(?,?,?)',(mid,seen[2],seen[1]))
                db.execute('INSERT OR IGNORE INTO conflicts VALUES(?,?,?)',(mid,str(path),encoded))
                db.execute('DELETE FROM matches WHERE message_id=?',(mid,))
                db.execute('DELETE FROM sources WHERE message_id=?',(mid,))
                db.execute('DELETE FROM tweets WHERE message_id=?',(mid,))
        hit=valid&chunk.text.str.contains(regex,na=False)
        if not hit.any(): continue
        points=shapely.points(lon[hit].to_numpy(),lat[hit].to_numpy())
        indices=chunk.index[hit]
        dates_by_tz={zone:times.loc[indices].dt.tz_convert(zone).dt.strftime('%Y-%m-%d') for zone in set(tz.values())}
        for key,polygon in polygons.items():
            days=dates_by_tz[tz[key]]
            relevant=days.map(lambda d:(key,d) in window_lookup).to_numpy()
            spatial=shapely.covers(polygon,points)&relevant
            for idx in indices[spatial]:
                row=chunk.loc[idx]; mid=str(row.message_id).strip()
                utc=times.loc[idx].isoformat(); text=str(row.text)
                core=[utc,text,float(lat.loc[idx]),float(lon.loc[idx])]
                fingerprint=identity(core)
                if db.execute('SELECT 1 FROM conflicts WHERE message_id=? LIMIT 1',(mid,)).fetchone():
                    db.execute('INSERT OR IGNORE INTO conflicts VALUES(?,?,?)',(mid,str(path),json.dumps(core,ensure_ascii=False)))
                    continue
                previous=db.execute('SELECT content_hash FROM tweets WHERE message_id=?',(mid,)).fetchone()
                if previous and previous[0]!=fingerprint:
                    old=db.execute('SELECT tweet_date_utc,text,latitude,longitude FROM tweets WHERE message_id=?',(mid,)).fetchone()
                    old_sources=[r[0] for r in db.execute('SELECT source_file FROM sources WHERE message_id=?',(mid,))]
                    for old_source in old_sources:
                        db.execute('INSERT OR IGNORE INTO conflicts VALUES(?,?,?)',(mid,old_source,json.dumps(old,ensure_ascii=False)))
                    db.execute('INSERT OR IGNORE INTO conflicts VALUES(?,?,?)',(mid,str(path),json.dumps(core,ensure_ascii=False)))
                    db.execute('DELETE FROM matches WHERE message_id=?',(mid,))
                    db.execute('DELETE FROM sources WHERE message_id=?',(mid,))
                    db.execute('DELETE FROM tweets WHERE message_id=?',(mid,))
                    continue
                db.execute('INSERT OR IGNORE INTO tweets VALUES(?,?,?,?,?,?,?,?,?,?,?)',
                           (mid,*core[:2],core[2],core[3],row.get('tweet_lang',''),row.get('place',''),row.get('data_source',''),row.get('GPS',''),row.get('spatialerror',''),fingerprint))
                db.execute('INSERT OR IGNORE INTO sources VALUES(?,?)',(mid,str(path)))
                for iid,offset in window_lookup[key,days.loc[idx]]:
                    db.execute('INSERT OR IGNORE INTO matches VALUES(?,?,?)',(mid,iid,offset))
                matched+=1
    if invalid:
        # Fail closed: no invalid records are silently accepted as archive completeness.
        raise ValueError(f'{invalid}/{read} invalid tweet rows; fix source/schema before extraction can publish.')
    db.execute('INSERT OR REPLACE INTO files VALUES(?,?,?,?,?,?,?)',(str(path),digest,'complete',read,invalid,matched,json.dumps(sorted(utc_dates))))

def coverage_map(path):
    if path is None: return {}
    with Path(path).open(encoding='utf-8-sig',newline='') as f:
        reader=csv.DictReader(f)
        if not {'utc_date','status'}<=set(reader.fieldnames or []): raise ValueError('Coverage CSV needs utc_date,status.')
        result={}
        for row in reader:
            day=pd.Timestamp(row['utc_date']).strftime('%Y-%m-%d')
            if day in result or row['status'] not in {'complete','verified_empty','missing'}: raise ValueError('Duplicate/invalid coverage declaration.')
            result[day]=row['status']
        return result

def window_coverage(day,zone,coverage,mode,seen_utc_dates):
    if mode in {'sample','test'}: return 'sample_not_population_coverage'
    start=pd.Timestamp(day).tz_localize(zone).tz_convert('UTC')
    end=(pd.Timestamp(day)+pd.Timedelta(days=1)).tz_localize(zone).tz_convert('UTC')-pd.Timedelta(nanoseconds=1)
    needed=pd.date_range(start.date(),end.date(),freq='D').strftime('%Y-%m-%d')
    states=[coverage.get(d,'unknown') for d in needed]
    if 'missing' in states: return 'missing_archive'
    if any(s=='unknown' for s in states): return 'unverified_archive_coverage'
    if any(coverage[d]=='complete' and d not in seen_utc_dates for d in needed): return 'declared_complete_but_no_file_evidence'
    return 'complete'

def extract(source,mode='sample',naive_tz='UTC',coverage=None,keyword_policy='word',chunk_rows=50000,max_files=None,output_root=None):
    if mode not in {'sample','pilot','production','test'}: raise ValueError('Unknown mode')
    if chunk_rows<1: raise ValueError('chunk_rows must be positive')
    if max_files is not None and (max_files<1 or mode=='production'): raise ValueError('File limits are only allowed in sample/pilot/test.')
    root=Path(output_root or ROOT/'outputs'/mode)
    with lock(root):
        atomic_json(root/'LAST_EXTRACT_ATTEMPT.json',{'status':'running'})
        db=None; run=None; active_source=None
        try:
            source=Path(source).resolve()
            if not source.exists(): raise FileNotFoundError('Tweet input unavailable: configure --input or --archive.')
            files=[source] if source.is_file() else sorted(source.rglob('*.csv.gz'))
            if not files: raise ValueError('No archive CSV gzip files found.')
            total_files=len(files)
            if max_files: files=files[:max_files]
            inventory=[{'path':str(p),'sha256':sha(p)} for p in files]
            cfg=dict(mode=mode,naive_timezone=naive_tz,keyword_policy=keyword_policy,day_offsets=[0,-1,-2,-3,-4],
                     coverage_path=str(Path(coverage).resolve()) if coverage else None,coverage_sha256=sha(coverage) if coverage else None,
                     max_files=max_files,source=str(source),total_discovered_files=total_files)
            initial_data=data_hash(); initial_code=code_hash()
            rid=identity({'config':cfg,'files':inventory,'data':initial_data,'code':initial_code})[:24]
            run=root/'extract'/rid; run.mkdir(parents=True,exist_ok=True)
            atomic_json(run/'attempt.json',{'status':'running','config':cfg})
            atomic_json(run/'source_inventory.json',inventory)
            registry,polygons,tz,windows=load_study()
            lookup={}
            from boundary53 import city_state_key
            for iid,incident_date,city,state,zone,day,offset in windows:
                lookup.setdefault((city_state_key(city,state),day),[]).append((iid,offset))
            db=connect(run/'state.sqlite'); db.executescript(SCHEMA)
            with db:
                db.executemany('INSERT OR IGNORE INTO windows VALUES(?,?,?,?,?,?,?,?)',[(*w,'pending') for w in windows])
            regex=keyword_regex(keyword_policy)
            resumed=0; seen=set(); record_dates=set()
            for i,item in enumerate(inventory):
                path=Path(item['path'])
                active_source=str(path)
                old=db.execute('SELECT sha256,status FROM files WHERE path=?',(str(path),)).fetchone()
                if old==(item['sha256'],'complete'): resumed+=1
                else:
                    # One transaction per file: crash or parse failure rolls back its rows.
                    with db: process_file(db,path,item['sha256'],polygons,tz,lookup,regex,naive_tz,chunk_rows)
                rows_read,dates=db.execute('SELECT rows_read,utc_dates FROM files WHERE path=?',(str(path),)).fetchone()
                seen.update(json.loads(dates))
                record_dates.update(json.loads(dates))
                if rows_read==0:
                    date_match=re.search(r'(\d{4})[_-](\d{2})[_-](\d{2})',path.name)
                    if date_match: seen.add('-'.join(date_match.groups()))
                print(f'Files complete: {i+1}/{len(files)} (resumed {resumed})',flush=True)
            declared=coverage_map(coverage)
            if any(declared.get(d)=='verified_empty' for d in record_dates):
                raise ValueError('Coverage declares a UTC day verified_empty but source records exist for that day.')
            conflicts=db.execute('SELECT count(DISTINCT message_id) FROM conflicts').fetchone()[0]
            with db:
                for iid,_,_,_,zone,day,offset in windows:
                    status=window_coverage(day,zone,declared,mode,seen)
                    if max_files and len(files)<total_files: status='pilot_subset'
                    if conflicts and status=='complete': status='source_conflicts_require_review'
                    db.execute('UPDATE windows SET coverage_status=? WHERE incident_id=? AND day_offset=?',(status,iid,offset))
            # Re-hash before publication to reject inputs modified during processing.
            if any(sha(p['path'])!=p['sha256'] for p in inventory): raise RuntimeError('Input changed during extraction.')
            if data_hash()!=initial_data or code_hash()!=initial_code: raise RuntimeError('Study input or code changed during extraction.')
            if coverage and sha(coverage)!=cfg['coverage_sha256']: raise RuntimeError('Coverage declaration changed during extraction.')
            if source.is_dir():
                current_files=sorted(source.rglob('*.csv.gz'))
                selected_files=current_files[:max_files] if max_files else current_files
                if len(current_files)!=total_files or selected_files!=files: raise RuntimeError('Archive inventory changed during extraction.')
            exports={
              'tweets.csv':'SELECT message_id,tweet_date_utc,text,latitude,longitude,tweet_lang,place,data_source,gps,spatialerror FROM tweets ORDER BY message_id',
              'tweet_incident_matches.csv':'''SELECT m.message_id,w.incident_id,w.incident_date,w.city,w.state,w.timezone,w.local_date,w.day_offset,
                   CASE WHEN w.day_offset=0 THEN 't' ELSE 't'||w.day_offset END AS tag FROM matches m JOIN windows w USING(incident_id,day_offset) ORDER BY m.message_id,w.incident_id,w.day_offset''',
              'incident_days.csv':'''SELECT w.*,count(m.message_id) AS observed_match_count,
                   CASE WHEN coverage_status='complete' THEN count(m.message_id) ELSE NULL END AS complete_coverage_tweet_count
                   FROM windows w LEFT JOIN matches m USING(incident_id,day_offset) GROUP BY w.incident_id,w.day_offset ORDER BY w.incident_id,w.day_offset''',
              'source_files.csv':'SELECT * FROM files ORDER BY path',
              'tweet_sources.csv':'SELECT * FROM sources ORDER BY message_id,source_file',
              'rejected_rows.csv':'SELECT * FROM rejected',
              'conflicting_tweets.csv':'SELECT * FROM conflicts ORDER BY message_id,source_file'}
            for name,query in exports.items(): export_query(db,query,run/name)
            counts={table:db.execute(f'SELECT count(*) FROM {table}').fetchone()[0] for table in ['tweets','matches','windows','files']}
            counts['conflicting_ids_excluded']=conflicts
            db.execute('PRAGMA wal_checkpoint(TRUNCATE)'); db.close(); db=None
            sources=inventory+([{'path':cfg['coverage_path'],'sha256':cfg['coverage_sha256']}] if coverage else [])
            manifest=publish(root,'EXTRACT',run,[*[run/n for n in exports],run/'state.sqlite',run/'source_inventory.json'],{'mode':mode,'config':cfg,'counts':counts,'sources':sources,'resumed_files':resumed,'warning':'Archive completeness requires independently verified daily coverage; sample counts are not population totals.'})
            print(json.dumps(counts)); return run,manifest
        except BaseException as exc:
            if db is not None: db.close()
            failure={'status':'failed','error_type':type(exc).__name__,'error':str(exc),'source_file':active_source}
            atomic_json(root/'LAST_EXTRACT_ATTEMPT.json',failure)
            if run: atomic_json(run/'attempt.json',failure)
            raise
