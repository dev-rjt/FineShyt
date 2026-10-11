"""Product propensity. Selection, calibration and threshold use TRAIN only.

Customer-level train/val/test partition is shared with transaction classification.
Training CV selects logistic regression or LightGBM by log loss. OOF logits fit
regularised Platt scaling; cross-fitted calibration selects an F1 threshold.
Validation/test do not participate in any fitting or model choice.
"""
import itertools, json, joblib
import numpy as np
import pandas as pd
import lightgbm as lgb
from sklearn.base import clone
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.impute import SimpleImputer
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import train_test_split, StratifiedKFold
from sklearn.metrics import (roc_auc_score, average_precision_score, log_loss,
    brier_score_loss, precision_recall_curve, confusion_matrix, precision_score,
    recall_score, f1_score, accuracy_score)
from config import *
from features import MODEL_FEATURES

KEY_FEATURES = {
    'EV_FINANCE': ['annual_mileage','fuel_spend_m','vehicle_age','fuel_type_code'],
    'GREEN_HOME': ['elec_kwh_yr','gas_kwh_yr','home_impr_spend_m','income_idx'],
    'SOLAR_FINANCE': ['elec_kwh_yr','income_idx','home_impr_spend_m'],
    'PAPERLESS': ['paper_share','digital_tx_m','branch_visits_m']}

def make_splits(f, takeup):
    if f.customer_id.duplicated().any() or takeup.customer_id.duplicated().any():
        raise ValueError('Customer IDs must be unique')
    ids = f.customer_id.to_numpy(dtype=object)  # pandas 3 returns an Arrow array from .values
    lab = takeup.set_index('customer_id').reindex(ids)
    if lab.filter(like='takeup_').isna().any().any(): raise ValueError('Missing customer labels')
    outcomes=lab.filter(like='takeup_')
    if outcomes.shape[1]==0 or not outcomes.isin([0,1]).all().all(): raise ValueError('Take-up labels must be 0/1')
    strat = outcomes.max(axis=1).values
    tr, rest = train_test_split(ids, test_size=1-SPLIT['train'], random_state=SEED, stratify=strat)
    va, te = train_test_split(rest, test_size=SPLIT['test']/(SPLIT['val']+SPLIT['test']),
        random_state=SEED, stratify=pd.Series(strat,index=ids).loc[rest].values)
    return pd.concat([pd.DataFrame({'customer_id':a,'split':s}) for a,s in
        [(tr,'train'),(va,'val'),(te,'test')]], ignore_index=True)

def _auc_ci(y,p,n=500):
    rng=np.random.default_rng(SEED); vals=[]
    for _ in range(n):
        ix=rng.integers(0,len(y),len(y))
        if len(np.unique(y[ix]))==2: vals.append(roc_auc_score(y[ix],p[ix]))
    return np.percentile(vals,[2.5,97.5]).tolist() if vals else [None,None]

def _metrics(y,p,threshold=.5):
    y=np.asarray(y); p=np.clip(np.asarray(p),1e-8,1-1e-8); yh=p>=threshold
    if not len(y): return {'n':0,'status':'NO_EVALUATION_ROWS'}
    bins=[]; ece=0.
    for i in range(10):
        mask=(p>=i/10)&(p<(i+1)/10)
        if mask.any():
            obs=float(y[mask].mean()); pred=float(p[mask].mean())
            bins.append({'lower':i/10,'upper':(i+1)/10,'n':int(mask.sum()),'mean_prediction':pred,'observed_rate':obs})
            ece+=mask.mean()*abs(obs-pred)
    k=max(1,int(.1*len(y))); order=np.argsort(-p,kind='stable'); two=len(np.unique(y))==2
    return dict(auc=float(roc_auc_score(y,p)) if two else None,
        pr_auc=float(average_precision_score(y,p)) if y.sum() else None,
        logloss=float(log_loss(y,p,labels=[0,1])),brier=float(brier_score_loss(y,p)),
        lift_top10=float(y[order[:k]].mean()/y.mean()) if y.mean() else None,
        precision=float(precision_score(y,yh,zero_division=0)),recall=float(recall_score(y,yh,zero_division=0)),
        f1=float(f1_score(y,yh,zero_division=0)),accuracy=float(accuracy_score(y,yh)),
        confusion_matrix=confusion_matrix(y,yh,labels=[0,1]).tolist(),threshold=float(threshold),
        ece_10bins=float(ece),calibration_bins=bins,prevalence=float(y.mean()),n=len(y),n_pos=int(y.sum()))

