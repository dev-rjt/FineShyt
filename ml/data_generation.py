"""Synthetic data generator for the Green Customer Insights Platform.

Produces every table in the problem statement. Take-up labels come from a
LATENT logistic process over observable features + unobserved noise, so
relationships are plausible (not arbitrary) but not perfectly learnable.
Take-up is only generated for customers who pass the product's candidate rules.
"""
import numpy as np, pandas as pd
from config import *

rng = np.random.default_rng(SEED)
sigmoid = lambda x: 1 / (1 + np.exp(-x))

REGIONS = {  # postcode area -> (region, urban 0-1)
    "EC": ("London", 1), "SW": ("London", 1), "E": ("London", 1), "M": ("North West", 1),
    "L": ("North West", 1), "B": ("West Midlands", 1), "LS": ("Yorkshire", 1),
    "S": ("Yorkshire", 1), "NE": ("North East", .8), "BS": ("South West", .8),
    "EX": ("South West", .4), "CF": ("Wales", .7), "EH": ("Scotland", .9),
    "IV": ("Scotland", .2), "NR": ("East", .5), "CB": ("East", .6), "OX": ("South East", .6),
    "TN": ("South East", .4), "LD": ("Wales", .1), "PL": ("South West", .3)}
INCOME_BANDS = ["<20k", "20-35k", "35-50k", "50-80k", "80k+"]
INCOME_MID = np.array([15, 28, 42, 65, 100])
MONTHS = pd.period_range(end=CUTOFF_DATE, periods=HISTORY_MONTHS, freq="M")

# ---------------------------------------------------------------- merchants
# (template, category). Boundary decisions are documented in README.
MERCHANTS = {
 "Fuel": ["SHELL {n} {c}", "BP CONNECT {n}", "ESSO {n} {c}", "TEXACO {n}", "TESCO PETROL {n}",
          "SAINSBURYS PETROL {n}", "SHELL RECHARGE {n}", "POD POINT CHARGING", "BP PULSE {n}"],
 "Electricity": ["OCTOPUS ENERGY ELEC DD", "BRITISH GAS ELEC DD", "EDF ENERGY ELECTRICITY",
                 "OVO ENERGY ELEC DD", "EON NEXT ELECTRICITY"],
 "Gas": ["OCTOPUS ENERGY GAS DD", "BRITISH GAS GAS DD", "EDF ENERGY GAS", "OVO ENERGY GAS DD",
         "EON NEXT GAS"],
 "Public Transport": ["TFL TRAVEL CH {n}", "TRAINLINE {n}", "NATIONAL RAIL {n}", "ARRIVA BUS {n}",
                      "STAGECOACH {c}", "FIRST BUS {n}", "LNER TICKETS"],
 "Home Improvement": ["B&Q {n} {c}", "SCREWFIX {n}", "WICKES {n}", "HOMEBASE {n}", "TOOLSTATION {n}",
                      "DULUX DECORATOR CTR", "TRAVIS PERKINS {n}"],
 "Automotive": ["HALFORDS {n}", "KWIK FIT {n}", "ATS EURODRIVE {n}", "DVLA VEHICLE TAX",
                "AUTOGLASS {n}", "MOT TEST CENTRE {c}", "EUROCAR PARTS {n}", "CAR WASH {c}"],
 "Utilities": ["THAMES WATER DD", "SEVERN TRENT WATER", "BT BROADBAND DD", "VIRGIN MEDIA DD",
               "SKY BROADBAND", "COUNCIL TAX {c}", "TV LICENCE", "VODAFONE MOBILE"],
 "Other": ["TESCO STORES {n}", "TESCO EXPRESS {n}", "SAINSBURYS S/MKTS {n}", "AMAZON.CO.UK {n}",
           "NETFLIX.COM", "SPOTIFY", "COSTA COFFEE {n}", "PRET A MANGER {n}", "WAITROSE {n}",
           "ASOS.COM", "DELIVEROO {n}", "BOOTS {n}", "SHELL SHOP {n}", "BP SHOP {n}",
           "GREGGS {n}", "PUREGYM", "ODEON CINEMAS", "ARGOS {n}"],
}
CITIES = ["LONDON", "MANCHESTER", "LEEDS", "BRISTOL", "CARDIFF", "GLASGOW", "NORWICH", "OXFORD"]

