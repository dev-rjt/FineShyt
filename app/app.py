import os

import pandas as pd
import requests
import streamlit as st

API = os.getenv("API_BASE_URL", "http://localhost:8000")

st.set_page_config(page_title="Glass-Box Green Insights", layout="wide")


@st.cache_data(ttl=20)
def get(path):
    r = requests.get(API + path, timeout=10)
    r.raise_for_status()
    return r.json()


st.title("Glass-Box Green Insights")
page = st.sidebar.radio("View", ["Customer view", "Business dashboard"])
st.sidebar.caption("All impact figures are estimates, not measured results.")

try:
    meta = get("/meta")
except Exception as e:
    st.error("Cannot reach the API at " + API + ". Is docker compose running? " + str(e))
    st.stop()

st.sidebar.caption("Data as of " + meta["cutoff_date"])
names = {p["product_id"]: p["product"] for p in get("/products")["items"]}

if page == "Customer view":
    customers = get("/customers")["items"]
    cid = st.sidebar.selectbox("Customer", [c["customer_id"] for c in customers])
    c = get("/customers/" + cid)
    p = c["profile"]

    st.subheader("Customer " + cid)
    cols = st.columns(4)
    cols[0].metric("Age", p["age"])
    cols[1].metric("Region", p["region"])
    cols[2].metric("Home owner", "Yes" if p["home_owner"] else "No")
    cols[3].metric("Data completeness", f"{c['data_quality']['completeness']:.0%}")
    with st.expander("Customer 360 details"):
        st.json(c)

    st.header("Green opportunities")
    for o in get("/customers/" + cid + "/opportunities")["items"]:
        with st.container(border=True):
            st.markdown("### " + names[o["product_id"]])
            if o["status"] == "INSUFFICIENT_DATA":
                st.warning("Low data: shown with low confidence")
            a, b = st.columns(2)
            a.metric("Propensity", f"{o['propensity']:.0%}")
            b.metric("Confidence", f"{o['confidence']:.0%}")
            st.write("**Why:** " + ", ".join(r["label"] for r in o["reason_codes"]))

            imp = o["impact"]
            if imp["status"] == "OK":
                m = imp["metrics"][0]
                st.write(f"**Potential impact (estimate):** {m['low']:,.0f} to {m['high']:,.0f} {m['unit']} (central {m['central']:,.0f})")
            else:
                st.write("**Potential impact:** not enough data to estimate. Missing: " + ", ".join(imp["missing_inputs"]))

            with st.expander("Method and evidence"):
                st.write("Method: " + imp["method"])
                for r in o["reason_codes"]:
                    st.write(f"- `{r['code']}`: {r['plain_text']}")
                st.caption(f"Data as of {o['data_as_of']} | model {o['model_version']}")

            st.info(o["insight"]["text"])
            st.button(o["action"]["label"], key=cid + "-" + o["product_id"])

    with st.expander("Audit view: products ruled out for this customer"):
        ruled_out = [o for o in get("/customers/" + cid + "/audit")["items"] if o["status"] == "SUPPRESSED"]
        if not ruled_out:
            st.write("No products were ruled out.")
        for o in ruled_out:
            why = "; ".join(r["message"] for r in o["gate"]["failed_rules"])
            st.write("**" + names[o["product_id"]] + "**: " + why)

else:
    s = get("/business/summary")
    st.header("Business dashboard")
    st.metric("Customers analysed", s["customers_analysed"])

    st.subheader("Opportunities by product")
    rows = pd.DataFrame(s["opportunities_by_product"]).set_index("opportunity")
    st.bar_chart(rows[["recommended", "suppressed", "insufficient_data"]])

    st.subheader("Potential impact (estimates, each reported separately)")
    pi = s["potential_impact"]
    pw = s["propensity_weighted_impact"]
    c1, c2, c3, c4 = st.columns(4)
    for col, label, key in [(c1, "CO2e (kg per year)", "co2e_kg_per_year"),
                            (c2, "Energy (kWh per year)", "energy_kwh_per_year"),
                            (c3, "Paper (sheets per year)", "paper_sheets_per_year")]:
        col.metric(label, f"{pi[key]['central']:,}")
        col.caption(f"Range {pi[key]['low']:,} to {pi[key]['high']:,}. Propensity-weighted: {pw[key]:,}")
    c4.metric("Digital adoption (points)", pi["digital_adoption_pp"]["central"])
    c4.caption("Not a carbon reduction")

    st.subheader("Next-best conversation queue")
    q = get("/business/queue")["items"]
    st.dataframe(pd.json_normalize(q), use_container_width=True)
