# Glass-Box Green Insights (Megathon X, Problem Statement 1)

An AI platform that finds green financial product opportunities from customer data, estimates the sustainability impact, and explains every recommendation. ML models make predictions, a rules-based carbon engine calculates impact, and the LLM only explains structured results.

**Current status:** the API and dashboard run on stub (fake) data that follows `docs/API_CONTRACT.md`. The real data, models, carbon engine and LLM layer replace the stubs one by one.

## Run the API (Docker)

You need Docker Desktop.

```bash
cp .env.example .env
docker compose up --build
```

- API docs: http://localhost:8000/docs
- Health check: http://localhost:8000/health

To reset the database: `docker compose down -v`

## Run the dashboard (Streamlit)

You need Python 3.11. Keep the API running in another terminal.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r app/requirements.txt
python -m streamlit run app/app.py
```

Open http://localhost:8501. The dashboard reads from `http://localhost:8000`; set `API_BASE_URL` to use a different address.

## Where things live

| Folder | What it holds |
|---|---|
| `src/api` | FastAPI app and the recommender |
| `src/common` | Shared data models that mirror the contract |
| `src/data` | Data generator and Customer 360 features |
| `src/ml` | Transaction categoriser and propensity models |
| `src/engine` | Product-rule gate and carbon engine |
| `src/llm` | LLM insight layer, verifier and template fallback |
| `app` | Streamlit dashboard |
| `db` | Database schema |
| `docs` | API contract and project documents |

## Read these first

- `docs/API_CONTRACT.md`: every endpoint and field. Change it before you change code.
- `ROLES.md`: who owns what.
- `AGENTS.md`: rules for AI coding agents in this repo.

## Working rules

- Work on a feature branch and open a pull request into `main`.
- Never commit `.env` or the `.venv` folder.
- Every impact figure is an estimate with a stated method. Propensity is not eligibility.
