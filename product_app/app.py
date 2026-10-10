"""Verdant Streamlit frontend. All protected data and scoring comes from FastAPI."""
import html, json, os
from pathlib import Path
import pandas as pd, plotly.express as px, plotly.graph_objects as go, requests, streamlit as st
from auth import Principal, credentials_ready, load_local_env

load_local_env(Path(__file__).with_name(".env"))

from config import PRODUCTS, CUTOFF_DATE, OUTCOME_WINDOW_MONTHS
from insight_layer import build_payload, explain, reason_phrases, EXCLUSION_TEXT, PRODUCT_NAME, ACTION

API_BASE_URL = os.getenv("API_BASE_URL", "http://127.0.0.1:8000").rstrip("/")

st.set_page_config(page_title="Verdant | Green Customer Insights", page_icon="🌿", layout="wide",
                   initial_sidebar_state="expanded")
GREEN = "#006A4D"
MINT = "#DDF5EA"
INK = "#102B24"
AMBER = "#E8A23A"
PRODUCT_COLOURS = {
    "EV Finance": "#006A4D", "Green Home Loan": "#2B8C6B",
    "Solar Finance": "#E8A23A", "Paperless Banking": "#5E6AD2",
}
BANK_PAGES = ["Executive overview", "Customer directory", "Opportunity desk", "Impact planner", "Model governance", "Data architecture", "Risk & controls"]
CUSTOMER_PAGES = ["My green insights"]
API_TO_INTERNAL_PRODUCT = {
    "EV_FINANCE": "EV_FINANCE", "GREEN_HOME_LOAN": "GREEN_HOME",
    "SOLAR_FINANCE": "SOLAR_FINANCE", "PAPERLESS_BANKING": "PAPERLESS",
}


st.markdown("""
<style>
    :root { --forest:#006A4D; --ink:#102B24; --mint:#DDF5EA; --paper:#F7FAF8; }
    .stApp { background: #F7FAF8; color: #102B24; }
    #MainMenu, footer, [data-testid="stToolbar"] { visibility: hidden; }
    [data-testid="stAppViewContainer"] > .main .block-container {
        max-width: 1440px; padding-top: 2rem; padding-bottom: 4rem;
    }
    [data-testid="stSidebar"] { background: #0D2F27; border-right: 0; }
    [data-testid="stSidebar"] * { color: #EDF8F3; }
    [data-testid="stSidebar"] [data-baseweb="select"] > div,
    [data-testid="stSidebar"] [data-baseweb="tag"] { background: #173F35; }
    [data-testid="stSidebar"] hr { border-color: rgba(255,255,255,.12); }
    [data-testid="stSidebar"] .stButton > button {
        background:rgba(255,255,255,.06); border:1px solid rgba(255,255,255,.32); color:#EDF8F3;
    }
    [data-testid="stSidebar"] .stButton > button:hover { background:rgba(255,255,255,.12); border-color:#EDF8F3; }
    [data-testid="stMetric"] {
        background: #FFFFFF; border: 1px solid #DDE8E3; border-radius: 16px;
        padding: 16px 18px; box-shadow: 0 8px 26px rgba(16,43,36,.05);
    }
    [data-testid="stMetricLabel"] { color: #587067; }
    [data-testid="stMetricValue"] { color: #102B24; letter-spacing: -0.03em; }
    [data-testid="stVerticalBlockBorderWrapper"] {
        background: #FFFFFF; border-color: #DDE8E3 !important; border-radius: 18px !important;
        box-shadow: 0 10px 30px rgba(16,43,36,.045);
    }
    .verdant-hero {
        background: linear-gradient(120deg,#0D2F27 0%,#006A4D 60%,#168865 100%);
        color: white; padding: 28px 32px; border-radius: 22px; margin: 2px 0 22px;
        box-shadow: 0 18px 50px rgba(0,74,53,.18); position: relative; overflow:hidden;
    }
    .verdant-hero:after { content:""; position:absolute; width:240px; height:240px; right:-65px; top:-110px;
        border:52px solid rgba(255,255,255,.08); border-radius:50%; }
    .verdant-eyebrow { font-size:.72rem; letter-spacing:.16em; text-transform:uppercase; opacity:.78; font-weight:700; }
    .verdant-hero h1 { color:white; margin:.35rem 0 .45rem; font-size:2.15rem; letter-spacing:-.04em; }
    .verdant-hero p { max-width:760px; margin:0; color:#DDF5EA; font-size:1rem; line-height:1.55; }
    .hero-meta { display:flex; gap:10px; flex-wrap:wrap; margin-top:18px; }
    .hero-pill { background:rgba(255,255,255,.11); border:1px solid rgba(255,255,255,.16);
        border-radius:999px; padding:6px 11px; font-size:.78rem; color:white; }
    .section-kicker { color:#006A4D; font-size:.72rem; letter-spacing:.13em; font-weight:800; text-transform:uppercase; margin-bottom:.2rem; }
    .profile-strip { background:#EAF7F1; border:1px solid #CDE9DD; border-radius:16px; padding:16px 19px; margin:8px 0 18px; }
    .profile-id { color:#006A4D; font-weight:750; font-size:1.05rem; }
    .profile-meta { color:#4C675E; margin-top:4px; }
    .trust-strip { display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:10px; margin:12px 0 22px; }
    .trust-step { background:white; border:1px solid #DDE8E3; border-radius:14px; padding:12px 14px; }
    .trust-step b { display:block; color:#006A4D; font-size:.73rem; text-transform:uppercase; letter-spacing:.08em; }
    .trust-step span { color:#4C675E; font-size:.82rem; }
    .risk-note { background:#FFF8E8; border-left:4px solid #E8A23A; border-radius:8px; padding:13px 15px; color:#694B18; }
    .business-note { background:#EAF7F1; border:1px solid #CDE9DD; border-radius:14px; padding:14px 16px; color:#264C40; margin:10px 0 18px; }
    .business-note b { color:#006A4D; }
    .stTabs [data-baseweb="tab-list"] { gap:8px; }
    .stTabs [data-baseweb="tab"] { background:#EEF4F1; border-radius:999px; padding:8px 16px; }
    .stTabs [aria-selected="true"] { background:#DDF5EA; color:#006A4D; }
    .stButton > button { border-radius:999px; border-color:#006A4D; color:#006A4D; font-weight:650; }
    .stButton > button[kind="primary"] { background:#006A4D; color:white; }
    h1,h2,h3 { color:#102B24; letter-spacing:-.025em; }
    @media(max-width:900px){ .trust-strip{grid-template-columns:1fr 1fr;} .verdant-hero{padding:24px;} }
</style>
""", unsafe_allow_html=True)


def hero(eyebrow, title, body, pills=()):
    tags = "".join(f'<span class="hero-pill">{html.escape(str(x))}</span>' for x in pills)
    st.markdown(f"""<div class="verdant-hero"><div class="verdant-eyebrow">{html.escape(eyebrow)}</div>
        <h1>{html.escape(title)}</h1><p>{html.escape(body)}</p><div class="hero-meta">{tags}</div></div>""",
        unsafe_allow_html=True)


def plot(fig, height=None):
    fig.update_layout(
        template="plotly_white", height=height, margin=dict(l=20, r=20, t=58, b=24),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="Inter, Arial, sans-serif", color="#38534A", size=12),
        title_font=dict(color=INK, size=17), legend_title_text="",
        hoverlabel=dict(bgcolor="#0D2F27", font_color="white"),
    )
    fig.update_xaxes(showgrid=False, linecolor="#DDE8E3")
    fig.update_yaxes(gridcolor="#E8EFEC", zeroline=False)
    return fig


