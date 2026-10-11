"""Reusable inference. Never trains or accepts outcome labels."""
import json, argparse, joblib
import numpy as np
import pandas as pd
from config import *
from rules import eligibility
from carbon_engine import estimate_impact

def recommendations(F,models,split=None):
    if 'customer_id' in F: F=F.set_index('customer_id')
    if F.index.duplicated().any(): raise ValueError('Duplicate customer IDs')
    rules=eligibility(F); rows=[]
    for prod in PRODUCTS:
        m=models[prod]; el=rules[f'eligible_{prod}']; X=F[el]; predictions=m.predict(X); evidence=m.evidence(X)
        for (cid,row),ev,(_,p) in zip(X.iterrows(),evidence,predictions.iterrows()):
            impact=estimate_impact(prod,row)
            recommend=bool(p.propensity>=m.threshold and p.confidence>=.5 and len(ev)>0)
            rows.append(dict(customer_id=cid,opportunity=prod,product_id=PRODUCT_IDS[prod],
                propensity=float(p.propensity),confidence=float(p.confidence),recommend=recommend,
                financial_eligibility='NOT_ASSESSED',suitability_status='CANDIDATE',model_family=m.family,
                reason_codes=';'.join(e['reason_code'] for e in ev),evidence_json=json.dumps(ev),
                data_timestamp=row.get('data_timestamp',str(CUTOFF_DATE.date())),
                impact_status=impact['status'],est_avoided_kg_co2e_yr=impact.get('avoided_kg_co2e_per_year'),
                impact_json=json.dumps(impact),review_required=bool(p.confidence<.5 or not ev or impact['status']!='OK')))
        for cid in F.index[~el]:
            rows.append(dict(customer_id=cid,opportunity=prod,product_id=PRODUCT_IDS[prod],propensity=np.nan,
                confidence=np.nan,recommend=False,financial_eligibility='NOT_ASSESSED',suitability_status='EXCLUDED',
                model_family=m.family,reason_codes='EXCLUDED:'+rules.loc[cid,f'exclusion_{prod}'],evidence_json='[]',
                data_timestamp=F.loc[cid].get('data_timestamp',str(CUTOFF_DATE.date())),impact_status='NOT_APPLICABLE',
                est_avoided_kg_co2e_yr=np.nan,impact_json='{}',review_required=False))
    R=pd.DataFrame(rows)
    if split is not None: R['split']=R.customer_id.map(split.set_index('customer_id').split)
    return R

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('features_csv'); ap.add_argument('--output',default=str(OUT_DIR/'inference_predictions.csv'))
    args=ap.parse_args(); models=joblib.load(MODEL_DIR/'propensity_models.joblib')
    R=recommendations(pd.read_csv(args.features_csv),models); R.to_csv(args.output,index=False)
    print(f'Saved {len(R)} customer-product predictions to {args.output}')
if __name__=='__main__': main()
