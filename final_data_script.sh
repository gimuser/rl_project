#!/usr/bin/env bash
set -e

# FINAL DATA SCRIPT
# Reads GUIDE files from ~/Desktop/Data_mission/data_finished.
# Uses a temporary copy of backend/app/data_pipeline from this repository's
# reference project only; never writes to ~/Desktop/new_one/RL_Agent.

ROOT="$HOME/Desktop/Data_mission"
SOURCE="$ROOT/data_finished"
TRAIN_GUIDE="$SOURCE/GUIDE_Train.csv"
TEST_GUIDE="$SOURCE/GUIDE_Test.csv"
REF="$HOME/Desktop/new_one/RL_Agent"
REF_PIPELINE="$REF/backend/app/data_pipeline"
WORK="$ROOT/.final_data_script_work"
TEMP="$WORK/RL_Agent_temp"
OUT="$ROOT/generated_final"
REDUCED="$OUT/source_13cols"
PROCESSED="$OUT/processed"
LIVE="$OUT/data_alert"
INCIDENT="$OUT/data_incident"
REPORT="$OUT/reports"
PYTHON="${PYTHON_BIN:-python3}"
CHUNK=50000
LIVE_TOTAL=80
SEED=20260816

KEEP_COLUMNS=(
  IncidentId Timestamp Category MitreTechniques IncidentGrade
  ActionGrouped ActionGranular EntityType EvidenceRole ThreatFamily
  OSFamily SuspicionLevel LastVerdict
)

EXPECTED_PROCESSED=(
  IncidentId Timestamp Category MitreTechniques IncidentGrade
  ActionGrouped ActionGranular EntityType EvidenceRole ThreatFamily
  OSFamily SuspicionLevel LastVerdict hour day month is_weekend
)

echo
echo "======================================================================"
echo " FINAL DATA SCRIPT"
echo "======================================================================"
echo

echo "[1/12] Checking inputs..."
test -d "$ROOT"
test -f "$TRAIN_GUIDE"
test -f "$TEST_GUIDE"
test -d "$REF_PIPELINE"
echo "[OK] GUIDE_Train.csv"
echo "[OK] GUIDE_Test.csv"
echo "[OK] old backend/app/data_pipeline"
echo "[OK] new_one/RL_Agent will NOT be modified"

echo
echo "[2/12] Cleaning only our previous generated workspace..."
rm -rf "$WORK" "$OUT"
mkdir -p "$WORK" "$TEMP/backend/app/data_pipeline" "$TEMP/data/processed" "$TEMP/models" "$REDUCED" "$PROCESSED" "$LIVE" "$INCIDENT" "$REPORT"
echo "[OK] Workspace ready"

echo
echo "[3/12] Copying the ACTUAL old pipeline into temporary workspace..."
cp -a "$REF_PIPELINE"/. "$TEMP/backend/app/data_pipeline/"
for f in loader.py cleaner.py validator.py encoder.py feature_engineering.py normalizer.py preprocessor.py exporter.py; do
  test -f "$TEMP/backend/app/data_pipeline/$f"
  echo "  [OK] $f"
done

echo
echo "[4/12] Reducing both GUIDE files to exact 13 columns + exact dedup..."
"$PYTHON" - "$TRAIN_GUIDE" "$TEST_GUIDE" "$REDUCED" "$WORK" "$CHUNK" <<'PY'
import csv, hashlib, sqlite3, sys
from pathlib import Path

train_path=Path(sys.argv[1]); test_path=Path(sys.argv[2]); out_dir=Path(sys.argv[3]); work_dir=Path(sys.argv[4]); chunk_size=int(sys.argv[5])
KEEP=["IncidentId","Timestamp","Category","MitreTechniques","IncidentGrade","ActionGrouped","ActionGranular","EntityType","EvidenceRole","ThreatFamily","OSFamily","SuspicionLevel","LastVerdict"]

def key(row):
    h=hashlib.sha256()
    for v in row:
        b=str(v).encode('utf-8',errors='surrogatepass'); h.update(len(b).to_bytes(8,'big')); h.update(b)
    return h.digest()

