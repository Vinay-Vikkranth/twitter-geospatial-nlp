import sys,unittest,tempfile,json
from pathlib import Path
import pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from demo import run_demo
from pipeline.labels import validate
from pipeline.study import utc_times
from pipeline.extract import window_coverage
class PublicPipelineTests(unittest.TestCase):
    def test_duplicate_conflict_spatial_keyword_filters(self):
        with tempfile.TemporaryDirectory() as out:r,t,m=run_demo(out)
        self.assertEqual(t.message_id.tolist(),['syn-1','syn-5']);self.assertEqual(r['conflicting_ids'],1);self.assertEqual(len(m),2)
        self.assertEqual(m.day_offset.tolist(),[-1,0])
    def test_midnight_local_date(self):
        v=utc_times(pd.Series(['2023-03-27T01:00:00Z']),'UTC')
        self.assertEqual(v.dt.tz_convert('America/Chicago').dt.strftime('%Y-%m-%d').iloc[0],'2023-03-26')
    def test_unknown_coverage_never_complete(self):
        self.assertNotEqual(window_coverage('2023-03-27','America/Chicago',{},'production',set()),'complete')
    def test_missing_and_nonfinite_labels_rejected(self):
        good={'e':'fear','c':90,'gv':True,'lg':1,'rs':2,'rl':0,'sc':0,'te':0,'la':0,'summary':'Fictional.'}
        for bad in [{k:v for k,v in good.items() if k!='lg'},{**good,'c':float('nan')},{**good,'gv':'true'}]:
            with self.assertRaises(ValueError):validate(json.dumps(bad))
    def test_malformed_timestamp_is_missing(self):
        self.assertTrue(utc_times(pd.Series(['garbage']),'UTC').isna().all())
if __name__=='__main__':unittest.main()
