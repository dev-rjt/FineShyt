# Glass-Box Green Insights

Documentation for the Lloyds Megathon problem statement and the team's proposed solution.

## Documents

1. [Official Lloyds problem statement](docs/01-lloyds-problem-statement.pdf)
2. [Simplified problem statement and five-person team guide](docs/02-green-insights-team-guide.pdf)
3. [Final shared JSON integration contract](docs/03-final-json-contract.pdf)

The official problem statement remains the source of truth. The team guide explains the solution in simpler terms, while the JSON contract defines the interface all implementation components should follow.

## Dataset pipeline

Dataset work is developed on the `feature/dataset-pipeline` branch.

The pipeline combines bounded samples from UCI Online Retail II and the London smart-meter dataset with synthetic banking, vehicle, digital and product data. It produces Customer 360 features, labels, customer-level splits, reference tables and validation reports.

Build everything with:

```bash
python3 src/data/download_public_sources.py
python3 src/data/build_dataset.py --customers 5000 --seed 42
python3 src/data/validate_dataset.py
python3 src/data/generate_documentation.py
```

See [dataset methodology](docs/data-methodology.md), [limitations](docs/data-limitations.md), and [transaction-category boundaries](docs/transaction-category-boundaries.md).
