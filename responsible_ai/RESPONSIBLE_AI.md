# Responsible AI controls

This package supports the synthetic Lloyds Green Customer Insights hackathon.
ML predicts, official rules decide eligibility, a deterministic carbon engine
estimates impact, and an LLM explains. This package implements checks only.
Controls are design demonstrations, not proof of security, fairness or regulatory compliance.

## 1. Privacy

`anonymise.py` writes value-only copies to `data/doctored/<original path relative
to data>`. It uses a seeded permutation of the existing `C` plus five-digit ID
space across every customer-linked source CSV; it does not hash identities.
`customer_since` becomes the month's first day. `pii_scrubber.py` removes payee
text after transfer/standing-order markers, emails, UK phone-like numbers,
account-like digit strings and full UK postcodes. Short merchant references
remain. It cannot detect arbitrary personal names reliably.

`schema_guard.py` compares column names/order, inferred pandas dtypes, observed
null positions and complete categorical domains after CSV disk round trips.
`anonymise.py` separately checks unchanged cells and row order. CSVs do not
declare nullability; dictionary sample observations are not exhaustive constraints.
IDs, dates and free text are not categorical enums. JSON uses an explicit schema
and a conservative structural fingerprint; null-to-value transitions fail that
preservation guard even when a contract permits them.

`canary_test.py` plants `ZZ TESTNAME` only in a transaction description in an
isolated raw copy, in a supported payee context. It scans doctored tables,
feature outputs, supplied JSON records, supplied logs and supplied caches.
It does not run ML/LLM components or inspect unprovided/external caches.
The scan checks UTF-8/UTF-16 bytes and decoded JSON; compressed, encrypted or
service-specific cache formats need their owner's export before scanning.

`identity_vault.csv` is permissioned to 0600 and gitignored. Its columns are
`original_customer_id,pseudonymous_customer_id`; it is never a model input.
The deterministic seed, preserved ID space, possible fixed points and retained
row order make this pseudonymisation, not irreversible anonymity. Coarsened age,
income bands and postcode areas can still be quasi-identifiers. Only synthetic
banking profiles are permitted; public seeds must not be linked to real people.

## 2. Bias

`features_loader.py` excludes age, postcode area, IDs, provenance and labels.
Income is banned by the single `BAN_INCOME_FOR_MODELS` configuration constant;
the ML owner must confirm any change. Age and income remain in doctored source
tables solely for audits. Excluding age and income does not remove proxy bias:
region, housing, spending and digital activity can correlate with them.

`bias_audit.py` reports per-product recommendation decision rates, mean propensity
and max-minus-min gaps by existing age and income bands. Every customer must have
an opportunity for each supplied product; a selected recommendations-only sample
is rejected. Groups below 10 suppress counts and metrics; gaps exclude suppressed
groups and are null with fewer than two publishable bands. This is not differential
privacy, and metrics are descriptive diagnostics rather than fairness conclusions.

## 3. Explainability

`contract_checks.py` requires documented reason-code structures and available
impact units, method, time horizon, assumptions, ordered estimate ranges and
emission-factor provenance. `audit_log.py` stores only allowlisted pseudonymous
IDs, product, versions, statuses and timestamps. Logs append under a Unix advisory
lock; they are not tamper-proof or cryptographically authenticated.

`model_cards/` contains four propensity-model templates and a transaction
classifier template. Metrics remain placeholders until supplied by the ML owner.
Confidence is not the probability of take-up. Propensity describes the model's
target score; neither it nor confidence establishes eligibility or causation.

## 4. Hallucination

`contract_checks.py` rejects unknown fields, incompatible major schema versions,
invalid enums, non-finite scores, empty/missing-value sentinels, unavailable
impact estimates and inconsistent visibility. Passing `before_llm` compares
every section except `explanation`; a final object alone cannot prove write scope.
Verification/fallback flags are checked, but this package does not implement an
LLM, fact verifier or fallback writer, and cannot prove text is factually supported.

The PDF's ineligible and missing-data examples are partial records. Their exact
structures are retained in `tests/fixtures/`; tests replace their sections into
the canonical example for complete-record checks. Minimal nonavailable impact
objects are accepted as shown in the PDF. `calculation_error.json` and
`conflicting_signals.json` are illustrative, not organiser examples. No illustrative
marker has been added to the contract object. The conflict fixture demonstrates
the documented manual-review shape; it does not define a homeownership rule.

## 5. Human oversight

`contract_checks.py` enforces customer visibility only for ELIGIBLE plus RECOMMEND.
High propensity cannot override an ineligible or unresolved eligibility status.
Manual review requires the audit human-review flag. Official eligibility rules
remain authoritative, and any lending/affordability decision belongs to the bank.

`scenario_tests.py` reads actual scenario names from `demo_scenarios.csv`, checks
their supplied records and exercises dangerous visibility/zero mutations. Without
team-supplied expectations it reports invariant coverage only. It does not infer
product-rule outcomes from scenario names. The rule owner must provide expected
contract paths/values for product-specific assertions and arrange human review.

## 6. Data limits

Profiles are synthetic. Some transaction descriptions/amounts are seeded from
UCI Online Retail II and some energy profiles from public London Smart Meter
data, as indicated by `source_basis` and `profile_source`. Synthetic profiles do
not make every source observation synthetic. These sources do not establish
real bank take-up, national household representativeness or causal impacts.

Source attribution: Chen, D. (2012), Online Retail II, UCI Machine Learning
Repository, DOI https://doi.org/10.24432/C5CG6D. The UCI dataset page states
CC BY 4.0: https://archive.ics.uci.edu/dataset/502/online+retail+ii.
UK Power Networks, Low Carbon London, SmartMeter Energy Consumption Data in
London Households: https://data.london.gov.uk/dataset/smartmeter-energy-consumption-data-in-london-households-vqm0d.
The London page states Creative Commons Attribution without an explicit version
in its rendered metadata; retain the exact downloaded resource's licence notice
and confirm it before redistribution. These notes are attribution, not a licence
grant for third-party material. Public source IDs/keys must not become model features.

`verify_inventory.py` checks bytes, rows and column counts for all listed source
files. `leakage_audit.py` checks banned features, customer partitions, dates,
post-cutoff outcome windows, label provenance, exact copies and absolute Pearson
correlation over 0.9. Undefined correlations and PASS do not prove no leakage;
fit encoders/imputers on training customers only. Transaction-label provenance
has no `label_method` column in the dictionary, so none is invented for it.

The dataset cutoff is 2026-06-30; the PDF example's 2026-08-31 is an illustrative
contract value, not permission to use later feature data. Impact figures are
estimates, not measured savings; this package does not calculate them. The PDF
documents only EV calculation-input keys; other products need a team-approved
schema extension using agreed fields before those inputs are accepted.

Tests use small synthetic fixtures. Full production-data results require all
18 inventory tables and externally produced opportunity records aligned to the
doctored IDs; missing inputs fail instead of being called PASS. Source tables
and raw predictions must not be logged or sent to an LLM by this package.
