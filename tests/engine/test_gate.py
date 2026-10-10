from engine import evaluate_gate


def test_electric_vehicle_owner_is_suppressed_by_ev_gate():
    gate = evaluate_gate("GP01", {"vehicle_fuel_type": "ELECTRIC"})
    assert gate["rule_pass"] is False
    assert gate["failed_rules"] == [
        {"code": "ALREADY_EV_OWNER", "message": "Customer already drives an electric vehicle"}
    ]
    assert "eligibility checks" in gate["note"]


def test_non_homeowner_is_suppressed_for_home_products():
    for product_id in ("GP02", "GP03"):
        gate = evaluate_gate(product_id, {"home_owner": "False"})
        assert gate["rule_pass"] is False
        assert gate["failed_rules"][0]["code"] == "NOT_HOME_OWNER"


def test_unknown_home_ownership_is_not_treated_as_a_failed_rule():
    assert evaluate_gate("GP03", {})["rule_pass"] is True
