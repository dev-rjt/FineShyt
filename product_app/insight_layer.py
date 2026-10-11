"""FR5 - Customer insight layer.

The LLM ONLY rewrites a structured payload into plain language. It never predicts, calculates impact
or decides eligibility. Every generated text is checked: any number in the text must exist in the payload,
otherwise we fall back to a deterministic template (so the UI never shows an ungrounded figure).

Set OLLAMA_API_KEY for Ollama Cloud, or point OLLAMA_BASE_URL at a local Ollama
server. Without a usable Ollama configuration the same facts are rendered by the
deterministic template.
"""
import hashlib, json, math, os, re, threading
from urllib.parse import urlsplit

import requests

REASON_TEXT = {
    "HIGH_FUEL_SPEND": "your monthly fuel spend is high", "HIGH_ANNUAL_MILEAGE": "you drive a lot each year",
    "OLDER_VEHICLE": "your vehicle is getting older", "EXISTING_VEHICLE_LOAN": "you already have vehicle finance",
    "FUEL_SHARE_OF_SPEND_HIGH": "fuel is a large share of your spending", "FREQUENT_REFUELLING": "you refuel often",
    "RISING_FUEL_SPEND": "your fuel spend has been rising", "ICE_VEHICLE_TYPE": "your current vehicle runs on petrol/diesel",
    "HIGH_SUSTAINABILITY_PREFERENCE": "you've told us sustainability matters to you",
    "URBAN_CHARGING_ACCESS": "you live where charging is easier to access", "INCOME_SUPPORTS_AFFORDABILITY": "your income profile fits this product",
    "HOME_OWNER": "you own your home", "EXISTING_MORTGAGE": "you have a mortgage", "EXISTING_INVESTMENTS": "you already hold investments",
    "HIGH_ELECTRICITY_USE": "your electricity use is high", "HIGH_GAS_USE": "your gas use is high",
    "HIGH_HEATING_ENERGY_USE": "your heating energy use is high", "HIGH_WINTER_HEATING_LOAD": "your winter heating load is high",
    "HOME_IMPROVEMENT_ACTIVITY": "you've been spending on home improvements", "HIGH_UTILITY_SPEND": "your utility spend is high",
    "HIGH_ELECTRICITY_SPEND": "your electricity bills are high", "HIGH_GAS_SPEND": "your gas bills are high",
    "HIGH_PAPER_STATEMENT_SHARE": "most of your statements are still on paper",
    "HIGH_DIGITAL_ACTIVITY": "you bank digitally a lot", "LOW_BRANCH_USE": "you rarely visit a branch",
    "HIGH_DIGITAL_ENGAGEMENT": "you're a confident digital user", "RISING_DIGITAL_ACTIVITY": "your digital activity is growing",
    "AGE_PROFILE_FIT": "your profile fits this product", "STRONG_BALANCE_PROFILE": "your balances are healthy",
    "STABLE_INCOME_INFLOW": "your income inflow is stable", "PUBLIC_TRANSPORT_USER": "you use public transport",
    "AUTOMOTIVE_SPEND": "you spend regularly on your vehicle", "VEHICLE_TYPE_FIT": "your vehicle type suits an EV swap",
    "HAS_SAVINGS": "you hold savings", "MULTI_PRODUCT_CUSTOMER": "you already use several of our products",
}
EXCLUSION_TEXT = {
    "NOT_HOME_OWNER": "no home ownership on record", "NO_VEHICLE_ON_RECORD": "no vehicle on record",
    "ALREADY_EV_NO_REPLACEMENT_USE_CASE": "you already drive an EV, so there is no replacement use case",
    "OUTSIDE_AGE_CRITERIA": "outside the product's age criteria", "ALREADY_HOLDS_PRODUCT": "you already hold this product",
    "ALREADY_MOSTLY_DIGITAL": "you're already mostly paperless",
    "OUTSIDE_ILLUSTRATIVE_AGE_RULE": "outside the product's illustrative age range",
    "UNKNOWN_VEHICLE_FUEL": "your vehicle's fuel type is not on record",
    "MISSING_SUITABILITY_DATA": "key details needed for this product are missing",
}
PRODUCT_NAME = {"EV_FINANCE": "EV Finance", "GREEN_HOME": "Green Home Loan", "SOLAR_FINANCE": "Solar Finance", "PAPERLESS": "Paperless Banking"}
ACTION = {"EV_FINANCE": "Explore EV options", "GREEN_HOME": "Explore green home upgrades",
          "SOLAR_FINANCE": "Explore solar finance", "PAPERLESS": "Go paperless"}


def reason_phrases(codes):
    return [REASON_TEXT.get(c, c.replace("_", " ").lower()) for c in codes]


