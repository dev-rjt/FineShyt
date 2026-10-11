# Green Customer Insights: improved ML core

This is a reproducible synthetic-data hackathon prototype for Lloyds Problem Statement 1. It predicts six-month green-product take-up, gates recommendations using suitability rules, calculates operational sustainability scenarios deterministically, and explains only verified structured facts.

**All data is synthetic. AUC is a ranking metric, not a percentage accuracy or real-world success rate. Financial eligibility is never assessed by this prototype.**

## Run

Python 3.12 is the tested runtime. Trained-model dependencies are pinned because pickle/joblib compatibility depends on library versions. Only load model files from trusted sources.

```bash
cd green_insights
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
# Train and evaluate using the included dataset:
python run_pipeline.py
# Optional: reconstruct all synthetic tables from the documented seed:
python run_pipeline.py --regenerate
# Run scenario and saved-model evaluation checks:
python -m unittest discover -s tests -v
# Predict from a customer-360 CSV without retraining:
python inference.py data/customer_360.csv --output outputs/inference_predictions.csv
# Refresh business summaries and offline grounded explanations:
python business_insights.py
# Optional dashboard (install the extra dependency):
pip install -r requirements-demo.txt
streamlit run app.py
```

Training duration depends on CPU. Exact timing is in `outputs/run_metadata.json`; regenerating 684,202 transaction rows adds data-generation time. The ML pipeline does not need a paid API, network access or a GPU. The optional dashboard reads saved results. Refresh its business CSVs after each training run. The included Streamlit UI was syntax-checked; it was not launched in this execution environment.

## Models and learning rate

* Transaction category: character TF-IDF (2-5 character n-grams) plus logistic regression, C=8, balanced class weighting. There is no manually chosen gradient-descent learning rate for this scikit-learn estimator.
* Each propensity product is evaluated with regularised logistic regression C in {0.03, 0.1, 0.3, 1, 3} and LightGBM. Candidate selection uses mean 5-fold training log loss, with ties favouring logistic regression.
* LightGBM grid: learning_rate {0.02, 0.05}; num_leaves {4, 8, 16}; min_child_samples {20, 50}. Rounds use training-fold early stopping, with max 3,000 rounds and patience 100. L1=0.5, L2=5, row and feature fractions=0.8.
* Logistic regression uses median imputation, missing-value indicators, scaling and L2 regularisation. Its solver chooses optimisation steps internally; `C` controls inverse regularisation strength, not learning rate.
* The selected models and their actual hyperparameters are recorded per product in `outputs/evaluation_report.json` and `outputs/model_selection_*.csv`. We do not force a boosted-tree model when a simpler model performs better in training CV.

## Evaluation and leakage controls

The original seeded customer split is retained: 3,499 training, 750 validation and 751 test customers. Small deviations from 70/15/15 arise from floating-point rounding in the original splitter. Customers are disjoint across all three splits, and the transaction classifier uses this same partition. Take-up labels are aligned by customer ID, not input row position.

Feature history ends on 2025-12-31. Product starts after that date and transaction/energy/digital records outside the 12-month history are filtered out. Synthetic take-up represents the subsequent six months (January-June 2026). No outcome column or label-provided candidate flag enters the feature matrix or recommendation gate.

Selection uses training CV only. Platt calibration (logistic C=1) uses training out-of-fold raw scores. Maximum-F1 threshold selection uses training scores with cross-fitted calibration. Because training CV selects hyperparameters using these labels, OOF training metrics are diagnostics, not independent evidence. Validation and test are independent of fitting, calibration and threshold selection. The original validation scores used a calibrator fitted on validation; those original validation metrics are optimistic relative to the new independent protocol.

Report ROC-AUC, average precision (the field `pr_auc`), log loss, Brier score, lift at the top 10%, precision, recall, F1, accuracy, confusion matrices, ten-bin calibration tables/ECE, positive counts and test AUC bootstrap intervals. Calibration bins/ECE are descriptive and unstable with small samples. A prevalence-only model and a fixed-C logistic baseline are reported on both validation and test. Metrics are evaluated on rules-suitable candidate customers; excluded customer-product pairs have null propensity/confidence and explicit exclusion reasons. Threshold metrics in the ML report evaluate the score operating point; final recommendations additionally require confidence >=0.5 and observed supporting evidence, so their counts need not equal the score-only confusion matrix.