def reduce_file(src,dst):
    db_path=work_dir/(src.stem+'_dedup.sqlite3'); db_path.unlink(missing_ok=True)
    db=sqlite3.connect(db_path); db.execute('PRAGMA journal_mode=OFF'); db.execute('PRAGMA synchronous=OFF'); db.execute('PRAGMA temp_store=FILE'); db.execute('CREATE TABLE seen(k BLOB PRIMARY KEY)')
    total=kept=dups=0
    with src.open('r',encoding='utf-8-sig',newline='') as fin:
        reader=csv.DictReader(fin)
        missing=[c for c in KEEP if c not in (reader.fieldnames or [])]
        if missing: raise RuntimeError(f'{src}: missing columns {missing}')
        with dst.open('w',encoding='utf-8',newline='') as fout:
            writer=csv.writer(fout); writer.writerow(KEEP)
            for r in reader:
                total+=1; vals=tuple((r.get(c) or '').strip() for c in KEEP); d=key(vals)
                cur=db.execute('INSERT OR IGNORE INTO seen(k) VALUES (?)',(d,))
                if cur.rowcount==0: dups+=1; continue
                writer.writerow(vals); kept+=1
                if total%500000==0:
                    db.commit(); print(f'{src.name}: seen={total:,} kept={kept:,} exact_dups={dups:,}',flush=True)
    db.commit(); db.close(); db_path.unlink(missing_ok=True)
    print(f'{src.name} COMPLETE: input={total:,} kept={kept:,} exact_dups={dups:,}')
reduce_file(train_path,out_dir/'train_13cols.csv'); reduce_file(test_path,out_dir/'test_13cols.csv')
PY

echo
echo "[5/12] Resolving TRAIN/TEST IncidentId overlap..."
"$PYTHON" - "$REDUCED/train_13cols.csv" "$REDUCED/test_13cols.csv" "$REDUCED" <<'PY'
import csv,sys
from pathlib import Path
train=Path(sys.argv[1]); test=Path(sys.argv[2]); out=Path(sys.argv[3])
KEEP=["IncidentId","Timestamp","Category","MitreTechniques","IncidentGrade","ActionGrouped","ActionGranular","EntityType","EvidenceRole","ThreatFamily","OSFamily","SuspicionLevel","LastVerdict"]
def ids(p):
    s=set()
    with p.open('r',encoding='utf-8',newline='') as f:
        for r in csv.DictReader(f): s.add(str(r['IncidentId']))
    return s
tr=ids(train); te=ids(test); common=tr&te
print('Before overlap:',len(common))
if common:
    tmp=out/'train_disjoint.tmp'
    removed=0
    with train.open('r',encoding='utf-8',newline='') as fi, tmp.open('w',encoding='utf-8',newline='') as fo:
        rd=csv.DictReader(fi); wr=csv.DictWriter(fo,fieldnames=KEEP); wr.writeheader()
        for r in rd:
            if str(r['IncidentId']) in common: removed+=1
            else: wr.writerow(r)
    tmp.replace(train); print('Removed TRAIN rows:',removed)
tr=ids(train); te=ids(test); common=tr&te
print('After overlap:',len(common))
if common: raise RuntimeError('TRAIN/TEST IncidentId overlap remains')
PY

echo
echo "[6/12] Preparing temporary project for the actual old loader..."
cp "$REDUCED/train_13cols.csv" "$TEMP/data/processed/train_processed.csv"
cp "$REDUCED/test_13cols.csv" "$TEMP/data/processed/test_processed.csv"

