"""Reproducible training/evaluation pipeline; --regenerate rebuilds synthetic data."""
import argparse, json, time, hashlib, platform, importlib.metadata
import numpy as np
import pandas as pd
import joblib
from config import *
from data_generation import make_all
from txn_classifier import train_txn_classifier
from features import build_customer_360
from rules import eligibility
from propensity import make_splits, train_all, _metrics
from inference import recommendations

TABLES={'customers':'customers','transactions':'transactions','products':'products','vehicles':'vehicles',
    'energy':'energy_usage','digital':'digital_usage','green_products':'green_products',
    'emissions_factors':'emissions_factors','labels':'labels_takeup','txn_labels':'labels_txn_category'}

def load_data():
    missing=[f'{v}.csv' for v in TABLES.values() if not (DATA_DIR/f'{v}.csv').exists()]
    if missing: raise FileNotFoundError(f'Missing {missing}. Run python run_pipeline.py --regenerate')
    return {k:pd.read_csv(DATA_DIR/f'{v}.csv') for k,v in TABLES.items()}

def compare_original(F,labels,split):
    path=ROOT/'baseline'/'propensity_models_portable.joblib'
    if not path.exists(): return {}
    original=joblib.load(path); saved=json.loads((ROOT/'baseline'/'original_evaluation_report.json').read_text())
    sp=split.set_index('customer_id').split; lab=labels.set_index('customer_id'); gate=eligibility(F); out={}
    for prod,m in original.items():
        out[prod]={}
        for name in ['val','test']:
            X=F[gate[f'eligible_{prod}'] & (sp.reindex(F.index)==name)]
            Z=np.column_stack([bm.predict(X[m.feats],raw_score=True) for bm in m.models])
            p=m.cal.predict_proba(Z.mean(axis=1)[:,None])[:,1]
            out[prod][name]=_metrics(lab.loc[X.index,f'takeup_{prod}'].values,p,m.threshold)
            out[prod][name]['matches_supplied_auc']=bool(abs(out[prod][name]['auc']-saved[prod][name]['auc'])<1e-10)
    return out

def main(regenerate=False):
    start=time.perf_counter(); d=make_all() if regenerate else load_data()
    split=make_splits(d['customers'],d['labels']); split.to_csv(DATA_DIR/'customer_splits.csv',index=False)
    vec,clf,txn_rep=train_txn_classifier(d['transactions'],d['txn_labels'],split)
    (OUT_DIR/'txn_evaluation.json').write_text(json.dumps(txn_rep,indent=2,allow_nan=False))
    F=build_customer_360(d,vec,clf); F.to_csv(DATA_DIR/'customer_360.csv',index=False); Fi=F.set_index('customer_id')
    original=compare_original(Fi,d['labels'],split)
    models,rep=train_all(Fi,d['labels'],eligibility(Fi),split)
    rep['txn_categorisation']=txn_rep; rep['original_reproduced']=original
    rep['methodology']=dict(data='Synthetic: 5000 customers, 684202 transactions; no real banking data',
        customer_split_counts=split.split.value_counts().to_dict(),cutoff_date=str(CUTOFF_DATE.date()),
        outcome_window_months=OUTCOME_WINDOW_MONTHS,
        selection='Train-only 5-fold CV logloss: regularised logistic regression C grid vs LightGBM grid',
        validation='Independent validation: never used for model selection, calibration or threshold fitting',
        test='Same supplied customer split; original results inspected during audit. Fresh external/temporal test needed before real-world accuracy claims.',
        limitations=['Synthetic take-up comes from a logistic label generator; linear models have a structural advantage',
            'OOF training diagnostics can be optimistic after CV hyperparameter selection',
            'Confidence is an input-quality/model-stability heuristic, not calibrated probability of correctness',
            'Products passed by rules are candidates only; credit eligibility not assessed'])
    R=recommendations(Fi,models,split); R.to_csv(OUT_DIR/'recommendations_all.csv',index=False)
    T=R[R.split=='test'].copy(); labels=d['labels'].set_index('customer_id')
    T['actual_takeup']=[int(labels.loc[cid,f'takeup_{prod}']) for cid,prod in zip(T.customer_id,T.opportunity)]
    T.to_csv(OUT_DIR/'test_predictions.csv',index=False)
    metrics=[]
    for prod in PRODUCTS:
        for name in ['val','test']:
            for model,key in [('selected',name),('logistic_baseline',f'baseline_logreg_{name}'),('prevalence_baseline',f'baseline_prevalence_{name}')]:
                metrics.append(dict(product=prod,split=name,model=model,**{k:v for k,v in rep[prod][key].items() if not isinstance(v,(list,dict))}))
    pd.DataFrame(metrics).to_csv(OUT_DIR/'metrics_summary.csv',index=False)
    metadata=dict(python=platform.python_version(),versions={m:importlib.metadata.version(m) for m in ['numpy','pandas','scikit-learn','lightgbm','joblib']},
        seed=SEED,input_sha256={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in DATA_DIR.glob('*.csv') if p.name not in ['customer_360.csv','customer_splits.csv']},
        elapsed_seconds=round(time.perf_counter()-start,2))
    rep['reproducibility']=metadata
    (OUT_DIR/'evaluation_report.json').write_text(json.dumps(rep,indent=2,allow_nan=False))
    (OUT_DIR/'run_metadata.json').write_text(json.dumps(metadata,indent=2))
    from business_insights import export_business
    export_business(R,F)
    print('Recommended counts:',R[R.recommend].groupby('opportunity').size().to_dict(),flush=True)
    print('Pipeline seconds:',metadata['elapsed_seconds'],flush=True)
    return d,F,models,R
if __name__=='__main__':
    ap=argparse.ArgumentParser(); ap.add_argument('--regenerate',action='store_true'); args=ap.parse_args(); main(args.regenerate)