The original test results were visible during this audit. Improvements on the same test customers are diagnostic, not a pristine new benchmark. A fresh external/temporal labelled evaluation is needed before claiming real-world accuracy. The shared synthetic merchant-template pool makes near-perfect transaction scores easier than unfamiliar bank feeds. See `AUDIT_REPORT.md` for measured comparisons and remaining gaps.

## Confidence, reason codes and suitability

Confidence is a documented heuristic in [0,1]: `(0.4 * fold-model agreement + 0.3 * key-feature completeness + 0.3 * in-training-range support) * min(1, training positives / 100)`. Agreement falls as fold-model predicted probabilities diverge; support uses training 1st-99th percentiles. Missing values do not count as supported. This is not a calibrated probability of correctness, financial approval or an interval around propensity.

Positive contributions produce fixed `POSITIVE_MODEL_SIGNAL_<FEATURE>` codes. Each output includes the observed feature value and its model contribution in `evidence_json`. LightGBM uses native tree contribution scores. Logistic regression uses coefficient times scaled distance from training medians, adjusted for calibration slope. Missing-value indicator contributions are omitted from evidence, and unavailable values cannot be stated as observed support. Contributions indicate model associations, not causation or affordability. A low value with a positive contribution is never misleadingly described as HIGH.

EV owners without a replacement use case, unknown fuel types, existing holders of the same green product, non-owners for Solar, and customers already mostly digital are excluded. Unknown critical suitability facts fail closed. The historical `eligible_*` function output is an internal candidate flag; all recommendations separately state `financial_eligibility=NOT_ASSESSED`. Institutional credit and product checks remain required.

## Data and label generation

All tables are generated by `data_generation.py` with seed 42. Five thousand customers have correlated age, income, postcode, home ownership, digital activity and sustainability preference. Vehicle mileage/fuel types drive fuel spending; household size/ownership and seasonal factors drive energy; digital engagement drives digital transactions and statement preference. Merchant labels come from the generating category before character noise is applied. Take-up labels use plausible feature relationships, unobserved Gaussian noise with standard deviation 0.9, and a Bernoulli draw; unsuitable customers do not take up a product.

For label generation, z(x) is cohort-standardised x and missing vehicle values use cohort medians. These generator statistics define simulated outcomes; they are not model preprocessing statistics. All fitted ML imputers and scalers use training rows only.

* EV: intercept -4; mileage +0.9z, fuel spending +0.75z, vehicle loan +0.6, vehicle age>7 +0.45, preference +0.9z, income +0.35z, urban +0.5, ownership +0.3, age -0.02(age-40).
* Green Home: intercept -4; heating +0.85z, home-improvement spend +0.55z, mortgage +0.7, preference +0.9z, income +0.3z, age 28-62 +0.3.
* Solar: intercept -4.1; electricity +1z, improvement spend +0.35z, income +0.5z, preference +0.95z, rural +0.4, ISA +0.35.
* Paperless: intercept -1.9; paper share +2.2(share-0.4), digital transactions +1.1z, branch visits -0.9z, digital usage +0.5z, preference +0.3z, age -0.02(age-45).

Each expression adds N(0,0.9) noise. Take-up is sampled with Bernoulli(sigmoid(expression)) and gated by suitability. This logistic generator structurally favours linear models; high synthetic scores are not evidence of genuine bank conversion prediction.

`data/` contains customers, transactions, transaction-category labels, products held, vehicles, monthly energy, monthly digital usage, green-products catalogue, emissions factors, take-up labels, shared splits and customer-360 features. The original ZIP omitted transactions and their labels; both have been restored. All eight supplied input CSVs initially matched seeded regeneration exactly; the factor catalogue and product-use-case description were then deliberately updated.

## Transaction boundaries

Fuel includes conventional refuelling and EV charging; it is a spending category, not direct evidence of combustion. Shell/BP forecourt shop purchases and supermarket stores are Other; petrol stations are Fuel. Electricity/Gas are separated by explicit bill descriptors. Vehicle servicing, tyres, tax and car washes are Automotive. Water, broadband, council tax, TV licences and mobile bills are Utilities. Ambiguous unlabelled energy bills remain Other unless a richer labelled dataset supports an attribution. Missing merchant text yields Other with confidence zero. Every transaction has exactly one category.

