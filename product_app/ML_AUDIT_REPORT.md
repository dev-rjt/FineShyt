# ML audit and improvement report

## Verdict

Good synthetic hackathon ML foundation, with material evaluation and recommendation issues in the original. The improved version restores reproducibility, selects appropriate models from training CV, separates validation from fitting, and improves EV/Solar ranking and all four products' test log loss. It is not evidence of real-world conversion accuracy or a completed production system.

## Verified same-data comparison

All eight originally supplied input CSVs matched deterministic regeneration exactly before the factor/product catalogues were updated. The missing 684,202 transactions and transaction labels were restored. Each of the four original models reproduced its supplied validation and test AUC exactly after a compatibility export. No feature, customer partition or outcome label was changed to manufacture higher scores.

Original models contain pandas 3.0.3 objects, which could not load directly under the tested pandas 2.2.3 runtime. An isolated pandas 3.0.3 runtime was used to export the original predictive state without its unused pandas grid/importance tables. `baseline/propensity_models_portable.joblib` preserves all original boosters, calibrators, feature names, thresholds and support values. The original metrics are reproduced by `run_pipeline.compare_original`.

| Product | Original test AUC | Improved test AUC | Original test log loss | Improved test log loss | Improved validation AUC |
|---|---:|---:|---:|---:|---:|
| EV_FINANCE | 0.8552 | 0.8638 | 0.3320 | 0.3212 | 0.8607 |
| GREEN_HOME | 0.7323 | 0.7321 | 0.4087 | 0.4016 | 0.8502 |
| SOLAR_FINANCE | 0.8306 | 0.8597 | 0.3471 | 0.3168 | 0.8375 |
| PAPERLESS | 0.8164 | 0.8162 | 0.2887 | 0.2877 | 0.8076 |

Higher AUC is better; lower log loss is better. AUC describes ranking of adopters above non-adopters and is not percentage accuracy. Green Home and Paperless AUC did not improve materially. Compared with the original fixed-C logistic baseline, the new models have similar performance; the benefit is selecting a competitive simple model through training CV and evaluating it more cleanly.

The original validation set was used to fit calibration, whereas the improved validation set is independent of calibration and threshold fitting. Therefore the validation protocols differ. Original test scores were visible during the audit; the same test is a diagnostic comparison, not a newly sealed external benchmark.

## Selected models and test metrics

| Product | Model | C | Test positives / candidate rows | PR average precision | Precision | Recall | F1 | Test AUC 95% bootstrap interval |
|---|---|---:|---:|---:|---:|---:|---:|---|
| EV_FINANCE | Logistic regression | 0.1 | 48/277 | 0.6070 | 0.4923 | 0.6667 | 0.5664 | 0.805-0.908 |
| GREEN_HOME | Logistic regression | 0.1 | 40/245 | 0.3893 | 0.4118 | 0.3500 | 0.3784 | 0.635-0.815 |
| SOLAR_FINANCE | Logistic regression | 0.1 | 38/240 | 0.5616 | 0.5000 | 0.5000 | 0.5000 | 0.796-0.916 |
| PAPERLESS | Logistic regression | 0.3 | 46/397 | 0.3713 | 0.3059 | 0.5652 | 0.3969 | 0.745-0.867 |

All four model choices were fixed using training cross-validation log loss. Logistic regression has no manually configured learning rate: C is inverse regularisation strength. LightGBM was still evaluated using learning rates 0.02 and 0.05, but was not selected. Do not present the unused LightGBM learning rate as the selected model's hyperparameter.

Confidence intervals are wide because only 38-48 positive test outcomes are available for each product. Small AUC changes are not proof of a statistically significant gain. Green Home still has a train-test AUC gap of approximately 0.115; its test performance and external robustness need further investigation with genuinely independent labelled data.

## Changes implemented

1. Restored transaction data/labels, shared split manifests and inference instructions; reset the generator seed on every call.
2. Fixed ID alignment in split stratification; removed label-provided candidate flags from training gates.
3. Compared training-CV logistic regression with LightGBM instead of forcing boosting; fit calibration from training OOF logits and select the threshold from training cross-fitted calibrated scores.
4. Reported transaction validation/test separately, both propensity baselines on validation/test, calibration bins/ECE, threshold metrics, subgroup diagnostics, test labels/predictions and reproducibility hashes.
5. Added reusable inference; unknown vehicle/critical suitability facts fail closed, and financial eligibility explicitly remains unassessed.
6. Replaced potentially misleading HIGH/affordability reason names with neutral contribution-based identifiers accompanied by observed values. No missing input is claimed as evidence.
7. Filtered future records and future product starts; partial annual energy data yields insufficient information. Missing transaction history remains unknown rather than zero spending.
8. Replaced approximate operational emissions factors with exact 2025 UK source values, row IDs, units and a bundled official workbook. Scenario assumptions are labelled separately.
9. Corrected solar accounting: cap on-site savings to demand, report export separately and avoid negative household emissions. Added sensitivity scenarios, invalid-input handling and missing-factor handling. Removed unsourced paper CO2 claims.
10. Added customer explanations, constrained optional LLM fact ordering with strict validation/fallback, product-specific regional summaries, observed trends and an optional Streamlit viewer. No live LLM provider evaluation was performed.
11. Replaced the problematic warm-start adaptation routine with independent-customer retraining, train-only calibration/support refresh, validation acceptance and separate test evaluation. External adaptation remains untested.