def friendly_source(source: str) -> str:
    """Business-facing description of the guarded explanation path."""
    return "AI-assisted, verified wording" if source == "llm" else "Verified standard wording"


def pretty_value(value) -> str:
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if isinstance(value, float):
        return f"{value:.0%}" if 0 <= value <= 1 else f"{value:,.2f}"
    return str(value)


def friendly_method(method: str) -> str:
    """Translate calculation notation into judge- and customer-ready language."""
    if not method:
        return "The estimate compares the recorded baseline with a documented 12-month scenario."
    if "EV_AVOIDED_V1" in method:
        return ("We compare emissions from driving the recorded annual distance in the current car "
                "with the electricity an EV would use for the same distance, using the approved grid factor.")
    if "car_petrol" in method:
        return ("We compare emissions from driving the recorded annual distance in the current petrol car "
                "with the electricity an EV would use for the same distance, using the approved grid factor.")
    if "car_diesel" in method:
        return ("We compare emissions from driving the recorded annual distance in the current diesel car "
                "with the electricity an EV would use for the same distance, using the approved grid factor.")
    if "car_hybrid" in method:
        return ("We compare emissions from driving the recorded annual distance in the current hybrid car "
                "with the electricity an EV would use for the same distance, using the approved grid factor.")
    if "HOME_EFFICIENCY_V1" in method or "metered kWh" in method:
        return ("We apply the documented home-efficiency reductions to the recorded annual gas and electricity "
                "use, then compare the resulting footprint with the current baseline.")
    if "SOLAR_GENERATION_V1" in method or "PV generation" in method:
        return ("We estimate annual solar generation from the modelled system size and compare the displaced "
                "grid electricity with the customer's current electricity footprint.")
    if "PAPER_AVOIDED_V1" in method or "paper statements" in method:
        return ("We multiply the annual paper statements that could be avoided by the documented per-statement "
                "factor. Digital adoption is reported separately from carbon impact.")
    return method.replace(" x ", " × ")


def friendly_assumption(item) -> str:
    if isinstance(item, dict):
        identifier = str(item.get("id", "Assumption")).replace("A_", "").replace("_", " ").title()
        value, unit = item.get("value"), item.get("unit")
        rendered = f"{value:g}" if isinstance(value, (int, float)) else str(value)
        return f"{identifier}: {rendered}{f' {unit}' if unit else ''} — {item.get('source', 'documented scenario assumption')}"
    return str(item).capitalize()


def login_screen():
    hero("Secure demo access", "Welcome to Verdant", "Choose the account supplied with the demo to open the customer or bank experience.",
         ["Role-based workspace", "Synthetic data only", "No financial decisions"])
    if not credentials_ready():
        st.error("Demo credentials are not configured. Copy .env.example to .env and set all four credential values.")
        st.stop()
    left, centre, right = st.columns([1, 1.15, 1])
    with centre:
        with st.container(border=True):
            st.markdown("### Sign in")
            with st.form("login", clear_on_submit=False):
                username = st.text_input("User ID", placeholder="Enter your bank or customer ID")
                password = st.text_input("Password", type="password")
                submitted = st.form_submit_button("Continue", type="primary", use_container_width=True)
            if submitted:
                try:
                    response = requests.post(
                        f"{API_BASE_URL}/auth/login",
                        json={"username": username, "password": password},
                        timeout=10,
                    )
                except requests.RequestException:
                    st.error("The API is not available. Start the complete app with ./run_demo.sh.")
                else:
                    if response.status_code == 200:
                        result = response.json()
                        identity = result["principal"]
                        principal = Principal(**identity)
                        st.session_state.clear()
                        st.session_state.principal = principal
                        st.session_state.access_token = result["access_token"]
                        st.rerun()
                    elif response.status_code == 401:
                        st.error("The user ID or password is incorrect.")
                    else:
                        st.error("The authentication service is not ready.")
            st.caption("Hackathon authentication boundary. A production deployment would use the bank's identity provider, MFA and server-side authorisation.")


if "principal" not in st.session_state:
    login_screen()
    st.stop()

principal = st.session_state.principal
access_token = st.session_state.access_token


def api_get(path: str, timeout: int = 60) -> dict:
    response = requests.get(
        f"{API_BASE_URL}{path}",
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=timeout,
    )
    response.raise_for_status()
    return response.json()


def canonical_to_ui_record(item: dict) -> dict:
    """Adapt the frozen public API contract to the dashboard's tabular view model."""
    internal = API_TO_INTERNAL_PRODUCT[item["opportunity"]]
    impact = dict(item["impact"])
    metrics = {metric["metric"]: metric for metric in impact.get("metrics", [])}
    co2e = metrics.get("CO2E_KG")
    if co2e:
        impact.update(avoided_kg_co2e_per_year=co2e["central"], estimate_low=co2e["low"],
                      estimate_central=co2e["central"], estimate_high=co2e["high"])
    energy = metrics.get("ENERGY_KWH")
    if energy:
        impact["energy_saved_kwh" if internal == "GREEN_HOME" else "energy_generated_kwh"] = energy["central"]
        impact["generation_kwh"] = energy["central"]
    paper = metrics.get("PAPER_SHEETS")
    if paper:
        impact["paper_sheets_avoided"] = int(paper["central"])
        impact["paper_statements_avoided"] = int(round(paper["central"] / 3))
    digital = metrics.get("DIGITAL_ADOPTION_PP")
    if digital:
        impact["digital_adoption_shift_pp"] = digital["central"]
    return {
        "customer_id": item["customer_id"], "opportunity": internal, "product_id": item["product_id"],
        "propensity": item["propensity"], "confidence": item["confidence"],
        "recommend": item["status"] == "RECOMMENDED",
        "reason_codes": ";".join(reason["code"] for reason in item["reason_codes"] if reason["kind"] == "DRIVER"),
        "data_timestamp": item["data_as_of"], "split": "live", "impact_status": impact["status"],
        "est_avoided_kg_co2e_yr": co2e["central"] if co2e else None,
        "impact_json": json.dumps(impact),
    }


# ----------------------------------------------------------------------------- data
@st.cache_data(show_spinner="Loading secure data from the API…")
def load(token: str, role: str, customer_id: str | None):
    del token  # Included in the cache key; requests use the current session token.
    if role == "bank":
        raw = api_get("/bank/bootstrap", timeout=120)
        recommendations = raw["recommendations"]
        customers = raw["customers"]
        digital = raw["digital_usage"]
        energy = raw["energy_usage"]
        factors = raw["emission_factors"]
        products = raw["products"]
        report = raw["evaluation"]
        scoring_source = "portfolio_batch"
    else:
        customer_360 = api_get(f"/customers/{customer_id}")
        scored = api_get(f"/customers/{customer_id}/opportunities")
        recommendations = [canonical_to_ui_record(item) for item in scored["items"]]
        customers = [{"customer_id": customer_360["customer_id"], **customer_360["profile"]}]
        digital, energy, factors, products, report = [], [], [], [], {}
        scoring_source = scored["scoring_source"]
    R = pd.DataFrame(recommendations)
    C = pd.DataFrame(customers)
    C["age_band"] = pd.cut(C.age, [17, 29, 44, 59, 120], labels=["18-29", "30-44", "45-59", "60+"])
    R = R.merge(C[["customer_id", "region", "income_band", "age_band", "age", "home_owner", "digital_usage",
                   "sustainability_preference"]], on="customer_id", how="left")
    imp = R.impact_json.map(json.loads)
    for k in ["avoided_kg_co2e_per_year", "estimate_low", "estimate_central", "estimate_high",
              "energy_saved_kwh", "energy_generated_kwh", "paper_statements_avoided",
              "paper_sheets_avoided", "digital_adoption_shift_pp"]:
        R[k] = imp.map(lambda d: d.get(k))
    R["product_name"] = R.opportunity.map(PRODUCT_NAME)
    return dict(R=R, C=C, dig=pd.DataFrame(digital), en=pd.DataFrame(energy),
                report=report, ef=pd.DataFrame(factors), prods=pd.DataFrame(products),
                scoring_source=scoring_source)


