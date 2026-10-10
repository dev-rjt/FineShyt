"""Central configuration: seeds, dates, paths, hyper-parameter search space."""
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).parent
DATA_DIR, MODEL_DIR, OUT_DIR = ROOT / "data", ROOT / "models", ROOT / "outputs"
for d in (DATA_DIR, MODEL_DIR, OUT_DIR):
    d.mkdir(exist_ok=True)

SEED = 42
N_CUSTOMERS = 5000
CUTOFF_DATE = pd.Timestamp("2025-12-31")   # last date covered by input data
HISTORY_MONTHS = 12                         # transaction / energy / digital history length
OUTCOME_WINDOW_MONTHS = 6                   # take-up measured in 6 months AFTER cutoff

PRODUCTS = ["EV_FINANCE", "GREEN_HOME", "SOLAR_FINANCE", "PAPERLESS"]
PRODUCT_IDS = {"EV_FINANCE": "GP01", "GREEN_HOME": "GP02",
               "SOLAR_FINANCE": "GP03", "PAPERLESS": "GP04"}

CATEGORIES = ["Fuel", "Electricity", "Gas", "Public Transport",
              "Home Improvement", "Automotive", "Utilities", "Other"]

# customer-level split (no customer appears in two splits => no leakage)
SPLIT = dict(train=0.70, val=0.15, test=0.15)

# LightGBM: conservative defaults to avoid overfitting on 5k rows
LGB_BASE = dict(objective="binary", metric="binary_logloss", verbosity=-1,
                feature_fraction=0.8, bagging_fraction=0.8, bagging_freq=1,
                lambda_l2=5.0, lambda_l1=0.5, min_gain_to_split=0.0,
                max_depth=-1, n_jobs=4)
GRID = dict(learning_rate=[0.02, 0.05], num_leaves=[4, 8, 16], min_child_samples=[20, 50])
MAX_ROUNDS, EARLY_STOP = 3000, 100
N_ENSEMBLE = 5   # bagged seeds -> used for confidence (agreement) score