## Verification completed

Full training/evaluation entry point completed in 43.11 seconds in this environment using included data (generation excluded). Independent validation was 750 customers and test was 751 customers; models were trained on suitable subsets of 3,499 training customers. Outputs contain exactly 20,000 unique customer-product pairs and 3,004 test rows.

23 automated checks passed. They cover split disjointness/label order, future-data exclusion, incomplete energy history, empty activity tables, duplicate monthly data, excluded products, unknown fuel/holdings, EV/retrofit formulas, low-demand solar exports, invalid inputs/factors, absence of unsourced paper carbon, persisted-model scoring, confidence penalties, inference and LLM output validation. The saved models reproduce the report's test AUC and log loss to 12 decimal places. Full details are in `outputs/test_results.log`.

On 60,000 sampled transactions from each customer-disjoint held-out partition, category macro-F1 was 0.999414 on validation and 0.999547 on test. These high numbers are synthetic-template results. They do not validate unseen-merchant generalisation. `outputs/txn_evaluation.json` includes baseline and per-category metrics.

## Requirement coverage and remaining work

| Area | Delivered | Limitation |
|---|---|---|
| Customer 360 / categorisation | Complete synthetic data, feature engineering, classifier, exclusive categories | Real bank feeds and unfamiliar merchants not tested |
| Four product opportunities | Candidate gates, propensity, confidence, evidence, exclusions | Institutional credit criteria not supplied or implemented |
| Sustainability impact | Deterministic operational scenarios, primary factors, assumptions and sensitivity | Full lifecycle, additionality and actual measured reductions not established |
| Customer / business insights | Grounded text, regional summaries, observed activity trends, drill-down data | Final app integration, user acceptance and conversion tracking pending |
| Working prototype UI | Optional Streamlit source provided | Syntax checked; browser/runtime UI was not launched here |
| LLM implementation | Prompt, HTTPS provider adapter, validated fact ordering and fallback | Provider API/key/model must be configured; no live-provider evaluation; template outputs are not GenAI results |
| Evaluation / predictions | Independent validation metrics, baselines, test predictions, hashes and tests | Synthetic labels favour linear models; same test was inspected during audit |
| Responsible AI | Documented privacy, subgroup limits, groundedness and human oversight | No fairness certification or production approval |

Before claiming a complete hackathon submission, integrate and demonstrate the dashboard with the existing frontend/backend, configure and evaluate the LLM if GenAI credit is sought, and explain the remaining limitations explicitly. Before real-world use, obtain lawfully usable independent labels, authorised eligibility rules and temporal/external validation. Do not use confidential banking data for this hackathon.

## What to tell judges

“We predict six-month take-up with separately trained models for four green products. We compared logistic regression and LightGBM using training cross-validation and selected logistic regression on our synthetic dataset. Our independent synthetic test AUCs are approximately 0.864 for EV, 0.732 for Green Home, 0.860 for Solar and 0.816 for Paperless. AUC is ranking quality, not adoption accuracy. The carbon engine calculates documented operational scenarios, while suitability rules and lender review remain separate. Confidence is a documented stability/data-quality heuristic. These are prototype results, and external validation is still required.”

## References and provenance

* User-provided Lloyds Problem Statement 1: Green Customer Insights Platform (LLOYDS-ps1.pdf).
* DESNZ 2025 conversion-factor publication: https://www.gov.uk/government/publications/greenhouse-gas-reporting-conversion-factors-2025
* Exact flat-file workbook: https://assets.publishing.service.gov.uk/media/6846b6ea57f3515d9611f0dd/ghg-conversion-factors-2025-flat-format.xlsx
* GHG Protocol comparative-emissions framework: https://ghgprotocol.org/estimating-and-reporting-avoided-emissions
* Scikit-learn probability calibration documentation: https://scikit-learn.org/stable/modules/calibration.html
* Original ZIP SHA256: 1d5f7add153b89868b05a9cb704ca6e73b9bacc61be9fdc5cf8b5bd1feac4ca2
* Bundled factor workbook SHA256: 8bfdb45b81ec4a88e3bdf4584637330f62e6bd09ce1940e654c5d7b7f736de94
