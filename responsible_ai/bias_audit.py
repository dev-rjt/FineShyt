"""Descriptive synthetic-data subgroup diagnostics; never certifies fairness."""

import argparse
from pathlib import Path

import pandas as pd

from responsible_ai.contract_checks import load_records, validate_record

CSV_FIELDS = [
    "customer_id",
    "product_id",
    "opportunity",
    "status",
    "propensity",
    "confidence",
    "gate.rule_pass",
]


def _records_frame(records):
    if any(validate_record(record) for record in records):
        raise ValueError("Bias audit requires valid API opportunity records")
    rows = []
    for record in records:
        rows.append({
            "customer_id": record["customer_id"],
            "product_id": record["product_id"],
            "opportunity": record["opportunity"],
            "status": record["status"],
            "propensity": record["propensity"],
            "confidence": record["confidence"],
            "gate.rule_pass": record["gate"]["rule_pass"],
        })
    return pd.DataFrame(rows)


def audit_bias(records, customers, *, minimum_group_size=10):
    if not isinstance(minimum_group_size, int) or minimum_group_size < 1:
        raise ValueError("Minimum group size must be a positive integer")
    frame = records.copy() if isinstance(records, pd.DataFrame) else _records_frame(records)
    if not set(CSV_FIELDS) <= set(frame):
        raise ValueError("Opportunity CSV needs the documented API projection columns")
    required = {"customer_id", "age_band", "income_band"}
    if not required <= set(customers) or not customers.customer_id.is_unique:
        raise ValueError("Bias customer table needs unique keys and existing bands")
    if frame.empty or frame.duplicated(["customer_id", "product_id"]).any():
        raise ValueError("Opportunities need unique customer/product keys")
    if (~frame.propensity.between(0, 1) | ~frame.confidence.between(0, 1)).any():
        raise ValueError("Invalid propensity or confidence")
    if not frame.status.isin({"RECOMMENDED", "SUPPRESSED", "INSUFFICIENT_DATA"}).all():
        raise ValueError("Invalid opportunity status")
    if not frame["gate.rule_pass"].map(lambda value: isinstance(value, bool)).all():
        raise ValueError("Invalid gate projection")
    if (frame.status.eq("SUPPRESSED") == frame["gate.rule_pass"]).any():
        raise ValueError("Status and product-rule gate are inconsistent")

    merged = frame.merge(
        customers[list(required)],
        on="customer_id",
        how="left",
        validate="many_to_one",
        indicator=True,
    )
    if not merged._merge.eq("both").all():
        raise ValueError("Opportunity and customer keys do not align")
    for _, group in frame.groupby("product_id"):
        if set(group.customer_id) != set(customers.customer_id):
            raise ValueError("Bias rates require every customer for each supplied product")

    merged["recommended"] = merged.status.eq("RECOMMENDED")
    rows = []
    for dimension in ("age_band", "income_band"):
        for (product_id, opportunity, band), group in merged.groupby(
            ["product_id", "opportunity", dimension], dropna=False
        ):
            size = len(group)
            suppressed = size < minimum_group_size
            rows.append({
                "product_id": product_id,
                "opportunity": opportunity,
                "dimension": dimension,
                "band": None if pd.isna(band) else band,
                "suppressed": suppressed,
                "group_size": None if suppressed else size,
                "recommendation_rate": None if suppressed else float(group.recommended.mean()),
                "mean_propensity": None if suppressed else float(group.propensity.mean()),
                "mean_confidence": None if suppressed else float(group.confidence.mean()),
            })
    report = pd.DataFrame(rows)
    gaps = []
    for (product_id, opportunity, dimension), group in report.groupby(
        ["product_id", "opportunity", "dimension"]
    ):
        visible = group[~group.suppressed]
        entry = {"product_id": product_id, "opportunity": opportunity, "dimension": dimension}
        for metric in ("recommendation_rate", "mean_propensity", "mean_confidence"):
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
        if pd.isna(value):
            return "null"
        return str(value).replace("|", "\\|").replace("\n", " ")

    lines = [
        "# Bias diagnostics",
        "",
        "Synthetic-data description only. This report does not establish fairness.",
        "Recommendation rate counts RECOMMENDED statuses among all evaluated opportunities.",
        "Propensity is not eligibility, and confidence is not take-up probability.",
        f"Groups smaller than {minimum_group_size} suppress counts and metrics.",
        "Gaps are max minus min among unsuppressed bands; fewer than two bands gives null.",
        "",
        "| " + " | ".join(report.columns) + " |",
        "|" + "---|" * len(report.columns),
    ]
    lines += ["| " + " | ".join(cell(value) for value in row) + " |" for row in report.itertuples(index=False, name=None)]
    lines += [
        "",
        "## Gaps",
        "",
        "| " + " | ".join(gaps.columns) + " |",
        "|" + "---|" * len(gaps.columns),
    ]
    lines += ["| " + " | ".join(cell(value) for value in row) + " |" for row in gaps.itertuples(index=False, name=None)]
    markdown_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--records", required=True)
    parser.add_argument("--customers", default="data/doctored/raw/customers.csv")
    parser.add_argument("--minimum-group-size", type=int, default=10)
    parser.add_argument("--output-dir", default="data/reports/rai")
    args = parser.parse_args()
    records = pd.read_csv(args.records) if Path(args.records).suffix == ".csv" else load_records(args.records)
    report, gaps = audit_bias(
        records,
        pd.read_csv(args.customers),
        minimum_group_size=args.minimum_group_size,
    )
    root = Path(args.output_dir)
    write_bias_report(report, gaps, root / "bias.csv", root / "bias.md", args.minimum_group_size)
    print("bias: diagnostics written; no fairness conclusion")


if __name__ == "__main__":
    main()
