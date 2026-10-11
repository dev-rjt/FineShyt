"""Suitability gates only. Financial eligibility remains institution review.
Compatibility: eligible_* is a historical column name meaning candidate, not approval.
Unknown critical facts fail closed. Rules never use take-up labels or propensity.
"""
import pandas as pd

def eligibility(f):
    f=f.copy(); out=pd.DataFrame(index=f.index)
    needed=['has_vehicle','fuel_type_code','age','home_owner','has_mortgage','paper_share']+[f'holds_GP0{i}' for i in range(1,5)]
    for k in needed:
        if k not in f: f[k]=float('nan')
        f[k]=pd.to_numeric(f[k],errors='coerce')
    def put(prod,ok,why,critical):
        missing=f[critical].isna().any(axis=1)
        ok=ok.fillna(False)&~missing
        out[f'eligible_{prod}']=ok.astype(bool)
        out[f'exclusion_{prod}']=why.mask(missing,'MISSING_SUITABILITY_DATA').mask(ok,'')
        out[f'financial_eligibility_{prod}']='NOT_ASSESSED'
    ok=(f.has_vehicle==1)&f.fuel_type_code.isin([0,1,2])&f.age.between(18,78)&(f.holds_GP01==0)
    why=pd.Series('NO_VEHICLE_ON_RECORD',index=f.index).mask((f.has_vehicle==1)&~f.fuel_type_code.isin([0,1,2,3]),'UNKNOWN_VEHICLE_FUEL')
    why=why.mask(f.fuel_type_code==3,'ALREADY_EV_NO_REPLACEMENT_USE_CASE').mask(~f.age.between(18,78),'OUTSIDE_ILLUSTRATIVE_AGE_RULE').mask(f.holds_GP01==1,'ALREADY_HOLDS_PRODUCT')
    # No vehicle is an explicit exclusion; an existing vehicle with missing fuel is unknown.
    f.loc[f.has_vehicle==0,'fuel_type_code']=-1
    put('EV_FINANCE',ok,why,['has_vehicle','fuel_type_code','age','holds_GP01'])
    ok=((f.home_owner==1)|(f.has_mortgage==1))&(f.holds_GP02==0)
    why=pd.Series('NOT_HOME_OWNER',index=f.index).mask(f.holds_GP02==1,'ALREADY_HOLDS_PRODUCT')
    # Ownership is known if either recorded ownership or mortgage is positive.
    f['_home_verified']=f.home_owner.mask(f.has_mortgage==1,1)
    put('GREEN_HOME',ok,why,['_home_verified','holds_GP02'])
    ok=(f.home_owner==1)&(f.holds_GP03==0)
    put('SOLAR_FINANCE',ok,pd.Series('NOT_HOME_OWNER',index=f.index).mask(f.holds_GP03==1,'ALREADY_HOLDS_PRODUCT'),['home_owner','holds_GP03'])
    ok=(f.paper_share>.15)&(f.holds_GP04==0)
    put('PAPERLESS',ok,pd.Series('ALREADY_MOSTLY_DIGITAL',index=f.index).mask(f.holds_GP04==1,'ALREADY_HOLDS_PRODUCT'),['paper_share','holds_GP04'])
    return out
