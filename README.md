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

## Integrated components

| Folder | Purpose |
|---|---|
| `data/`, `src/data/` | Canonical 5,000-customer dataset, source adapters, validation and documentation |
| `ml/` | Transaction classifier, four propensity models, saved artifacts, evaluation and contract output |
| `src/engine/` | Deterministic product gate and impact calculations |
| `responsible_ai/` | Privacy, leakage, bias, schema, scenario and audit controls |
| `src/api/` | Original API contract implementation and integration reference |
| `src/llm/` | Grounded local LLM explanations, fact extraction and output verification |
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
