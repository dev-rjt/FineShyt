# Dataset methodology

## Scope

The dataset supports the four required opportunities: EV Finance, Green Home Loan, Solar Finance and Paperless Banking. It contains no real or confidential banking data.

Dataset version: `1.0.0`  
Random seed: `42`  
Feature period: `2025-07-01` to `2026-06-30`  
Cutoff date: `2026-06-30`  
Outcome window: 90 days after cutoff  
Customers: 5,000

## Public-source use

### UCI Online Retail II

Source: https://archive.ics.uci.edu/dataset/502/online+retail+ii

The source contains 1,067,371 UK online-retail transaction records from 2009 to 2011 and is licensed under CC BY 4.0. A deterministic reservoir sample of 20,000 valid positive transactions is retained. Source customer identifiers are hashed. The final banking transactions use a bounded subset of the real description text and amount distribution for `OTHER` transactions. Dates and final customer identifiers are synthetic.

This source does not contain bank merchant categories, fuel transactions, vehicle ownership or green-product take-up. Those fields are generated separately and are not claimed to come from UCI.

### London smart-meter data

Source: https://data.london.gov.uk/dataset/smartmeter-energy-consumption-data-in-london-households-vqm0d

The official partitioned ZIP is about 759 MB compressed and approximately 10 GB expanded. The downloader uses HTTP byte ranges to read a bounded official partition. It aggregates 100,000 half-hour readings into hashed household-month profiles and retains only the aggregates. The distribution of scaled monthly kWh seeds the synthetic customer energy profiles. Gas consumption, solar ownership and banking links are synthetic.

### UK Government GHG Conversion Factors 2026

Source: https://www.gov.uk/government/publications/greenhouse-gas-reporting-conversion-factors-2026

The emissions reference table uses exact values and units from the revised 2026 flat-format workbook published by the Department for Energy Security and Net Zero. The selected factors cover petrol, diesel, natural gas, UK grid electricity and transmission/distribution.

## Synthetic generation

Customers are assigned one of eight archetypes. The archetype controls correlated probabilities for home ownership, vehicle ownership, mileage, digital behaviour and energy usage. Noise and missingness are added after generation.

Transactions have exactly one category from the required vocabulary. Clear merchant examples support rule-based classification, while suffixes, retailer descriptions and public-source text provide a noisier long tail.

Take-up labels use hidden green-attitude and financial-readiness variables, observable weak signals, and random noise. Labels are not copied from a single feature. This prevents the model from simply recovering the synthetic label formula.

## Leakage prevention

- All transaction, energy and digital features end on or before `2026-06-30`.
- Positive take-up dates occur only in the following 90-day window.
- Future green-product records are filtered out when Customer 360 is built.
- `take_up` and `take_up_date` never appear in Customer 360.
- Train, validation and test splits are disjoint at customer level.
- Fixed seeds make the full build reproducible.

## Split design

- Train: 3,500 customers (70%)
- Validation: 750 customers (15%)
- Test: 750 customers (15%)

All rows belonging to one customer remain in the same split.

## Rebuild

Run:

```bash
PYTHON_BIN=python3 bash scripts/build_data.sh
```

The public-source cache is ignored by Git. Derived bounded samples and generated project data are versioned.
