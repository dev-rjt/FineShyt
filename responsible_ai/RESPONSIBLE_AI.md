# Responsible AI controls

These controls support a synthetic-data hackathon demonstration. Passing them is
not proof of security, fairness, model quality or regulatory compliance.

## Runtime boundary

The app follows `docs/API_CONTRACT.md`: ML produces propensity, confidence and
reason codes; deterministic product rules produce `gate`; the carbon engine
produces `impact`; and the LLM may write only `insight`. Propensity never decides
eligibility, and neither the UI nor generated text may claim that a customer is
eligible, approved, pre-approved, guaranteed or qualified.

`contract_checks.py` validates the API `Opportunity` object. It rejects unknown
fields, invalid enums, non-finite scores, mismatched product IDs, inconsistent
gate/status combinations, customer-visible suppression, unordered impact ranges,
missing production provenance, unverified text and unsafe claims. Passing a
`before_llm` snapshot verifies that no field except `insight` changed.

The current app uses explicit placeholder assumptions and factors so that the UI
can be developed before the carbon component lands. Strict validation rejects
those placeholders. `allow_stub_placeholders=True` exists only for `USE_STUBS=true`
tests and must not be used for production records.

## Privacy

`anonymise.py` creates schema-preserving copies under `data/doctored/` and uses a
seeded permutation of the existing `C` plus five-digit customer ID space. It
coarsens `customer_since` to a month and scrubs common transfer payees, emails,
UK phone-like numbers, long account-like digit strings and full UK postcodes.
Original files are never changed.

The default `identity_vault.csv` is permissioned to 0600 and ignored by Git. The
mapping is pseudonymisation, not irreversible anonymity: the seed is fixed, row
order is retained, values may have fixed points, and age/income/region fields can
remain quasi-identifiers. Only synthetic or lawfully public data is permitted.

`canary_test.py` inserts a synthetic payee token into an isolated data copy, runs
the anonymiser and feature projection, then scans the supplied records, reports,
logs and caches. It cannot inspect stores that were not supplied, encrypted or
compressed formats, or external services.

## Feature and leakage controls

`features_loader.py` is a fail-closed projection. IDs, age, postcode area,
provenance, labels and generated archetypes are excluded. Income is banned by the
single `BAN_INCOME_FOR_MODELS` switch unless the ML owner explicitly changes the
policy. Removing protected fields does not remove proxy bias.

`leakage_audit.py` checks customer split coverage, duplicate/overlapping keys,
feature dates, post-cutoff label windows, label provenance, exact label copies and
very high numeric correlations. Undefined correlations and a PASS result do not
prove that leakage is absent. Encoders, imputers and text vocabularies must still
be fitted on training customers only.

## Explainability and impact

For `impact.status = OK`, records need at least one ordered low/central/high range,
a positive horizon, a documented method, assumptions and emission-factor
provenance. Metrics remain separate: CO2e, energy, paper and digital adoption are
never summed. `INSUFFICIENT_DATA` carries no metrics; zero is not a missing-value
substitute.

Customer-facing `insight` objects must be verified and come from `LLM` or the
deterministic `TEMPLATE` fallback. The checks can enforce write scope and basic
claim language, but they cannot prove that arbitrary prose is factually supported.
The explanation owner remains responsible for number, product and reason-code
verification before a response is shown.

`audit_log.py` stores only an event ID, pseudonymous customer/product identifiers,
statuses, component versions, factor IDs, dates and timestamp. It never stores
explanation text, customer profiles or the full opportunity. Its Unix advisory
lock serialises package writers; it is not a tamper-evident ledger.

## Bias and human oversight

`bias_audit.py` reports per-product recommendation rate, mean propensity and mean
confidence by existing age and income bands. Every customer must have a decision
for each included product, preventing a recommendations-only denominator. Groups
below the configured threshold suppress counts and metrics. Gaps are descriptive
diagnostics on synthetic data, not fairness conclusions.

`scenario_tests.py` validates actual scenario records and always exercises core
guard mutations. Product-specific expectations are checked only when the rule
owner supplies an expectations mapping. The module does not infer business rules
from scenario names. Authorised bank processes own lending, affordability and
human-review decisions.

## Data and model limits

The profiles are synthetic. Public retail and smart-meter samples may seed some
descriptions and shapes; retain source attribution and licence notices. Synthetic
outcomes do not demonstrate real customer demand, national representativeness or
causal sustainability impact.

The model cards in `responsible_ai/model_cards/` are templates until the ML owner
adds actual versions, features, seeds, metrics, calibration, thresholds and review
dates. Confidence is not take-up probability. Impact estimates come only from the
deterministic carbon engine and must be labelled as estimates.

## Required ownership hand-offs

- Data owner: complete inventory, generator version, source provenance and licences.
- ML owner: approved features, train-only preprocessing, splits, labels and metrics.
- Rules owner: authoritative product-rule logic and scenario expectations.
- Carbon owner: formulas, ranges, assumptions and versioned factor provenance.
- Explanation owner: before/after snapshots, verifier results and template fallback.
- Integration owner: validate full API opportunity records and preserve audit scope.
