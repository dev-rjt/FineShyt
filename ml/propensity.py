"""FR3 - Propensity models (one per product).

Algorithm : LightGBM gradient-boosted trees, 5-seed bagged ensemble, Platt-calibrated.
Training  : only rules-eligible ("candidate") customers, customer-level 70/15/15 split.
Anti-overfit / anti-underfit controls
  * low learning rate (grid 0.02/0.05) + number of rounds chosen by 5-fold CV early stopping on TRAIN only
  * shallow trees (num_leaves 4/8/16), min_child_samples 20/50, L1/L2 regularisation, row+feature subsampling
  * hyper-parameters picked by CV logloss (not by test); val set used ONLY for calibration + threshold; test untouched
  * diagnostics: train vs CV vs val vs test AUC gap; compared with logistic-regression & prevalence baselines
Confidence : 0.4*ensemble agreement + 0.3*feature completeness + 0.3*in-distribution support (documented, != propensity)
"""
import itertools, joblib, json, numpy as np, pandas as pd, lightgbm as lgb
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.impute import SimpleImputer
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import train_test_split
from sklearn.metrics import roc_auc_score, average_precision_score, log_loss, brier_score_loss, precision_recall_curve
from config import *
from features import MODEL_FEATURES

KEY_FEATURES = {  # inputs whose absence reduces confidence
    "EV_FINANCE": ["annual_mileage", "fuel_spend_m", "vehicle_age", "fuel_type_code"],
    "GREEN_HOME_LOAN": ["elec_kwh_yr", "gas_kwh_yr", "home_impr_spend_m", "income_idx"],
    "SOLAR_FINANCE": ["elec_kwh_yr", "income_idx", "home_impr_spend_m"],
    "PAPERLESS_BANKING": ["paper_share", "digital_tx_m", "branch_visits_m"]}

REASON_CODES = {  # feature -> reason code (emitted when its SHAP contribution is positive)
    "fuel_spend_m": "HIGH_FUEL_SPEND", "annual_mileage": "HIGH_ANNUAL_MILEAGE", "vehicle_age": "OLDER_VEHICLE",
    "has_vehicle_loan": "EXISTING_VEHICLE_LOAN", "fuel_share_of_spend": "FUEL_SHARE_OF_SPEND_HIGH",
    "n_fuel_txn": "FREQUENT_REFUELLING", "fuel_spend_trend": "RISING_FUEL_SPEND", "fuel_type_code": "ICE_VEHICLE_TYPE",
    "sustainability_preference": "HIGH_SUSTAINABILITY_PREFERENCE", "urban": "URBAN_CHARGING_ACCESS",
    "income_idx": "INCOME_SUPPORTS_AFFORDABILITY", "home_owner": "HOME_OWNER", "has_mortgage": "EXISTING_MORTGAGE",
    "has_isa": "EXISTING_INVESTMENTS", "elec_kwh_yr": "HIGH_ELECTRICITY_USE", "gas_kwh_yr": "HIGH_GAS_USE",
    "heating_kwh_yr": "HIGH_HEATING_ENERGY_USE", "winter_gas_share": "HIGH_WINTER_HEATING_LOAD",
    "home_impr_spend_m": "HOME_IMPROVEMENT_ACTIVITY", "spend_utilities_m": "HIGH_UTILITY_SPEND",
    "spend_electricity_m": "HIGH_ELECTRICITY_SPEND", "spend_gas_m": "HIGH_GAS_SPEND",
    "paper_share": "HIGH_PAPER_STATEMENT_SHARE", "digital_tx_m": "HIGH_DIGITAL_ACTIVITY",
    "branch_visits_m": "LOW_BRANCH_USE", "digital_usage": "HIGH_DIGITAL_ENGAGEMENT", "digital_tx_trend": "RISING_DIGITAL_ACTIVITY",
    "age": "AGE_PROFILE_FIT", "total_balance": "STRONG_BALANCE_PROFILE", "inflow_m": "STABLE_INCOME_INFLOW",
    "spend_public_transport_m": "PUBLIC_TRANSPORT_USER", "spend_automotive_m": "AUTOMOTIVE_SPEND",
    "vehicle_type_code": "VEHICLE_TYPE_FIT", "has_savings": "HAS_SAVINGS", "has_credit_card": "HAS_CREDIT_CARD", "n_products": "MULTI_PRODUCT_CUSTOMER"}