D = load(access_token, principal.role, principal.customer_id)
if D is None:
    st.error("The API did not return model data. Run the pipeline, then restart the complete app.")
    st.stop()
R, C = D["R"], D["C"]

# ----------------------------------------------------------------------------- sidebar
st.sidebar.markdown("## ◉ VERDANT")
st.sidebar.caption("Green customer intelligence")
st.sidebar.markdown(f"**{principal.display_name}**  \n<span style='color:#A9C7BB;font-size:.78rem'>{principal.role.upper()} ACCESS</span>",
                    unsafe_allow_html=True)
if st.sidebar.button("Sign out", use_container_width=True):
    st.session_state.clear()
    st.rerun()

pages = BANK_PAGES if principal.role == "bank" else CUSTOMER_PAGES
if "page" not in st.session_state or st.session_state.page not in pages:
    st.session_state.page = pages[0]
page = st.sidebar.radio("Workspace", pages, key="page", label_visibility="collapsed")
st.sidebar.markdown("---")
f_region, f_income, f_split, f_prod = [], [], "all", PRODUCTS
use_llm = bool(os.getenv("ANTHROPIC_API_KEY"))
if page == "Executive overview":
    st.sidebar.markdown("#### Portfolio filters")
    f_region = st.sidebar.multiselect("Region", sorted(C.region.dropna().unique()), placeholder="All regions")
    f_income = st.sidebar.multiselect("Income band", ["<20k", "20-35k", "35-50k", "50-80k", "80k+"],
                                      key="inc", placeholder="All income bands")
    f_prod = st.sidebar.multiselect("Product", PRODUCTS, default=PRODUCTS, format_func=PRODUCT_NAME.get)
elif page == "Opportunity desk":
    st.sidebar.markdown("#### Customer communication")
    use_llm = st.sidebar.toggle("Use approved AI wording", value=use_llm,
                                help="If configured, AI improves the wording only. Facts are verified and standard wording is used automatically if a check fails.")

st.sidebar.markdown("---")
st.sidebar.markdown("**Prototype status**  \n<span style='color:#A9C7BB;font-size:.82rem'>Synthetic customers · deterministic impact · estimates only</span>",
                    unsafe_allow_html=True)


def go_customer(cid):
    st.session_state.cust = cid; st.session_state.page = "Opportunity desk"


def record_response(cid, opportunity, response):
    memory = st.session_state.setdefault("customer_memory", {})
    memory[f"{cid}:{opportunity}"] = response


def filt(df):
    if f_region: df = df[df.region.isin(f_region)]
    if f_income: df = df[df.income_band.isin(f_income)]
    if f_split != "all": df = df[df.split == f_split]
    return df[df.opportunity.isin(f_prod)]


# ----------------------------------------------------------------------------- customer portal
if page == "My green insights":
    cid = principal.customer_id
    cust = R[R.customer_id == cid]
    profile = C[C.customer_id == cid]
    if cust.empty or profile.empty:
        st.error("This demo customer is not present in the scored dataset. Ask the demo administrator to update CUSTOMER_DEMO_ID.")
        st.stop()
    prof = profile.iloc[0]
    hero("Your green banking", "Small changes, made relevant to you.",
         "Explore sustainability options suggested from your synthetic demo activity. These are insights, not financial offers or approvals.",
         [f"Data as of {str(cust.data_timestamp.iloc[0])[:10]}", "Live model + rules + impact engine", "Eligibility checked separately"])
    st.markdown(f"""<div class="profile-strip"><div class="profile-id">Hello, {html.escape(str(cid))}</div>
        <div class="profile-meta">{html.escape(str(prof.region))} · digital banking profile · your recommendations are private to this signed-in demo account</div></div>""",
        unsafe_allow_html=True)
    flagged = cust[cust.recommend].sort_values("propensity", ascending=False)
    a, b, c = st.columns(3)
    a.metric("Ideas for you", len(flagged))
    b.metric("Highest relevance", "High" if len(flagged) and flagged.propensity.max() >= .65 else "Medium" if len(flagged) else "None")
    b.caption("Relevance is take-up propensity, not financial eligibility.")
    c.metric("Data freshness", str(cust.data_timestamp.iloc[0])[:10])
    st.markdown("### Your personalised insights")
    if flagged.empty:
        st.info("There are no new green insights for you right now. We do not force a recommendation when the evidence is weak.")
    for _, r in flagged.iterrows():
        payload = build_payload(r.to_dict())
        with st.container(border=True):
            title, confidence = st.columns([4, 1])
            title.markdown(f"<div class='section-kicker'>Personalised opportunity</div><h3>{html.escape(payload['product'])}</h3>",
                           unsafe_allow_html=True)
            confidence.metric("Evidence confidence", f"{payload['confidence_pct']}%")
            text, source = explain(payload, use_llm)
            st.write(text)
            st.caption(f"{friendly_source(source)} · based only on the evidence and estimate shown below")
            st.markdown("**Why this may be relevant**")
            st.markdown("  \n".join(f"- {phrase}" for phrase in payload["reasons_plain"][:4]))
            impact = json.loads(r.impact_json)
            if impact.get("status") == "OK":
                metrics = st.columns(3)
                metrics[0].metric("Estimated CO₂e range", f"{impact.get('estimate_low', impact['avoided_kg_co2e_per_year']):,.1f}–{impact.get('estimate_high', impact['avoided_kg_co2e_per_year']):,.1f} kg/year")
                if r.opportunity == "PAPERLESS":
                    metrics[1].metric("Paper statements avoided", f"{impact['paper_statements_avoided']}/year")
                    metrics[2].metric("Paper sheets avoided", f"{impact['paper_sheets_avoided']}/year")
                else:
                    metrics[1].metric("Current baseline", f"{impact['baseline_kg_co2e']:,.0f} kg/year")
                    metrics[2].metric("Modelled scenario", f"{impact['scenario_kg_co2e']:,.0f} kg/year")
                with st.expander("How this estimate was calculated"):
                    st.markdown(f"**Method**  \n{friendly_method(impact.get('method', ''))}")
                    assumptions = impact.get("assumptions", [])
                    if assumptions:
                        st.markdown("**Assumptions**")
                        st.markdown("  \n".join(f"- {friendly_assumption(item)}" for item in assumptions))
                    factors = impact.get("factors", [])
                    if factors:
                        st.markdown("**Factor provenance**")
                        st.markdown("  \n".join(f"- {factor['factor_id']}: {factor['kg_co2e_per_unit']} kg CO₂e/{factor['unit']} — {factor['source']}" for factor in factors))
                    st.caption("This is a modelled 12-month estimate, not a measured reduction.")
            elif impact.get("status") == "INSUFFICIENT_DATA":
                st.warning("We need more information before we can estimate the potential impact.")
            memory_key = f"{cid}:{r.opportunity}"
            saved = st.session_state.get("customer_memory", {}).get(memory_key)
            primary, later, status = st.columns([1.3, 1, 2])
            primary.button(ACTION[r.opportunity] + " →", key=f"my_act_{r.opportunity}", type="primary",
                           on_click=record_response, args=(cid, r.opportunity, "Interested"), use_container_width=True)
            later.button("Maybe later", key=f"my_later_{r.opportunity}", on_click=record_response,
                         args=(cid, r.opportunity, "Not now"), use_container_width=True)
            status.caption(f"Saved preference: {saved}" if saved else "No preference saved in this demo session.")
    st.caption("Any product application remains subject to the institution's authorised affordability, suitability and eligibility checks.")