def _noisy(text, p=0.06):
    """Simulate raw bank-feed noise: typos, prefixes, dropped chars."""
    out = []
    for ch in text:
        r = rng.random()
        if ch.isalpha() and r < p / 2: continue
        if ch.isalpha() and r < p: out.append(chr(rng.integers(65, 91))); continue
        out.append(ch)
    t = "".join(out)
    if rng.random() < .4: t = rng.choice(["CARD PAYMENT TO ", "POS ", "VIS ", "CRD "]) + t
    if rng.random() < .3: t += " GB"
    return t

def _render(cat):
    tpl = rng.choice(MERCHANTS[cat])
    txt = tpl.format(n=rng.integers(100, 9999), c=rng.choice(CITIES))
    return _noisy(txt)

# ---------------------------------------------------------------- customers
def make_customers(n):
    age = np.clip(rng.normal(44, 15, n), 18, 88).astype(int)
    inc_idx = np.clip(np.round(rng.normal(1.8 + (age - 18) / 40 - np.maximum(age - 60, 0) / 25, 1.1)), 0, 4).astype(int)
    areas = rng.choice(list(REGIONS), n)
    urban = np.array([REGIONS[a][1] for a in areas])
    p_home = sigmoid(-3.2 + 0.06 * (age - 18) + 0.55 * inc_idx - 0.9 * urban)
    home_owner = (rng.random(n) < p_home).astype(int)
    digital_usage = np.clip(rng.beta(4, 2.2, n) - 0.006 * np.maximum(age - 50, 0) + .03 * inc_idx, 0.02, 1)
    sust = np.clip(rng.beta(2, 2.5, n) + .04 * (age < 40) + .03 * inc_idx / 4, 0, 1)
    return pd.DataFrame(dict(
        customer_id=[f"C{10001+i}" for i in range(n)], age=age, income_band=[INCOME_BANDS[i] for i in inc_idx],
        postcode=[a + str(rng.integers(1, 30)) + " " + str(rng.integers(1, 9)) + "AA" for a in areas],
        home_owner=home_owner, digital_usage=digital_usage.round(3),
        sustainability_preference=sust.round(3), _inc=inc_idx, _urban=urban,
        region=[REGIONS[a][0] for a in areas]))

def make_vehicles(c):
    n = len(c)
    has = rng.random(n) < sigmoid(-0.2 + 0.5 * c._inc - 0.9 * c._urban + .02 * (c.age - 40) - .00*c.age)
    fuel = np.where(rng.random(n) < sigmoid(-2.3 + 1.6 * c.sustainability_preference + .3 * c._inc), "EV",
            rng.choice(["petrol", "diesel", "hybrid"], n, p=[.55, .33, .12]))
    vtype = rng.choice(["hatchback", "saloon", "SUV", "van", "estate"], n, p=[.35, .15, .3, .08, .12])
    age_v = np.clip(rng.gamma(2.2, 3.0, n), 0, 22).round(1)
    miles = np.clip(rng.normal(7800, 3200, n) + 700 * (1 - c._urban) * 3 + 400 * (vtype == "van") * 3, 800, 25000).round(-1)
    v = pd.DataFrame(dict(customer_id=c.customer_id, vehicle_type=vtype, fuel_type=fuel, vehicle_age=age_v,
                          annual_mileage=miles))
    return v[has].reset_index(drop=True)

