"""Stub data for the Megathon API.

Same shapes as docs/API_CONTRACT.md, fake values. No emission factors are
invented here: factor and assumption values stay None until R3 provides them.
Everything in this file is replaced by the real pipeline later.
"""

DATA_AS_OF = "2026-06-30"
NOTE = "Subject to the institution's authorised eligibility checks"

PRODUCTS = [
    {"product_id": "GP01", "product": "EV Finance", "opportunity": "EV_FINANCE",
     "category": "Transport", "required": True,
     "intended_use_case": "Replace a petrol, diesel or hybrid vehicle with an electric vehicle",
     "eligibility": "Product rules screen only; final eligibility is decided by authorised processes",
     "sustainability_metric": "CO2E_KG", "action_label": "Explore EV options"},
    {"product_id": "GP02", "product": "Green Home Loan", "opportunity": "GREEN_HOME_LOAN",
     "category": "Home", "required": True,
     "intended_use_case": "Improve the energy efficiency of a home you own, for example insulation, glazing or a heat pump",
     "eligibility": "Product rules screen only; final eligibility is decided by authorised processes",
     "sustainability_metric": "ENERGY_KWH", "action_label": "Explore home upgrades"},
    {"product_id": "GP03", "product": "Solar Finance", "opportunity": "SOLAR_FINANCE",
     "category": "Home", "required": True,
     "intended_use_case": "Generate your own electricity with solar panels on a home you own",
     "eligibility": "Product rules screen only; final eligibility is decided by authorised processes",
     "sustainability_metric": "ENERGY_KWH", "action_label": "Explore solar options"},
    {"product_id": "GP04", "product": "Paperless Banking", "opportunity": "PAPERLESS_BANKING",
     "category": "Digital", "required": True,
     "intended_use_case": "Switch from paper statements to digital statements",
     "eligibility": "Product rules screen only; final eligibility is decided by authorised processes",
     "sustainability_metric": "PAPER_SHEETS", "action_label": "Go paperless"},
]
PRODUCT_BY_ID = {p["product_id"]: p for p in PRODUCTS}

_RC_ROWS = [
    ("HIGH_FUEL_SPEND", "DRIVER", "High fuel spend", "You spend a lot on fuel each year.", "GP01"),
    ("HIGH_ANNUAL_MILEAGE", "DRIVER", "High annual mileage", "You drive a lot of miles each year.", "GP01"),
    ("EXISTING_VEHICLE", "DRIVER", "Runs a combustion vehicle", "You currently run a petrol, diesel or hybrid vehicle.", "GP01"),
    ("HOME_OWNER", "DRIVER", "Home owner", "You own your home.", None),
    ("HIGH_ELECTRICITY_USE", "DRIVER", "High electricity use", "Your home uses a lot of electricity.", None),
    ("HIGH_PAPER_STATEMENTS", "DRIVER", "Mostly paper statements", "Most of your statements still arrive on paper.", "GP04"),
    ("HIGH_DIGITAL_ACTIVITY", "DRIVER", "Active digital user", "You already use digital banking often.", "GP04"),
    ("ALREADY_EV_OWNER", "GATE", "Already drives an EV", "You already drive an electric vehicle.", "GP01"),
    ("NOT_HOME_OWNER", "GATE", "Not a home owner", "This product is for people who own their home.", None),
    ("MISSING_MILEAGE", "DATA_QUALITY", "Mileage missing", "We do not have your yearly mileage yet.", "GP01"),
    ("LOW_DATA_COMPLETENESS", "DATA_QUALITY", "Limited data", "We do not have enough information to be sure.", None),
]
REASON_CODES = [
    {"code": c, "kind": k, "label": l, "plain_text": t, "product_id": p}
    for c, k, l, t, p in _RC_ROWS
]
RC = {r["code"]: {key: r[key] for key in ("code", "kind", "label", "plain_text")} for r in REASON_CODES}

GATE_MESSAGES = {
    "ALREADY_EV_OWNER": "Customer already drives an electric vehicle",
    "NOT_HOME_OWNER": "Customer is not a home owner",
}

