"""Reviewed wording populated from contract facts, never upstream free text.

Keep additions to these vocabularies under the explanation owner's review.
Unknown codes remain visible to staff without guessing their meaning.
"""

from dataclasses import dataclass
import re

PRODUCTS = {
    "EV_FINANCE": ("GP01", "EV Finance"),
    "GREEN_HOME_LOAN": ("GP02", "Green Home Loan"),
    "SOLAR_FINANCE": ("GP03", "Solar Finance"),
    "PAPERLESS_BANKING": ("GP04", "Paperless Banking"),
}
REASONS = {
    "HIGH_FUEL_SPEND": "High recurring fuel spending",
    "HIGH_ANNUAL_MILEAGE": "High annual vehicle mileage",
    "EXISTING_ICE_VEHICLE": "An existing petrol or diesel vehicle",
    "EXISTING_VEHICLE": "An existing vehicle",
    "HOME_OWNER": "Home ownership",
    "HIGH_ELECTRICITY_USE": "High electricity use",
    "HIGH_UTILITY_SPEND": "High utility spending",
    "HOME_IMPROVEMENT_ACTIVITY": "Home improvement activity",
    "HIGH_PAPER_STATEMENTS": "Paper statement use",
    "PAPER_STATEMENTS_ACTIVE": "Active paper statements",
    "HIGH_DIGITAL_ACTIVITY": "High digital activity",
    "LOW_DATA_COMPLETENESS": "Incomplete input data",
    "MISSING_MILEAGE": "Missing annual mileage information",
}
RULES = {
    "EXISTING_EV_WITHOUT_REPLACEMENT_CASE": "An existing EV with no replacement case",
    "ALREADY_EV_OWNER": "An existing electric vehicle",
    "NOT_HOME_OWNER": "The home ownership rule did not pass",
    "ANNUAL_MILEAGE_MISSING": "Annual mileage is unavailable",
}
METHODS = {
    "EV_AVOIDED_EMISSIONS_V1": "current fuel emissions minus estimated EV electricity emissions",
}
METRICS = {
    "POTENTIAL_CO2E_AVOIDED": "avoided emissions",
    "CURRENT_TRANSPORT_EMISSIONS": "current transport emissions",
    "ESTIMATED_EV_EMISSIONS": "EV emissions",
    "ENERGY_KWH": "energy",
    "PAPER_SHEETS": "paper sheets",
    "DIGITAL_ADOPTION_PP": "digital adoption",
}
UNITS = {"kgCO2e/year", "kgCO2e", "kg CO2e/year", "kWh/year", "kWh",
         "sheets/year", "sheets", "pages/year", "pages", "percentage_points",
         "percentage points", "GBP", "miles/year", "km/year", "litres/year"}
ACTIONS = {
    "EXPLORE_EV_OPTIONS": "Explore EV options",
    "EXPLORE_GREEN_HOME_OPTIONS": "Explore green home options",
    "EXPLORE_GREEN_HOME_LOAN": "Explore green home loan options",
    "EXPLORE_SOLAR_OPTIONS": "Explore solar options",
    "GO_PAPERLESS": "Explore paperless banking",
    "SWITCH_TO_PAPERLESS": "Explore paperless banking",
    "REQUEST_MILEAGE_DATA": "Request mileage information",
}
ACTION_PRODUCTS = {
    "EXPLORE_EV_OPTIONS": "EV_FINANCE",
    "EXPLORE_GREEN_HOME_OPTIONS": "GREEN_HOME_LOAN",
    "EXPLORE_GREEN_HOME_LOAN": "GREEN_HOME_LOAN",
    "EXPLORE_SOLAR_OPTIONS": "SOLAR_FINANCE",
    "GO_PAPERLESS": "PAPERLESS_BANKING",
    "SWITCH_TO_PAPERLESS": "PAPERLESS_BANKING",
    "REQUEST_MILEAGE_DATA": "EV_FINANCE",
}
ASSUMPTIONS = {
    "MILEAGE_UNCHANGED": "Annual mileage remains unchanged after switching vehicles",
    "EV_EFFICIENCY_RANGE": "EV efficiency is represented by a documented range",
}


def number(value):
    """Render the supplied value without estimating or rounding it."""
    return format(value, ",").removesuffix(".0")


def code(value):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Z][A-Z0-9_]{0,95}", value):
        raise ValueError("Unreviewed identifier in explanation facts")
    return value


def unit(value):
    if value not in UNITS:
        raise ValueError("Impact unit needs reviewed display wording")
    return value


@dataclass(frozen=True)
class Card:
    id: str
    variants: tuple[str, ...]
    sources: tuple[str, ...]


@dataclass(frozen=True)
class Catalog:
    headlines: tuple[str, ...]
    customer: tuple[Card, ...]
    manager: tuple[Card, ...]

    def prompt_data(self):
        return {
            "headlines": list(self.headlines),
            "customer": [{"id": c.id, "variants": list(c.variants)} for c in self.customer],
            "manager": [{"id": c.id, "variants": list(c.variants)} for c in self.manager],
        }


