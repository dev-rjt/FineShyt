"""End-to-end: data -> txn classifier -> customer 360 -> rules -> propensity -> carbon engine -> recommendations."""
import json, sys, numpy as np, pandas as pd
from config import *
from data_generation import make_all
from txn_classifier import train_txn_classifier
from features import build_customer_360
from rules import eligibility
from propensity import make_splits, train_all
from carbon_engine import estimate_impact

def main(regenerate=True):
    d = make_all() if regenerate else None
    # build the customer split first (same split used by txn classifier + propensity models)
    from propensity import make_splits
    cust = d["customers"]; split = make_splits(cust, d["labels"])
    vec, clf, txn_rep = train_txn_classifier(d["transactions"], d["txn_labels"], split)
    F = build_customer_360(d, vec, clf); F.to_csv(DATA_DIR / "customer_360.csv", index=False)
    Fi = F.set_index("customer_id"); rules = eligibility(Fi)
    models, rep = train_all(Fi, d["labels"], rules, split)
    rep["txn_categorisation"] = txn_rep; json.dump(rep, open(OUT_DIR / "evaluation_report.json", "w"), indent=2, default=float)

    recs = []
    sp = split.set_index("customer_id").split
    for prod in PRODUCTS:
        m = models[prod]; el = rules[f"eligible_{prod}"]
        X = Fi[el]; pr = m.predict(X); rc = m.reason_codes(X)
        for (cid, row), rcodes, (_, p) in zip(X.iterrows(), rc, pr.iterrows()):
            imp = estimate_impact(prod, row)
            recs.append(dict(customer_id=cid, opportunity=prod, product_id=PRODUCT_IDS[prod], propensity=round(p.propensity, 4),
                             confidence=round(p.confidence, 4), recommend=bool(p.propensity >= m.threshold),
                             reason_codes=";".join(rcodes), data_timestamp=row.data_timestamp, split=sp[cid],
                             impact_status=imp["status"], est_avoided_kg_co2e_yr=imp.get("avoided_kg_co2e_per_year"),
                             impact_json=json.dumps(imp)))
        ne = Fi[~el]
        for cid, why in zip(ne.index, rules.loc[~el, f"exclusion_{prod}"]):   # explicit "do not recommend"
            recs.append(dict(customer_id=cid, opportunity=prod, product_id=PRODUCT_IDS[prod], propensity=np.nan, confidence=np.nan,
                             recommend=False, reason_codes=f"EXCLUDED:{why}", data_timestamp=ne.loc[cid, "data_timestamp"],
                             split=sp[cid], impact_status="NOT_APPLICABLE", est_avoided_kg_co2e_yr=np.nan, impact_json="{}"))
    R = pd.DataFrame(recs); R.to_csv(OUT_DIR / "recommendations_all.csv", index=False)
    R[R.split == "test"].to_csv(OUT_DIR / "test_predictions.csv", index=False)
    print("\nSaved: recommendations_all.csv, test_predictions.csv, evaluation_report.json, feature_weights_*.csv, cv_grid_*.csv")
    top = R[R.recommend].sort_values("propensity", ascending=False).head(3)
    for _, r in top.iterrows():
        print(json.dumps(dict(customer_id=r.customer_id, opportunity=r.opportunity, propensity=r.propensity, confidence=r.confidence,
                              reason_codes=r.reason_codes.split(";"), data_timestamp=r.data_timestamp,
                              impact=json.loads(r.impact_json)), indent=1))
    print("\nRecommended counts:", R[R.recommend].groupby("opportunity").size().to_dict())
    return d, F, models, R

if __name__ == "__main__":
    main()
