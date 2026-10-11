"""Scenario checks and persisted-model evaluation; no API calls or retraining."""
import sys,json,unittest
from unittest.mock import patch
from pathlib import Path
import numpy as np
import pandas as pd
import joblib
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from config import *
from rules import eligibility
from carbon_engine import estimate_impact,KM_PER_MILE
from propensity import make_splits,_metrics
from inference import recommendations
from features import build_customer_360
from insights import explain,facts,validate_order

class RulesAndImpact(unittest.TestCase):
    def row(self,**kw):
        r=dict(has_vehicle=1,fuel_type_code=0,age=40,home_owner=1,has_mortgage=0,paper_share=.4,
            holds_GP01=0,holds_GP02=0,holds_GP03=0,holds_GP04=0,annual_mileage=10000,
            vehicle_type_code=0,elec_kwh_yr=3000,gas_kwh_yr=10000,paper_stmts_yr=20)
        r.update(kw); return pd.Series(r)
    def test_ev_owner_unknown_and_existing_product_excluded(self):
        f=pd.DataFrame([self.row(fuel_type_code=3),self.row(fuel_type_code=np.nan),self.row(fuel_type_code=99),self.row(holds_GP01=1)])
        g=eligibility(f); self.assertFalse(g.eligible_EV_FINANCE.any())
    def test_unknown_holdings_fail_closed(self):
        f=pd.DataFrame([self.row()]).drop(columns=['holds_GP01']); self.assertFalse(eligibility(f).eligible_EV_FINANCE.iloc[0])
    def test_mortgage_is_not_solar_ownership_evidence(self):
        g=eligibility(pd.DataFrame([self.row(home_owner=0,has_mortgage=1)]))
        self.assertTrue(g.eligible_GREEN_HOME.iloc[0]); self.assertFalse(g.eligible_SOLAR_FINANCE.iloc[0])
    def test_no_home_and_digital_already_excluded(self):
        g=eligibility(pd.DataFrame([self.row(home_owner=0,paper_share=.1)]))
        self.assertFalse(g.eligible_GREEN_HOME.iloc[0]); self.assertFalse(g.eligible_SOLAR_FINANCE.iloc[0]); self.assertFalse(g.eligible_PAPERLESS.iloc[0])
    def test_ev_formula_units(self):
        x=estimate_impact('EV_FINANCE',self.row())
        self.assertAlmostEqual(x['avoided_kg_co2e_per_year'],10000*KM_PER_MILE*(.16272-.2*.177),places=2)
        self.assertTrue(x['is_estimate']); self.assertEqual(len(x['factor_evidence']),2)
    def test_invalid_missing_and_unsupported_activity(self):
        self.assertEqual(estimate_impact('EV_FINANCE',self.row(annual_mileage=-1))['status'],'INVALID_DATA')
        self.assertEqual(estimate_impact('EV_FINANCE',self.row(annual_mileage=np.nan))['status'],'INSUFFICIENT_DATA')
        self.assertEqual(estimate_impact('EV_FINANCE',self.row(vehicle_type_code=3))['status'],'INSUFFICIENT_DATA')
    def test_home_formula(self):
        x=estimate_impact('GREEN_HOME',self.row())
        self.assertAlmostEqual(x['avoided_kg_co2e_per_year'],10000*.2*.18296+3000*.05*.177,places=2)
        self.assertEqual(x['energy_saved_kwh'],2150)
    def test_solar_low_load_export_separate(self):
        x=estimate_impact('SOLAR_FINANCE',self.row(elec_kwh_yr=100))
        self.assertEqual(x['scenario_kg_co2e'],0); self.assertEqual(x['grid_import_avoided_kwh'],100)
        self.assertEqual(x['exported_kwh'],1700); self.assertEqual(x['avoided_kg_co2e_per_year'],17.7)
    def test_solar_invalid_share_and_zero_demand(self):
        self.assertEqual(estimate_impact('SOLAR_FINANCE',self.row(solar_self_use_fraction=2))['status'],'INVALID_DATA')
        self.assertEqual(estimate_impact('SOLAR_FINANCE',self.row(elec_kwh_yr=0))['status'],'INSUFFICIENT_DATA')
    def test_missing_or_invalid_factor_is_not_fabricated(self):
        with patch('carbon_engine._factors',return_value=pd.DataFrame()):
            self.assertEqual(estimate_impact('EV_FINANCE',self.row())['status'],'INSUFFICIENT_FACTOR')
        from carbon_engine import _factors
        f=_factors().copy(); f.loc['grid_electricity','kg_co2e_per_unit']=-1
        with patch('carbon_engine._factors',return_value=f):
            self.assertEqual(estimate_impact('SOLAR_FINANCE',self.row())['status'],'INVALID_FACTOR')
    def test_paper_is_not_unsourced_carbon(self):
        x=estimate_impact('PAPERLESS',self.row()); self.assertEqual(x['paper_sheets_avoided'],60)
        self.assertIsNone(x['avoided_kg_co2e_per_year']); self.assertEqual(x['carbon_status'],'INSUFFICIENT_FACTOR')