def make_splits(f, takeup):
    """Customer-level split, stratified on 'any take-up' so every split has positives."""
    ids = f.customer_id.values; strat = takeup[[c for c in takeup if c.startswith("takeup_")]].max(1).values
    tr, rest = train_test_split(ids, test_size=1 - SPLIT["train"], random_state=SEED, stratify=strat)
    va, te = train_test_split(rest, test_size=SPLIT["test"] / (SPLIT["val"] + SPLIT["test"]), random_state=SEED,
                              stratify=pd.Series(strat, index=ids).loc[rest].values)
    return pd.concat([pd.DataFrame({"customer_id": tr, "split": "train"}), pd.DataFrame({"customer_id": va, "split": "val"}),
                      pd.DataFrame({"customer_id": te, "split": "test"})])

def _auc_ci(y, p, n=500):
    rng = np.random.default_rng(SEED); a = []
    for _ in range(n):
        i = rng.integers(0, len(y), len(y))
        if y[i].min() != y[i].max(): a.append(roc_auc_score(y[i], p[i]))
    return np.percentile(a, [2.5, 97.5])

def _metrics(y, p):
    top = max(1, int(.1 * len(y))); order = np.argsort(-p)
    return dict(auc=roc_auc_score(y, p), pr_auc=average_precision_score(y, p), logloss=log_loss(y, np.clip(p, 1e-6, 1 - 1e-6)),
                brier=brier_score_loss(y, p), lift_top10=y[order[:top]].mean() / max(y.mean(), 1e-9), prevalence=y.mean(), n=len(y), n_pos=int(y.sum()))

def tune(X, y):
    """5-fold CV grid; returns best params + best rounds (early-stopped) + full grid table."""
    rows = []; ds = lgb.Dataset(X, y, free_raw_data=False)
    for lr, nl, mcs in itertools.product(GRID["learning_rate"], GRID["num_leaves"], GRID["min_child_samples"]):
        p = dict(LGB_BASE, learning_rate=lr, num_leaves=nl, min_child_samples=mcs, seed=SEED)
        cv = lgb.cv(p, ds, num_boost_round=MAX_ROUNDS, nfold=5, stratified=True, seed=SEED,
                    callbacks=[lgb.early_stopping(EARLY_STOP, verbose=False)])
        k = "valid binary_logloss-mean"; rows.append(dict(learning_rate=lr, num_leaves=nl, min_child_samples=mcs,
                                                          cv_logloss=min(cv[k]), best_rounds=int(np.argmin(cv[k]) + 1)))
    g = pd.DataFrame(rows).sort_values("cv_logloss").reset_index(drop=True)
    b = g.iloc[0]
    return dict(LGB_BASE, learning_rate=float(b.learning_rate), num_leaves=int(b.num_leaves),
                min_child_samples=int(b.min_child_samples)), int(b.best_rounds), g