def build_payload(rec: dict) -> dict:
    """Structured, LLM-safe payload from one recommendation row (nothing else is passed to the LLM)."""
    impact = json.loads(rec["impact_json"]) if isinstance(rec.get("impact_json"), str) else {}
    codes = [c for c in str(rec["reason_codes"]).split(";") if c and not c.startswith("EXCLUDED:")]
    p = dict(product=PRODUCT_NAME[rec["opportunity"]], product_id=rec["product_id"],
             recommended=bool(rec["recommend"]), propensity_pct=round(100 * rec["propensity"]) if rec["propensity"] == rec["propensity"] else None,
             confidence_pct=round(100 * rec["confidence"]) if rec["confidence"] == rec["confidence"] else None,
             reason_codes=codes, reasons_plain=reason_phrases(codes), data_as_of=str(rec["data_timestamp"]),
             impact_status=impact.get("status", "NOT_APPLICABLE"), action=ACTION[rec["opportunity"]])
    if impact.get("status") == "OK":
        for k in ("avoided_kg_co2e_per_year", "estimate_low", "estimate_central", "estimate_high",
                  "horizon", "method", "assumptions", "factors", "paper_statements_avoided",
                  "paper_sheets_avoided", "digital_adoption_shift_pp", "energy_saved_kwh", "system_kwp", "generation_kwh"):
            if k in impact: p[k] = impact[k]
        # The public API sends the period as horizon_months, not horizon.
        months = impact.get("horizon_months")
        if not p.get("horizon") and isinstance(months, int) and not isinstance(months, bool) and months > 0:
            p["horizon"] = f"{months} months"
    elif impact.get("status") == "INSUFFICIENT_DATA":
        p["missing_inputs"] = impact.get("missing_inputs")
    return p


def template_explain(p: dict) -> str:
    if not p["recommended"]:
        return f"We are not highlighting {p['product']} for you right now."
    why = "; ".join(p["reasons_plain"][:3]) or "your recent activity"
    s = f"{p['product']} may suit you because {why}. "
    if p["impact_status"] == "OK":
        if p["product"] == "Paperless Banking":
            s += (f"Switching could avoid about {p['paper_statements_avoided']} paper statements "
                  f"(~{p['paper_sheets_avoided']} sheets) a year")
            low = p.get("estimate_low", p.get("avoided_kg_co2e_per_year"))
            high = p.get("estimate_high", p.get("avoided_kg_co2e_per_year"))
            s += (f", with an estimated potential range of {low}–{high} kg CO2e. " if low is not None and high is not None
                  else ". We do not show a carbon figure because no sourced paper-statement factor is available. ")
        else:
            if not p.get("horizon"):
                return (s + "The estimate period is unavailable. "
                        f"This is an indication of interest, not an offer or approval; eligibility is confirmed separately. Based on data as of {p['data_as_of']}.")
            s += (f"Our estimated potential range is {p.get('estimate_low', p['avoided_kg_co2e_per_year']):,}–"
                  f"{p.get('estimate_high', p['avoided_kg_co2e_per_year']):,} kg CO2e per "
                  f"{p['horizon'].replace('12 months', 'year')} (not a measured result). ")
    elif p["impact_status"] == "INSUFFICIENT_DATA":
        s += "We don't have enough data to estimate the carbon impact yet. "
    s += f"This is an indication of interest, not an offer or approval; eligibility is confirmed separately. Based on data as of {p['data_as_of']}."
    return s


SYSTEM = (
    "You write a short, warm explanation for a bank customer from a JSON object of verified facts.\n"
    "Rules:\n"
    "- Write 2 or 3 plain sentences, under 70 words. No lists, headings or markdown.\n"
    "- Start by naming the product and saying it may suit them, then explain why using only the items in \"reasons\", "
    "in your own words.\n"
    "- If impact_status is \"ESTIMATE\": say switching could potentially avoid between co2e_low and co2e_high followed by "
    "\"unit\", copied exactly, and say this is an estimate, not a measured result. If paper_statements_avoided_per_year is present, also "
    "mention the paper statements (and sheets) avoided each year. Keep paper and carbon figures separate; never add them. "
"\n"
    "- If impact_status is \"PAPER_ONLY\": say switching could avoid about paper_statements_avoided_per_year paper "
    "statements (and paper_sheets_avoided_per_year sheets) a year, copied exactly. Do not mention carbon, CO2e, emissions "
    "or missing data at all.\n"
    "- If impact_status is \"INSUFFICIENT_DATA\": say we do not have enough data to estimate the carbon impact yet, "
    "with no figures.\n"
    "- If impact_status is \"NOT_AVAILABLE\": do not mention any carbon figure.\n"
    "- Copy numbers exactly as written in the JSON. Never round, convert, calculate or add numbers. Never use percentages.\n"
    "- Never say the customer is eligible, approved, pre-approved, qualifies or is guaranteed anything. "
    "Never say \"we recommend\" and never promise savings.\n"
    "- Do not mention dates, eligibility checks, offers or next steps; those are added separately."
)
COMPLIANCE_TAIL = ("This is an indication of interest, not an offer or approval, and is subject to eligibility checks. "
                   "Based on data as of {data_as_of}.")
