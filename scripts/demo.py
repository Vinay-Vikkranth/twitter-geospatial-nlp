"""Exercise the original chunked extractor using invented records and a polygon."""
from pathlib import Path
import sys,csv,json,sqlite3,re
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from shapely.geometry import box
import pandas as pd
from pipeline.extract import SCHEMA,process_file
from pipeline.common import sha
from pipeline.labels import validate
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
ROOT=Path(__file__).resolve().parents[1]
def run_demo(out):
    out=Path(out);out.mkdir(parents=True,exist_ok=True)
    src=ROOT/'data/sample/tweets.csv'
    fields=['message_id','tweet_date','text','latitude','longitude']
    rows=[['syn-1','2023-03-27T01:00:00Z','A fictional shooting report',41.5,-87.5],
        ['syn-1','2023-03-27T01:00:00Z','A fictional shooting report',41.5,-87.5],
        ['syn-2','2023-03-27T01:00:00Z','gun violence sample',41.6,-87.6],
        ['syn-2','2023-03-27T01:00:00Z','a different gun violence sample',41.6,-87.6],
        ['syn-3','2023-03-27T01:00:00Z','gun violence outside polygon',30,-100],
        ['syn-4','2023-03-27T01:00:00Z','coffee at home',41.5,-87.5],
        ['syn-5','2023-03-28T01:00:00Z','A gun violence discussion',41.5,-87.5]]
    with src.open('w',newline='',encoding='utf-8') as f:
        w=csv.writer(f);w.writerow(fields);w.writerows(rows)
    db=sqlite3.connect(':memory:');db.executescript(SCHEMA)
    key=('synthetic city','synthetic state');tz={key:'America/Chicago'}
    windows=[('SYN-INC-1','2023-03-27','Synthetic City','Synthetic State','America/Chicago','2023-03-26',-1,'sample'),('SYN-INC-1','2023-03-27','Synthetic City','Synthetic State','America/Chicago','2023-03-27',0,'sample')]
    db.executemany('INSERT INTO windows VALUES(?,?,?,?,?,?,?,?)',windows)
    lookup={(key,'2023-03-26'):[('SYN-INC-1',-1)],(key,'2023-03-27'):[('SYN-INC-1',0)]}
    with db:process_file(db,src,sha(src),{key:box(-88,41,-87,42)},tz,lookup,re.compile(r'gun violence|shooting',re.I),'UTC',2)
    tweets=pd.read_sql_query('SELECT * FROM tweets ORDER BY message_id',db);matches=pd.read_sql_query('SELECT * FROM matches ORDER BY message_id',db)
    tweets.to_csv(out/'tweets.csv',index=False);matches.to_csv(out/'matches.csv',index=False)
    result={'data':'SYNTHETIC','rows_read':len(rows),'selected_unique_tweets':len(tweets),'links':len(matches),'conflicting_ids':db.execute('SELECT count(DISTINCT message_id) FROM conflicts').fetchone()[0],'llm_inference_run':False}
    # This hand-written object demonstrates schema validation only. It is not an LLM result.
    example={'e':'community concern','c':70,'gv':True,'lg':0,'rs':40,'rl':0,'sc':30,'te':0,'la':0,'summary':'Fictional discussion of gun violence.'}
    (out/'schema_example_NOT_MODEL_OUTPUT.json').write_text(json.dumps(validate(json.dumps(example)),indent=2))
    (out/'metrics.json').write_text(json.dumps(result,indent=2));db.close();return result,tweets,matches
def main():
    result,_,_=run_demo(ROOT/'outputs/demo')
    fig,ax=plt.subplots(figsize=(8,4),layout='constrained');ax.barh(['Input rows','Selected unique tweets','Incident links','Conflicting IDs'],[result[k] for k in ['rows_read','selected_unique_tweets','links','conflicting_ids']],color=['#356db3','#137c8b','#137c8b','#c75b40']);ax.set(xlabel='Count',title='Synthetic extractor run | no real tweets or model inference');fig.savefig(ROOT/'docs/assets/demo.png',dpi=160);plt.close(fig);print(json.dumps(result,indent=2))
if __name__=='__main__':main()