UNITS = {"CO2E_KG": "kg CO2e per year", "ENERGY_KWH": "kWh per year", "PAPER_SHEETS": "sheets per year"}
UNIT_WORDS = {"CO2E_KG": "kg CO2e a year", "ENERGY_KWH": "kWh of energy a year", "PAPER_SHEETS": "sheets of paper a year"}
METHODS = {
    "GP01": "EV_AVOIDED_V1: current fuel emissions minus electricity emissions after switching",
    "GP02": "HOME_EFFICIENCY_V1: energy saved by efficiency upgrades against current use",
    "GP03": "SOLAR_GENERATION_V1: electricity generated on site against current grid use",
    "GP04": "PAPER_AVOIDED_V1: paper statements replaced by digital statements",
}
LEADS = {
    "GP01": "An EV may suit your driving.",
    "GP02": "Energy efficiency upgrades may suit your home.",
    "GP03": "Solar panels may suit your home.",
    "GP04": "Going paperless could suit you.",
}


def _ok(pid, metric, low, central, high):
    return {
        "status": "OK", "is_estimate": True, "horizon_months": 12, "method": METHODS[pid],
        "metrics": [{"metric": metric, "unit": UNITS[metric], "low": low, "central": central, "high": high}],
        "assumptions": [{"id": "A_PLACEHOLDER", "value": None, "unit": None, "source": "placeholder"}],
        "factors": [{"factor_id": "EF_PLACEHOLDER", "activity": "placeholder", "kg_co2e_per_unit": None,
                     "unit": None, "source": "placeholder", "source_year": None}],
        "missing_inputs": [],
    }


def _missing(pid, missing):
    return {
        "status": "INSUFFICIENT_DATA", "is_estimate": True, "horizon_months": 12, "method": METHODS[pid],
        "metrics": [], "assumptions": [], "factors": [], "missing_inputs": missing,
    }


def _insight_text(pid, impact):
    lead = LEADS[pid]
    if impact["status"] != "OK":
        return f"{lead} We need a little more information before we can estimate the impact. Subject to eligibility checks."
    m = impact["metrics"][0]
    return (f"{lead} Our estimate is {m['low']:,.0f} to {m['high']:,.0f} {UNIT_WORDS[m['metric']]}. "
            "Subject to eligibility checks.")


def _opp(cid, pid, status, propensity, confidence, codes, impact, rank=None, score=None, gate_fail=None):
    p = PRODUCT_BY_ID[pid]
    gate_fail = gate_fail or []
    if status == "SUPPRESSED":
        insight, action, reason = None, None, gate_fail[0]
    else:
        insight = {"text": _insight_text(pid, impact), "source": "TEMPLATE", "verified": True}
        action = {"label": p["action_label"], "note": "Subject to eligibility checks"}
        reason = None
    return {
        "customer_id": cid, "opportunity": p["opportunity"], "product_id": pid, "status": status,
        "propensity": propensity, "confidence": confidence,
        "reason_codes": [RC[c] for c in codes] + [RC[c] for c in gate_fail],
        "gate": {"rule_pass": not gate_fail,
                 "failed_rules": [{"code": c, "message": GATE_MESSAGES[c]} for c in gate_fail],
                 "rule_version": "v1", "note": NOTE},
        "impact": impact, "insight": insight, "action": action,
        "suppression_reason": reason, "rank_in_customer": rank, "rank_score": score,
        "data_as_of": DATA_AS_OF, "model_version": f"propensity-{pid.lower()}-v1",
    }


CUSTOMERS = {
    "C10001": {
        "split": "test",
        "profile": {"age": 41, "income_band": "MID", "postcode": "M1 1AA", "region": "North West",
                    "home_owner": True, "digital_usage": 0.62, "sustainability_preference": "MEDIUM"},
        "features": {"fuel_spend_12m": 2100.0, "annual_mileage": 14000, "electricity_kwh_12m": 3900.0,
                     "paper_statement_ratio": 0.8},
        "holdings": [{"product": "VEHICLE_LOAN", "start_date": "2024-03-01", "balance": 6400.0, "status": "ACTIVE"}],
        "vehicle": {"vehicle_type": "CAR", "fuel_type": "PETROL", "vehicle_age": 9, "annual_mileage": 14000},
        "data_quality": {"completeness": 0.93, "missing_fields": []},
    },
    "C10002": {
        "split": "validation",
        "profile": {"age": 29, "income_band": "MID", "postcode": "E1 6AN", "region": "London",
                    "home_owner": False, "digital_usage": 0.91, "sustainability_preference": "HIGH"},
        "features": {"fuel_spend_12m": 120.0, "annual_mileage": 6000, "electricity_kwh_12m": 2100.0,
                     "paper_statement_ratio": 0.7},
        "holdings": [],
        "vehicle": {"vehicle_type": "CAR", "fuel_type": "ELECTRIC", "vehicle_age": 2, "annual_mileage": 6000},
        "data_quality": {"completeness": 0.9, "missing_fields": []},
    },
    "C10003": {
        "split": "train",
        "profile": {"age": 52, "income_band": "HIGH", "postcode": "LS1 4AP", "region": "Yorkshire and The Humber",
                    "home_owner": True, "digital_usage": 0.35, "sustainability_preference": "LOW"},
        "features": {"fuel_spend_12m": 1800.0, "annual_mileage": None, "electricity_kwh_12m": 5200.0,
                     "paper_statement_ratio": 0.9},
        "holdings": [],
        "vehicle": {"vehicle_type": "CAR", "fuel_type": "DIESEL", "vehicle_age": 6, "annual_mileage": None},
        "data_quality": {"completeness": 0.71, "missing_fields": ["annual_mileage"]},
    },
}