BANNED = re.compile(r"\b(eligib\w*|approv\w*|pre-approv\w*|qualif\w*|guarantee\w*|we recommend|definitely|certainly|"
                    r"will (save|reduce|cut|lower))\b", re.IGNORECASE)
NO_DATA = re.compile(r"(not|n't) (have )?enough data|insufficient data|(unable|not able|cannot|can't) (to )?estimate", re.IGNORECASE)
_EXPLANATION_CACHE: dict[str, tuple[str, str]] = {}
_CACHE_LOCK = threading.Lock()
_CACHE_LIMIT = 4096

DEFAULT_OLLAMA_MODEL = "gemma4:31b"
DEFAULT_OLLAMA_BASE_URL = "https://ollama.com"


def _enabled(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _ollama_config() -> tuple[str, str, str | None, float]:
    """Return a validated Ollama origin, model, optional key and timeout."""
    base_url = os.getenv("OLLAMA_BASE_URL", DEFAULT_OLLAMA_BASE_URL).strip().rstrip("/")
    model = os.getenv("OLLAMA_MODEL", DEFAULT_OLLAMA_MODEL).strip()
    api_key = os.getenv("OLLAMA_API_KEY", "").strip() or None
    parsed = urlsplit(base_url)
    loopback = parsed.hostname in {"localhost", "127.0.0.1", "::1"}
    cloud = parsed.scheme == "https" and parsed.hostname == "ollama.com"
    lan = _enabled(os.getenv("OLLAMA_ALLOW_LAN"))
    clean_origin = (not parsed.username and not parsed.password and parsed.path in {"", "/"}
                    and not parsed.query and not parsed.fragment)
    if not clean_origin or not ((parsed.scheme == "http" and loopback)
                                or cloud or (lan and parsed.scheme in {"http", "https"})):
        raise ValueError("OLLAMA_BASE_URL is not an allowed Ollama origin")
    if cloud and not api_key:
        raise ValueError("OLLAMA_API_KEY is required for Ollama Cloud")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}", model):
        raise ValueError("OLLAMA_MODEL is invalid")
    timeout = float(os.getenv("OLLAMA_TIMEOUT_SECONDS", "90"))
    if not math.isfinite(timeout) or not 1 <= timeout <= 300:
        raise ValueError("OLLAMA_TIMEOUT_SECONDS must be between 1 and 300")
    return base_url, model, api_key, timeout


def ollama_configured() -> bool:
    try:
        _ollama_config()
        return True
    except (TypeError, ValueError):
        return False


def _ollama_explain(facts: dict, timeout: float | None = None) -> str:
    base_url, model, api_key, configured_timeout = _ollama_config()
    timeout = configured_timeout if timeout is None else min(configured_timeout, timeout)
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    response = requests.post(
        f"{base_url}/api/chat",
        headers=headers,
        json={
            "model": model,
            "messages": [
                {"role": "system", "content": SYSTEM},
                {"role": "user", "content": json.dumps(facts, default=str)},
            ],
            "stream": False,
            "options": {"temperature": 0, "seed": 2026, "num_predict": 300},
        },
        timeout=timeout,
        allow_redirects=False,
    )
    response.raise_for_status()
    result = response.json()
    if result.get("done") is not True or result.get("done_reason") not in {None, "stop"}:
        raise ValueError("Ollama returned an incomplete response")
    text = result.get("message", {}).get("content")
    if not isinstance(text, str) or not text.strip():
        raise ValueError("Ollama returned no message")
    return text.strip()


def _numbers(text):
    return {n.replace(",", "") for n in re.findall(r"\d[\d,]*\.?\d*", text)}


def is_grounded(text: str, p: dict) -> bool:
    allowed = _numbers(json.dumps(p, default=str))
    allowed |= {n.rstrip("0").rstrip(".") for n in allowed}
    for n in _numbers(text):
        n = n.rstrip(".")
        if n not in allowed and n.rstrip("0").rstrip(".") not in allowed and n not in {"12"}:
            return False
    return True


def _fmt(value) -> str:
    return f"{value:,}" if isinstance(value, (int, float)) and not isinstance(value, bool) else str(value)


