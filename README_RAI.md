# Responsible AI package

This package adds privacy, leakage, contract, audit, scenario and subgroup checks
to the Glass-Box Green Insights app. It does not train models, decide product
rules, calculate impact, generate explanations or render the dashboard.

The runtime source of truth is `docs/API_CONTRACT.md`. The validator consumes the
same flat `Opportunity` objects returned by:

- `GET /customers/{customer_id}/opportunities`
- `GET /customers/{customer_id}/opportunities/{product_id}`
- `GET /customers/{customer_id}/audit`
- `POST /score` (the objects inside `items`)

The older PDF JSON contract remains in `docs/03-final-json-contract.pdf` for
history, but the RAI code no longer expects its nested pipeline-record shape.

## Install and test

Use Python 3.11+ in an isolated environment:

```bash
python3 -m venv .venv-rai
source .venv-rai/bin/activate
python -m pip install -r requirements-rai.txt
PYTHONDONTWRITEBYTECODE=1 python -m pytest -q -p no:cacheprovider tests/responsible_ai
```

`tests/responsible_ai/test_app_contract.py` checks every current app stub and
confirms that customer-facing lists never expose `SUPPRESSED` opportunities.

## Validate API output

Save an opportunity, a list of opportunities, a JSONL stream, or an API response
whose `items` field contains opportunities:

```bash
python -m responsible_ai.contract_checks opportunity.json
python -m responsible_ai.contract_checks customer-opportunities.json --customer-visible
```

Production validation is strict by default. An `impact.status` of `OK` requires
non-placeholder assumption and emission-factor provenance. The current app runs
on deliberate placeholder stubs; validate those only with the explicit demo flag:

```bash
python -m responsible_ai.contract_checks stub-response.json \
  --customer-visible --allow-stub-placeholders
```

That flag is not appropriate for production records.

## Run the complete data and record audit

The source dataset must follow the inventory paths under `data/`. Originals are
never modified. The identity vault defaults to
`responsible_ai/identity_vault.csv`, outside `data/` and ignored by Git.

```bash
python -m responsible_ai.verify_inventory --inventory file_inventory.csv
python -m responsible_ai.anonymise --data-root data --seed 2026

bash run_rai.sh \
  --records data/reports/rai/opportunities.json \
  --scan data/reports/rai
```

`run_rai.sh` executes every stage and returns nonzero when any stage fails. It
accepts `--records`, `--data-root`, `--inventory`, `--report-dir`, `--vault`,
repeatable `--scan`, and optional `--expectations`. Set `RAI_PYTHON` to choose an
interpreter.

Generated doctored tables preserve source schemas and paths under
`data/doctored/`. Reports go to `data/reports/rai/`. Never commit the identity
vault, doctored data, reports, caches, environments or secrets.

## Integration API

```python
from copy import deepcopy

from responsible_ai.audit_log import append_audit
from responsible_ai.contract_checks import validate_record
from responsible_ai.features_loader import load_features

features = load_features("data/doctored/processed/customer_360.csv")

before_llm = deepcopy(opportunity)
# The explanation layer may now write opportunity["insight"] only.
violations = validate_record(opportunity, before_llm=before_llm)
if violations:
    raise ValueError("Opportunity failed Responsible AI validation")
append_audit(opportunity)
```

Customer-facing responses must also call `validate_record(...,
customer_visible=True)` or `validate_customer_response(...)`. Audit endpoints
validate records without that flag so suppressed decisions remain inspectable.

## What the checks enforce

- Product IDs, opportunity names, statuses and field shapes match the app API.
- A failed product-rule gate always overrides propensity and suppresses output.
- Suppressed opportunities have no insight, action or customer rank.
- Missing impact is never represented as a zero estimate.
- Available impact has ordered ranges, a method, assumptions and factor provenance.
- Customer text is verified, preserves the eligibility disclaimer and avoids
  approval or eligibility claims.
- A before/after snapshot proves the LLM changed only `insight`.
- Audit logs contain allowlisted metadata only, never explanation text or payloads.
- Bias diagnostics use every customer/product decision, with small-group
  suppression; they describe synthetic data and do not certify fairness.

See `responsible_ai/RESPONSIBLE_AI.md` for limitations and control ownership.
