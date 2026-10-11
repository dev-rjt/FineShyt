"""Deterministic operational baseline-versus-scenario estimates.

Method follows comparative-assessment principles: same activity/horizon,
explicit counterfactual, documented boundary. Not a full lifecycle assessment,
PCAF accounting, credit issuance or claimed measured emissions reduction.
"""
from functools import lru_cache
import numpy as np
import pandas as pd
from config import DATA_DIR

KM_PER_MILE=1.609344
METHOD_SOURCE='https://ghgprotocol.org/estimating-and-reporting-avoided-emissions'
ASSUMPTIONS=dict(ev_kwh_per_km=.20,green_home_gas_reduction=.20,
    green_home_elec_reduction=.05,solar_kwp_min=2.,solar_kwp_max=6.,
    solar_yield_kwh_per_kwp=900.,solar_self_use_fraction=.5,paper_sheets_per_statement=3,
    horizon='12 months',boundary='Operational emissions only; manufacturing, upstream fuel/electricity and T&D losses excluded')

def _factors():
    path=DATA_DIR/'emissions_factors.csv'
    return _cached_factors(str(path),path.stat().st_mtime_ns)

@lru_cache(maxsize=4)
def _cached_factors(path,mtime):
    ef=pd.read_csv(path)
    if ef.activity.duplicated().any(): raise ValueError('Duplicate emissions factors')
    return ef.set_index('activity')

def _insufficient(prod,missing,status='INSUFFICIENT_DATA'):
    return dict(product=prod,status=status,missing_inputs=missing,is_estimate=True,horizon=ASSUMPTIONS['horizon'])

def _validate(prod,r,keys):
    missing=[]; invalid=[]
    for k in keys:
        try: value=float(r.get(k,np.nan))
        except (TypeError,ValueError): value=np.nan
        if not np.isfinite(value): missing.append(k)
        elif value<0: invalid.append(k)
    if missing: return _insufficient(prod,missing)
    if invalid: return _insufficient(prod,invalid,'INVALID_DATA')
    return None

def _ok(prod,base,scen,method,factors,**extra):
    rows=_factors(); evidence=[]
    for k in factors:
        row=rows.loc[k]
        evidence.append(dict(activity=k,value=float(row.kg_co2e_per_unit),unit=row.unit,
            source=row.source,source_url=row.source_url,source_row_id=row.source_row_id,source_year=int(row.source_year)))
    return dict(product=prod,status='OK',baseline_kg_co2e=round(base,2),scenario_kg_co2e=round(scen,2),
        avoided_kg_co2e_per_year=round(base-scen,2),horizon=ASSUMPTIONS['horizon'],method=method,
        method_source=METHOD_SOURCE,boundary=ASSUMPTIONS['boundary'],is_estimate=True,
        factor_evidence=evidence,financial_eligibility='NOT_ASSESSED',**extra)

def ev_finance(r):
    err=_validate('EV_FINANCE',r,['annual_mileage','fuel_type_code'])
    if err: return err
    fk={0:'car_petrol',1:'car_diesel',2:'car_hybrid'}.get(r['fuel_type_code'])
    if fk is None: return _insufficient('EV_FINANCE',['supported_non_EV_fuel_type'])
    if r.get('vehicle_type_code')==3: return _insufficient('EV_FINANCE',['passenger_car_factor_not_applicable_to_van'])
    ef=_factors().kg_co2e_per_unit; km=float(r['annual_mileage'])*KM_PER_MILE
    intensity=float(r.get('ev_kwh_per_km',ASSUMPTIONS['ev_kwh_per_km']))
    if not np.isfinite(intensity) or intensity<=0: return _insufficient('EV_FINANCE',['ev_kwh_per_km'],'INVALID_DATA')
    base=km*ef[fk]; scenario=km*intensity*ef.grid_electricity
    return _ok('EV_FINANCE',base,scenario,'baseline = annual km x passenger-car factor; scenario = annual km x EV kWh/km x grid factor',
        [fk,'grid_electricity'],inputs={'annual_km':km,'ev_kwh_per_km':intensity},
        assumptions=['Replacement at equal annual mileage','EV energy intensity is a scenario assumption, not a measured value'],
        sensitivity_avoided_kg_co2e={'ev_0_15_kwh_per_km':round(base-km*.15*ef.grid_electricity,2),
            'ev_0_25_kwh_per_km':round(base-km*.25*ef.grid_electricity,2)})

def green_home(r):
    err=_validate('GREEN_HOME',r,['gas_kwh_yr','elec_kwh_yr'])
    if err: return err
    ef=_factors().kg_co2e_per_unit; gas=float(r['gas_kwh_yr']); elec=float(r['elec_kwh_yr'])
    base=gas*ef.natural_gas+elec*ef.grid_electricity
    saved_g=gas*ASSUMPTIONS['green_home_gas_reduction']; saved_e=elec*ASSUMPTIONS['green_home_elec_reduction']
    scen=base-saved_g*ef.natural_gas-saved_e*ef.grid_electricity
    return _ok('GREEN_HOME',base,scen,'annual metered kWh x factors; insulation/retrofit scenario reduces gas 20% and electricity 5%',
        ['natural_gas','grid_electricity'],energy_saved_kwh=round(saved_g+saved_e,2),
        assumptions=['20% gas and 5% electricity reduction are scenario assumptions','Green Home maps to retrofit/insulation, not solar generation or a heat-pump model'],
        sensitivity_avoided_kg_co2e={'gas_10pct_elec_2pct':round(gas*.1*ef.natural_gas+elec*.02*ef.grid_electricity,2),
            'gas_30pct_elec_10pct':round(gas*.3*ef.natural_gas+elec*.1*ef.grid_electricity,2)})