OPPS = {
    "C10001": [
        _opp("C10001", "GP01", "RECOMMENDED", 0.84, 0.87,
             ["HIGH_FUEL_SPEND", "HIGH_ANNUAL_MILEAGE", "EXISTING_VEHICLE"],
             _ok("GP01", "CO2E_KG", 800.0, 1200.0, 1500.0), rank=1, score=0.62),
        _opp("C10001", "GP03", "RECOMMENDED", 0.61, 0.78, ["HOME_OWNER", "HIGH_ELECTRICITY_USE"],
             _ok("GP03", "ENERGY_KWH", 1800.0, 2600.0, 3200.0), rank=2, score=0.41),
        _opp("C10001", "GP04", "RECOMMENDED", 0.57, 0.81, ["HIGH_PAPER_STATEMENTS", "HIGH_DIGITAL_ACTIVITY"],
             _ok("GP04", "PAPER_SHEETS", 40.0, 55.0, 70.0), rank=3, score=0.30),
        _opp("C10001", "GP02", "INSUFFICIENT_DATA", 0.35, 0.42, ["HOME_OWNER", "LOW_DATA_COMPLETENESS"],
             _missing("GP02", ["gas_kwh_12m"]), rank=4, score=0.05),
    ],
    "C10002": [
        _opp("C10002", "GP04", "RECOMMENDED", 0.78, 0.86, ["HIGH_PAPER_STATEMENTS", "HIGH_DIGITAL_ACTIVITY"],
             _ok("GP04", "PAPER_SHEETS", 60.0, 80.0, 100.0), rank=1, score=0.45),
        _opp("C10002", "GP01", "SUPPRESSED", 0.22, 0.70, [], _missing("GP01", []), gate_fail=["ALREADY_EV_OWNER"]),
        _opp("C10002", "GP02", "SUPPRESSED", 0.05, 0.80, [], _missing("GP02", []), gate_fail=["NOT_HOME_OWNER"]),
        _opp("C10002", "GP03", "SUPPRESSED", 0.05, 0.80, [], _missing("GP03", []), gate_fail=["NOT_HOME_OWNER"]),
    ],
    "C10003": [
        _opp("C10003", "GP03", "RECOMMENDED", 0.66, 0.74, ["HOME_OWNER", "HIGH_ELECTRICITY_USE"],
             _ok("GP03", "ENERGY_KWH", 2000.0, 2900.0, 3600.0), rank=1, score=0.38),
        _opp("C10003", "GP02", "RECOMMENDED", 0.52, 0.70, ["HOME_OWNER", "HIGH_ELECTRICITY_USE"],
             _ok("GP02", "ENERGY_KWH", 900.0, 1400.0, 2000.0), rank=2, score=0.20),
        _opp("C10003", "GP04", "RECOMMENDED", 0.40, 0.66, ["HIGH_PAPER_STATEMENTS"],
             _ok("GP04", "PAPER_SHEETS", 30.0, 45.0, 60.0), rank=3, score=0.12),
        _opp("C10003", "GP01", "INSUFFICIENT_DATA", 0.48, 0.35,
             ["HIGH_FUEL_SPEND", "EXISTING_VEHICLE", "MISSING_MILEAGE"],
             _missing("GP01", ["annual_mileage"]), rank=4, score=0.05),
    ],
}