def make_energy(c):
    n = len(c); size = np.clip(rng.normal(2.6, 1.1, n), 1, 6)
    owner_boost = 1 + .22 * c.home_owner
    base_e = 2300 * (0.55 + .22 * size) * owner_boost * rng.lognormal(0, .18, n)
    base_g = 9500 * (0.55 + .2 * size) * owner_boost * rng.lognormal(0, .22, n)
    rows = []
    for m in MONTHS:
        mo = m.month
        s_e = 1 + .18 * np.cos((mo - 1) / 12 * 2 * np.pi)
        s_g = 1 + .85 * np.cos((mo - 1) / 12 * 2 * np.pi)
        e = base_e / 12 * s_e * rng.lognormal(0, .06, n); g = base_g / 12 * s_g * rng.lognormal(0, .1, n)
        rows.append(pd.DataFrame(dict(customer_id=c.customer_id, month=str(m),
                                      electricity_kwh=e.round(1), gas_kwh=g.round(1))))
    return pd.concat(rows, ignore_index=True), base_e, base_g

def make_digital(c):
    n = len(c)
    paper_pref = sigmoid(-2.0 * (c.digital_usage.values - .45) * 3 + .03 * (c.age.values - 45) + rng.normal(0, .8, n))
    rows = []
    for m in MONTHS:
        stm = rng.poisson(1.5, n) + 1
        paper = rng.binomial(stm, np.clip(paper_pref, .02, .98))
        dtx = rng.poisson(10 + 55 * c.digital_usage.values)
        br = rng.poisson(np.clip(2.2 * (1 - c.digital_usage.values) ** 2 + .3 * (c.age.values > 65), .05, 4))
        rows.append(pd.DataFrame(dict(customer_id=c.customer_id, month=str(m), digital_statements=stm - paper,
                                      paper_statements=paper, digital_transactions=dtx, branch_visits=br)))
    return pd.concat(rows, ignore_index=True)

def make_products(c, veh):
    rows = []; n = len(c); cid = c.customer_id.values
    def add(mask, prod, bal_fn, status_p_open=.93):
        for i in np.where(mask)[0]:
            rows.append((cid[i], prod, (CUTOFF_DATE - pd.Timedelta(days=int(rng.integers(30, 3000)))).date(),
                         round(float(bal_fn(i)), 2), "active" if rng.random() < status_p_open else "closed"))
    add(np.ones(n, bool), "CURRENT_ACCOUNT", lambda i: rng.gamma(2, 900))
    add(rng.random(n) < .55, "SAVINGS", lambda i: rng.gamma(2, 4000))
    add(rng.random(n) < sigmoid(-.5 + .25 * c._inc), "CREDIT_CARD", lambda i: rng.gamma(2, 600))
    add(rng.random(n) < sigmoid(-1.8 + .15 * c._inc), "PERSONAL_LOAN", lambda i: rng.gamma(2, 3500))
    has_v = np.isin(cid, veh.customer_id)
    add(has_v & (rng.random(n) < .22), "VEHICLE_LOAN", lambda i: rng.gamma(2.5, 5000))
    add((c.home_owner.values == 1) & (rng.random(n) < .62), "MORTGAGE", lambda i: rng.gamma(3, 60000))
    add(rng.random(n) < sigmoid(-2.0 + .45 * c._inc + 1.0 * c.sustainability_preference), "INVESTMENT_ISA",
        lambda i: rng.gamma(2, 9000))
    # a few customers already hold a green product -> must be excluded from recommendations
    for prod, gp, p in [("EV_FINANCE", "GP01", .03), ("GREEN_HOME_LOAN", "GP02", .02),
                        ("SOLAR_FINANCE", "GP03", .015), ("PAPERLESS_BANKING", "GP04", .0)]:
        add(rng.random(n) < p, gp, lambda i: rng.gamma(2, 8000))
    return pd.DataFrame(rows, columns=["customer_id", "product", "start_date", "balance", "status"])