# ----------------------------------------------------------------------------- 1. business dashboard
elif page == "Executive overview":
    F = filt(R); rec = F[F.recommend]
    ncust = F.customer_id.nunique()
    hero("Executive overview", "Turn customer signals into credible green growth.",
         "A single portfolio view for commercial opportunity, customer relevance and measurable sustainability potential—each with a clear control owner.",
         [f"Portfolio current to {CUTOFF_DATE.date()}", f"{OUTCOME_WINDOW_MONTHS}-month planning horizon", "Controlled synthetic environment"])
    st.markdown("<div class='trust-strip'><div class='trust-step'><b>1 · Predict</b><span>ML estimates propensity</span></div>"
                "<div class='trust-step'><b>2 · Gate</b><span>Rules check product fit</span></div>"
                "<div class='trust-step'><b>3 · Calculate</b><span>Carbon engine estimates impact</span></div>"
                "<div class='trust-step'><b>4 · Explain</b><span>LLM words verified facts only</span></div></div>", unsafe_allow_html=True)
    if F.empty:
        st.info("No records match these filters. Remove one or more filters to restore the portfolio view.")
        st.stop()
    c = st.columns(4)
    c[0].metric("Customers analysed", f"{ncust:,}")
    c[1].metric("Opportunities flagged", f"{len(rec):,}")
    c[2].metric("Customers with ≥1 opportunity", f"{rec.customer_id.nunique():,}")
    c[3].metric("Expected conversions*", f"{rec.propensity.sum():,.0f}", help="Sum of propensities of flagged opportunities")
    excluded_count = int(F.reason_codes.str.startswith("EXCLUDED").sum())
    st.caption(f"Expected conversions is the sum of flagged propensities; it is a planning estimate, not a guarantee. "
               f"Product rules suppressed {excluded_count:,} unsuitable product-customer combinations.")

    if len(rec):
        lead = rec.groupby("product_name").size().sort_values(ascending=False)
        st.markdown(f"<div class='business-note'><b>Executive signal:</b> {html.escape(str(lead.index[0]))} is the largest current opportunity pool "
                    f"with {int(lead.iloc[0]):,} prioritised conversations. Relationship teams can open the customer queue below; product eligibility remains a separate authorised process.</div>",
                    unsafe_allow_html=True)

    st.markdown("### Portfolio signals")
    t1, t2, t3, t4 = st.tabs(["Opportunities", "Impact ledger", "Segments & regions", "Trends"])
    with t1:
        a, b = st.columns(2)
        g = rec.groupby("product_name").agg(flagged=("customer_id", "size"), avg_propensity=("propensity", "mean"),
                                           avg_confidence=("confidence", "mean")).reset_index()
        a.plotly_chart(plot(px.bar(g, x="product_name", y="flagged", text="flagged", color="product_name",
                                   color_discrete_map=PRODUCT_COLOURS, title="Flagged opportunities by product",
                                   labels={"product_name": "", "flagged": "customers"})), width="stretch")
        cand = F[~F.reason_codes.str.startswith("EXCLUDED")]
        b.plotly_chart(plot(px.histogram(cand, x="propensity", color="product_name", nbins=30, barmode="overlay", opacity=.68,
                                         color_discrete_map=PRODUCT_COLOURS, title="Propensity among rule-eligible customers",
                                         labels={"product_name": "product"})), width="stretch")
        business_summary = g.rename(columns={"product_name": "Product", "flagged": "Prioritised customers",
                                              "avg_propensity": "Average interest signal", "avg_confidence": "Evidence confidence"})
        st.dataframe(business_summary.style.format({"Average interest signal": "{:.0%}", "Evidence confidence": "{:.0%}"}),
                     hide_index=True, width="stretch")
        rc = rec.reason_codes.str.split(";").explode().value_counts().head(12).reset_index()
        rc.columns = ["reason_code", "count"]
        rc["Customer signal"] = rc.reason_code.map(lambda x: reason_phrases([x])[0].capitalize())
        st.plotly_chart(plot(px.bar(rc.iloc[::-1], x="count", y="Customer signal", orientation="h",
                                    title="Most common evidence signals", color_discrete_sequence=[GREEN]), height=420), width="stretch")

    with t2:
        st.markdown("<div class='risk-note'><b>Impact ledger:</b> emissions, energy, paper and digital adoption are reported separately. Digital adoption is not counted as a carbon reduction. All values are modelled 12-month estimates.</div>", unsafe_allow_html=True)
        em = rec[rec.opportunity.isin(["EV_FINANCE", "GREEN_HOME", "SOLAR_FINANCE"])]
        pl = rec[rec.opportunity == "PAPERLESS"]
        m = st.columns(4)
        m[0].metric("Potential CO₂e range (EV+Home+Solar)", f"{em.estimate_low.sum() / 1000:,.0f}–{em.estimate_high.sum() / 1000:,.0f} t/yr")
        m[1].metric("Energy: saved + generated", f"{(rec.energy_saved_kwh.fillna(0).sum() + rec.energy_generated_kwh.fillna(0).sum()) / 1000:,.0f} MWh/yr")
        m[2].metric("Paper statements avoided", f"{pl.paper_statements_avoided.sum():,.0f}/yr", f"{pl.paper_sheets_avoided.sum():,.0f} sheets", delta_color="off")
        m[3].metric("Digital adoption", f"{len(pl):,} customers to switch", f"avg paper share {pl.digital_adoption_shift_pp.mean():.0f}%", delta_color="off")
        by = em.groupby("product_name").avoided_kg_co2e_per_year.agg(["sum", "mean", "count"]).reset_index()
        by["tonnes"] = by["sum"] / 1000
        x, y = st.columns(2)
        x.plotly_chart(plot(px.bar(by, x="product_name", y="tonnes", text=by.tonnes.round(0), color="product_name",
                                   color_discrete_map=PRODUCT_COLOURS, title="Potential avoided CO₂e by product",
                                   labels={"product_name": "", "tonnes": "tCO₂e / year"})), width="stretch")
        y.dataframe(by.rename(columns={"product_name": "Product", "mean": "avg kg/customer", "count": "customers"})[["Product", "customers", "avg kg/customer", "tonnes"]]
                    .style.format({"avg kg/customer": "{:,.0f}", "tonnes": "{:,.1f}"}), hide_index=True, width="stretch")
        with st.expander("Methods & emission factors"):
            st.dataframe(D["ef"], hide_index=True, width="stretch")
            st.caption("Factors are approximate UK DESNZ-style values and the paper factor is an assumption – verify before any real use. "
                       "Method: baseline vs scenario over 12 months (project/avoided-emissions style). Not a PCAF financed-emissions calculation.")

    with t3:
        seg = rec.groupby(["region", "income_band", "product_name"]).agg(flagged=("customer_id", "size"), avg_propensity=("propensity", "mean"),
                                                                       potential_kg=("avoided_kg_co2e_per_year", "sum")).reset_index()
        hm = rec.pivot_table(index="region", columns="product_name", values="customer_id", aggfunc="count", fill_value=0)
        st.plotly_chart(plot(px.imshow(hm, text_auto=True, aspect="auto", color_continuous_scale=[[0,"#F3F8F5"],[1,GREEN]],
                                     title="Flagged opportunities: region × product"), height=430), width="stretch")
        st.subheader("Top segments")
        top = seg[seg.flagged >= 3].sort_values(["avg_propensity", "flagged"], ascending=False).head(15)
        st.dataframe(top.rename(columns={"product_name": "Product", "income_band": "Income"}).style.format({"avg_propensity": "{:.2f}", "potential_kg": "{:,.0f}"}),
                     hide_index=True, width="stretch")
        ab = rec.groupby(["age_band", "product_name"], observed=True).size().reset_index(name="flagged")
        st.plotly_chart(plot(px.bar(ab, x="age_band", y="flagged", color="product_name", color_discrete_map=PRODUCT_COLOURS,
                                    barmode="group", title="Flagged by age band")), width="stretch")

    with t4:
        dg = D["dig"].copy()
        if f_region or f_income:
            ids = set(C[(C.region.isin(f_region) if f_region else True) & (C.income_band.isin(f_income) if f_income else True)].customer_id)
            dg = dg[dg.customer_id.isin(ids)]
        mt = dg.groupby("month")[["digital_statements", "paper_statements"]].sum()
        mt["digital_share_%"] = 100 * mt.digital_statements / (mt.digital_statements + mt.paper_statements)
        st.plotly_chart(plot(px.line(mt.reset_index(), x="month", y="digital_share_%", markers=True,
                                     color_discrete_sequence=[GREEN], title="Digital statement share by month (%)")), width="stretch")
        en = D["en"]
        if f_region or f_income: en = en[en.customer_id.isin(ids)]
        em_ = en.groupby("month")[["electricity_kwh", "gas_kwh"]].mean().reset_index().melt("month")
        st.plotly_chart(plot(px.line(em_, x="month", y="value", color="variable", markers=True,
                                     color_discrete_sequence=[GREEN, AMBER], title="Average household energy use per month (kWh)")), width="stretch")

    st.markdown("### Relationship-manager action queue")
    st.caption("A prioritised, explainable queue for the next customer conversation. Scores indicate interest—not financial eligibility.")
    top = rec.sort_values("propensity", ascending=False).head(25)[["customer_id", "product_name", "propensity", "confidence",
                                                                  "avoided_kg_co2e_per_year", "region"]].copy()
    if top.empty:
        st.info("No recommended opportunities match the current filters.")
    else:
        queue = top.rename(columns={"customer_id": "Customer", "product_name": "Opportunity", "propensity": "Interest signal",
                                    "confidence": "Evidence confidence", "avoided_kg_co2e_per_year": "Potential kg CO₂e/year", "region": "Region"})
        st.dataframe(queue.style.format({"Interest signal": "{:.0%}", "Evidence confidence": "{:.0%}", "Potential kg CO₂e/year": "{:,.0f}"}),
                     hide_index=True, width="stretch")
        left, right = st.columns([3, 1])
        sel = left.selectbox("Open a customer", top.customer_id.unique(), key="drill")
        right.write("")
        right.button("Open customer →", type="primary", on_click=go_customer, args=(sel,), use_container_width=True)

