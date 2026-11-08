import contextlib
import csv
import gzip
import io
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
import pandas as pd
from shapely.geometry import box
from pipeline.common import lock, latest, ROOT, sha
from pipeline.extract import extract, window_coverage
from pipeline.labels import EMOTIONS, THEMES, validate, emoji_score, label
from pipeline.study import utc_times, keyword_regex, load_study

GOOD={'e':'grief/sadness','c':90,'gv':True,'lg':80,'rs':60,'rl':0,'sc':10,'te':50,'la':0,'summary':'The author mourns a shooting.'}
MID='1640389678703550464'
SCRATCH=ROOT/'outputs/test_scratch'
SCRATCH.mkdir(parents=True,exist_ok=True)
def fixture_study():
    key=('chicago','illinois')
    windows=[]
    for iid,date in [('1','2023-03-27'),('2','2023-03-28')]:
        for offset in range(0,-5,-1):
            windows.append((iid,date,'Chicago','Illinois','America/Chicago',(pd.Timestamp(date)+pd.Timedelta(days=offset)).strftime('%Y-%m-%d'),offset))
    return {key:('Chicago','Illinois')},{key:box(-88,41,-87,42)},{key:'America/Chicago'},windows

class Fake:
    is_test=True; model_id='TEST_ONLY_FAKE_NOT_RESEARCH'; revision='fixture-v1'
    def __init__(self,value=None): self.value=GOOD.copy() if value is None else value; self.calls=0
    def __call__(self,text):
        self.calls+=1
        if isinstance(self.value,Exception): raise self.value
        return json.dumps(self.value)

class UnitTests(unittest.TestCase):
    def test_taxonomies_separate(self):
        self.assertEqual(len(EMOTIONS),10); self.assertEqual(len(THEMES),6)
        self.assertEqual(validate(json.dumps(GOOD))['retaliation_language_pct'],0)
    def test_missing_field_rejected(self):
        for field in GOOD:
            bad=GOOD.copy(); del bad[field]
            with self.assertRaises(ValueError): validate(json.dumps(bad))
    def test_invalid_labels_rejected(self):
        for field,value in [('e',''),('e','happy'),('c',True),('c','90'),('c',101),('c',float('nan')),('gv','false'),('lg',-1),('summary','')]:
            bad={**GOOD,field:value}
            with self.assertRaises(ValueError): validate(json.dumps(bad))
    def test_nonjson_rejected(self):
        for text in ['hello','[]','null','```json\n{}\n```']:
            with self.assertRaises((ValueError,TypeError)): validate(text)
    def test_emoji_sequences(self):
        self.assertEqual(emoji_score('😭😡')['emoji_count'],2)
        self.assertEqual(emoji_score('😭😡')['emoji_lexicon_score'],emoji_score('😭 😡')['emoji_lexicon_score'])
        self.assertEqual(emoji_score('👨‍👩‍👧‍👦')['emoji_count'],1)
        self.assertIsNone(emoji_score('👨‍👩‍👧‍👦')['emoji_lexicon_score'])
    def test_keyword_boundaries(self):
        self.assertFalse(bool(keyword_regex().search('investigation')))
        self.assertTrue(bool(keyword_regex().search('gun violence')))
        self.assertTrue(bool(keyword_regex('substring').search('investigation')))
    def test_timezones_midnight(self):
        ts=utc_times(pd.Series(['2023-03-27 01:00:00','2023-03-26T20:00:00-05:00']),'UTC')
        self.assertEqual(ts.nunique(),1)
        self.assertEqual(ts.dt.tz_convert('America/Chicago').dt.strftime('%Y-%m-%d').tolist(),['2023-03-26']*2)
    def test_naive_non_utc(self):
        ts=utc_times(pd.Series(['2023-03-27 01:00:00']),'America/Chicago')
        self.assertEqual(ts.iloc[0].hour,6)
    def test_phoenix_dst(self):
        ts=utc_times(pd.Series(['2023-07-01 06:00:00','2023-01-01 06:00:00']),'UTC')
        self.assertEqual(ts.dt.tz_convert('America/Phoenix').dt.hour.tolist(),[23,23])
    def test_invalid_timestamp(self):
        self.assertTrue(utc_times(pd.Series(['','nonsense','1680000000']),'UTC').isna().all())
    def test_coverage_requires_adjacent_utc_day(self):
        self.assertEqual(window_coverage('2023-03-27','America/Chicago',{'2023-03-27':'complete'},'production',{'2023-03-27'}),'unverified_archive_coverage')
        self.assertEqual(window_coverage('2023-03-27','America/Chicago',{'2023-03-27':'complete','2023-03-28':'complete'},'production',{'2023-03-27','2023-03-28'}),'complete')
    def test_coverage_missing_and_empty(self):
        c={'2023-03-27':'verified_empty','2023-03-28':'verified_empty'}
        self.assertEqual(window_coverage('2023-03-27','America/Chicago',c,'production',set()),'complete')
        c['2023-03-28']='missing'
        self.assertEqual(window_coverage('2023-03-27','America/Chicago',c,'production',set()),'missing_archive')
    def test_real_population(self):
        with contextlib.redirect_stdout(io.StringIO()): reg,polys,tz,windows=load_study()
        self.assertEqual(len(reg),53); self.assertEqual(len(polys),53); self.assertEqual(len(windows),3578*5)
        self.assertNotIn(('kansas city','kansas'),reg)
    def test_concurrent_lock(self):
        with tempfile.TemporaryDirectory(dir=SCRATCH) as tmp:
            with lock(tmp):
                with self.assertRaises(RuntimeError):
                    with lock(tmp): pass
    def test_offline_model_requires_immutable_revision(self):
        from pipeline.labels import TransformersBackend
        with patch('torch.cuda.is_available',return_value=True), patch('torch.cuda.mem_get_info',return_value=(16*1024**3,24*1024**3)):
            with self.assertRaises(ValueError): TransformersBackend('test','main',True)
            with patch('huggingface_hub.HfApi.model_info',side_effect=AssertionError('Offline must not query Hub')):
                backend=TransformersBackend('test','a'*40,True)
                self.assertEqual(backend.revision,'a'*40)

class IntegrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(dir=SCRATCH); self.base=Path(self.tmp.name); self.out=self.base/'outputs'
        self.patcher=patch('pipeline.extract.load_study',fixture_study); self.patcher.start()
        self.quiet=contextlib.redirect_stdout(io.StringIO()); self.quiet.__enter__()
    def tearDown(self): self.quiet.__exit__(None,None,None); self.patcher.stop(); self.tmp.cleanup()
    def input(self,rows=None,name='tweets.csv'):
        path=self.base/name
        pd.DataFrame(rows if rows is not None else [self.row()],columns=['message_id','date','text','latitude','longitude']).to_csv(path,index=False)
        return path
    def row(self,mid=MID,date='2023-03-27 17:00:00',text='gun violence is tragic',lat=41.5,lon=-87.5):
        return dict(message_id=mid,date=date,text=text,latitude=lat,longitude=lon)
    def extract(self,path=None,**kwargs): return extract(path or self.input(),mode='test',output_root=self.out,**kwargs)
    def label(self,backend=None,**kwargs): return label(mode='test',backend=backend or Fake(),output_root=self.out,**kwargs)
    def test_incident_links_and_id_precision(self):
        run,m=self.extract()
        tweets=pd.read_csv(run/'tweets.csv',dtype=str); matches=pd.read_csv(run/'tweet_incident_matches.csv',dtype=str)
        self.assertEqual(tweets.message_id.tolist(),[MID]); self.assertEqual(len(matches),2)
        self.assertEqual(set(matches.day_offset),{'0','-1'})
    def test_all_five_days_and_exclude_sixth(self):
        run,m=self.extract(self.input([self.row(str(i),f'2023-03-{27-i} 17:00:00') for i in range(6)]))
        matches=pd.read_csv(run/'tweet_incident_matches.csv',dtype=str)
        self.assertEqual(set(matches.query("incident_id == '1'").day_offset),{'0','-1','-2','-3','-4'})
        self.assertNotIn('5',set(matches.message_id))
    def test_utc_midnight_offset(self):
        run,m=self.extract(self.input([self.row(date='2023-03-27 01:00:00')]))
        matches=pd.read_csv(run/'tweet_incident_matches.csv',dtype=str)
        self.assertEqual(matches.query("incident_id == '1'").day_offset.iloc[0],'-1')
    def test_boundary_edge_included(self):
        run,m=self.extract(self.input([self.row(lon=-88)])); self.assertEqual(m['counts']['tweets'],1)
    def test_outside_boundary(self):
        run,m=self.extract(self.input([self.row(lon=-90)])); self.assertEqual(m['counts']['tweets'],0)
    def test_exact_duplicate_deduplicated(self):
        run,m=self.extract(self.input([self.row(),self.row()])); self.assertEqual(m['counts']['tweets'],1)
    def test_conflicting_duplicate_quarantined(self):
        run,m=self.extract(self.input([self.row(),self.row(text='gun shooting news'),self.row()]),chunk_rows=1)
        self.assertEqual(m['counts']['tweets'],0); self.assertEqual(m['counts']['conflicting_ids_excluded'],1)
        self.assertGreaterEqual(len(pd.read_csv(run/'conflicting_tweets.csv')),2)
    def test_bad_schema_blocks_stale(self):
        self.extract()
        bad=self.base/'bad.csv'; bad.write_text('date,text\n2023-03-27,gun\n')
        with self.assertRaises(ValueError): self.extract(bad)
        with self.assertRaises(RuntimeError): latest(self.out,'EXTRACT')
    def test_bad_rows_fail_transaction(self):
        source=self.input([self.row(),self.row('bad',date='nonsense')])
        with self.assertRaises(ValueError): self.extract(source,chunk_rows=1)
        db=sqlite3.connect(next(self.out.glob('extract/*/state.sqlite')))
        self.assertEqual(db.execute('SELECT count(*) FROM tweets').fetchone()[0],0); db.close()
    def test_corrupt_archive_fails(self):
        p=self.base/'bad.csv.gz'; p.write_bytes(b'not gzip')
        with self.assertRaises(Exception): self.extract(p)
        self.assertFalse((self.out/'LATEST_EXTRACT.json').exists())
    def test_empty_input_no_model(self):
        self.extract(self.input([])); fake=Fake(); run,m=self.label(fake)
        self.assertEqual(fake.calls,0); self.assertEqual(len(pd.read_csv(run/'tweets_labeled_research.csv')),0)
        summary=pd.read_csv(run/'incident_day_summary.csv'); self.assertTrue(summary['mean_loss_grief_expression_pct'].isna().all())
    def test_label_and_resume(self):
        self.extract(); fake=Fake(); run,m=self.label(fake); self.assertEqual(fake.calls,1)
        fake2=Fake(); run2,m2=self.label(fake2); self.assertEqual(fake2.calls,0); self.assertEqual(run,run2)
        frame=pd.read_csv(run/'tweets_labeled_research.csv',dtype={'message_id':str})
        self.assertEqual(frame.message_id.iloc[0],MID); self.assertEqual(frame.final_emotion.iloc[0],'grief/sadness')
    def test_low_confidence_exclusion_consistent(self):
        self.extract(); run,m=self.label(Fake({**GOOD,'c':5}))
        research=pd.read_csv(run/'tweets_labeled_research.csv'); summary=pd.read_csv(run/'incident_day_summary.csv')
        self.assertTrue(research.final_emotion.isna().all())
        self.assertTrue(research[list(THEMES.values())].isna().all().all())
        self.assertEqual(summary.eligible_label_count.sum(),0)
        self.assertTrue(summary.mean_loss_grief_expression_pct.isna().all())
    def test_low_confidence_flag_policy(self):
        self.extract(); run,m=self.label(Fake({**GOOD,'c':5}),confidence_policy='flag')
        self.assertEqual(pd.read_csv(run/'tweets_labeled_research.csv').final_emotion.iloc[0],'grief/sadness')
    def test_failed_labels_not_neutral(self):
        self.extract(); run,m=self.label(Fake(RuntimeError('test failure')),min_success=0)
        frame=pd.read_csv(run/'tweets_labeled_research.csv')
        self.assertEqual(frame.label_status.iloc[0],'failed'); self.assertTrue(frame.final_emotion.isna().all())
        self.assertTrue(frame[list(THEMES.values())].isna().all().all())
    def test_failed_qc_not_published(self):
        self.extract()
        with self.assertRaises(RuntimeError): self.label(Fake({}))
        self.assertFalse((self.out/'LATEST_LABELS.json').exists())
    def test_changed_text_relabels(self):
        source=self.input(); self.extract(source); first=Fake(); self.label(first)
        self.input([self.row(text='gun violence causes fear')]); self.extract(source)
        second=Fake(); self.label(second); self.assertEqual(second.calls,1)
    def test_changed_model_relabels(self):
        self.extract(); self.label(); fake=Fake(); fake.revision='fixture-v2'; self.label(fake); self.assertEqual(fake.calls,1)
    def test_changed_prompt_relabels(self):
        self.extract(); self.label()
        with patch('pipeline.labels.PROMPT','different prompt'):
            fake=Fake(); self.label(fake); self.assertEqual(fake.calls,1)
    def test_output_tamper_rejected(self):
        run,m=self.extract(); (run/'tweets.csv').write_text('tampered')
        with self.assertRaises(RuntimeError): latest(self.out,'EXTRACT')
    def test_source_tamper_rejected(self):
        source=self.input(); self.extract(source); self.input([self.row(text='gun changed')])
        with self.assertRaises(RuntimeError): latest(self.out,'EXTRACT')
    def test_config_change_creates_run(self):
        source=self.input(); run,_=self.extract(source); run2,_=self.extract(source,keyword_policy='substring'); self.assertNotEqual(run,run2)
    def test_test_backend_forbidden_production(self):
        with self.assertRaises(ValueError): label(mode='production',backend=Fake(),output_root=self.out)
    def test_sqlite_partial_checkpoint_rolls_back(self):
        self.extract(); run,_=self.label(); db=sqlite3.connect(run/'checkpoints.sqlite')
        db.execute('DELETE FROM labels'); db.close()
        fake=Fake(); self.label(fake); self.assertEqual(fake.calls,0)
    def test_corrupt_cached_response_retried(self):
        self.extract(); run,_=self.label(); db=sqlite3.connect(run/'checkpoints.sqlite')
        db.execute("UPDATE labels SET raw_response='broken'"); db.commit(); db.close()
        fake=Fake(); self.label(fake); self.assertEqual(fake.calls,1)
    def test_failed_latest_label_blocks_previous(self):
        self.extract(); self.label()
        bad=Fake({}); bad.revision='different'
        with self.assertRaises(RuntimeError): self.label(bad)
        with self.assertRaises(RuntimeError): latest(self.out,'LABELS')
    def test_new_extraction_invalidates_old_labels(self):
        self.extract(); self.label(); self.extract(self.input([self.row('new')],name='new.csv'))
        with self.assertRaises(RuntimeError): latest(self.out,'LABELS')
    def test_date_columns_disagree(self):
        row=self.row(); row['tweet_date']='2023-03-28 17:00:00'
        p=self.base/'different_dates.csv'; pd.DataFrame([row]).to_csv(p,index=False)
        with self.assertRaises(ValueError): self.extract(p)
    def test_real_zero_vs_unknown_coverage(self):
        empty=self.input([])
        run,m=self.extract(empty)
        days=pd.read_csv(run/'incident_days.csv')
        self.assertTrue(days.complete_coverage_tweet_count.isna().all())
        self.assertTrue(days.observed_match_count.eq(0).all())
    def test_coverage_false_empty_rejected(self):
        coverage=self.base/'coverage.csv'; coverage.write_text('utc_date,status\n2023-03-27,verified_empty\n')
        with self.assertRaises(ValueError): self.extract(coverage=coverage)
    def test_conflict_across_files_survives_resume(self):
        archive=self.base/'conflict'; archive.mkdir()
        pd.DataFrame([self.row()]).to_csv(archive/'a.csv.gz',index=False,compression='gzip')
        pd.DataFrame([self.row(text='a completely different message')]).to_csv(archive/'b.csv.gz',index=False,compression='gzip')
        run,m=self.extract(archive); self.assertEqual(m['counts']['tweets'],0)
        run,m=self.extract(archive); self.assertEqual(m['resumed_files'],2); self.assertEqual(m['counts']['tweets'],0)
    def test_labeled_events_keep_scores(self):
        self.extract(); run,m=self.label()
        events=pd.read_csv(run/'tweet_incident_labels.csv')
        self.assertEqual(len(events),2); self.assertTrue(events.loss_grief_expression_pct.eq(80).all())
    def test_failure_does_not_publish_partial_file(self):
        archive=self.base/'partial'; archive.mkdir()
        pd.DataFrame([self.row()]).to_csv(archive/'a.csv.gz',index=False,compression='gzip')
        (archive/'b.csv.gz').write_bytes(b'broken')
        with self.assertRaises(Exception): self.extract(archive)
        self.assertFalse((self.out/'LATEST_EXTRACT.json').exists())
        db=sqlite3.connect(next(self.out.glob('extract/*/state.sqlite')))
        self.assertEqual(db.execute('SELECT count(*) FROM files').fetchone()[0],1); db.close()
    def test_gzip_archive_and_inventory_addition(self):
        archive=self.base/'archive'; archive.mkdir()
        p=archive/'2023-03-27.csv.gz'; pd.DataFrame([self.row()]).to_csv(p,index=False,compression='gzip')
        self.extract(archive)
        pd.DataFrame([self.row('other')]).to_csv(archive/'2023-03-28.csv.gz',index=False,compression='gzip')
        with self.assertRaises(RuntimeError): latest(self.out,'EXTRACT')
    def test_file_checkpoint_resume(self):
        source=self.input(); first,m=self.extract(source); second,m2=self.extract(source)
        self.assertEqual(first,second); self.assertEqual(m2['resumed_files'],1)

if __name__=='__main__': unittest.main()
