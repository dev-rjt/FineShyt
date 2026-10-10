# Glass-Box Green Insights

Documentation for the Lloyds Megathon problem statement and the team's proposed solution.

## Documents

1. [Official Lloyds problem statement](docs/01-lloyds-problem-statement.pdf)
2. [Simplified problem statement and five-person team guide](docs/02-green-insights-team-guide.pdf)
3. [Final shared JSON integration contract](docs/03-final-json-contract.pdf)

The official problem statement remains the source of truth. The team guide explains the solution in simpler terms, while the JSON contract defines the interface all implementation components should follow.

## Dataset pipeline

Dataset work is developed on the `feature/dataset-pipeline` branch.

The pipeline combines bounded samples from UCI Online Retail II and the London smart-meter dataset with synthetic banking, vehicle, digital and product data. It produces Customer 360 features, labels, customer-level splits, reference tables and validation reports.

Build everything with:

```bash
python3 src/data/download_public_sources.py
python3 src/data/build_dataset.py --customers 5000 --seed 42
python3 src/data/validate_dataset.py
python3 src/data/generate_documentation.py
```

See [dataset methodology](docs/data-methodology.md), [limitations](docs/data-limitations.md), and [transaction-category boundaries](docs/transaction-category-boundaries.md).

## How each component should use the data

All components join customer-level results with `customer_id`. Use the snapshot dates in `data/dataset_config.json`: features end on `2026-06-30`, and product labels describe the following 90 days. Do not use future label columns as input features.

| Component | Primary inputs | Join key | Purpose |
|---|---|---|---|
| Product propensity ML | `data/processed/customer_360.csv`, `data/processed/product_takeup_labels.csv`, `data/splits/*.csv` | `customer_id` | Train one binary model per `product_code` and generate customer-product propensity scores. |
| Transaction classifier | `data/raw/transactions.csv`, `data/processed/transaction_category_labels.csv` | `transaction_id` | Train a merchant-text/category model. Drop `true_category` from the feature matrix; it is the answer, not an input. |
| Carbon engine | `data/raw/energy_usage.csv`, `data/raw/vehicles.csv`, classified transactions, `data/reference/emission_factors.csv` | `customer_id`; factors by activity and unit | Calculate activity-based emissions with explicit units, factor version and scope. |
| Rules/recommendation engine | `data/processed/customer_360.csv`, ML scores, carbon results, `data/reference/green_products.csv` | `customer_id`, `product_code` | Apply eligibility gates, handle missing/conflicting evidence and rank eligible products. |
| API/dashboard | Outputs from ML, carbon and rules engines | `customer_id`, `product_code` | Assemble the final JSON response defined by `docs/03-final-json-contract.pdf`. |

### Product propensity ML

For each product, filter the label table by `product_code`, join it to Customer 360, and restrict customers using the appropriate split file. Keep all rows for a customer in exactly one split.

```python
import pandas as pd

features = pd.read_csv("data/processed/customer_360.csv")
labels = pd.read_csv("data/processed/product_takeup_labels.csv")
train_ids = pd.read_csv("data/splits/train_customers.csv")

ev_labels = labels.query("product_code == 'EV_FINANCE'")
train = train_ids.merge(features, on="customer_id").merge(ev_labels, on="customer_id")
X = train.drop(columns=["customer_id", "take_up", "take_up_date", "label_method"])
y = train["take_up"]
```

The transaction classifier should train on merchant text and permitted transaction-time fields. Join the label table by `transaction_id`, and remove both `true_category` columns before fitting to prevent leakage.

### Carbon engine

Use physical activity data where it exists:

- Electricity: multiply `electricity_kwh` by the grid factor; report Scope 2 and transmission/distribution Scope 3 separately.
- Gas: multiply `gas_kwh` by the natural-gas factor.
- Petrol/diesel: the official factors are per litre. Transaction `amount` is GBP, not litres, so never multiply spend directly by a per-litre factor. If litres are estimated from spend, record the fuel-price assumption, version and lower confidence.
- Vehicle mileage: it can support an estimate only when fuel type and efficiency are available. Missing values must remain unknown rather than silently becoming zero.

Every carbon result should retain `activity_value`, `activity_unit`, `factor_id`, `factor_value`, `factor_unit`, `scope`, `source_year`, calculated `kg_co2e` and an `ACTUAL` or `ESTIMATED` quality flag.

### Rules and recommendation engine

Treat rules as explainable gates, not hidden scoring logic:

- `EV_FINANCE`: consider existing-EV status, vehicle availability, mileage, fuel/automotive behaviour and ML propensity.
- `GREEN_HOME_LOAN`: consider home ownership or mortgage evidence, property data, home-improvement behaviour and energy need.
- `SOLAR_FINANCE`: require suitable home evidence, exclude known existing solar, and consider electricity usage and ML propensity.
- `PAPERLESS_BANKING`: consider paper statements, digital engagement and ML propensity.

Use `conflicting_homeownership_signal` and the `*_data_available` fields explicitly. Missing or contradictory evidence should produce `REVIEW_REQUIRED` or a reduced-confidence recommendation, not an automatic rejection. Return the triggered rules and evidence values so the dashboard can explain every recommendation.

### Integration rules

- Use only the documented IDs and controlled values; do not join people by postcode or merchant text.
- Keep monetary, energy and emissions units attached to every value.
- Do not expose `take_up`, `take_up_date`, `true_category` or test labels in production scoring responses.
- Keep ML probability, rule eligibility and carbon impact as separate fields; the recommendation layer may combine them, but must preserve their individual explanations.
- Validate data before training or scoring with `python3 src/data/validate_dataset.py`.