# ----------------------------------------------------------------------------- 2. complete customer directory
elif page == "Customer directory":
    hero("Customer directory", "Every customer in one governed portfolio view.",
         "Search and review all 5,000 synthetic customer profiles, their current opportunity count and their leading green conversation.",
         ["5,000 customer records", "Searchable portfolio", "Relationship-manager drill-down"])

    recommended = R[R.recommend].copy()
    opportunity_summary = (recommended.groupby("customer_id")
                            .agg(relevant_opportunities=("opportunity", "size"),
                                 highest_interest=("propensity", "max"),
                                 potential_kg_co2e=("avoided_kg_co2e_per_year", "sum"))
                            .reset_index())
    leading = (recommended.sort_values("propensity", ascending=False)
               .drop_duplicates("customer_id")[["customer_id", "product_name"]]
               .rename(columns={"product_name": "leading_opportunity"}))
    directory = C.copy().merge(opportunity_summary, on="customer_id", how="left").merge(leading, on="customer_id", how="left")
    directory["relevant_opportunities"] = directory.relevant_opportunities.fillna(0).astype(int)
    directory["leading_opportunity"] = directory.leading_opportunity.fillna("No prioritised opportunity")
    directory["potential_kg_co2e"] = directory.potential_kg_co2e.fillna(0)

    search_col, region_col, income_col = st.columns([1.25, 1, 1])
    search = search_col.text_input("Search customer ID", placeholder="For example, C12558")
    regions = region_col.multiselect("Region", sorted(directory.region.dropna().unique()), placeholder="All regions")
    incomes = income_col.multiselect("Income band", ["<20k", "20-35k", "35-50k", "50-80k", "80k+"], placeholder="All income bands")
    visible = directory.copy()
    if search:
        visible = visible[visible.customer_id.str.contains(search.strip(), case=False, regex=False)]
    if regions:
        visible = visible[visible.region.isin(regions)]
    if incomes:
        visible = visible[visible.income_band.isin(incomes)]

    metrics = st.columns(4)
    metrics[0].metric("Customers in directory", f"{len(directory):,}")
    metrics[1].metric("Currently displayed", f"{len(visible):,}")
    metrics[2].metric("With a prioritised opportunity", f"{(directory.relevant_opportunities > 0).sum():,}")
    metrics[3].metric("Without a current opportunity", f"{(directory.relevant_opportunities == 0).sum():,}")

    st.markdown("### Customer portfolio")
    st.caption("All records are synthetic. Interest signals support prioritisation and never establish financial eligibility.")
    customer_table = visible.rename(columns={
        "customer_id": "Customer ID", "age": "Age", "income_band": "Income band", "postcode": "Postcode",
        "home_owner": "Home owner", "digital_usage": "Digital engagement", "sustainability_preference": "Sustainability preference",
        "region": "Region", "relevant_opportunities": "Relevant opportunities", "leading_opportunity": "Leading opportunity",
        "highest_interest": "Highest interest signal", "potential_kg_co2e": "Potential kg CO₂e/year",
    })
    customer_table["Home owner"] = customer_table["Home owner"].map(lambda value: "Yes" if bool(value) else "No")
    customer_table = customer_table[["Customer ID", "Region", "Postcode", "Age", "Income band", "Home owner",
                                     "Digital engagement", "Sustainability preference", "Relevant opportunities",
                                     "Leading opportunity", "Highest interest signal", "Potential kg CO₂e/year"]]
    st.dataframe(customer_table.style.format({"Digital engagement": "{:.0%}", "Sustainability preference": "{:.0%}",
                                              "Highest interest signal": "{:.0%}", "Potential kg CO₂e/year": "{:,.1f}"},
                 na_rep="—"), hide_index=True, width="stretch", height=620)

    if len(visible):
        open_col, action_col = st.columns([3, 1])
        selected_customer = open_col.selectbox("Open full opportunity profile", visible.customer_id.tolist(), key="directory_customer")
        action_col.write("")
        action_col.button("Open opportunity profile →", type="primary", on_click=go_customer,
                          args=(selected_customer,), use_container_width=True)
    else:
        st.info("No customers match those filters.")

