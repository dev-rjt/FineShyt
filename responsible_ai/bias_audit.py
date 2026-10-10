"""Descriptive synthetic-data subgroup diagnostics; never certifies fairness."""
import argparse
from pathlib import Path

import pandas as pd

from responsible_ai.contract_checks import load_records, validate_record

CSV_PATHS = ["customer.customer_id", "opportunity.product_code", "prediction.propensity",
             "eligibility.status", "recommendation.decision", "recommendation.customer_visible"]


def _records_frame(records):
    if any(validate_record(record) for record in records):
        raise ValueError("Bias audit requires valid contract records")
    return pd.DataFrame([{key: record[key.split(".")[0]][key.split(".")[1]]
                          for key in CSV_PATHS} for record in records])


def audit_bias(records, customers, *, minimum_group_size=10):
    if not isinstance(minimum_group_size, int) or minimum_group_size < 1:
        raise ValueError("Minimum group size must be a positive integer")
    frame = records.copy() if isinstance(records, pd.DataFrame) else _records_frame(records)
    if not set(CSV_PATHS) <= set(frame):
        raise ValueError("Recommendations CSV needs literal contract-path columns")
    required = {"customer_id", "age_band", "income_band"}
    if not required <= set(customers) or not customers.customer_id.is_unique:
        raise ValueError("Bias customer table needs unique keys and existing bands")
    if frame.empty or frame.duplicated([CSV_PATHS[0], CSV_PATHS[1]]).any():
        raise ValueError("Recommendations need unique customer/product keys")
    propensity = frame[CSV_PATHS[2]]
    if (propensity.notna() & ~propensity.between(0, 1)).any():
        raise ValueError("Invalid propensity")
    products = {"EV_FINANCE", "GREEN_HOME_LOAN", "SOLAR_FINANCE", "PAPERLESS_BANKING"}
    eligibilities = {"ELIGIBLE", "INELIGIBLE", "MANUAL_REVIEW", "INSUFFICIENT_DATA"}
    decisions = {"RECOMMEND", "DO_NOT_RECOMMEND", "MANUAL_REVIEW"}
    if not (frame[CSV_PATHS[1]].isin(products).all() and frame[CSV_PATHS[3]].isin(eligibilities).all()
            and frame[CSV_PATHS[4]].isin(decisions).all()
            and frame[CSV_PATHS[5]].map(lambda x: isinstance(x, bool)).all()):
        raise ValueError("Invalid projected contract statuses")
    recommend = frame[CSV_PATHS[4]].eq("RECOMMEND")
    eligible = frame[CSV_PATHS[3]].eq("ELIGIBLE")
    if (recommend & ~eligible).any() or (frame[CSV_PATHS[5]] & ~(eligible & recommend)).any():
        raise ValueError("Invalid eligibility/visibility gate")
    merged = frame.merge(customers[list(required)], left_on=CSV_PATHS[0], right_on="customer_id",
                         how="left", validate="many_to_one", indicator=True)
    if not merged._merge.eq("both").all():
        raise ValueError("Recommendations and customer keys do not align")
    # Auditing denominators must include every customer for every supplied
    # product; a recommendations-only selected sample gives misleading rates.
    for _, group in frame.groupby(CSV_PATHS[1]):
        if set(group[CSV_PATHS[0]]) != set(customers.customer_id):
            raise ValueError("Bias rates require all customer opportunities for each supplied product")
    merged["recommended"] = merged[CSV_PATHS[4]].eq("RECOMMEND")
    rows = []
    for dimension in ("age_band", "income_band"):
        for (product, band), group in merged.groupby([CSV_PATHS[1], dimension], dropna=False):
            n = len(group)
            suppressed = n < minimum_group_size
            rows.append({"product_code": product, "dimension": dimension,
                         "band": None if pd.isna(band) else band, "suppressed": suppressed,
                         "group_size": None if suppressed else n,
                         "propensity_observations": None if suppressed else int(group[CSV_PATHS[2]].notna().sum()),
                         "recommendation_rate": None if suppressed else float(group.recommended.mean()),
                         "mean_propensity": None if suppressed else group[CSV_PATHS[2]].mean()})
    report = pd.DataFrame(rows)
    gaps = []
    for (product, dimension), group in report.groupby(["product_code", "dimension"]):
        visible = group[~group.suppressed]
        entry = {"product_code": product, "dimension": dimension}
        for metric in ("recommendation_rate", "mean_propensity"):
            values = visible[metric].dropna()
            entry[metric + "_gap"] = float(values.max() - values.min()) if len(values) >= 2 else None
        gaps.append(entry)
    return report, pd.DataFrame(gaps)


def write_bias_report(report, gaps, csv_path, markdown_path, minimum_group_size=10):
    csv_path, markdown_path = Path(csv_path), Path(markdown_path)
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    report.to_csv(csv_path, index=False)
    def cell(value):
        if pd.isna(value): return "null"
        return str(value).replace("|", "\\|").replace("\n", " ")
    lines = ["# Bias diagnostics", "", "Synthetic-data description only. This report does not establish fairness.",
             "Recommendation rate counts RECOMMEND decisions among all opportunities for the supplied product.",
             "Mean propensity uses available scores; confidence is not a take-up probability.",
             f"Groups smaller than {minimum_group_size} suppress counts and metrics.",
             "Gaps are max minus min among unsuppressed bands; fewer than two bands gives null.",
             "", "| " + " | ".join(report.columns) + " |", "|" + "---|" * len(report.columns)]
    lines += ["| " + " | ".join(cell(x) for x in row) + " |" for row in report.itertuples(index=False, name=None)]
    lines += ["", "## Gaps", "", "| " + " | ".join(gaps.columns) + " |", "|" + "---|" * len(gaps.columns)]
    lines += ["| " + " | ".join(cell(x) for x in row) + " |" for row in gaps.itertuples(index=False, name=None)]
    markdown_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--records", required=True)
    parser.add_argument("--customers", default="data/doctored/raw/customers.csv")
    parser.add_argument("--minimum-group-size", type=int, default=10)
    parser.add_argument("--output-dir", default="data/reports/rai")
    args = parser.parse_args()
    records = pd.read_csv(args.records) if Path(args.records).suffix == ".csv" else load_records(args.records)
    report, gaps = audit_bias(records, pd.read_csv(args.customers), minimum_group_size=args.minimum_group_size)
    root = Path(args.output_dir)
    write_bias_report(report, gaps, root / "bias.csv", root / "bias.md", args.minimum_group_size)
    print("bias: diagnostics written; no fairness conclusion")


if __name__ == "__main__":
    main()