def _lr(C=.3):
    return make_pipeline(SimpleImputer(strategy='median',add_indicator=True,keep_empty_features=True),
        StandardScaler(),LogisticRegression(C=C,max_iter=2000,random_state=SEED))

def _folds(y):
    n=min(5,int(np.bincount(np.asarray(y,dtype=int),minlength=2).min()))
    if n<3: raise ValueError('Need at least three positive and three negative training examples per product')
    return list(StratifiedKFold(n_splits=n,shuffle=True,random_state=SEED).split(np.zeros(len(y)),y))

def _crossfit(est,X,y,folds):
    raw=np.empty(len(y)); models=[]; losses=[]
    for a,b in folds:
        m=clone(est).fit(X.iloc[a],y[a]); models.append(m)
        z=m.decision_function(X.iloc[b]) if hasattr(m,'decision_function') else m.predict(X.iloc[b],raw_score=True)
        raw[b]=z; losses.append(log_loss(y[b],1/(1+np.exp(-np.clip(z,-40,40))),labels=[0,1]))
    return raw,models,losses

def tune(X,y,folds=None):
    folds=folds or _folds(y); rows=[]; ds=lgb.Dataset(X,y,free_raw_data=False)
    for lr,nl,mcs in itertools.product(GRID['learning_rate'],GRID['num_leaves'],GRID['min_child_samples']):
        p=dict(LGB_BASE,learning_rate=lr,num_leaves=nl,min_child_samples=mcs,seed=SEED)
        cv=lgb.cv(p,ds,num_boost_round=MAX_ROUNDS,folds=folds,seed=SEED,
            callbacks=[lgb.early_stopping(EARLY_STOP,verbose=False)])
        k='valid binary_logloss-mean'; j=int(np.argmin(cv[k]))
        rows.append(dict(learning_rate=lr,num_leaves=nl,min_child_samples=mcs,
            cv_logloss=float(cv[k][j]),cv_std=float(cv['valid binary_logloss-stdv'][j]),best_rounds=j+1))
    g=pd.DataFrame(rows).sort_values('cv_logloss').reset_index(drop=True); b=g.iloc[0]
    p=dict(LGB_BASE,learning_rate=float(b.learning_rate),num_leaves=int(b.num_leaves),min_child_samples=int(b.min_child_samples))
    return p,int(b.best_rounds),g