# ----------------------------------------------------------------------------- 3. customer view
elif page == "Opportunity desk":
    hero("Opportunity desk", "The next best green conversation, with evidence attached.",
         "Review customer relevance, product-rule outcomes and estimated impact in one relationship-manager workspace.",
         ["Human-led conversation", "Verified customer wording", "End-to-end evidence trail"])
    ids = sorted(R.customer_id.unique())
    if "cust" not in st.session_state: st.session_state.cust = ids[0]
    cid = st.selectbox("Find a customer", ids, key="cust", help="Synthetic customer identifier")
    cust = R[R.customer_id == cid]; prof = C[C.customer_id == cid].iloc[0]
    st.markdown(f"""<div class="profile-strip"><div class="profile-id">{html.escape(str(cid))}</div>
        <div class="profile-meta">{html.escape(str(prof.region))} · age {int(prof.age)} · income {html.escape(str(prof.income_band))} ·
        home owner: {'yes' if prof.home_owner else 'no'} · evidence current to {html.escape(str(cust.data_timestamp.iloc[0])[:10])}</div></div>""",
        unsafe_allow_html=True)
    flagged = cust[cust.recommend].sort_values("propensity", ascending=False)
    below = cust[(~cust.recommend) & (~cust.reason_codes.str.startswith("EXCLUDED"))]
    excl = cust[cust.reason_codes.str.startswith("EXCLUDED")]

    summary = st.columns(4)
    summary[0].metric("Relevant opportunities", len(flagged))
    summary[1].metric("Ruled out by data", len(excl))
    summary[2].metric("Highest propensity", f"{100 * flagged.propensity.max():.0f}%" if len(flagged) else "—")
    summary[3].metric("Evidence timestamp", str(cust.data_timestamp.iloc[0])[:10])

    st.markdown("### Recommended next conversations")
    if flagged.empty: st.info("No opportunities stand out for this customer right now. That is a valid outcome; no product is forced.")
    for _, r in flagged.iterrows():
        p = build_payload(r.to_dict())
        with st.container(border=True):
            h1, h2, h3 = st.columns([3, 1, 1])
            h1.markdown(f"<div class='section-kicker'>Priority customer conversation</div><h3>{html.escape(p['product'])}</h3>",
                        unsafe_allow_html=True)
            h2.metric("Interest signal", f"{p['propensity_pct']}%", help="Model estimate of take-up within the outcome window")
            h3.metric("Evidence confidence", f"{p['confidence_pct']}%", help="Reliability of the estimate (not eligibility)")
            text, src = explain(p, use_llm)
            st.write(text)
            st.caption(f"{friendly_source(src)} · Facts checked against the approved customer evidence")
            st.markdown("**Evidence behind this recommendation**")
            st.markdown("  \n".join(f"- {phrase.capitalize()}" for phrase in p["reasons_plain"]))
            imp = json.loads(r.impact_json)
            if imp.get("status") == "OK":
                if r.opportunity == "PAPERLESS":
                    q = st.columns(3)
                    q[0].metric("Paper statements avoided", f"{imp['paper_statements_avoided']}/yr")
                    q[1].metric("Sheets avoided", f"{imp['paper_sheets_avoided']}/yr")
                    q[2].metric("Est. CO₂e range", f"{imp['estimate_low']:,.2f}–{imp['estimate_high']:,.2f} kg/yr")
                    st.caption("Digital adoption is shown separately and is not itself a carbon reduction.")
                else:
                    q = st.columns(3)
                    q[0].metric("Est. CO₂e range", f"{imp.get('estimate_low', imp['avoided_kg_co2e_per_year']):,.0f}–{imp.get('estimate_high', imp['avoided_kg_co2e_per_year']):,.0f} kg/yr", help="Estimated range, not a measured result")
                    q[1].metric("Baseline → scenario", f"{imp['baseline_kg_co2e']:,.0f} → {imp['scenario_kg_co2e']:,.0f} kg")
                    extra = imp.get("energy_saved_kwh") or imp.get("generation_kwh")
                    if extra: q[2].metric("Energy " + ("saved" if "energy_saved_kwh" in imp else "generated"), f"{extra:,.0f} kWh/yr")
                with st.expander("Method & assumptions"):
                    st.markdown(f"**Calculation method**  \n{friendly_method(imp.get('method', ''))}")
                    assumptions = imp.get("assumptions", [])
                    if assumptions:
                        st.markdown("**Planning assumptions**")
                        st.markdown("  \n".join(f"- {friendly_assumption(item)}" for item in assumptions))
                    factors = imp.get("factors", [])
                    if factors:
                        st.markdown("**Factor provenance**")
                        st.dataframe(pd.DataFrame(factors), hide_index=True, width="stretch")
                    st.caption("The estimate uses recorded activity inputs and approved emission factors. Raw payloads remain in the audit layer, not the business interface.")
            elif imp.get("status") == "INSUFFICIENT_DATA":
                st.warning(f"Not enough data to estimate impact: missing {', '.join(imp['missing_inputs'])}")
            memory_key = f"{cid}:{r.opportunity}"
            saved = st.session_state.get("customer_memory", {}).get(memory_key)
            action_col, later_col, note_col = st.columns([1.3, 1, 2])
            action_col.button(ACTION[r.opportunity] + " →", key=f"act_{cid}_{r.opportunity}", type="primary",
                              on_click=record_response, args=(cid, r.opportunity, "Interested"), use_container_width=True,
                              help="Records an in-session response only; it does not submit an application")
            later_col.button("Not now", key=f"later_{cid}_{r.opportunity}", on_click=record_response,
                             args=(cid, r.opportunity, "Not now"), use_container_width=True)
            note_col.caption(f"Saved response: {saved}" if saved else "No customer response recorded in this demo session.")
    if len(below):
        with st.expander(f"Monitor, but do not contact yet ({len(below)})"):
            watch = below[["product_name", "propensity", "confidence"]].rename(columns={"product_name": "Opportunity",
                    "propensity": "Interest signal", "confidence": "Evidence confidence"})
            st.dataframe(watch.style.format({"Interest signal": "{:.0%}", "Evidence confidence": "{:.0%}"}),
                         hide_index=True, width="stretch")
    if len(excl):
        with st.expander(f"Suppressed by product rules ({len(excl)})"):
            for _, r in excl.iterrows():
                why = r.reason_codes.split(":", 1)[1]
                st.write(f"**{r.product_name}** — {EXCLUSION_TEXT.get(why, 'This opportunity does not meet the configured product rules.').capitalize()}.")