def make_transactions(c, veh, base_e, base_g, prods):
    vmap = veh.set_index("customer_id")
    cust_idx = {cid: i for i, cid in enumerate(c.customer_id)}
    has_gas_acct = rng.random(len(c)) < .85
    rows = []; tid = 0
    start = CUTOFF_DATE - pd.DateOffset(months=HISTORY_MONTHS) + pd.Timedelta(days=1)
    for i, cid in enumerate(c.customer_id.values):
        # --- fuel / charging spend driven by mileage + fuel type
        if cid in vmap.index:
            v = vmap.loc[cid]; miles = v.annual_mileage
            cost_per_mile = {"petrol": .155, "diesel": .145, "hybrid": .1, "EV": .06}[v.fuel_type]
            annual_fuel = miles * cost_per_mile * rng.lognormal(0, .12)
            n_fill = max(3, int(miles / 450 * rng.uniform(.7, 1.3)))
        else:
            annual_fuel, n_fill = 0, 0
        for _ in range(n_fill):
            d = start + pd.Timedelta(days=int(rng.integers(0, 365)))
            amt = annual_fuel / n_fill * rng.uniform(.6, 1.4)
            rows.append((cid, d, _render("Fuel"), round(amt, 2), "debit", "Fuel"))
        # --- energy direct debits (monthly)
        for m in MONTHS:
            d = m.to_timestamp() + pd.Timedelta(days=int(rng.integers(0, 27)))
            rows.append((cid, d, _render("Electricity"), round(base_e[i] / 12 * .30 * rng.uniform(.9, 1.1), 2), "debit", "Electricity"))
            if has_gas_acct[i]:
                rows.append((cid, d, _render("Gas"), round(base_g[i] / 12 * .075 * rng.uniform(.9, 1.1), 2), "debit", "Gas"))
            for _ in range(2): rows.append((cid, d, _render("Utilities"), round(rng.uniform(15, 65), 2), "debit", "Utilities"))
        # --- other categories
        n_pt = rng.poisson(8 + 30 * (1 - 0)*(c._urban[i]) )
        n_hi = rng.poisson(1.5 + 5 * c.home_owner.iat[i] * (.5 + c.sustainability_preference.iat[i]))
        n_au = rng.poisson(3 + (cid in vmap.index) * 2)
        n_ot = rng.poisson(22 + 4 * c._inc[i])
        for cat, k, lo, hi in [("Public Transport", n_pt, 2, 45), ("Home Improvement", n_hi, 12, 450),
                               ("Automotive", n_au, 8, 400), ("Other", n_ot, 2, 140)]:
            for _ in range(k):
                d = start + pd.Timedelta(days=int(rng.integers(0, 365)))
                rows.append((cid, d, _render(cat), round(float(rng.lognormal(np.log((lo * hi) ** .5), .6)), 2), "debit", cat))
        if rng.random() < .97:  # salary credit
            for m in MONTHS:
                rows.append((cid, m.to_timestamp() + pd.Timedelta(days=25), "SALARY ACME LTD",
                             round(INCOME_MID[c._inc[i]] * 1000 / 12 * .78, 2), "credit", "Other"))
    t = pd.DataFrame(rows, columns=["customer_id", "date", "merchant_description", "amount", "debit_credit", "category"])
    t["transaction_id"] = [f"T{j:08d}" for j in range(len(t))]
    t["date"] = pd.to_datetime(t["date"]).dt.date
    # ground-truth category by construction (re-derive from template pool for audit)
    return t[["transaction_id", "customer_id", "date", "merchant_description", "amount", "debit_credit", "category"]]