echo
echo "[7/12] Running ACTUAL old backend/app/data_pipeline..."
(
  cd "$TEMP"
  PYTHONPATH="$TEMP/backend/app/data_pipeline" "$PYTHON" - "$PROCESSED" <<'PY'
import sys
from pathlib import Path
out=Path(sys.argv[1])
sys.path.insert(0,str(Path.cwd()/'backend/app/data_pipeline'))
from loader import load_train_data, load_test_data
from cleaner import clean_data
from validator import validate_data
from encoder import encode_data
from feature_engineering import create_features
from normalizer import normalize_data
print('===== LOADING =====')
train=load_train_data(); test=load_test_data(); print(train.shape,test.shape)
print('===== CLEANING ====='); train=clean_data(train); test=clean_data(test)
print('===== VALIDATION ====='); assert validate_data(train,'TRAIN'); assert validate_data(test,'TEST')
print('===== ENCODING ====='); train,test=encode_data(train,test)
print('===== FEATURE ENGINEERING ====='); train,test=create_features(train,test)
print('===== NORMALIZATION ====='); train,test=normalize_data(train,test)
out.mkdir(parents=True,exist_ok=True); train.to_csv(out/'train_processed.csv',index=False); test.to_csv(out/'test_processed.csv',index=False)
print('TRAIN:',train.shape); print('TEST:',test.shape)
PY
)

echo
echo "[8/12] Verifying 17-column processed output..."
"$PYTHON" - "$PROCESSED" <<'PY'
import csv,sys
from pathlib import Path
root=Path(sys.argv[1]); expected=["IncidentId","Timestamp","Category","MitreTechniques","IncidentGrade","ActionGrouped","ActionGranular","EntityType","EvidenceRole","ThreatFamily","OSFamily","SuspicionLevel","LastVerdict","hour","day","month","is_weekend"]
for s in ('train','test'):
    p=root/f'{s}_processed.csv'
    with p.open('r',encoding='utf-8',newline='') as f:
        r=csv.reader(f); h=next(r); n=sum(1 for _ in r)
    if h!=expected: raise RuntimeError(f'{s} schema mismatch: {h}')
    if n==0: raise RuntimeError(f'{s} empty')
    print(f'{s}: rows={n:,} columns={len(h)}')
PY

echo
echo "[9/12] Extracting exactly 80 live alerts using timestamp+occurrence lineage..."
"$PYTHON" - "$REDUCED/train_13cols.csv" "$REDUCED/test_13cols.csv" "$PROCESSED/train_processed.csv" "$PROCESSED/test_processed.csv" "$LIVE" "$LIVE_TOTAL" "$SEED" <<'PY'
import csv,random,sys,json
from pathlib import Path
from datetime import datetime,timezone
src_tr,src_te,pr_tr,pr_te,out=map(Path,sys.argv[1:6]); n=int(sys.argv[6]); seed=int(sys.argv[7]); random.seed(seed)
SRC=["IncidentId","Timestamp","Category","MitreTechniques","IncidentGrade","ActionGrouped","ActionGranular","EntityType","EvidenceRole","ThreatFamily","OSFamily","SuspicionLevel","LastVerdict"]
def rows(p):
    with p.open('r',encoding='utf-8',newline='') as f: return list(csv.DictReader(f))
def norm(v): return datetime.fromisoformat(v.replace('Z','+00:00')).astimezone(timezone.utc).isoformat()
def lineage(source,processed,split):
    sg={}; pg={}
    for i,r in enumerate(source): sg.setdefault(norm(r['Timestamp']),[]).append((i,r))
    for i,r in enumerate(processed): pg.setdefault(norm(r['Timestamp']),[]).append((i,r))
    result=[]
    for ts,vals in sg.items():
        pvals=pg.get(ts,[])
        for occ in range(min(len(vals),len(pvals))):
            si,sr=vals[occ]; pi,pr=pvals[occ]
            result.append({'source_split':split,'source_index':si,'processed_index':pi,'IncidentId':str(sr['IncidentId']),'Timestamp':sr['Timestamp'],'source_row':sr,'processed_row':pr})
    return result
