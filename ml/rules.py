"""Rules-based product eligibility / candidate gate (NOT machine learning, NOT the LLM).

Illustrative only: in production these are replaced by the institution's authorised
product criteria. A propensity never overrides this gate (FR7)."""
import pandas as pd

def eligibility(f: pd.DataFrame) -> pd.DataFrame:
    """f = customer-360 feature frame. Returns one boolean + one reason column per product."""
    out = pd.DataFrame(index=f.index)
    def put(prod, ok, why_not):
        out[f"eligible_{prod}"] = ok.astype(bool)
        out[f"exclusion_{prod}"] = pd.Series("", index=f.index).mask(~ok, why_not)
    # EV finance: owns a non-EV vehicle (replacement use case), age 18-78, doesn't already hold GP01
    ev_owner = f.fuel_type_code == 3   # 3 = EV
    ok = (f.has_vehicle == 1) & ~ev_owner & f.age.between(18, 78) & (f.holds_GP01 == 0)
    why = pd.Series("NO_VEHICLE_ON_RECORD", index=f.index).mask(ev_owner, "ALREADY_EV_NO_REPLACEMENT_USE_CASE") \
            .mask(~f.age.between(18, 78), "OUTSIDE_AGE_CRITERIA").mask(f.holds_GP01 == 1, "ALREADY_HOLDS_PRODUCT")
    put("EV_FINANCE", ok, why)
    # Green home loan: home owner or mortgage holder
    ok = ((f.home_owner == 1) | (f.has_mortgage == 1)) & (f.holds_GP02 == 0)
    put("GREEN_HOME_LOAN", ok, pd.Series("NOT_HOME_OWNER", index=f.index).mask(f.holds_GP02 == 1, "ALREADY_HOLDS_PRODUCT"))
    # Solar finance: home owner (PV installation use case)
    ok = (f.home_owner == 1) & (f.holds_GP03 == 0)
    put("SOLAR_FINANCE", ok, pd.Series("NOT_HOME_OWNER", index=f.index).mask(f.holds_GP03 == 1, "ALREADY_HOLDS_PRODUCT"))
    # Paperless: still receives paper statements
    ok = (f.paper_share > 0.15) & (f.holds_GP04 == 0)
    put("PAPERLESS_BANKING", ok, pd.Series("ALREADY_MOSTLY_DIGITAL", index=f.index).mask(f.holds_GP04 == 1, "ALREADY_HOLDS_PRODUCT"))
    return out

def eligibility_detail(r: pd.Series, product: str) -> dict:
    """Canonical tri-state eligibility result for one customer-product pair."""
    checks = []
    def check(code, result, message):
        checks.append({"code": code, "result": result, "message": message})

    if product == "EV_FINANCE":
        check("HAS_EXISTING_VEHICLE", "PASS" if r.has_vehicle == 1 else "FAIL",
              "Customer has an existing vehicle." if r.has_vehicle == 1 else "No existing vehicle was found.")
        is_ev = r.get("fuel_type_code") == 3
        check("NOT_EXISTING_EV_OWNER", "FAIL" if is_ev else "PASS",
              "Customer already owns an EV and no replacement case exists." if is_ev else "No existing electric vehicle was found.")
        check("AGE_CRITERIA", "PASS" if 18 <= r.age <= 78 else "FAIL", "Customer age is within criteria." if 18 <= r.age <= 78 else "Customer age is outside criteria.")
        check("NOT_CURRENT_PRODUCT_HOLDER", "PASS" if r.holds_GP01 == 0 else "FAIL", "Customer does not hold GP01." if r.holds_GP01 == 0 else "Customer already holds GP01.")
        check("MILEAGE_DATA_AVAILABLE", "UNKNOWN" if pd.isna(r.get("annual_mileage")) else "PASS", "Annual mileage is not available." if pd.isna(r.get("annual_mileage")) else "Annual mileage information is available.")
    elif product == "GREEN_HOME_LOAN":
        owns = r.home_owner == 1 or r.has_mortgage == 1
        check("HOME_OWNERSHIP_OR_MORTGAGE", "PASS" if owns else "FAIL", "Home ownership or a mortgage is recorded." if owns else "No home ownership or mortgage was found.")
        check("NOT_CURRENT_PRODUCT_HOLDER", "PASS" if r.holds_GP02 == 0 else "FAIL", "Customer does not hold GP02." if r.holds_GP02 == 0 else "Customer already holds GP02.")
    elif product == "SOLAR_FINANCE":
        check("HOME_OWNER", "PASS" if r.home_owner == 1 else "FAIL", "Home ownership is recorded." if r.home_owner == 1 else "Customer is not recorded as a homeowner.")
        check("NOT_CURRENT_PRODUCT_HOLDER", "PASS" if r.holds_GP03 == 0 else "FAIL", "Customer does not hold GP03." if r.holds_GP03 == 0 else "Customer already holds GP03.")
    else:
        paper = r.get("paper_share")
        result = "UNKNOWN" if pd.isna(paper) else ("PASS" if paper > .15 else "FAIL")
        check("PAPER_STATEMENTS_ACTIVE", result, "Paper statement usage is active." if result == "PASS" else ("Paper statement data is unavailable." if result == "UNKNOWN" else "Customer is already mostly digital."))
        check("NOT_CURRENT_PRODUCT_HOLDER", "PASS" if r.holds_GP04 == 0 else "FAIL", "Customer does not hold GP04." if r.holds_GP04 == 0 else "Customer already holds GP04.")

    failed = [c["code"] for c in checks if c["result"] == "FAIL"]
    missing = ["annual_mileage" if c["code"] == "MILEAGE_DATA_AVAILABLE" else "paper_share" for c in checks if c["result"] == "UNKNOWN"]
    if failed:
        status, eligible, review = "INELIGIBLE", False, False
    elif missing:
        status, eligible, review = "MANUAL_REVIEW", None, True
    else:
        status, eligible, review = "ELIGIBLE", True, False
    return {"status": status, "is_eligible": eligible, "rule_version": f"{product.lower()}_eligibility_v1.0.0",
            "decision_codes": checks, "failed_rules": failed, "missing_requirements": missing,
            "requires_human_review": review}