# ---------------------------------------------------------------- labels
def make_takeup(c, veh, prods, energy_agg, digital_agg, txn_spend):
    """Latent-propensity label generation. Documented coefficients (README)."""
    df = c.set_index("customer_id").join(veh.set_index("customer_id"), how="left")
    df = df.join(energy_agg).join(digital_agg).join(txn_spend)
    held = prods[prods.status == "active"].groupby("customer_id")["product"].apply(set)
    df["held"] = held.reindex(df.index).apply(lambda s: s if isinstance(s, set) else set())
    z = lambda s: (s - s.mean()) / (s.std() + 1e-9)
    out = pd.DataFrame(index=df.index)
    noise = lambda: rng.normal(0, 0.9, len(df))      # unobserved heterogeneity

    has_v = df.vehicle_type.notna()
    cand = {}
    cand["EV_FINANCE"] = has_v & (df.fuel_type != "EV") & ~df.held.apply(lambda s: "GP01" in s) & df.age.between(18, 78)
    cand["GREEN_HOME_LOAN"] = ((df.home_owner == 1) | df.held.apply(lambda s: "MORTGAGE" in s)) & ~df.held.apply(lambda s: "GP02" in s)
    cand["SOLAR_FINANCE"] = (df.home_owner == 1) & ~df.held.apply(lambda s: "GP03" in s)
    cand["PAPERLESS_BANKING"] = (df.paper_share > 0.15) & ~df.held.apply(lambda s: "GP04" in s)

    lz = lambda x: x.fillna(x.median())
    ev = (-4.0 + 0.9 * z(lz(df.annual_mileage)) + 0.75 * z(lz(df.fuel_spend_m)) + 0.6 * df.held.apply(lambda s: "VEHICLE_LOAN" in s)
          + 0.45 * (lz(df.vehicle_age) > 7) + 0.9 * z(df.sustainability_preference) + 0.35 * z(df._inc)
          + 0.5 * df._urban + 0.3 * df.home_owner - 0.02 * (df.age - 40) + noise())
    gh = (-4.0 + 0.85 * z(df.heating_kwh_yr) + 0.55 * z(df.home_impr_spend_m) + 0.7 * df.held.apply(lambda s: "MORTGAGE" in s)
          + 0.9 * z(df.sustainability_preference) + 0.3 * z(df._inc) + 0.3 * (df.age.between(28, 62)) + noise())
    so = (-4.1 + 1.0 * z(df.elec_kwh_yr) + 0.35 * z(df.home_impr_spend_m) + 0.5 * z(df._inc)
          + 0.95 * z(df.sustainability_preference) + 0.4 * (1 - df._urban) + 0.35 * df.held.apply(lambda s: "INVESTMENT_ISA" in s) + noise())
    pl = (-1.9 + 2.2 * (df.paper_share - .4) + 1.1 * z(df.digital_tx_m) - 0.9 * z(df.branch_visits_m)
          + 0.5 * z(df.digital_usage) - 0.02 * (df.age - 45) + 0.3 * z(df.sustainability_preference) + noise())
    for name, logit in [("EV_FINANCE", ev), ("GREEN_HOME_LOAN", gh), ("SOLAR_FINANCE", so), ("PAPERLESS_BANKING", pl)]:
        p = sigmoid(logit)
        out[f"candidate_{name}"] = cand[name].astype(int)
        out[f"takeup_{name}"] = ((rng.random(len(df)) < p) & cand[name]).astype(int)
    return out.reset_index()

def make_green_products():
    return pd.DataFrame([
        ("GP01", "EV Finance", "Transport", "Rules: vehicle owner, non-EV, age 18-78, no existing GP01", "kg CO2e avoided / yr (tailpipe vs grid)"),
        ("GP02", "Green Home Loan", "Home", "Rules: home owner or mortgage holder; retrofit / heat-pump / insulation use case", "kg CO2e avoided / yr (gas+elec reduction)"),
        ("GP03", "Solar Finance", "Home", "Rules: home owner; PV installation use case only (generation assets)", "kg CO2e avoided / yr (grid displacement)"),
        ("GP04", "Paperless Banking", "Digital", "Rules: paper statement share > 15%", "paper statements avoided / yr (reported separately from CO2e)")],
        columns=["product_id", "product", "category", "eligibility", "sustainability_metric"])