train_src=rows(src_tr); test_src=rows(src_te); train_pr=rows(pr_tr); test_pr=rows(pr_te)
cands=lineage(train_src,train_pr,'train')+lineage(test_src,test_pr,'test')
by_inc={}
for x in cands: by_inc.setdefault(x['IncidentId'],x)
if len(by_inc)<n: raise RuntimeError(f'only {len(by_inc)} live candidates')
selected=random.sample(list(by_inc.values()),n); selected.sort(key=lambda x:(norm(x['Timestamp']),x['IncidentId']))
for i,x in enumerate(selected,1): x['alert_id']=f'LIVE-{i:04d}'
ids={x['IncidentId'] for x in selected}
if len(ids)!=n: raise RuntimeError('duplicate live IncidentId')
with (out/'live_source.csv').open('w',encoding='utf-8',newline='') as f:
    w=csv.DictWriter(f,fieldnames=['alert_id']+SRC); w.writeheader()
    for x in selected: w.writerow({'alert_id':x['alert_id'],**{c:x['source_row'][c] for c in SRC}})
fields=list(selected[0]['processed_row'].keys())
with (out/'live_processed.csv').open('w',encoding='utf-8',newline='') as f:
    w=csv.DictWriter(f,fieldnames=['alert_id']+fields); w.writeheader()
    for x in selected: w.writerow({'alert_id':x['alert_id'],**x['processed_row']})
with (out/'live_mapping.csv').open('w',encoding='utf-8',newline='') as f:
    w=csv.DictWriter(f,fieldnames=['alert_id','IncidentId','Timestamp','source_row_number','processed_row_number']); w.writeheader()
    for x in selected: w.writerow({'alert_id':x['alert_id'],'IncidentId':x['IncidentId'],'Timestamp':x['Timestamp'],'source_row_number':x['source_index'],'processed_row_number':x['processed_index']})
(out/'live_incidents.txt').write_text('\n'.join(sorted(ids))+'\n',encoding='utf-8')
(out/'manifest.json').write_text(json.dumps({'requested_alerts':n,'selected_alerts':n,'unique_incidents':len(ids),'random_seed':seed,'selection_rule':'one alert per unique IncidentId','mapping_rule':'normalized Timestamp + occurrence number','source_counts':{'train':sum(x['source_split']=='train' for x in selected),'test':sum(x['source_split']=='test' for x in selected)}},indent=2),encoding='utf-8')
print('LIVE:',n); print('LIVE unique IncidentId:',len(ids))
PY

echo
echo "[10/12] Holding out the 80 live IncidentIds from final processed TRAIN/TEST..."
"$PYTHON" - "$PROCESSED/train_processed.csv" "$PROCESSED/test_processed.csv" "$LIVE/live_incidents.txt" <<'PY'
import csv,sys
from pathlib import Path
tr,te,lf=map(Path,sys.argv[1:]); live={x.strip() for x in lf.read_text().splitlines() if x.strip()}
def filt(p):
    tmp=p.with_suffix('.tmp'); removed=0
    with p.open('r',encoding='utf-8',newline='') as fi, tmp.open('w',encoding='utf-8',newline='') as fo:
        rd=csv.DictReader(fi); wr=csv.DictWriter(fo,fieldnames=rd.fieldnames); wr.writeheader()
        for r in rd:
            if str(r['IncidentId']) in live: removed+=1
            else: wr.writerow(r)
    tmp.replace(p); return removed
print('TRAIN live rows removed:',filt(tr)); print('TEST live rows removed:',filt(te))
PY

echo
echo "[11/12] Creating incident-level TRAIN / VALIDATION / TEST..."
"$PYTHON" - "$PROCESSED/train_processed.csv" "$PROCESSED/test_processed.csv" "$INCIDENT" "$SEED" <<'PY'
import csv,random,sys,json
from collections import defaultdict
from pathlib import Path
tr,te,out,seed=Path(sys.argv[1]),Path(sys.argv[2]),Path(sys.argv[3]),int(sys.argv[4]); random.seed(seed)
def load(p):
    with p.open('r',encoding='utf-8',newline='') as f:
        r=csv.DictReader(f); return r.fieldnames,list(r)
