"""Adapt the synthetic-pretrained propensity models to a SMALL real dataset (warm-start fine-tuning).

Usage:  python adapt_to_real.py real_customer_360.csv EV_FINANCE takeup_column
The real CSV must contain the same feature columns as customer_360.csv (see features.MODEL_FEATURES)
plus a 0/1 label column. Steps: (1) hold out 30% for validation, (2) keep the pretrained trees and add up to
60 extra low-learning-rate trees with early stopping on real data, (3) re-fit Platt calibration on real data.
If the adapted model is not better than the pretrained one on real validation logloss, the original is kept."""
import sys, joblib, numpy as np, pandas as pd, lightgbm as lgb
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import train_test_split
from sklearn.metrics import log_loss, roc_auc_score
from config import MODEL_DIR, SEED

def adapt(real_csv, product, label_col, extra_lr=0.01, max_extra=60):
    models = joblib.load(MODEL_DIR / "propensity_models.joblib"); m = models[product]
    df = pd.read_csv(real_csv); X, y = df[m.feats], df[label_col].values
    Xa, Xb, ya, yb = train_test_split(X, y, test_size=0.3, stratify=y, random_state=SEED)
    before = m.cal.predict_proba(m._raw(Xb).mean(1, keepdims=True))[:, 1]
    old_models, old_cal = m.models, m.cal
    new = []
    for i, bm in enumerate(old_models):
        p = dict(m.params, learning_rate=extra_lr, seed=SEED + i)
        new.append(lgb.train(p, lgb.Dataset(Xa, ya), num_boost_round=max_extra, init_model=bm, valid_sets=[lgb.Dataset(Xb, yb)],
                             callbacks=[lgb.early_stopping(15, verbose=False)]))
    m.models = new
    m.cal = LogisticRegression(C=1.0).fit(m._raw(Xa).mean(1, keepdims=True), ya)   # recalibrate on real
    after = m.cal.predict_proba(m._raw(Xb).mean(1, keepdims=True))[:, 1]
    print(f"{product}: real-val logloss {log_loss(yb, before):.4f} -> {log_loss(yb, after):.4f} | AUC {roc_auc_score(yb, before):.3f} -> {roc_auc_score(yb, after):.3f}")
    if log_loss(yb, after) >= log_loss(yb, before):
        m.models, m.cal = old_models, old_cal; print("No improvement -> keeping pretrained model")
    else:
        joblib.dump(models, MODEL_DIR / "propensity_models_adapted.joblib"); print("Saved propensity_models_adapted.joblib")

if __name__ == "__main__":
    adapt(*sys.argv[1:4])