def make_emission_factors():
    return pd.DataFrame([
        ("grid_electricity", "kWh", 0.207, "UK DESNZ/DEFRA GHG conversion factors (~2023/24 grid avg) - VERIFY latest"),
        ("natural_gas", "kWh", 0.183, "UK DESNZ/DEFRA GHG conversion factors (gross CV) - VERIFY latest"),
        ("car_petrol", "km", 0.170, "UK DESNZ avg petrol car, approx - VERIFY latest"),
        ("car_diesel", "km", 0.171, "UK DESNZ avg diesel car, approx - VERIFY latest"),
        ("car_hybrid", "km", 0.120, "UK DESNZ hybrid car, approx - VERIFY latest"),
        ("ev_energy_intensity", "kWh/km", 0.200, "Typical BEV consumption assumption (not a CO2e factor)"),
        ("paper_statement", "statement", 0.025, "ASSUMPTION: ~3 A4 sheets + envelope; replace with sourced LCA value"),
        ("pv_yield", "kWh/kWp/yr", 900.0, "Typical UK PV yield assumption (not a CO2e factor)")],
        columns=["activity", "unit", "kg_co2e_per_unit", "source"])


def _ground_truth_aggregates(c, en, dg, tx):
    """Aggregates from TRUE categories - used ONLY by the label generator (never as model input)."""
    d = tx[tx.debit_credit == "debit"]
    sp = d.pivot_table(index="customer_id", columns="category", values="amount", aggfunc="sum", fill_value=0) / HISTORY_MONTHS
    sp = sp.reindex(c.customer_id).fillna(0)
    spend = pd.DataFrame({"fuel_spend_m": sp.get("Fuel", 0), "home_impr_spend_m": sp.get("Home Improvement", 0)})
    e = en.groupby("customer_id").agg(elec_kwh_yr=("electricity_kwh", "sum"), gas_kwh_yr=("gas_kwh", "sum"))
    e["heating_kwh_yr"] = e.gas_kwh_yr + 0.3 * e.elec_kwh_yr
    g = dg.groupby("customer_id").agg(p=("paper_statements", "sum"), dgs=("digital_statements", "sum"),
                                      digital_tx_m=("digital_transactions", "mean"), branch_visits_m=("branch_visits", "mean"))
    g["paper_share"] = g.p / (g.p + g.dgs)
    return e, g[["paper_share", "digital_tx_m", "branch_visits_m"]], spend

def make_all(n=N_CUSTOMERS, save=True):
    c = make_customers(n); veh = make_vehicles(c); en, be, bg = make_energy(c); dg = make_digital(c)
    pr = make_products(c, veh)
    tx = make_transactions(c, veh, be, bg, pr)
    e, g, sp = _ground_truth_aggregates(c, en, dg, tx)
    labels = make_takeup(c, veh, pr, e, g, sp)
    gp, ef = make_green_products(), make_emission_factors()
    txn_labels = tx[["transaction_id", "category"]].copy()
    tx = tx.drop(columns="category")
    cust = c.drop(columns=["_inc", "_urban"])
    if save:
        for name, df in dict(customers=cust, transactions=tx, products=pr, vehicles=veh, energy_usage=en,
                             digital_usage=dg, green_products=gp, emissions_factors=ef,
                             labels_takeup=labels, labels_txn_category=txn_labels).items():
            df.to_csv(DATA_DIR / f"{name}.csv", index=False)
    return dict(customers=cust, transactions=tx, products=pr, vehicles=veh, energy=en, digital=dg,
                green_products=gp, emissions_factors=ef, labels=labels, txn_labels=txn_labels)

if __name__ == "__main__":
    d = make_all()
    print({k: v.shape for k, v in d.items()})
    print(d["labels"].filter(like="takeup").mean().round(3).to_dict(), d["labels"].filter(like="candidate").mean().round(3).to_dict())