def _norm(number: str) -> str:
    number = number.replace(",", "").rstrip(".")
    return number.rstrip("0").rstrip(".") if "." in number else number


def llm_facts(p: dict) -> dict:
    """The only data the LLM sees: no scores, factors or IDs, and figures pre-formatted like the template."""
    facts = {"product": p["product"], "reasons": p["reasons_plain"][:3] or ["your recent activity"]}
    low = p.get("estimate_low", p.get("avoided_kg_co2e_per_year"))
    high = p.get("estimate_high", p.get("avoided_kg_co2e_per_year"))
    has_range = low is not None and high is not None
    if p["impact_status"] == "OK" and p["product"] == "Paperless Banking" and "paper_statements_avoided" in p:
        facts.update(impact_status="PAPER_ONLY", paper_statements_avoided_per_year=_fmt(p["paper_statements_avoided"]))
        if "paper_sheets_avoided" in p:
            facts["paper_sheets_avoided_per_year"] = _fmt(p["paper_sheets_avoided"])
        if has_range:  # only when a sourced paper factor exists
            facts.update(impact_status="ESTIMATE", co2e_low=_fmt(low), co2e_high=_fmt(high), unit="kg CO2e per year")
    elif p["impact_status"] == "OK" and has_range and p.get("horizon"):
        facts.update(impact_status="ESTIMATE", co2e_low=_fmt(low), co2e_high=_fmt(high),
                     unit=f"kg CO2e per {p['horizon'].replace('12 months', 'year')}")
    elif p["impact_status"] == "INSUFFICIENT_DATA":
        facts["impact_status"] = "INSUFFICIENT_DATA"
    else:
        facts["impact_status"] = "NOT_AVAILABLE"
    return facts


def verify_llm_text(text: str, facts: dict, data_as_of: str) -> str | None:
    """Return None when the text meets the template's standard, otherwise a short rejection reason."""
    if not 40 <= len(text) <= 700:
        return "length"
    if facts["product"].casefold() not in text.casefold():
        return "product not named"
    if BANNED.search(text):
        return "forbidden wording"
    if "%" in text:
        return "percentage"
    allowed = {_norm(n) for n in _numbers(json.dumps(facts) + " " + data_as_of)}
    numbers = {_norm(n) for n in _numbers(text)}
    if numbers - allowed:
        return "ungrounded number"
    status = facts["impact_status"]
    if status == "ESTIMATE":
        required = {_norm(facts[key]) for key in ("co2e_low", "co2e_high", "paper_statements_avoided_per_year") if key in facts}
        if not required <= numbers:
            return "missing estimate range"
        if "estimat" not in text.casefold():
            return "figure not called an estimate"
    elif status == "PAPER_ONLY":
        if _norm(facts["paper_statements_avoided_per_year"]) not in numbers:
            return "missing paper figure"
        if re.search(r"co2|carbon|emission|enough data", text, re.IGNORECASE):
            return "carbon claim without a sourced factor"
    elif status == "INSUFFICIENT_DATA" and not NO_DATA.search(text):
        return "missing insufficient-data statement"
    return None  # NOT_AVAILABLE facts hold no figures, so the grounding check already rejects any number


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", text.replace("**", "")).strip()


def explain(p: dict, use_llm: bool = True, timeout: float | None = None):
    """Returns (text, source) where source is 'llm', 'template', 'template (llm rejected: ...)' or 'template (llm error: ...)'.

    LLM text must pass verify_llm_text; the compliance sentence is always appended by code, never written by the LLM.
    """
    if not (use_llm and p["recommended"] and ollama_configured()):
        return template_explain(p), "template"
    facts = llm_facts(p)
    base_url, model, _, _ = _ollama_config()
    key = hashlib.sha256(json.dumps([base_url, model, SYSTEM, facts, p["data_as_of"]], sort_keys=True).encode()).hexdigest()
    with _CACHE_LOCK:
        cached = _EXPLANATION_CACHE.get(key)
    if cached:
        return cached
    try:
        text = _clean(_ollama_explain(facts, timeout))
    except Exception as e:  # network / auth / quota -> never break the UI; not cached so it retries later
        return template_explain(p), f"template (llm error: {type(e).__name__})"
    problem = verify_llm_text(text, facts, p["data_as_of"])
    if problem:
        result = template_explain(p), f"template (llm rejected: {problem})"
    else:
        tail = COMPLIANCE_TAIL.format(data_as_of=p["data_as_of"])
        result = f"{text if text.endswith(('.', '!')) else text + '.'} {tail}", "llm"
    with _CACHE_LOCK:
        if len(_EXPLANATION_CACHE) >= _CACHE_LIMIT:
            _EXPLANATION_CACHE.clear()
        _EXPLANATION_CACHE[key] = result
    return result