def solar_finance(r):
    err=_validate('SOLAR_FINANCE',r,['elec_kwh_yr'])
    if err: return err
    load=float(r['elec_kwh_yr']); ef=_factors().kg_co2e_per_unit
    if load==0: return _insufficient('SOLAR_FINANCE',['positive_electricity_demand_for_sizing'])
    yield_=ASSUMPTIONS['solar_yield_kwh_per_kwp']; share=float(r.get('solar_self_use_fraction',ASSUMPTIONS['solar_self_use_fraction']))
    if not np.isfinite(share) or not 0<=share<=1: return _insufficient('SOLAR_FINANCE',['solar_self_use_fraction'],'INVALID_DATA')
    kwp=float(np.clip(load/yield_,ASSUMPTIONS['solar_kwp_min'],ASSUMPTIONS['solar_kwp_max']))
    gen=kwp*yield_; onsite=min(load,gen*share); export=max(0,gen-onsite)
    base=load*ef.grid_electricity; scen=(load-onsite)*ef.grid_electricity
    return _ok('SOLAR_FINANCE',base,scen,'household avoided operational emissions = min(load, PV generation x self-use fraction) x grid factor',
        ['grid_electricity'],system_kwp=round(kwp,2),generation_kwh=round(gen,2),
        energy_generated_kwh=round(gen,2),grid_import_avoided_kwh=round(onsite,2),exported_kwh=round(export,2),
        inputs={'annual_load_kwh':load,'self_use_fraction':share,'yield_kwh_per_kwp':yield_},
        assumptions=['900 kWh/kWp/year yield and 50% self-use are illustrative UK scenario assumptions','Roof suitability, installation permissions and shading require assessment','Export benefits excluded from household savings; no negative household emissions'],
        sensitivity_avoided_kg_co2e={'self_use_30pct':round(min(load,gen*.3)*ef.grid_electricity,2),
            'self_use_70pct':round(min(load,gen*.7)*ef.grid_electricity,2)})

def paperless(r):
    err=_validate('PAPERLESS',r,['paper_share','paper_stmts_yr'])
    if err: return err
    if not 0<=r['paper_share']<=1: return _insufficient('PAPERLESS',['paper_share'],'INVALID_DATA')
    return dict(product='PAPERLESS',status='OK',paper_statements_avoided=int(r['paper_stmts_yr']),
        paper_sheets_avoided=int(r['paper_stmts_yr']*ASSUMPTIONS['paper_sheets_per_statement']),
        digital_adoption_shift_pp=round(100*r['paper_share'],2),avoided_kg_co2e_per_year=None,
        carbon_status='INSUFFICIENT_FACTOR',is_estimate=True,horizon=ASSUMPTIONS['horizon'],
        method='Paper statements avoided x assumed 3 sheets/statement. No sourced statement life-cycle factor: no carbon claim.',
        assumptions=['All observed annual paper statements switch to digital','3 A4 sheets per statement assumed'],
        financial_eligibility='NOT_ASSESSED')

ENGINE=dict(EV_FINANCE=ev_finance,GREEN_HOME=green_home,SOLAR_FINANCE=solar_finance,PAPERLESS=paperless)
def estimate_impact(product,row):
    if product not in ENGINE: raise ValueError('Unknown opportunity')
    if product != 'PAPERLESS':
        keys=['grid_electricity']
        if product=='GREEN_HOME': keys.append('natural_gas')
        if product=='EV_FINANCE':
            fk={0:'car_petrol',1:'car_diesel',2:'car_hybrid'}.get(row.get('fuel_type_code'))
            if fk: keys.append(fk)
        try: factors=_factors()
        except (FileNotFoundError,KeyError): return _insufficient(product,['documented_emissions_factors'],'INSUFFICIENT_FACTOR')
        required=['kg_co2e_per_unit','unit','source','source_url','source_row_id','source_year']
        if not all(k in factors for k in required): return _insufficient(product,['factor_metadata'],'INSUFFICIENT_FACTOR')
        bad=[k for k in keys if k not in factors.index]
        if bad: return _insufficient(product,['factor:'+k for k in bad],'INSUFFICIENT_FACTOR')
        for k in keys:
            value=pd.to_numeric(factors.loc[k,'kg_co2e_per_unit'],errors='coerce')
            expected_unit='km' if k.startswith('car_') else 'kWh'
            if not np.isfinite(value) or value<0 or factors.loc[k,'unit']!=expected_unit:
                return _insufficient(product,['factor:'+k],'INVALID_FACTOR')
    return ENGINE[product](row)
