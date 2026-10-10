from src.api import stubs

from responsible_ai.contract_checks import validate_customer_response, validate_record


def test_all_app_stub_opportunities_match_api_contract_in_stub_mode():
    opportunities = [item for items in stubs.OPPS.values() for item in items]
    errors = [
        (item["customer_id"], item["product_id"], validate_record(item, allow_stub_placeholders=True))
        for item in opportunities
    ]
    assert all(not error for _, _, error in errors), errors


def test_customer_view_never_exposes_suppressed_opportunities():
    for customer_id in stubs.CUSTOMERS:
        visible = stubs.visible(customer_id)
        assert all(item["status"] != "SUPPRESSED" for item in visible)
        assert validate_customer_response(visible, allow_stub_placeholders=True) == []


def test_strict_mode_identifies_stub_impact_placeholders():
    recommended = next(
        item
        for items in stubs.OPPS.values()
        for item in items
        if item["status"] == "RECOMMENDED"
    )
    errors = validate_record(recommended)
    assert any("production provenance required" in error for error in errors)
