# Glass-Box Green Insights - Integrated Final Branch

This integration branch combines the team's canonical dataset pipeline, trained
ML artifacts, backend/API contract, deterministic product and impact engine, and
Responsible AI controls. The production-style business application is under
`product_app/`.

## Run the final application

```bash
cd product_app
./run_demo.sh
```

The customer and bank experiences open at <http://127.0.0.1:8502>. FastAPI
documentation is available at <http://127.0.0.1:8000/docs>.

Demo sign-in: bank `bank_manager` / `GreenBank@2026`; customer `C12558` /
`GreenCustomer@2026`. See [FINAL_HANDOFF.md](FINAL_HANDOFF.md) for the complete
problem-statement walkthrough, rebuild commands and prototype boundaries.

## Host the demo

The repository includes a Render Blueprint in `render.yaml`. It installs the
Python dependencies, starts FastAPI on the service's internal loopback address,
and exposes the Streamlit interface on Render's assigned public port.

1. Push this repository to GitHub.
2. In Render, choose **New → Blueprint** and connect the repository.
3. Review the `verdant-green-insights` service and apply the Blueprint.
4. Wait for `/_stcore/health` to pass, then open the generated `onrender.com` URL.

The checked-in credentials are only for synthetic hackathon data. Replace the
two passwords in the Render environment before using the URL beyond judging.

## Integrated components

| Folder | Purpose |
|---|---|
| `data/`, `src/data/` | Canonical 5,000-customer dataset, source adapters, validation and documentation |
| `ml/` | Transaction classifier, four propensity models, saved artifacts, evaluation and contract output |
| `src/engine/` | Deterministic product gate and impact calculations |
| `responsible_ai/` | Privacy, leakage, bias, schema, scenario and audit controls |
| `src/api/` | Original API contract implementation and integration reference |
| `src/llm/` | Grounded local LLM explanations, fact extraction and output verification |
| `db/` | Executable SQLite schema, database builder, foreign keys, indexes and portfolio view |
| `product_app/` | Final authenticated FastAPI + business/customer Streamlit product |
| `integrations/engine_reference/` | Clean source imported from the independent engine branch |

## Rebuild the canonical pipeline

```bash
python3 src/data/build_dataset.py --customers 5000 --seed 42
python3 src/data/validate_dataset.py
python3 ml/run_project_dataset.py
```

All data is synthetic or based on bounded lawful public samples. Propensity is
not eligibility. Sustainability figures are estimates from deterministic rules.

## Component documentation

- [Responsible AI controls and run instructions](README_RAI.md)
- [Customer and bank-staff LLM explanations with local Ollama](README_LLM.md)
