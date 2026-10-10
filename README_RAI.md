# Responsible AI package

This package provides audit controls only. It does not train models, decide
product eligibility, calculate carbon, generate explanations or create a dashboard.

Use Python 3.11+; the pinned environment was tested with Python 3.12. Create an
isolated environment and install the lock-style requirements:

```bash
python3.12 -m venv .venv-rai
source .venv-rai/bin/activate
python -m pip install -r requirements-rai.txt
```

The complete source dataset must use the dictionary's paths below `data/`.
Keep `file_inventory.csv` and `data_dictionary.csv` at the repository root, or
pass the inventory path explicitly. The runner does not download or synthesize
missing production tables. Originals are never modified.

```bash
# Run before ML/eligibility/impact/explanation components consume the dataset.
python -m responsible_ai.verify_inventory --inventory file_inventory.csv
python -m responsible_ai.anonymise --data-root data --seed 2026

# Team components then produce contract JSON/JSONL using doctored IDs.
# Provide all customer/product opportunities, including blocked decisions.
bash run_rai.sh --records data/reports/rai/opportunities.json \
  --scan data/reports/rai

# Unit tests alone do not require any production dataset.
PYTHONDONTWRITEBYTECODE=1 python -m pytest -q -p no:cacheprovider tests/responsible_ai
```

`run_rai.sh` runs inventory, anonymisation, leakage, contract, audit logging, canary, scenarios,
bias and pytest even if a stage fails, then returns a nonzero exit code for any
failure. It prints stage statuses only, except synthetic-fixture pytest failures.
Use `RAI_PYTHON=/path/to/python` to select the interpreter. Supported options:
`--records`, `--data-root`, `--inventory`, `--report-dir`, `--vault`, repeatable
`--scan`, and optional `--expectations`. Logs/caches must be explicitly supplied
to `--scan`; its own report/log directory is scanned automatically. Unprovided
external stores are outside the canary's scope.

The default vault is `responsible_ai/identity_vault.csv`, outside `data/` and
gitignored. It must never be shared with models or committed. All generated
reports go in `data/reports/rai/`; doctored copies keep the original relative
paths beneath `data/doctored/`. Check reports even if a later stage passes.

Integration API:

```python
from copy import deepcopy
from responsible_ai.features_loader import load_features
from responsible_ai.contract_checks import validate_record
from responsible_ai.audit_log import append_audit

features = load_features("data/doctored/processed/customer_360.csv")
# Join keys stay in a separate audit frame; do not train on customer_id.

before_llm = deepcopy(record)  # record is supplied by the integration owner
# The explanation owner now writes record["explanation"].
violations = validate_record(record, before_llm=before_llm)
if violations:
    raise ValueError("Contract validation failed")
append_audit(record)
```

Do not mutate a DataFrame before taking its schema snapshot. CSV schema checking
uses inferred types and observed null masks, while every unmodified cell is also
compared lexically by the anonymiser. It conservatively preserves complete object
domains except documented identifier, date and free-text columns. Declared enum
sets/nullability need upstream schema metadata; dictionary examples alone cannot
provide them. A single source ID is a valid identity permutation, not anonymity.

`contracts/opportunity_v1.schema.json` was derived from the PDF, because none was
available in this workspace. Do not overwrite an existing team schema. Compare
and agree before integration. Top-level and canonical section keys are required;
unavailable impact permits the minimal shapes shown in the PDF. Known values may
be null where allowed, but AVAILABLE impact requires real estimates/provenance.
Other product calculation-input keys are not documented by the PDF and must be
agreed by teammates rather than guessed. All unsupported keys fail validation.

Fixtures: `eligible_ev.json` is canonical; `ineligible_ev.json` and
`missing_data_ev.json` are exact PDF section fragments, not complete records.
Only PDF line-wrap whitespace in strings was normalized. The other two fixtures
are illustrative. No fixtures are created/overwritten automatically at runtime.

