"""Business summaries. Per-product impact only; cross-product totals are invalid.
Solar and retrofit overlap, so their standalone counterfactuals must not be added.
"""
import json
import pandas as pd
from config import DATA_DIR, OUT_DIR
from insights import explain

def export_business(R,F):
    if 'customer_id' not in F: F=F.reset_index()
    joined=R.merge(F[['customer_id','region']],on='customer_id',how='left',validate='many_to_one')
    candidate=joined[joined.suitability_status=='CANDIDATE'].copy()
    candidate['expected_takeups']=candidate.propensity
    for k in ['energy_saved_kwh','energy_generated_kwh','paper_statements_avoided','paper_sheets_avoided','digital_adoption_shift_pp']:
        candidate[k]=candidate.impact_json.map(lambda x:json.loads(x).get(k))
    g=candidate[candidate.recommend].groupby(['opportunity','region'])
    segments=g.agg(customers=('customer_id','nunique'),mean_propensity=('propensity','mean'),
        expected_takeups=('expected_takeups','sum'),mean_confidence=('confidence','mean'))
    # sum(min_count=1) preserves missing impact; unavailable is never displayed as zero.
    impacts=g[['est_avoided_kg_co2e_yr','energy_saved_kwh','energy_generated_kwh',
        'paper_statements_avoided','paper_sheets_avoided']].sum(min_count=1)
    summary=segments.join(impacts).reset_index()
    summary['interpretation']='Standalone potential if ALL listed customers adopt; product scenarios overlap; do not add product impacts. Expected takeups is model-based, not measured.'
    summary.to_csv(OUT_DIR/'business_segments.csv',index=False)
    digital=candidate[candidate.opportunity=='PAPERLESS'].groupby('region').digital_adoption_shift_pp.mean()
    digital.to_csv(OUT_DIR/'paperless_adoption_shift.csv',header=['mean_potential_shift_pp'])
    # Observed pre-cutoff trends; this is not a conversion forecast.
    energy=pd.read_csv(DATA_DIR/'energy_usage.csv'); digital_raw=pd.read_csv(DATA_DIR/'digital_usage.csv')
    from config import CUTOFF_DATE,HISTORY_MONTHS
    first=(CUTOFF_DATE.to_period('M')-(HISTORY_MONTHS-1)).strftime('%Y-%m'); last=CUTOFF_DATE.strftime('%Y-%m')
    e=energy[energy.month.between(first,last)].groupby('month')[['electricity_kwh','gas_kwh']].sum(min_count=1)
    d=digital_raw[digital_raw.month.between(first,last)].groupby('month')[['paper_statements','digital_transactions']].sum(min_count=1)
    e.join(d).to_csv(OUT_DIR/'observed_monthly_trends.csv')
    sample=R[R.recommend].sort_values('propensity',ascending=False).groupby('opportunity').head(10)
    examples=[explain(row) for _,row in sample.iterrows()]
    (OUT_DIR/'customer_insight_examples.json').write_text(json.dumps(examples,indent=2))
    return summary

if __name__=='__main__': export_business(pd.read_csv(OUT_DIR/'recommendations_all.csv'),pd.read_csv(DATA_DIR/'customer_360.csv'))