## Sustainability methodology

`carbon_engine.py` uses a 12-month operational baseline-versus-scenario comparison informed by [GHG Protocol comparative-emissions guidance](https://ghgprotocol.org/estimating-and-reporting-avoided-emissions). Boundaries exclude manufacturing, upstream fuel/electricity and electricity transmission/distribution losses. This is not a full lifecycle comparison, PCAF financed-emissions calculation or measured reduction. Negative avoided emissions are retained when a scenario would be worse.

The exact 2025 UK factors match the demo activity year; they are not labelled as the latest year. Downloaded primary source workbook `data/factors_2025.xlsx`, worksheet `Factors by Category`, is included with exact row IDs and source URLs in `data/emissions_factors.csv`:

| Activity | Value | Unit | DESNZ row ID |
|---|---:|---|---|
| UK electricity generated | 0.177 | kg CO2e/kWh | 7_400_4000_5_1 |
| Natural gas, gross CV | 0.18296 | kg CO2e/kWh | 1_100_1004_6_1 |
| Average petrol passenger car | 0.16272 | kg CO2e/km | 4_301_3070_4_1 |
| Average diesel passenger car | 0.17304 | kg CO2e/km | 4_301_3069_4_1 |
| Average non-plug-in hybrid passenger car | 0.12825 | kg CO2e/km | 4_301_3071_4_1 |

[Primary source and methodology](https://www.gov.uk/government/publications/greenhouse-gas-reporting-conversion-factors-2025). Government factor content is available under the source's Open Government Licence; no software licence was added on your behalf.

EV compares equal mileage, converting miles to km using 1.609344. EV consumption 0.2 kWh/km is explicitly a scenario assumption, with 0.15/0.25 sensitivity scenarios. A van is not assigned a passenger-car factor. Green Home maps to insulation/retrofit, assuming gas -20%, electricity -5%, with lower/higher sensitivity scenarios; heat-pump performance is not modelled. Solar assumes 900 kWh/kWp/year, 2-6 kWp and 50% self-use. Household grid savings are capped at household demand; exports are recorded separately without crediting export CO2. Self-use sensitivities 30%/70% are reported. Roof permissions, shading and actual yield remain unknown.

Annual energy impact needs all twelve monthly rows and complete values; a partial year is not treated as zero consumption or quietly extrapolated. Paperless reports statements and assumed sheets separately from digital-adoption percentage-point changes. An unsourced per-statement carbon factor has been removed, so Paperless CO2 is null with `INSUFFICIENT_FACTOR`, rather than an invented carbon claim. Product-specific impacts are standalone scenarios; Solar and Green Home must not be added for one household.

## Grounded insight/LLM layer

`insights.py` produces labelled template explanations from structured outputs. Optional model configuration uses `LLM_BASE_URL` (HTTPS OpenAI-compatible API base, usually ending `/v1`), `LLM_API_KEY`, and `LLM_MODEL`. The LLM only proposes the order of supplied fact IDs; the renderer supplies every word and number. Unknown/duplicate/missing IDs trigger deterministic fallback. The prompt, provider request, grounding checks and failure handling are included. No API key is bundled, and no external provider was called in this audit. The dashboard uses template explanations by default; provider behaviour and language quality have not been live-evaluated. Do not claim the bundled template examples are LLM-generated.

## Responsible AI and limits

No confidential or personal banking data is used. Bias is not solved by synthetic data: age, income and region affect the generator and predictors. Validation age-band/region metrics are descriptive; small subgroups are flagged insufficient, and they do not certify fairness. Age rules are illustrative, not authorised institutional criteria. Suitability, credit decisions and impact assumptions require human oversight. Forecasts are associations; hypothetical emissions savings do not prove additionality, financed attribution or causal take-up.

The optional adaptation script retrains on independently labelled public or synthetic customer data with disjoint customer train/validation/test splits, refreshes confidence support/calibration, compares adaptation on validation, and reports test separately. It no longer adds trees then calibrates on fitted training predictions. It has not been run on external data here, and it must not be used with confidential bank records for this hackathon.

The included dashboard and constrained LLM adapter improve submission completeness, but production API integration, live LLM evaluation, bank-authorised eligibility, real conversion labels and external robustness evaluation remain unfinished. Optional green investments/green loans and customer memory were not implemented.
