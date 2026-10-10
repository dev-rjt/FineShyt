# Product gate and sustainability impact engine

`src/engine` implements the deterministic product-rule and impact layer for
GP01--GP04. It contains no ML, LLM, database client, or financial eligibility
logic.

## Integration

Load emission-factor rows and model-assumption rows in the data layer, then
pass them into the pure calculation:

```python
from engine import estimate_impact, evaluate_gate

gate = evaluate_gate("GP01", customer_features)
impact = estimate_impact(
    "GP01",
    customer_features,
    factors=emission_factor_rows,
    assumptions=model_assumption_rows,
)
```

Factor rows accept the project dataset columns (`factor_id`, `factor_value`,
`activity_unit`, `source`, and `source_year`) or the API names
(`kg_co2e_per_unit` and `unit`). Assumption rows use `id`, `value`, `unit`, and
`source`; deterministic ranges additionally use `low`, `central`, and `high`.
The calculation returns `INSUFFICIENT_DATA` when a required input or reference
record is absent.

## Required model assumptions

The data/schema owner must populate and version these records before the real
pipeline replaces stubs:

| ID | Unit | Used by |
|---|---|---|
| `A_PETROL_L_PER_100KM` | litres/100km | GP01 |
| `A_DIESEL_L_PER_100KM` | litres/100km | GP01 |
| `A_HYBRID_L_PER_100KM` | litres/100km | GP01 |
| `A_EV_KWH_PER_KM` | kWh/km | GP01 |
| `A_HOME_ELECTRICITY_REDUCTION` | ratio | GP02 |
| `A_HOME_GAS_REDUCTION` | ratio | GP02 |
| `A_SOLAR_SYSTEM_KWP` | kWp | GP03 when system size is not supplied |
| `A_SOLAR_YIELD_KWH_PER_KWP` | kWh/kWp/year | GP03 |
| `A_PAPER_STATEMENTS_PER_YEAR` | statements/year | GP04 when only the active flag is supplied |
| `A_PAPER_SHEETS_PER_STATEMENT` | sheets/statement | GP04 |

The engine uses the dataset's four 2026 factor IDs directly. Paperless banking
reports paper and digital-adoption metrics only; it does not claim a carbon
reduction. Home and solar calculations report energy and CO2e as separate
metrics and never add them together.

## Product rules

- GP01 is suppressed for an existing electric vehicle (`ALREADY_EV_OWNER`).
- GP02 and GP03 are suppressed when `home_owner` is explicitly false
  (`NOT_HOME_OWNER`).
- Missing values do not fail a product rule. They are handled as data quality
  and may cause `impact.status = INSUFFICIENT_DATA`.

These are product screens only. Every Gate payload states that authorised
eligibility checks are still required.