def visible(cid):
    """Opportunities a customer may see: not suppressed, best rank first."""
    items = [o for o in OPPS[cid] if o["status"] != "SUPPRESSED"]
    return sorted(items, key=lambda o: o["rank_in_customer"])


def customer_list(region=None, search=None):
    rows = []
    for cid, c in CUSTOMERS.items():
        p = c["profile"]
        if region and p["region"].lower() != region.lower():
            continue
        if search and not cid.lower().startswith(search.lower()):
            continue
        top = visible(cid)[0] if visible(cid) else None
        rows.append({
            "customer_id": cid, "age": p["age"], "income_band": p["income_band"], "region": p["region"],
            "home_owner": p["home_owner"], "split": c["split"],
            "top_opportunity": top["opportunity"] if top else None,
            "top_rank_score": top["rank_score"] if top else None,
        })
    return rows


def meta():
    splits = {"train": 0, "validation": 0, "test": 0}
    for c in CUSTOMERS.values():
        splits[c["split"]] += 1
    return {"cutoff_date": DATA_AS_OF, "takeup_window_days": 90, "customers": len(CUSTOMERS), "splits": splits,
            "generator_version": "stub", "model_versions": {"categoriser": "stub", "propensity": "stub"},
            "generated_at": "2026-10-10T12:00:00Z"}


def business_summary():
    by_product = {}
    totals = {k: [0.0, 0.0, 0.0] for k in UNITS}
    weighted = {k: 0.0 for k in UNITS}
    for cid, opps in OPPS.items():
        rec = [o for o in opps if o["status"] == "RECOMMENDED"]
        # GP02 and GP03 can claim the same electricity saving: count only the higher-ranked one.
        home = sorted((o for o in rec if o["product_id"] in ("GP02", "GP03")), key=lambda o: o["rank_in_customer"])
        skip = {o["product_id"] for o in home[1:]}
        for o in opps:
            row = by_product.setdefault(o["product_id"], {
                "product_id": o["product_id"], "opportunity": o["opportunity"],
                "recommended": 0, "suppressed": 0, "insufficient_data": 0, "_props": []})
            row[o["status"].lower()] += 1
            row["_props"].append(o["propensity"])
        for o in rec:
            if o["product_id"] in skip:
                continue
            m = o["impact"]["metrics"][0]
            t = totals[m["metric"]]
            t[0] += m["low"]
            t[1] += m["central"]
            t[2] += m["high"]
            weighted[m["metric"]] += m["central"] * o["propensity"]
    rows = []
    for row in sorted(by_product.values(), key=lambda r: r["product_id"]):
        props = row.pop("_props")
        row["avg_propensity"] = round(sum(props) / len(props), 2)
        rows.append(row)

    def rng(k):
        t = totals[k]
        return {"low": round(t[0]), "central": round(t[1]), "high": round(t[2]), "is_estimate": True}

    return {
        "customers_analysed": len(CUSTOMERS),
        "opportunities_by_product": rows,
        "potential_impact": {
            "co2e_kg_per_year": rng("CO2E_KG"),
            "energy_kwh_per_year": rng("ENERGY_KWH"),
            "paper_sheets_per_year": rng("PAPER_SHEETS"),
            "digital_adoption_pp": {"low": 0, "central": 0, "high": 0, "is_estimate": True},
        },
        "propensity_weighted_impact": {
            "co2e_kg_per_year": round(weighted["CO2E_KG"]),
            "energy_kwh_per_year": round(weighted["ENERGY_KWH"]),
            "paper_sheets_per_year": round(weighted["PAPER_SHEETS"]),
            "digital_adoption_pp": 0, "is_estimate": True,
        },
        "data_as_of": DATA_AS_OF,
    }


def queue(product_id=None, min_confidence=0.0):
    rows = []
    for cid, opps in OPPS.items():
        for o in opps:
            if o["status"] == "SUPPRESSED":
                continue
            if product_id and o["product_id"] != product_id:
                continue
            if o["confidence"] < min_confidence:
                continue
            m = o["impact"]["metrics"]
            rows.append({
                "customer_id": cid, "product_id": o["product_id"], "opportunity": o["opportunity"],
                "status": o["status"], "propensity": o["propensity"], "confidence": o["confidence"],
                "impact_central": {"metric": m[0]["metric"], "value": m[0]["central"]} if m else None,
                "rank_score": o["rank_score"], "low_confidence": o["confidence"] < 0.5,
            })
    rows.sort(key=lambda r: r["rank_score"], reverse=True)
    return rows