class PropensityModel:
    def __init__(self, product, feats): self.product, self.feats = product, feats
    def _raw(self, X):  # per-member raw logits -> (n, n_members)
        return np.column_stack([m.predict(X[self.feats], raw_score=True) for m in self.models])
    def fit(self, Xtr, ytr, Xva, yva):
        self.params, self.rounds, self.grid = tune(Xtr[self.feats], ytr)
        self.models = []
        for s in range(N_ENSEMBLE):
            p = dict(self.params, seed=SEED + s, bagging_seed=SEED + s, feature_fraction_seed=SEED + s)
            self.models.append(lgb.train(p, lgb.Dataset(Xtr[self.feats], ytr), num_boost_round=max(30, int(self.rounds * 1.1))))
        z = self._raw(Xva).mean(1, keepdims=True)           # Platt scaling fit on VAL (never on test)
        self.cal = LogisticRegression(C=1e6).fit(z, yva)
        self.lr = make_pipeline(SimpleImputer(strategy="median"), StandardScaler(),
                                LogisticRegression(C=0.3, max_iter=2000)).fit(Xtr[self.feats], ytr)
        p_tree = self.cal.predict_proba(z)[:, 1]
        p_lr = self.lr.predict_proba(Xva[self.feats])[:, 1]
        candidates = [(w, log_loss(yva, np.clip(w * p_tree + (1 - w) * p_lr, 1e-6, 1 - 1e-6)))
                      for w in np.linspace(0, 1, 5)]
        self.blend_weight = min(candidates, key=lambda x: x[1])[0]
        self.support = {f: np.nanpercentile(Xtr[f], [1, 99]) for f in self.feats}
        pv = self.predict(Xva)["propensity"].values
        prec, rec, thr = precision_recall_curve(yva, pv); f1 = 2 * prec * rec / (prec + rec + 1e-9)
        self.threshold = float(thr[np.argmax(f1[:-1])])      # operating threshold = max-F1 on val
        # learned feature weights (normalised gain, averaged over ensemble)
        gain = np.mean([m.feature_importance("gain") for m in self.models], axis=0)
        self.importance = pd.Series(gain / gain.sum(), index=self.feats).sort_values(ascending=False)
        return self
    def predict(self, X):
        Z = self._raw(X); tree_p = self.cal.predict_proba(Z.mean(1, keepdims=True))[:, 1]
        lr_p = self.lr.predict_proba(X[self.feats])[:, 1]
        pm = self.blend_weight * tree_p + (1 - self.blend_weight) * lr_p
        pe = np.column_stack([self.cal.predict_proba(Z[:, [i]])[:, 1] for i in range(Z.shape[1])])
        pe = np.column_stack([pe, lr_p])
        agree = 1 - np.minimum(1, pe.std(1) / 0.10)
        key = KEY_FEATURES[self.product]
        complete = X[key].notna().mean(1).values
        support = np.mean([((X[k] >= self.support[k][0]) & (X[k] <= self.support[k][1])) | X[k].isna() for k in key], axis=0)
        # missing key inputs are penalised through completeness; out-of-range through support
        conf = np.clip(0.4 * agree + 0.3 * complete + 0.3 * support, 0, 1)
        return pd.DataFrame({"propensity": pm, "confidence": conf}, index=X.index)
    def reason_codes(self, X, top_k=3):
        """Top positive SHAP contributions (LightGBM pred_contrib, ensemble mean) mapped to reason codes."""
        C = np.mean([m.predict(X[self.feats], pred_contrib=True)[:, :-1] for m in self.models], axis=0)
        out = []
        for row in C:
            idx = [i for i in np.argsort(-row) if row[i] > 0.05][:top_k]
            out.append([REASON_CODES.get(self.feats[i], self.feats[i].upper()) for i in idx])
        return out
    def reason_details(self, X, top_k=3):
        """Return code, source feature, and normalized local positive contribution."""
        tree_c = np.mean([m.predict(X[self.feats], pred_contrib=True)[:, :-1] for m in self.models], axis=0)
        transformed = self.lr.named_steps["standardscaler"].transform(
            self.lr.named_steps["simpleimputer"].transform(X[self.feats]))
        lr_c = transformed * self.lr.named_steps["logisticregression"].coef_[0]
        def normalize_positive(a):
            positive = np.maximum(a, 0)
            return positive / np.maximum(positive.sum(axis=1, keepdims=True), 1e-9)
        C = self.blend_weight * normalize_positive(tree_c) + (1 - self.blend_weight) * normalize_positive(lr_c)
        out = []
        for row in C:
            idx = [i for i in np.argsort(-row) if row[i] > 0.05][:top_k]
            total = sum(row[i] for i in idx) or 1.0
            out.append([{"code": REASON_CODES.get(self.feats[i], self.feats[i].upper()),
                         "feature": self.feats[i], "importance": float(row[i] / total)} for i in idx])
        return out