# ----------------------------------------------------------------------------- 3. what-if simulator
elif page == "Impact planner":
    from carbon_engine import estimate_impact, ASSUMPTIONS
    hero("Impact planner", "Build a credible sustainability scenario.",
         "Test a customer activity scenario and compare its modelled 12-month impact. Calculations are deterministic, documented and kept separate from customer propensity.",
         ["Scenario planning", "Approved factors", "Baseline vs future state"])
    controls, results = st.columns([.8, 1.2], gap="large")
    with controls:
        st.markdown("### Scenario inputs")
        prod = st.selectbox("Opportunity", PRODUCTS, format_func=PRODUCT_NAME.get)
    row = {}
    with controls:
        if prod == "EV_FINANCE":
            row["annual_mileage"] = st.slider("Annual mileage (miles)", 1000, 30000, 10000, 500)
            ft = st.selectbox("Current fuel", ["petrol", "diesel", "hybrid"]); row["fuel_type_code"] = {"petrol": 0, "diesel": 1, "hybrid": 2}[ft]
        elif prod == "GREEN_HOME":
            row["gas_kwh_yr"] = st.slider("Gas use (kWh/year)", 0, 25000, 12000, 500)
            row["elec_kwh_yr"] = st.slider("Electricity use (kWh/year)", 500, 10000, 3500, 100)
        elif prod == "SOLAR_FINANCE":
            row["elec_kwh_yr"] = st.slider("Electricity use (kWh/year)", 500, 10000, 3500, 100)
        else:
            row["paper_stmts_yr"] = st.slider("Paper statements per year", 0, 36, 12)
            row["paper_share"] = st.slider("Paper share of statements", 0.0, 1.0, 0.8, 0.05)
        st.caption("Inputs are illustrative. This calculator does not assess affordability or financial eligibility.")
    imp = estimate_impact(prod, pd.Series(row))
    with results:
        st.markdown("### Estimated outcome")
        if imp["status"] != "OK":
            st.warning(f"Insufficient data: {imp.get('missing_inputs')}")
        else:
            c = st.columns(3)
            c[0].metric("Est. CO₂e range", f"{imp.get('estimate_low', imp['avoided_kg_co2e_per_year']):,.1f}–{imp.get('estimate_high', imp['avoided_kg_co2e_per_year']):,.1f} kg/yr")
            if "baseline_kg_co2e" in imp:
                c[1].metric("Baseline", f"{imp['baseline_kg_co2e']:,.0f} kg"); c[2].metric("Scenario", f"{imp['scenario_kg_co2e']:,.0f} kg")
                comparison = go.Figure(go.Bar(x=["Current baseline", "Modelled scenario"],
                                              y=[imp["baseline_kg_co2e"], imp["scenario_kg_co2e"]],
                                              marker_color=["#A8B7B1", GREEN],
                                              text=[f"{imp['baseline_kg_co2e']:,.0f}", f"{imp['scenario_kg_co2e']:,.0f}"],
                                              textposition="outside"))
                st.plotly_chart(plot(comparison.update_layout(title="Annual footprint comparison", yaxis_title="kg CO₂e / year"), height=350),
                                width="stretch")
            else:
                c[1].metric("Paper statements avoided", imp["paper_statements_avoided"]); c[2].metric("Sheets avoided", imp["paper_sheets_avoided"])
            st.markdown(f"<div class='business-note'><b>Calculation method:</b> {html.escape(friendly_method(imp.get('method', '')))}</div>", unsafe_allow_html=True)
            if imp.get("assumptions"):
                with st.expander("Scenario assumptions"):
                    st.markdown("  \n".join(f"- {friendly_assumption(item)}" for item in imp["assumptions"]))
                    if imp.get("factors"):
                        st.markdown("**Factor provenance**")
                        st.dataframe(pd.DataFrame(imp["factors"]), hide_index=True, width="stretch")
            st.caption("Planning estimate only. It does not represent a measured customer outcome or a financial-product decision.")
    with st.expander("Portfolio modelling assumptions"):
        assumptions_view = ASSUMPTIONS.reset_index().rename(columns={
            "assumption_id": "Assumption ID", "low": "Low", "central": "Central", "high": "High",
            "unit": "Unit", "source": "Source", "version": "Version",
        })
        st.dataframe(assumptions_view, hide_index=True, width="stretch")

# ----------------------------------------------------------------------------- 4. model & evaluation
elif page == "Model governance":
    hero("Model governance", "Performance, controls and limitations in one view.",
         "Review held-out performance, benchmark comparisons, signal importance and subgroup monitoring before any model-led campaign.",
         ["Held-out evaluation", "Leakage controls", "Human accountability"])
    rep = D["report"]
    rows = []
    for p in PRODUCTS:
        x = rep[p]
        rows.append(dict(Product=PRODUCT_NAME[p], **{"GBM AUC": x["test"]["auc"], "LogReg AUC": x["baseline_logreg_test"]["auc"],
                         "GBM PR-AUC": x["test"]["pr_auc"], "LogReg PR-AUC": x["baseline_logreg_test"]["pr_auc"],
                         "GBM logloss": x["test"]["logloss"], "LogReg logloss": x["baseline_logreg_test"]["logloss"],
                         "Prevalence logloss": x["baseline_prevalence_test_logloss"], "AUC 95% CI": f"{x['auc_test_ci95'][0]:.2f}–{x['auc_test_ci95'][1]:.2f}",
                         "Top-10% lift": x["test"]["lift_top10"], "Train–test AUC gap": x["overfit_gap_auc_train_minus_test"], "Threshold": x["threshold"]}))
    metrics, explainability, monitoring, catalogue = st.tabs(["Evaluation", "Explainability", "Subgroup monitoring", "Product catalogue"])
    with metrics:
        st.dataframe(pd.DataFrame(rows).style.format({c: "{:.3f}" for c in pd.DataFrame(rows).columns if c not in ("Product", "AUC 95% CI")}),
                     hide_index=True, width="stretch")
        st.markdown("<div class='risk-note'><b>Honest reading:</b> LightGBM beats the prevalence baseline, but is roughly level with the logistic-regression baseline on held-out data. The synthetic labels are generated from a mostly linear logit, so this is plausible rather than a claim of superiority.</div>",
                    unsafe_allow_html=True)
        st.markdown("#### Transaction categorisation")
        t = rep["txn_categorisation"]
        c = st.columns(4)
        c[0].metric("Model macro-F1", f"{t['model_macro_f1']:.3f}"); c[1].metric("Rules baseline F1", f"{t['rules_macro_f1']:.3f}")
        c[2].metric("Model accuracy", f"{t['model_acc']:.3f}"); c[3].metric("Rules accuracy", f"{t['rules_acc']:.3f}")
        st.caption("Near-perfect categorisation reflects templated synthetic merchant text and should not be treated as expected real-world performance.")
    with explainability:
        sel = st.selectbox("Feature importance for", PRODUCTS, format_func=PRODUCT_NAME.get)
        fw = pd.DataFrame(api_get(f"/bank/model/feature-weights/{sel}")["items"])
        importance = px.bar(fw.sort_values("normalised_gain").tail(12), x="normalised_gain", y="feature", orientation="h",
                            color_discrete_sequence=[GREEN], labels={"normalised_gain": "normalised gain", "feature": ""},
                            title=f"Signals used by {PRODUCT_NAME[sel]}")
        st.plotly_chart(plot(importance, height=470), width="stretch")
        st.caption("Global feature importance describes the model overall. The Opportunity desk provides plain-language evidence for an individual recommendation.")
    with monitoring:
        st.markdown("#### Recommendation-rate monitor")
        st.caption("A descriptive prototype check, not a completed fairness assessment. Differences can reflect eligibility rules and synthetic data design and require human investigation.")
        group_field = st.selectbox("Compare groups by", ["age_band", "income_band", "region"],
                                   format_func={"age_band":"Age band", "income_band":"Income band", "region":"Region"}.get)
        mon = (R.groupby([group_field, "product_name"], observed=True)
                 .agg(customers=("customer_id", "nunique"), recommendation_rate=("recommend", "mean"),
                      avg_confidence=("confidence", "mean")).reset_index())
        fairness_chart = px.bar(mon, x=group_field, y="recommendation_rate", color="product_name", barmode="group",
                                color_discrete_map=PRODUCT_COLOURS, title="Recommendation rate by group and product",
                                labels={group_field: "", "recommendation_rate": "share recommended"})
        fairness_chart.update_yaxes(tickformat=".0%")
        st.plotly_chart(plot(fairness_chart, height=430), width="stretch")
        st.dataframe(mon.style.format({"recommendation_rate":"{:.1%}", "avg_confidence":"{:.2f}"}), hide_index=True, width="stretch")
    with catalogue:
        st.dataframe(D["prods"], hide_index=True, width="stretch")
        st.caption("The catalogue defines the intended use case, eligibility gate and sustainability metric for each required opportunity.")

