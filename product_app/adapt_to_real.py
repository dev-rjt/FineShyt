"""Retrain on independently labelled PUBLIC or synthetic data, not confidential bank data.

Usage: python adapt_to_real.py dataset.csv EV_FINANCE takeup_column
No warm-start transfer claims: retrain on train customers, compare frozen models
on validation customers, then report once on test customers. For the hackathon,
never use real personal/confidential banking data.
"""
import sys,json,joblib
import pandas as pd
from config import MODEL_DIR,OUT_DIR,PRODUCTS
from propensity import PropensityModel,make_splits,_metrics

def adapt(csv,product,label_col):
    if product not in PRODUCTS: raise ValueError('Unknown product')
    models=joblib.load(MODEL_DIR/'propensity_models.joblib'); old=models[product]
    df=pd.read_csv(csv)
    if 'customer_id' not in df or df.customer_id.duplicated().any(): raise ValueError('Exactly one row per customer_id required')
    if not df[label_col].isin([0,1]).all(): raise ValueError('Outcome labels must be observed 0/1 values')
    labels=df[['customer_id',label_col]].rename(columns={label_col:'takeup_'+product})
    split=make_splits(df,labels).set_index('customer_id').split
    df=df.set_index('customer_id'); parts={s:df[split.reindex(df.index)==s] for s in ['train','val','test']}
    new=PropensityModel(product,old.feats).fit(parts['train'],parts['train'][label_col].values)
    before={s:_metrics(parts[s][label_col].values,old.predict(parts[s]).propensity.values,old.threshold) for s in ['val','test']}
    after={s:_metrics(parts[s][label_col].values,new.predict(parts[s]).propensity.values,new.threshold) for s in ['val','test']}
    use_new=after['val']['logloss']<before['val']['logloss']
    if use_new: models[product]=new
    joblib.dump(models,MODEL_DIR/'propensity_models_adapted.joblib')
    report=dict(product=product,selected='retrained' if use_new else 'pretrained',pretrained=before,retrained=after,
        note='Validation used for adaptation acceptance; test not used in model choice. Synthetic pretraining is not evidence of real-world transfer.')
    (OUT_DIR/'adaptation_report.json').write_text(json.dumps(report,indent=2)); print(json.dumps(report,indent=2))
if __name__=='__main__': adapt(*sys.argv[1:4])