Bias auditing accepts contract records or a CSV with these literal existing
contract-path headers (this is a projection convention, not a new dataset table):
`customer.customer_id`, `opportunity.product_code`, `prediction.propensity`,
`eligibility.status`, `recommendation.decision`, `recommendation.customer_visible`.
The customer lookup must use the same doctored ID mapping. Provide every customer
for each supplied product; suppressed groups do not publish counts or metrics.

Scenario names are read from the file. Optional `--expectations` is a team-authored
JSON mapping from each actual scenario name to `product_code` and `fields` (existing
dotted contract paths mapped to expected values). Unknown scenario meanings are
not guessed. Without it, scenario PASS means records satisfy safety invariants,
not that eligibility rules themselves were tested.

Required teammate inputs:

- Data owner: all 18 source files at inventory paths, exact inventory, generator
  seed/version, external-source attribution/licence notices and provenance.
- ML owner: confirm allowed features and income policy; train-only preprocessing;
  customer splits; label creation rationale; trained versions, seed and metrics.
- Eligibility owner: official rules and actual scenario-to-product expectations;
  human-review handling and deterministic decisions independent of propensity.
- Carbon owner: estimates, units, ranges, assumptions, factor provenance and
  documented calculation-input keys for non-EV products.
- Explanation/integration owners: before-LLM snapshots, verified/fallback text,
  component versions, full opportunity records for doctored IDs, logs/cache paths.

Git delivery: use a new `Harshik-responsible-ai` branch or the first unused numeric
suffix, from the current remote default branch. Never overwrite existing requested
files. Stage exact package/test/docs paths only and append .gitignore rules. The
original staging allowlist did not include a newly derived contract schema; include
it only after explicit authorization to expand that allowlist, or have the team
contract owner add it. Never push without successful tests and staged-path review.
Never commit the vault, doctored data, generated reports, environment files or caches.

If direct Git authentication is unavailable, download and extract the delivery
archive into `~/Downloads/rai-complete`, open a terminal in your authenticated
FineShyt clone, and run the following. It stops if the remote team schema is
missing, because Step 10's staging allowlist excludes a newly created schema.
The contract owner must first supply the agreed schema on the default branch.
It also stops for any existing requested file; nothing is overwritten.