def baseline_lr(Xtr, ytr, Xs):
    m = make_pipeline(SimpleImputer(strategy="median"), StandardScaler(), LogisticRegression(C=0.3, max_iter=2000)).fit(Xtr, ytr)
    return m, {k: m.predict_proba(v)[:, 1] for k, v in Xs.items()}

def train_all(F, labels, rules, split, verbose=True):
    """F: customer-360 indexed by customer_id. Returns models + evaluation report."""
    models, report = {}, {}
    sp = split.set_index("customer_id").split.reindex(F.index)
    for prod in PRODUCTS:
        cand = rules[f"eligible_{prod}"] & (labels.set_index("customer_id")[f"candidate_{prod}"].reindex(F.index) == 1)
        y = labels.set_index("customer_id")[f"takeup_{prod}"].reindex(F.index)
        feats = MODEL_FEATURES[prod]; d = lambda s: cand & (sp == s)
        Xtr, ytr, Xva, yva, Xte, yte = F[d("train")], y[d("train")].values, F[d("val")], y[d("val")].values, F[d("test")], y[d("test")].values
        m = PropensityModel(prod, feats).fit(Xtr, ytr, Xva, yva); models[prod] = m
        _, base = baseline_lr(Xtr[feats], ytr, {"val": Xva[feats], "test": Xte[feats]})
        r = {}
        for nm, X, yy in [("train", Xtr, ytr), ("val", Xva, yva), ("test", Xte, yte)]:
            r[nm] = _metrics(yy, m.predict(X)["propensity"].values)
        r["baseline_logreg_test"] = _metrics(yte, base["test"])
        r["baseline_prevalence_test_logloss"] = log_loss(yte, np.full(len(yte), ytr.mean()))
        r["auc_test_ci95"] = _auc_ci(yte, m.predict(Xte)["propensity"].values).round(3).tolist()
        r["cv_best"] = dict(m.params, rounds=m.rounds); r["threshold"] = m.threshold
        r["champion_blend"] = {"lightgbm_weight": float(m.blend_weight), "logistic_regression_weight": float(1 - m.blend_weight),
                               "selection_metric": "validation_logloss"}
        r["overfit_gap_auc_train_minus_test"] = r["train"]["auc"] - r["test"]["auc"]
        report[prod] = r
        m.grid.to_csv(OUT_DIR / f"cv_grid_{prod}.csv", index=False); m.importance.to_csv(OUT_DIR / f"feature_weights_{prod}.csv", header=["normalised_gain"])
        if verbose:
            print(f"\n=== {prod}: n_train={len(ytr)} (pos {int(ytr.sum())}), n_val={len(yva)}, n_test={len(yte)} (pos {int(yte.sum())})")
            print(f"  chosen: lr={m.params['learning_rate']} leaves={m.params['num_leaves']} min_child={m.params['min_child_samples']} rounds={m.rounds}")
            for nm in ("train", "val", "test"):
                x = r[nm]; print(f"  {nm:5s} AUC={x['auc']:.3f} PR-AUC={x['pr_auc']:.3f} logloss={x['logloss']:.3f} brier={x['brier']:.3f} lift@10%={x['lift_top10']:.2f}")
            b = r["baseline_logreg_test"]; print(f"  baseline LogReg(test) AUC={b['auc']:.3f} PR-AUC={b['pr_auc']:.3f} logloss={b['logloss']:.3f} | prevalence-only logloss={r['baseline_prevalence_test_logloss']:.3f}")
            print(f"  test AUC 95% CI {r['auc_test_ci95']}  train-test AUC gap={r['overfit_gap_auc_train_minus_test']:.3f}")
            print("  top weights:", ", ".join(f"{k}={v:.2f}" for k, v in m.importance.head(5).items()))
    joblib.dump(models, MODEL_DIR / "propensity_models.joblib")
    json.dump(report, open(OUT_DIR / "evaluation_report.json", "w"), indent=2, default=float)
    return models, report
