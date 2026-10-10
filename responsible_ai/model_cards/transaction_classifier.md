# Transaction classifier model card template

Status: TEMPLATE ONLY. No classifier is trained by this package.

| Item | Owner must complete |
|---|---|
| Model version / seed | `<ML_OWNER_VERSION_AND_SEED>` |
| Training data | `data/doctored/raw/transactions.csv`; scrubbed descriptions and explicitly approved feature subset |
| Feature candidates | `merchant_description`, `amount`, `debit_credit` from `features_loader.py` |
| Label data | `data/doctored/processed/transaction_category_labels.csv`, joined through separate `transaction_id` metadata |
| Target | Existing `true_category`; never included in model features |
| Vocabulary | Exact eight-class vocabulary from the complete source label table; dictionary examples are not exhaustive |
| Provenance | Raw `source_basis` retained for audit only; label table has no `label_method` column |
| Customer partition | Existing train/validation/test customer sets; no customer appears across partitions |
| Date limits | `transaction_date` no later than the customer's cutoff |
| Algorithm / preprocessing | `<ML_OWNER_DETAILS>`; vocabulary and transformations fitted on training customers only |
| Macro-F1 / per-class precision-recall | `<NOT_MEASURED>` |
| Confusion matrix / class support | `<NOT_MEASURED>` |
| Unknown/ambiguous text behaviour | `<ML_OWNER_POLICY>` |
| Public seeds / licences | UCI Online Retail II, CC BY 4.0, retain attribution and transformation notes |
| Reviewer/date | `<HUMAN_REVIEWER_AND_DATE>` |

Limitations: labels and merchant names can contain obvious synthetic category clues;
near-duplicate public retail descriptions can inflate evaluation results. Report
merchant/text overlap across customer splits separately; the current leakage audit
does not certify absence of text duplicates. Scrubbing may remove useful payee text
and does not recognise arbitrary personal names. Do not train on `customer_id`,
`transaction_id`, `true_category`, `source_basis`, provenance or customer archetype.

Evidence: `pii_scrubber.py`, `features_loader.py`, `leakage_audit.py`,
`canary_test.py` and their tests.