```bash
bash <<'BASH'
set -euo pipefail
git fetch origin && git ls-remote --heads origin Harshik-responsible-ai
case "$(git remote get-url --push origin)" in
  https://github.com/dev-rjt/FineShyt|https://github.com/dev-rjt/FineShyt.git|git@github.com:dev-rjt/FineShyt.git) ;;
  *) echo "STOP: unexpected origin"; exit 1 ;;
esac
default_branch=$(git ls-remote --symref origin HEAD |
  awk '$1 == "ref:" {sub("^refs/heads/", "", $2); print $2; exit}')
test -n "$default_branch"
branch=Harshik-responsible-ai
suffix=2
while test -n "$(git ls-remote --heads origin "$branch")" ||
      git show-ref --verify --quiet "refs/heads/$branch"; do
  branch="Harshik-responsible-ai-$suffix"
  suffix=$((suffix + 1))
done
delivery_dir=$(mktemp -d "${TMPDIR:-/tmp}/rai-delivery.XXXXXX")
git worktree add --detach "$delivery_dir/FineShyt" "origin/$default_branch"
cd "$delivery_dir/FineShyt"
git checkout -b "$branch" "origin/$default_branch"
source_dir="$HOME/Downloads/rai-complete"
test -f contracts/opportunity_v1.schema.json || {
  echo "STOP: contract owner must add the agreed schema first (Step 10 allowlist)"
  exit 1
}
test -f "$source_dir/README_RAI.md"

# Preflight every path, then copy only the authorised files.
export RAI_DELIVERY_SOURCE="$source_dir"
python3 - <<'PY'
import os, shutil
from pathlib import Path
source = Path(os.environ['RAI_DELIVERY_SOURCE'])
roots = ['responsible_ai', 'tests/responsible_ai', 'tests/fixtures']
files = [p for folder in roots for p in (source / folder).rglob('*') if p.is_file()]
files += [source / name for name in ['README_RAI.md', 'requirements-rai.txt', 'run_rai.sh']]
for file in files:
    destination = Path(file.relative_to(source))
    if not file.is_file() or destination.exists() or destination.is_symlink():
        raise SystemExit('STOP: existing or missing requested file: ' + str(destination))
    if any(parent.is_symlink() for parent in destination.parents):
        raise SystemExit('STOP: symlinked destination')
if Path('.gitignore').is_symlink():
    raise SystemExit('STOP: symlinked .gitignore')
for file in files:
    destination = Path(file.relative_to(source))
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(file, destination)
with Path('.gitignore').open('a') as stream:
    stream.write('\n' + (source / '.gitignore').read_text())
PY

python3.12 -m venv "$delivery_dir/venv"
"$delivery_dir/venv/bin/python" -m pip install -r requirements-rai.txt
PYTHONDONTWRITEBYTECODE=1 "$delivery_dir/venv/bin/python" -m pytest \
  -q -p no:cacheprovider tests/responsible_ai

commit_batch() {
  local message="$1"
  shift
  git add -- "$@"
  git status
  git diff --cached --name-only
  git diff --cached --check
  while IFS= read -r file; do
    case "$file" in
      *identity_vault.csv|data/doctored/*|*.env|*.env.*|*__pycache__*|*.pyc|*cache/*|*output/*|*outputs/*)
        git restore --staged -- "$file"
        echo "STOP: forbidden staged path was unstaged; fix .gitignore"
        exit 1 ;;
      responsible_ai/*.py|responsible_ai/RESPONSIBLE_AI.md|responsible_ai/model_cards/*.md|tests/responsible_ai/test_*.py|tests/fixtures/*.json|README_RAI.md|requirements-rai.txt|run_rai.sh|.gitignore) ;;
      *) git restore --staged -- "$file"; echo "STOP: unexpected staged path"; exit 1 ;;
    esac
  done < <(git diff --cached --name-only)
  git commit -m "$message"
}
commit_batch "Add schema, privacy and feature safeguards" \
  responsible_ai/schema_guard.py responsible_ai/pii_scrubber.py responsible_ai/features_loader.py \
  tests/responsible_ai/test_schema_guard.py tests/responsible_ai/test_pii_scrubber.py \
  tests/responsible_ai/test_features_loader.py .gitignore
commit_batch "Add inventory and schema-preserving anonymisation" \
  responsible_ai/verify_inventory.py responsible_ai/anonymise.py tests/responsible_ai/test_anonymise.py
commit_batch "Add leakage diagnostics and metadata-only audit logging" \
  responsible_ai/leakage_audit.py responsible_ai/audit_log.py tests/responsible_ai/test_leakage_audit.py
commit_batch "Add contract checks and documented test fixtures" \
  responsible_ai/contract_checks.py tests/responsible_ai/test_contract_checks.py tests/fixtures
commit_batch "Add canary, scenario and bias audits" \
  responsible_ai/canary_test.py responsible_ai/scenario_tests.py responsible_ai/bias_audit.py
commit_batch "Document RAI controls and reproducible runner" \
  responsible_ai/RESPONSIBLE_AI.md responsible_ai/model_cards README_RAI.md requirements-rai.txt run_rai.sh

test -z "$(git ls-remote --heads origin "$branch")" || {
  echo "STOP: branch now exists remotely"; exit 1;
}
git push -u origin "$branch"
printf '\nBranch: %s\n' "$branch"
git log --reverse --format='%H %s' "origin/$default_branch..HEAD"
git diff --name-only "origin/$default_branch..HEAD"
printf '\nTeammate PR command:\n'
printf 'gh pr create --repo dev-rjt/FineShyt --base "%s" --head "%s" --web\n' \
  "$default_branch" "$branch"
BASH
```