# ----------------------------------------------------------------------------- 6. database and data lineage
elif page == "Data architecture":
    hero("Data architecture", "The tables behind every customer insight.",
         "Inspect the live demo database, row counts, columns, keys and relationships without leaving the governed bank workspace.",
         ["Normalised SQLite schema", "Foreign keys enforced", "Reproducible CSV seeds"])
    catalog = api_get("/bank/data-catalog")
    table_objects = [item for item in catalog["tables"] if item["kind"] == "table"]
    relationships = [
        {"Table": item["name"], "Column": key["column"], "References": f"{key['references_table']}.{key['references_column']}"}
        for item in table_objects for key in item["foreign_keys"]
    ]
    metrics = st.columns(4)
    metrics[0].metric("Database engine", catalog["engine"])
    metrics[1].metric("Schema version", catalog["schema_version"])
    metrics[2].metric("Tables", f"{len(table_objects):,}")
    metrics[3].metric("Enforced relationships", f"{len(relationships):,}")
    st.caption(f"Database: {catalog['database_file']} · built {catalog['built_at']} · {catalog['dataset_name']}")

    overview, detail, schema_source = st.tabs(["Table inventory", "Column explorer", "SQL schema"])
    with overview:
        inventory = pd.DataFrame([
            {"Object": item["name"], "Type": item["kind"].title(), "Rows": item["rows"],
             "Columns": len(item["columns"]), "Foreign keys": len(item["foreign_keys"])}
            for item in catalog["tables"]
        ])
        st.dataframe(inventory.style.format({"Rows": "{:,}"}), hide_index=True, width="stretch")
        st.markdown("#### Relationships")
        if relationships:
            st.dataframe(pd.DataFrame(relationships), hide_index=True, width="stretch")
        st.markdown("<div class='business-note'><b>Lineage:</b> versioned synthetic CSV sources are loaded into this database; FastAPI reads the database; the frontend reads only protected API responses. Training artifacts remain reproducible from the source datasets.</div>", unsafe_allow_html=True)
    with detail:
        selected_table = st.selectbox("Inspect table or view", [item["name"] for item in catalog["tables"]])
        selected = next(item for item in catalog["tables"] if item["name"] == selected_table)
        st.metric("Rows", f"{selected['rows']:,}")
        column_frame = pd.DataFrame(selected["columns"]).rename(columns={
            "position": "#", "column": "Column", "type": "SQL type", "nullable": "Nullable", "primary_key": "Primary key"
        })
        st.dataframe(column_frame, hide_index=True, width="stretch")
        if selected["foreign_keys"]:
            st.markdown("#### Foreign keys")
            st.dataframe(pd.DataFrame(selected["foreign_keys"]), hide_index=True, width="stretch")
    with schema_source:
        schema_text = (Path(__file__).parent.parent / "db" / "schema.sql").read_text(encoding="utf-8")
        st.caption("This is the exact executable schema used to build the running demo database.")
        st.code(schema_text, language="sql", line_numbers=True)

# ----------------------------------------------------------------------------- 7. trust & governance
else:
    hero("Risk & controls", "A glass-box path from signal to action.",
         "Use this view to explain what each component is allowed to do, how unsafe outputs are blocked and where human oversight remains essential.",
         ["Privacy by design", "Grounded generation", "Human oversight"])

    st.markdown("### Decision responsibilities")
    role_data = pd.DataFrame([
        ["ML models", "Estimate take-up propensity and confidence; emit fixed reason codes", "Approve products or calculate carbon impact"],
        ["Product rules", "Remove opportunities ruled out by known customer data", "Replace the institution's authorised eligibility process"],
        ["Carbon engine", "Calculate a reproducible baseline-vs-scenario estimate", "Predict behaviour or decide eligibility"],
        ["LLM / template", "Rewrite a constrained structured payload in customer-friendly language", "Invent numbers, predict, calculate or approve"],
        ["Human colleague", "Review evidence, context and the appropriate next conversation", "Treat the prototype as an automated financial decision"],
    ], columns=["Component", "Allowed", "Not allowed"])
    st.dataframe(role_data, hide_index=True, width="stretch")

    safeguards, scenarios, limitations = st.tabs(["Safeguards", "Scenario readiness", "Limitations"])
    with safeguards:
        s1, s2 = st.columns(2)
        with s1:
            st.markdown("#### Before a recommendation")
            st.markdown("- Customer-level train, validation and test splits reduce leakage risk.\n- Mutually exclusive transaction categories support consistent features.\n- Product-specific rule gates suppress known conflicts.\n- Fixed reason codes preserve an inspectable evidence trail.")
        with s2:
            st.markdown("#### Before an explanation")
            st.markdown("- The LLM receives a narrow structured payload only.\n- Every generated number must already exist in that payload.\n- Ungrounded wording falls back to a deterministic template.\n- Impact status and missing inputs are surfaced, not guessed.")
    with scenarios:
        scenario_data = pd.DataFrame([
            ["Missing activity data", "Return INSUFFICIENT_DATA and name the missing inputs", "Impact engine"],
            ["Customer already drives an EV", "Suppress EV finance when no replacement use case exists", "Eligibility rules"],
            ["Customer already mostly paperless", "Suppress the paperless recommendation", "Eligibility rules"],
            ["High propensity but rules conflict", "Rules win; do not recommend", "Recommendation engine"],
            ["LLM introduces a new figure", "Reject the text and use the grounded template", "Insight layer"],
            ["Customer says 'not now'", "Store the in-session response without changing model outputs", "Demo memory"],
        ], columns=["Evaluation scenario", "Expected behaviour", "Control owner"])
        st.dataframe(scenario_data, hide_index=True, width="stretch")
    with limitations:
        st.markdown("<div class='risk-note'><b>Prototype boundary:</b> this experience uses synthetic customers and approximate emissions factors. It demonstrates architecture and controls; it does not establish real-world accuracy, financial eligibility, regulatory compliance or measured emissions reduction.</div>",
                    unsafe_allow_html=True)
        st.markdown("""
        - Replace synthetic data with lawfully sourced, permissioned and minimised inputs before any live use.
        - Validate the latest emissions factors, sources, units and methodology with sustainability specialists.
        - Complete formal bias, accessibility, privacy, security and model-risk reviews.
        - Recalibrate propensities and confidence on representative real outcomes; monitor drift after launch.
        - Keep a human accountable for customer communication and every authorised financial decision.
        """)