def build_catalog(record):
    """Called only after schema/consistency validation of a complete record."""
    opportunity = record["opportunity"]
    product_id, name = PRODUCTS[opportunity["product_code"]]
    if opportunity["product_name"] not in (None, name) or opportunity["product_id"] not in (None, product_id):
        raise ValueError("Product code, ID and name do not agree")
    prediction, eligibility = record["prediction"], record["eligibility"]
    impact, recommendation = record["impact"], record["recommendation"]
    allowed = eligibility["status"] == "ELIGIBLE" and recommendation["decision"] == "RECOMMEND"
    show_customer = allowed and recommendation["customer_visible"]
    show_manager = recommendation["manager_visible"]
    customer, manager = [], []

    def add(key, customer_text, manager_text, *sources, customer_alt=None, manager_alt=None):
        if show_customer and customer_text:
            customer.append(Card(key, tuple(dict.fromkeys([customer_text, customer_alt or customer_text])), sources))
        if show_manager and manager_text:
            manager.append(Card(key, tuple(dict.fromkeys([manager_text, manager_alt or manager_text])), sources))

    add("product", f"{name} may be worth exploring.", f"Product: {name}.", "opportunity.product_code",
        customer_alt=f"Consider exploring {name}.")
    status = eligibility["status"]
    decision = recommendation["decision"]
    gate_text = {
        "ELIGIBLE": "The configured product rules passed; authorised bank checks still apply.",
        "INELIGIBLE": "The configured product rules did not pass. Do not present this product as an offer.",
        "INSUFFICIENT_DATA": "Eligibility information is incomplete. Do not present this product as an offer.",
        "MANUAL_REVIEW": "Eligibility requires human review. Do not present this product as an offer.",
    }[status]
    add("gate", "This opportunity passed the configured product rules; authorised bank checks still apply.",
        f"Eligibility status: {status}. Decision: {decision}. {gate_text}",
        "eligibility.status", "recommendation.decision")
    if not allowed and status == "ELIGIBLE":
        add("blocked", None, "The recommendation decision blocks an offer despite the product-rule result.",
            "recommendation.decision")
    if not recommendation["customer_visible"]:
        add("visibility", None, "This opportunity is hidden from the customer view.", "recommendation.customer_visible")

    known_customer_reasons = []
    for index, reason in enumerate(prediction["reason_codes"]):
        if reason["code"] is None:
            add(f"reason_{index}", "A model signal has no reason code, so its meaning is unavailable.",
                "A supplied model signal has an unavailable reason code.", f"prediction.reason_codes[{index}].code")
            continue
        reason_code = code(reason["code"])
        wording = REASONS.get(reason_code)
        if wording:
            known_customer_reasons.append(wording.lower())
        add(f"reason_{index}", None if wording else
            "An additional model signal has no reviewed customer wording; ask the bank team for clarification.",
            f"Signal {reason_code}: {wording or 'no reviewed wording available'}.",
            f"prediction.reason_codes[{index}].code")
        evidence = reason["evidence"]
        # Numeric evidence uses a controlled metric/unit vocabulary. Text, labels,
        # descriptions and merchant/payee references never enter the prompt.
        metric = evidence["metric"]
        value = evidence["value"]
        numeric = isinstance(value, (int, float)) and not isinstance(value, bool)
        evidence_labels = {"average_monthly_fuel_spend": "Average monthly fuel spending",
                           "annual_mileage": "Annual mileage"}
        if numeric and metric in evidence_labels and evidence["unit"] in UNITS:
            text = f"{evidence_labels[metric]}: {number(value)} {unit(evidence['unit'])}."
            add(f"evidence_{index}", None, text, f"prediction.reason_codes[{index}].evidence")
    if known_customer_reasons:
        reasons = "; ".join(dict.fromkeys(known_customer_reasons))
        add("relevance", f"The signals behind this opportunity include {reasons}.", None,
            "prediction.reason_codes", customer_alt=f"This opportunity reflects these recorded signals: {reasons}.")
    if not prediction["reason_codes"]:
        add("no_reasons", "No reason codes were supplied, so relevance cannot be explained further.",
            "No model reason codes were supplied.", "prediction.reason_codes")

    for field in ("propensity", "confidence"):
        value = prediction[field]
        label = "Model take-up propensity" if field == "propensity" else "Prediction confidence"
        text = f"{label}: {number(value)} on a zero-to-one scale." if value is not None else f"{label} is unavailable."
        add(field, text if field == "confidence" else None, text, f"prediction.{field}")
    add("score_meaning", None, "Propensity describes predicted take-up; confidence is separate. Neither establishes financial eligibility.",
        "prediction.propensity", "prediction.confidence")
    if prediction["confidence_band"] == "LOW":
        add("low_confidence", "This prediction has low confidence and should be treated cautiously.",
            "Low-confidence prediction: check the evidence before a customer conversation.", "prediction.confidence_band")

    if impact["status"] == "AVAILABLE":
        primary = impact["primary_metric"]
        metric_code = code(primary["metric"])
        metric_name = METRICS.get(metric_code, f"metric {metric_code}")
        horizon = impact["time_horizon"]
        horizon_unit = code(horizon["unit"])
        if horizon_unit not in {"YEAR", "MONTH", "DAY"}:
            raise ValueError("Time horizon unit needs reviewed wording")
        horizon_label = horizon_unit.lower() + ("" if horizon["value"] == 1 else "s")
        text = (f"Estimated potential {metric_name}: {number(primary['lower_estimate'])} to "
                f"{number(primary['upper_estimate'])} {unit(primary['unit'])}, "
                f"over {number(horizon['value'])} {horizon_label}.")
        add("impact", text, text, "impact.primary_metric", "impact.time_horizon")
        add("estimate", "This is a modelled estimate, not a measured or guaranteed saving.",
            "Impact is a modelled estimate, not a measured or guaranteed outcome.", "impact.status")
        method_id = code(impact["method_id"])
        method = METHODS.get(method_id, f"documented calculation {method_id}")
        add("method", f"Method: {method}.", f"Method: {method} ({method_id}).", "impact.method_id")
        reviewed_assumptions = [ASSUMPTIONS.get(code(item["code"]), f"documented assumption {code(item['code'])}")
                                for item in impact["assumptions"]]
        text = "Assumptions: " + "; ".join(reviewed_assumptions) + "."
        add("assumptions", text, text, "impact.assumptions")
        factor_codes = []
        for factor in impact["emission_factors"]:
            # Source text is upstream content; only compact source identifiers
            # are rendered. Full provenance remains in the unchanged impact object.
            source = factor["source"]
            if isinstance(source, str) and re.fullmatch(r"[A-Z][A-Z0-9_]{0,95}", source):
                factor_codes.append(f"{source} ({str(factor['source_year']).removesuffix('.0')})")
        provenance = "Factor sources: " + "; ".join(dict.fromkeys(factor_codes)) + "." if factor_codes else (
            "Full emission-factor provenance is available in the impact evidence panel.")
        add("factors", "Documented emissions factors underpin the estimate; see the impact evidence panel.",
            provenance, "impact.emission_factors")
        for index, metric in enumerate(impact["supporting_metrics"]):
            if metric["value"] is not None and metric["unit"] in UNITS and metric["metric"] is not None:
                label = METRICS.get(code(metric["metric"]), code(metric["metric"]))
                add(f"support_{index}", None, f"Supporting estimate for {label}: {number(metric['value'])} {unit(metric['unit'])}.",
                    f"impact.supporting_metrics[{index}]")
        add("metric_separation", None, "Keep emissions, energy, paper and digital adoption as separate metrics; digital adoption alone is not a carbon saving.",
            "impact.primary_metric.metric")
    else:
        text = {
            "INSUFFICIENT_DATA": "There is insufficient data to estimate sustainability impact.",
            "CALCULATION_ERROR": "The impact calculation failed; no impact estimate is available.",
            "NOT_APPLICABLE": "No sustainability impact estimate applies to this opportunity.",
        }[impact["status"]]
        add("impact", text, text, "impact.status")

    for index, failed in enumerate(eligibility["failed_rules"]):
        if failed is None:
            add(f"failed_{index}", None, "A failed rule was reported without its identifier.",
                f"eligibility.failed_rules[{index}]")
            continue
        failed_code = code(failed)
        add(f"failed_{index}", None, f"Failed rule {failed_code}: {RULES.get(failed_code, 'see the rules evidence panel')}.",
            f"eligibility.failed_rules[{index}]")
    if eligibility["missing_requirements"]:
        add("missing", "Required information is missing; the bank team must review the data.",
            "Required eligibility information is missing; consult the structured missing-requirements list.",
            "eligibility.missing_requirements")
    if eligibility["requires_human_review"] or record["audit"]["human_review_required"] or decision == "MANUAL_REVIEW":
        add("human_review", "A bank staff member must review this opportunity.",
            "Human review is required before any further action.", "audit.human_review_required")
    action = recommendation["action_code"]
    if action is not None:
        action = code(action)
        if action in ACTION_PRODUCTS and ACTION_PRODUCTS[action] != opportunity["product_code"]:
            raise ValueError("Action does not match the product")
        wording = ACTIONS.get(action)
        # A customer offer action is allowed only behind the already-set gate.
        customer_action = (wording + ", subject to authorised bank checks.") if wording else (
            "Ask the bank team about the approved next step.")
        add("action", customer_action, f"Next step: {wording or 'consult the approved action in the structured record'} ({action}).",
            "recommendation.action_code")
    else:
        add("action", "No customer action was supplied; contact the bank team for guidance.",
            "No next-step action was supplied. Do not invent an offer.", "recommendation.action_code")
    cutoff = record["data_cutoff_date"]
    add("timestamp", f"Based on data available as of {cutoff}.", f"Data cutoff: {cutoff}.", "data_cutoff_date",
        customer_alt=f"Data as of {cutoff}.")
    headlines = (f"Explore {name}", f"Your {name} insight") if show_customer else ()
    if len(customer) > 64 or len(manager) > 64:
        raise ValueError("Too many facts for one explanation; review the upstream record")
    return Catalog(headlines, tuple(customer), tuple(manager))