tf,trw=load(tr); ef,tew=load(te)
tg=defaultdict(list); eg=defaultdict(list)
for r in trw: tg[str(r['IncidentId'])].append(r)
for r in tew: eg[str(r['IncidentId'])].append(r)
train_ids=set(tg); test_ids=set(eg)
if train_ids&test_ids: raise RuntimeError('final TRAIN/TEST IncidentId overlap')
ids=list(train_ids); random.shuffle(ids); n_val=int(len(ids)*0.25); val_ids=set(ids[:n_val]); final_train_ids=train_ids-val_ids
def write(path,fields,groups,ids):
    with path.open('w',encoding='utf-8',newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields); w.writeheader();
        for i in sorted(ids):
            for r in groups[i]: w.writerow(r)
write(out/'train_incident.csv',tf,tg,final_train_ids)
write(out/'validation_incident.csv',tf,tg,val_ids)
write(out/'test_incident.csv',ef,eg,test_ids)
(out/'train_incidents.txt').write_text('\n'.join(sorted(final_train_ids))+'\n',encoding='utf-8')
(out/'validation_incidents.txt').write_text('\n'.join(sorted(val_ids))+'\n',encoding='utf-8')
(out/'test_incidents.txt').write_text('\n'.join(sorted(test_ids))+'\n',encoding='utf-8')
report={'train_rows':sum(map(len,(tg[i] for i in final_train_ids))),'validation_rows':sum(map(len,(tg[i] for i in val_ids))),'test_rows':sum(map(len,(eg[i] for i in test_ids))),'train_incidents':len(final_train_ids),'validation_incidents':len(val_ids),'test_incidents':len(test_ids),'incident_overlap':0,'features':['Category','MitreTechniques','ActionGrouped','ActionGranular','EntityType','EvidenceRole','ThreatFamily','OSFamily','SuspicionLevel','hour','day','month','is_weekend'],'incident_id':'IncidentId','target':'IncidentGrade'}
(out/'split_report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps(report,indent=2))
PY

echo
echo "[12/12] FINAL AUDIT"
"$PYTHON" - "$PROCESSED" "$INCIDENT" "$LIVE" <<'PY'
import csv,sys
from pathlib import Path
p,i,l=map(Path,sys.argv[1:]); exp=['IncidentId','Timestamp','Category','MitreTechniques','IncidentGrade','ActionGrouped','ActionGranular','EntityType','EvidenceRole','ThreatFamily','OSFamily','SuspicionLevel','LastVerdict','hour','day','month','is_weekend']
def read(path):
    with path.open('r',encoding='utf-8',newline='') as f: r=csv.DictReader(f); return r.fieldnames,list(r)
def ids(rows): return {str(x['IncidentId']) for x in rows}
trf,tr=read(p/'train_processed.csv'); tef,te=read(p/'test_processed.csv'); vf,vr=read(i/'validation_incident.csv'); tif,ti=read(i/'test_incident.csv'); lr,lrows=read(l/'live_source.csv')
if trf!=exp or tef!=exp: raise RuntimeError('processed schema mismatch')
if len(lrows)!=80 or len(ids(lrows))!=80: raise RuntimeError('live count/uniqueness failure')
train_ids=ids(read(i/'train_incident.csv')[1]); val_ids=ids(vr); test_ids=ids(ti); live_ids=ids(lrows)
checks={'train_validation':len(train_ids&val_ids),'train_test':len(train_ids&test_ids),'validation_test':len(val_ids&test_ids),'live_train':len(live_ids&train_ids),'live_validation':len(live_ids&val_ids),'live_test':len(live_ids&test_ids)}
print('TRAIN rows:',len(tr)); print('VALIDATION rows:',len(vr)); print('TEST rows:',len(ti)); print('LIVE rows:',len(lrows)); print('OVERLAPS:',checks)
if any(checks.values()): raise RuntimeError(f'overlap audit failed: {checks}')
print('ALL FINAL CHECKS PASSED')
PY

echo
echo "CLEANING TEMPORARY WORKSPACE"
rm -rf "$WORK"

echo
echo "======================================================================"
echo " DATA MISSION FINISHED"
echo "======================================================================"
echo
echo "OUTPUT: $OUT"
echo "SOURCE GUIDES UNTOUCHED: $SOURCE"
echo "REFERENCE PROJECT UNTOUCHED: $REF"
echo