class FeatureAndSplitChecks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.F=pd.read_csv(DATA_DIR/'customer_360.csv'); cls.lab=pd.read_csv(DATA_DIR/'labels_takeup.csv')
        cls.vec,cls.clf=joblib.load(MODEL_DIR/'txn_classifier.joblib')
    def test_split_disjoint_and_label_order_independent(self):
        a=make_splits(self.F,self.lab).sort_values('customer_id').reset_index(drop=True)
        b=make_splits(self.F,self.lab.sample(frac=1,random_state=7)).sort_values('customer_id').reset_index(drop=True)
        pd.testing.assert_frame_equal(a,b)
        self.assertEqual(a.customer_id.nunique(),5000); self.assertEqual(a.split.value_counts().to_dict(),{'train':3499,'test':751,'val':750})
    def tiny_data(self):
        cid=self.F.customer_id.iloc[0]
        names={'customers':'customers','transactions':'transactions','products':'products','vehicles':'vehicles','energy':'energy_usage','digital':'digital_usage'}
        d={}
        for k,name in names.items():
            df=pd.read_csv(DATA_DIR/f'{name}.csv'); d[k]=df[df.customer_id==cid].copy()
        return d
    def test_future_rows_cannot_change_features(self):
        d=self.tiny_data(); before=build_customer_360(d,self.vec,self.clf)
        t=d['transactions'].iloc[[0]].copy(); t['date']='2026-01-15'; t['amount']=1e8
        d['transactions']=pd.concat([d['transactions'],t],ignore_index=True)
        p=d['products'].iloc[[0]].copy(); p['start_date']='2026-01-15'; p['product']='GP01'
        d['products']=pd.concat([d['products'],p],ignore_index=True)
        pd.testing.assert_frame_equal(before,build_customer_360(d,self.vec,self.clf))
    def test_partial_energy_is_unknown_not_zero(self):
        d=self.tiny_data(); d['energy']=d['energy'].iloc[:-1]
        f=build_customer_360(d,self.vec,self.clf).iloc[0]
        self.assertTrue(pd.isna(f.elec_kwh_yr)); self.assertEqual(f.energy_months_observed,11)
    def test_empty_transactions_and_digital_do_not_crash(self):
        d=self.tiny_data(); d['transactions']=d['transactions'].iloc[:0]; d['digital']=d['digital'].iloc[:0]
        f=build_customer_360(d,self.vec,self.clf).iloc[0]
        self.assertTrue(pd.isna(f.fuel_spend_m)); self.assertTrue(pd.isna(f.paper_share))
    def test_duplicate_energy_month_rejected(self):
        d=self.tiny_data(); d['energy']=pd.concat([d['energy'],d['energy'].iloc[:1]])
        with self.assertRaises(ValueError): build_customer_360(d,self.vec,self.clf)

class PersistedModelAndGrounding(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.F=pd.read_csv(DATA_DIR/'customer_360.csv').set_index('customer_id')
        cls.models=joblib.load(MODEL_DIR/'propensity_models.joblib')
        cls.R=pd.read_csv(OUT_DIR/'recommendations_all.csv'); cls.rep=json.loads((OUT_DIR/'evaluation_report.json').read_text())
    def test_serialised_models_match_test_metrics(self):
        split=pd.read_csv(DATA_DIR/'customer_splits.csv').set_index('customer_id').split
        lab=pd.read_csv(DATA_DIR/'labels_takeup.csv').set_index('customer_id'); rules=eligibility(self.F)
        for prod,m in self.models.items():
            X=self.F[rules[f'eligible_{prod}']&(split.reindex(self.F.index)=='test')]
            p=m.predict(X).propensity.values; metric=_metrics(lab.loc[X.index,f'takeup_{prod}'].values,p,m.threshold)
            self.assertAlmostEqual(metric['auc'],self.rep[prod]['test']['auc'],places=12)
            self.assertAlmostEqual(metric['logloss'],self.rep[prod]['test']['logloss'],places=12)
    def test_all_products_and_no_duplicate_predictions(self):
        self.assertEqual(len(self.R),20000); self.assertFalse(self.R.duplicated(['customer_id','opportunity']).any())
        self.assertFalse(self.R[self.R.suitability_status=='EXCLUDED'].recommend.any())
    def test_missing_inputs_reduce_confidence(self):
        m=self.models['EV_FINANCE']; sample=self.F[self.F.fuel_type_code.eq(0)].head(10).copy()
        before=m.predict(sample).confidence.values
        sample['annual_mileage']=np.nan; sample['fuel_spend_m']=np.nan
        after=m.predict(sample).confidence.values; self.assertTrue((after<before).all())
    def test_llm_hallucination_missing_and_duplicate_facts_rejected(self):
        row=self.R[self.R.recommend].iloc[0]; f=facts(row)
        for ids in [list(f)+['YOU_ARE_ELIGIBLE'],list(f)[:-1],list(f)+list(f)[:1]]:
            with self.assertRaises(ValueError): validate_order({'fact_ids':ids},f)
        r=explain(row,llm_response={'fact_ids':['MADE_UP_CARBON']})
        self.assertEqual(r['mode'],'template_fallback'); self.assertEqual(r['fallback_reason'],'INVALID_GROUNDED_OUTPUT')
    def test_valid_llm_response_renders_only_supplied_facts(self):
        row=self.R[self.R.recommend].iloc[0]; f=facts(row); ids=list(reversed(f))
        r=explain(row,llm_response={'fact_ids':ids})
        self.assertEqual(r['text'],' '.join(f[i] for i in ids)); self.assertEqual(r['mode'],'llm_fact_order_verified')
    def test_excluded_explanation_contains_no_action_offer(self):
        row=self.R[self.R.suitability_status=='EXCLUDED'].iloc[0]
        self.assertNotIn('Explore',explain(row)['text'])
    def test_inference_handles_unknown_vehicle_and_missing_features(self):
        f=self.F.head(3).copy(); f['fuel_type_code']=np.nan
        R=recommendations(f,self.models)
        self.assertFalse(R[R.opportunity=='EV_FINANCE'].recommend.any())

if __name__=='__main__': unittest.main(verbosity=2)
