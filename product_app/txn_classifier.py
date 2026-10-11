"""FR2 - Transaction categorisation (exactly one of 8 mutually-exclusive categories).

Model : TF-IDF (char 2-5 grams, robust to bank-feed typos) + Logistic Regression.
Baseline : keyword rules (documented boundary decisions).
Split  : by CUSTOMER (same split as the propensity models) -> no leakage.
"""
import re, joblib, numpy as np, pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import f1_score, accuracy_score, classification_report
from config import *

# ---- Boundary decisions (documented) -------------------------------------------------
#  * EV public charging (SHELL RECHARGE, POD POINT, BP PULSE) -> Fuel
#  * Forecourt SHOP purchases (SHELL SHOP / BP SHOP)           -> Other  (not fuel)
#  * Supermarket petrol stations (TESCO PETROL)                -> Fuel ; TESCO STORES/EXPRESS -> Other
#  * Tyres / MOT / parts / car wash / DVLA                     -> Automotive
#  * Energy supplier bills: ELEC -> Electricity, GAS -> Gas (dual fuel is billed as two DDs)
#  * Water, broadband, mobile, council tax, TV licence         -> Utilities
KEYWORDS = [  # ordered: first match wins
    ("Other", r"SHELL SHOP|BP SHOP|TESCO STORES|TESCO EXPRESS|SALARY"),
    ("Fuel", r"SHELL|\bBP\b|ESSO|TEXACO|PETROL|RECHARGE|POD POINT|BP PULSE|BP CONNECT|CHARGING"),
    ("Electricity", r"ELEC"),
    ("Gas", r"\bGAS\b"),
    ("Public Transport", r"TFL|TRAINLINE|NATIONAL RAIL|BUS|STAGECOACH|LNER"),
    ("Home Improvement", r"B&Q|SCREWFIX|WICKES|HOMEBASE|TOOLSTATION|DULUX|TRAVIS"),
    ("Automotive", r"HALFORDS|KWIK|ATS|DVLA|AUTOGLASS|MOT|EUROCAR|CAR WASH"),
    ("Utilities", r"WATER|BROADBAND|COUNCIL TAX|TV LICENCE|MOBILE|BT |VIRGIN|SKY"),
]
def rule_classify(text: str) -> str:
    t = str(text or "").upper()
    for cat, pat in KEYWORDS:
        if re.search(pat, t): return cat
    return "Other"

def _clean(s: pd.Series) -> pd.Series:
    s = s.fillna("").astype(str).str.upper().str.replace(r"\d+", " ", regex=True)
    return s.str.replace(r"\b(CARD PAYMENT TO|POS|VIS|CRD|GB)\b", " ", regex=True).str.replace(r"\s+", " ", regex=True).str.strip()

def train_txn_classifier(tx, labels, split):
    if tx.transaction_id.duplicated().any() or labels.transaction_id.duplicated().any():
        raise ValueError("Transaction IDs must be unique")
    if not labels.category.isin(CATEGORIES).all(): raise ValueError("Unknown transaction label")
    if set(tx.transaction_id) != set(labels.transaction_id): raise ValueError("Every transaction needs exactly one label")
    df = tx.merge(labels, on="transaction_id", validate="one_to_one").merge(split, on="customer_id", validate="many_to_one")
    if len(df) != len(tx): raise ValueError("Split missing transaction customers")
    df["clean"] = _clean(df.merchant_description)
    tr = df[df.split == "train"]
    # unique texts (weighted by freq) keep training fast on 1M rows
    g = tr.groupby(["clean", "category"]).size().reset_index(name="w")
    vec = TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 5), min_df=2, sublinear_tf=True)
    X = vec.fit_transform(g.clean)
    clf = LogisticRegression(C=8.0, max_iter=2000, class_weight="balanced")
    clf.fit(X, g.category, sample_weight=np.log1p(g.w))
    rep = {}
    for name in ["val", "test"]:
        held = df[df.split == name]
        ev = held.sample(min(len(held), 60000), random_state=SEED)
        pred = clf.predict(vec.transform(ev.clean)); base = ev.merchant_description.map(rule_classify)
        rep[name] = dict(n=len(ev), model_macro_f1=f1_score(ev.category, pred, labels=CATEGORIES, average="macro", zero_division=0),
            model_acc=accuracy_score(ev.category, pred), rules_macro_f1=f1_score(ev.category, base, labels=CATEGORIES, average="macro", zero_division=0),
            rules_acc=accuracy_score(ev.category, base), per_category=classification_report(ev.category, pred, labels=CATEGORIES, output_dict=True, zero_division=0))
    rep["limitation"] = "Customer-disjoint synthetic data shares merchant templates across splits; near-perfect scores do not establish generalisation to unseen banks or merchants."
    print("Transaction classifier:", {s: rep[s]["model_macro_f1"] for s in ["val", "test"]}, flush=True)
    joblib.dump((vec, clf), MODEL_DIR / "txn_classifier.joblib")
    return vec, clf, rep

def predict_categories(tx, vec, clf, conf_floor=0.0):
    if len(tx) == 0: return np.array([], dtype=object), np.array([], dtype=float)
    clean = _clean(tx.merchant_description)
    u = pd.DataFrame({"clean": clean})
    uniq = u.clean.drop_duplicates()
    P = clf.predict_proba(vec.transform(uniq)); cls = clf.classes_
    m = pd.DataFrame({"clean": uniq.values, "category": cls[P.argmax(1)], "cat_conf": P.max(1)}).set_index("clean")
    out = u.join(m, on="clean")
    missing = clean.eq("").values
    out.loc[missing, "category"] = "Other"
    out.loc[missing, "cat_conf"] = 0.0
    return out.category.values, out.cat_conf.values
