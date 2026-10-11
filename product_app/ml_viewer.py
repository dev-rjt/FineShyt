"""Optional Streamlit view over saved, structured model outputs (no retraining)."""
import json
import pandas as pd
import streamlit as st
from config import DATA_DIR,OUT_DIR,PRODUCTS
from insights import explain

st.set_page_config(page_title='Green Customer Insights',layout='wide')
st.title('Green Customer Insights')
st.caption('Synthetic demonstration • Six-month take-up model • Potential annual impact estimates • Financial eligibility not assessed')
@st.cache_data
def load():
    return (pd.read_csv(OUT_DIR/'recommendations_all.csv'),pd.read_csv(DATA_DIR/'customer_360.csv'),
        json.loads((OUT_DIR/'evaluation_report.json').read_text()))
R,F,report=load(); view=st.sidebar.radio('View',['Customer','Business','Evaluation'])
if view=='Customer':
    cid=st.selectbox('Customer',F.customer_id); rows=R[R.customer_id==cid]
    for _,row in rows.iterrows():
        with st.expander(row.opportunity,expanded=bool(row.recommend)):
            st.write(explain(row)['text'])
            st.write('Recommendation',bool(row.recommend)); st.write('Review required',bool(row.review_required))
            st.dataframe(pd.DataFrame(json.loads(row.evidence_json)),hide_index=True)
            st.json(json.loads(row.impact_json))
elif view=='Business':
    product=st.selectbox('Product scenario',PRODUCTS)
    st.info('Product impacts are separate counterfactuals. Solar and retrofit savings overlap; do not add across products.')
    c1,c2,c3=st.columns(3)
    c1.metric('Customers analysed',R.customer_id.nunique()); c2.metric('Recommended for product',int(R[R.opportunity==product].recommend.sum()))
    valid=R[(R.opportunity==product)&R.recommend].est_avoided_kg_co2e_yr
    c3.metric('Standalone potential kg CO2e/year',f'{valid.sum(min_count=1):,.1f}' if valid.notna().any() else 'Unavailable')
    segments=pd.read_csv(OUT_DIR/'business_segments.csv'); st.dataframe(segments[segments.opportunity==product],hide_index=True)
    trends=pd.read_csv(OUT_DIR/'observed_monthly_trends.csv').set_index('month')
    st.subheader('Observed energy history (kWh)'); st.line_chart(trends[['electricity_kwh','gas_kwh']])
    st.subheader('Observed digital activity (counts)'); st.line_chart(trends[['paper_statements','digital_transactions']])
    st.dataframe(R[(R.opportunity==product)&R.recommend].sort_values('propensity',ascending=False).head(50),hide_index=True)
else:
    st.warning('All metrics are on synthetic data. Merchant templates overlap across customer splits. AUC is ranking performance, not percent accuracy.')
    table=pd.read_csv(OUT_DIR/'metrics_summary.csv'); st.dataframe(table,hide_index=True)
    prod=st.selectbox('Calibration and diagnostics',PRODUCTS)
    st.dataframe(pd.DataFrame(report[prod]['val']['calibration_bins']),hide_index=True)
    st.json(report[prod]); st.write('LLM mode in included examples: template fallback. Fact-order validation is tested with mocked LLM outputs; no live-provider evaluation has been performed.')
