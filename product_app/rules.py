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
    put("GREEN_HOME", ok, pd.Series("NOT_HOME_OWNER", index=f.index).mask(f.holds_GP02 == 1, "ALREADY_HOLDS_PRODUCT"))
    # Solar finance: home owner (PV installation use case)
    ok = (f.home_owner == 1) & (f.holds_GP03 == 0)
    put("SOLAR_FINANCE", ok, pd.Series("NOT_HOME_OWNER", index=f.index).mask(f.holds_GP03 == 1, "ALREADY_HOLDS_PRODUCT"))
    # Paperless: still receives paper statements
    ok = (f.paper_share > 0.15) & (f.holds_GP04 == 0)
    put("PAPERLESS", ok, pd.Series("ALREADY_MOSTLY_DIGITAL", index=f.index).mask(f.holds_GP04 == 1, "ALREADY_HOLDS_PRODUCT"))
    return out