class PropensityModel:
    def __init__(self,product,feats): self.product,self.feats=product,feats
    def _X(self,X): return X.reindex(columns=self.feats).apply(pd.to_numeric,errors='coerce').replace([np.inf,-np.inf],np.nan)
    def _member_raw(self,m,X):
        return m.decision_function(X) if hasattr(m,'decision_function') else m.predict(X,raw_score=True)
    def _raw(self,X):
        xx=self._X(X); return np.column_stack([self._member_raw(m,xx) for m in self.models])
    def fit(self,Xtr,ytr,Xva=None,yva=None):
        X=self._X(Xtr); y=np.asarray(ytr,dtype=int); folds=_folds(y); choices=[]
        best_lr=None
        for C in [.03,.1,.3,1.,3.]:
            raw,mods,loss=_crossfit(_lr(C),X,y,folds)
            choices.append({'family':'logistic_regression','C':C,'cv_logloss':float(np.mean(loss))})
            if best_lr is None or np.mean(loss)<best_lr[0]: best_lr=(np.mean(loss),C,raw,mods)
        self.params,self.rounds,self.grid=tune(X,y,folds)
        params={k:v for k,v in self.params.items() if k not in ['metric','n_jobs']}
        tree=lgb.LGBMClassifier(**params,n_jobs=2,n_estimators=self.rounds,random_state=SEED)
        tree_raw,tree_mods,tree_losses=_crossfit(tree,X,y,folds)
        choices.append({'family':'lightgbm','cv_logloss':float(np.mean(tree_losses)),**self.params,'rounds':self.rounds})
        self.selection=pd.DataFrame(choices)
        if best_lr[0]<=np.mean(tree_losses):
            self.family='logistic_regression'; self.lr_C=best_lr[1]
            oof,self.uncertainty_models=best_lr[2:]; self.models=[_lr(self.lr_C).fit(X,y)]
        else:
            self.family='lightgbm'; oof,self.uncertainty_models=tree_raw,tree_mods; self.models=[]
            for s in range(N_ENSEMBLE):
                m=clone(tree).set_params(random_state=SEED+s,bagging_seed=SEED+s,feature_fraction_seed=SEED+s).fit(X,y)
                self.models.append(m)
        # Calibration input is always an out-of-fold prediction, never a fitted-row prediction.
        self.cal=LogisticRegression(C=1.0,max_iter=2000).fit(oof[:,None],y)
        crosscal=np.empty(len(y))
        for a,b in folds:
            cal=LogisticRegression(C=1.0,max_iter=2000).fit(oof[a,None],y[a])
            crosscal[b]=cal.predict_proba(oof[b,None])[:,1]
        prec,rec,thr=precision_recall_curve(y,crosscal); f1=2*prec*rec/(prec+rec+1e-12)
        self.threshold=float(thr[np.argmax(f1[:-1])])
        self.support={k:np.nanpercentile(X[k],[1,99]) if X[k].notna().any() else [np.nan,np.nan] for k in self.feats}
        self.reference=X.median(); self.n_positive=int(y.sum())
        if self.family=='lightgbm': gain=np.mean([m.booster_.feature_importance('gain') for m in self.models],axis=0)
        else: gain=np.abs(self.models[0][-1].coef_[0][:len(self.feats)])
        self.importance=pd.Series(gain/max(gain.sum(),1e-12),index=self.feats).sort_values(ascending=False)
        self.oof_metrics=_metrics(y,crosscal,self.threshold)
        self.oof_note='Diagnostic only: CV model choice and cross-fitted calibration use training labels; validation/test are the independent estimates.'
        return self
    def predict(self,X):
        xx=self._X(X)
        if not len(xx): return pd.DataFrame(columns=['propensity','confidence'],index=X.index)
        p=self.cal.predict_proba(self._raw(X).mean(axis=1)[:,None])[:,1]
        member=np.column_stack([self.cal.predict_proba(self._member_raw(m,xx)[:,None])[:,1] for m in self.uncertainty_models])
        key=KEY_FEATURES[self.product]; complete=xx[key].notna().mean(axis=1).values
        support=np.mean([xx[k].between(*self.support[k]).fillna(False).values for k in key],axis=0)
        agreement=1-np.minimum(1,member.std(axis=1)/.10)
        conf=np.clip((.4*agreement+.3*complete+.3*support)*min(1,self.n_positive/100),0,1)
        return pd.DataFrame({'propensity':p,'confidence':conf},index=X.index)
    def contributions(self,X):
        xx=self._X(X)
        if not len(xx): return np.empty((0,len(self.feats)))
        if self.family=='lightgbm':
            c=np.mean([m.booster_.predict(xx,pred_contrib=True)[:,:-1] for m in self.models],axis=0)
        else:
            m=self.models[0]; transformed=m[:-1].transform(xx)
            ref=m[:-1].transform(pd.DataFrame([self.reference],columns=self.feats))[0]
            c=(transformed[:,:len(self.feats)]-ref[:len(self.feats)])*m[-1].coef_[0][:len(self.feats)]
        return c*float(self.cal.coef_[0,0])
    def evidence(self,X,top_k=3):
        xx=self._X(X); c=self.contributions(X); out=[]
        for j,(_,row) in enumerate(xx.iterrows()):
            ix=[i for i in np.argsort(-c[j]) if c[j,i]>.01 and pd.notna(row.iloc[i])][:top_k]
            out.append([{'reason_code':'POSITIVE_MODEL_SIGNAL_'+self.feats[i].upper(),
                'feature':self.feats[i],'observed_value':float(row.iloc[i]),
                'log_odds_contribution':round(float(c[j,i]),5)} for i in ix])
        return out
    def reason_codes(self,X,top_k=3): return [[e['reason_code'] for e in row] for row in self.evidence(X,top_k)]

