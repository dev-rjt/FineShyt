#!/usr/bin/env bash
# Every stage runs; a missing input or any failed stage makes the run fail.
set -uo pipefail
cd "$(dirname "$0")" || exit 1

records=""
data_root="data"
inventory="file_inventory.csv"
reports="data/reports/rai"
vault="responsible_ai/identity_vault.csv"
expectations=""
scan_paths=()

while (($#)); do
  case "$1" in
    --records|--data-root|--inventory|--report-dir|--vault|--expectations|--scan)
      if (($# < 2)); then echo "Missing option value"; exit 2; fi
      case "$1" in
        --records) records="$2" ;;
        --data-root) data_root="$2" ;;
        --inventory) inventory="$2" ;;
        --report-dir) reports="$2" ;;
        --vault) vault="$2" ;;
        --expectations) expectations="$2" ;;
        --scan) scan_paths+=(--scan "$2") ;;
      esac
      shift 2
      ;;
    *) echo "Unknown option"; exit 2 ;;
  esac
done
if [[ -z "$records" ]]; then
  echo "Usage: bash run_rai.sh --records CONTRACT_RECORDS.json [--scan CACHE_OR_LOG_PATH]"
  exit 2
fi
python_bin="${RAI_PYTHON:-python3}"
export PYTHONDONTWRITEBYTECODE=1
failed=0
run_stage() {
  local name="$1"
  shift
  if "$@" >/dev/null 2>&1; then
    printf '%s: PASS\n' "$name"
  else
    printf '%s: FAIL\n' "$name"
    failed=1
  fi
}

run_stage verify_inventory "$python_bin" -m responsible_ai.verify_inventory \
  --root . --inventory "$inventory" --output "$reports/inventory.json"
run_stage anonymise "$python_bin" -m responsible_ai.anonymise \
  --data-root "$data_root" --vault "$vault"
run_stage leakage_audit "$python_bin" -m responsible_ai.leakage_audit \
  --data-root "$data_root/doctored" --output "$reports/leakage.md"
run_stage contract_checks "$python_bin" -m responsible_ai.contract_checks "$records"
run_stage audit_log "$python_bin" -m responsible_ai.audit_log \
  --records "$records" --output "$reports/audit.jsonl"
run_stage canary_test "$python_bin" -m responsible_ai.canary_test \
  --data-root "$data_root" --records "$records" --scan "$reports" "${scan_paths[@]}" \
  --output "$reports/canary.json"
scenario_options=()
if [[ -n "$expectations" ]]; then scenario_options=(--expectations "$expectations"); fi
run_stage scenario_tests "$python_bin" -m responsible_ai.scenario_tests \
  --scenarios "$data_root/doctored/processed/demo_scenarios.csv" \
  --records "$records" "${scenario_options[@]}" --output "$reports/scenarios.md"
run_stage bias_audit "$python_bin" -m responsible_ai.bias_audit \
  --records "$records" --customers "$data_root/doctored/raw/customers.csv" \
  --output-dir "$reports"
if "$python_bin" -m pytest -q -p no:cacheprovider tests/responsible_ai; then
  echo "pytest: PASS"
else
  echo "pytest: FAIL"
  failed=1
fi
exit "$failed"