def baseline_lr(Xtr,ytr,Xs):
    m=_lr().fit(Xtr,ytr); return m,{k:m.predict_proba(v)[:,1] for k,v in Xs.items()}

def train_all(F,labels,rules,split,verbose=True):
    lab=labels.set_index('customer_id').reindex(F.index); sp=split.set_index('customer_id').split.reindex(F.index)
    if sp.isna().any() or lab.isna().any().any(): raise ValueError('Unaligned labels or splits')
    models,report={},{}
    for prod in PRODUCTS:
        cand=rules[f'eligible_{prod}'].reindex(F.index).fillna(False)
        # Candidate fields in label files are NOT features or training gates.
        y=lab[f'takeup_{prod}']; feats=MODEL_FEATURES[prod]
        xs={s:F[cand&(sp==s)] for s in ['train','val','test']}
        ys={s:y.reindex(xs[s].index).to_numpy(dtype=int) for s in xs}
        m=PropensityModel(prod,feats).fit(xs['train'],ys['train']); models[prod]=m
        _,baseline=baseline_lr(xs['train'][feats],ys['train'],{s:xs[s][feats] for s in ['val','test']})
        r={s:_metrics(ys[s],m.predict(xs[s]).propensity.values,m.threshold) for s in xs}
        for s in ['val','test']:
            r[f'baseline_logreg_{s}']=_metrics(ys[s],baseline[s])
            r[f'baseline_prevalence_{s}']=_metrics(ys[s],np.full(len(ys[s]),ys['train'].mean()))
        r['selected_model']=m.family
        r['model_hyperparameters']={'C':m.lr_C} if m.family=='logistic_regression' else {**m.params,'rounds':m.rounds}
        r['training_cv_choices']=json.loads(m.selection.to_json(orient='records'))
        r['threshold']=m.threshold; r['threshold_method']='Maximum F1 on training cross-fitted OOF calibrated scores; illustrative marketing operating point, not financial eligibility.'
        r['calibration_method']='Regularised sigmoid (C=1) on training OOF logits; no validation/test fitting.'
        r['confidence_method']='Heuristic: (0.4 fold-model agreement + 0.3 key-input completeness + 0.3 training p1-p99 support) * min(1, training positives/100); not a probability of correctness.'
        r['auc_test_ci95']=_auc_ci(ys['test'],m.predict(xs['test']).propensity.values)
        r['overfit_gap_auc_train_minus_test']=r['train']['auc']-r['test']['auc']
        r['training_oof_diagnostic']=m.oof_metrics; r['training_oof_note']=m.oof_note
        # Descriptive subgroup metrics; suppress small groups rather than imply fairness certification.
        r['subgroup_validation']={}
        for attr,groups in [('age_band',pd.cut(xs['val'].age,[0,30,60,120],labels=['18-30','31-60','61+'])),('region',xs['val'].region)]:
            p=m.predict(xs['val']).propensity.values
            r['subgroup_validation'][attr]={str(g):_metrics(ys['val'][groups.eq(g).values],p[groups.eq(g).values],m.threshold)
                if groups.eq(g).sum()>=30 and ys['val'][groups.eq(g).values].sum()>=5 else {'n':int(groups.eq(g).sum()),'status':'INSUFFICIENT_SUBGROUP_SAMPLE'} for g in groups.dropna().unique()}
        report[prod]=r
        m.grid.to_csv(OUT_DIR/f'cv_grid_{prod}.csv',index=False)
        m.selection.to_csv(OUT_DIR/f'model_selection_{prod}.csv',index=False)
        m.importance.to_csv(OUT_DIR/f'feature_weights_{prod}.csv',header=['normalised_importance'])
        if verbose: print(f'{prod}: {m.family}, val AUC={r["val"]["auc"]:.4f}, test AUC={r["test"]["auc"]:.4f}, test logloss={r["test"]["logloss"]:.4f}',flush=True)
    joblib.dump(models,MODEL_DIR/'propensity_models.joblib')
    (OUT_DIR/'evaluation_report.json').write_text(json.dumps(report,indent=2,allow_nan=False))
    return models,report
