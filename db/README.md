# Verdant database layer

`schema.sql` is the inspectable SQLite schema for the final demo. It defines
normalised customer, transaction, product, vehicle, energy and digital tables,
the model-ready feature snapshot, recommendations, indexes, foreign keys and a
portfolio view.

Build or refresh the local database from the versioned synthetic sources:

```bash
python db/build_demo_db.py
```

The generated `db/verdant_demo.sqlite3` file is intentionally ignored by Git.
Both launchers build it automatically before starting FastAPI. The backend reads
the database through `product_app/api_service.py`; CSV files remain the
reproducible seed and model-training inputs.

Inspect it with SQLite:

```bash
sqlite3 db/verdant_demo.sqlite3 ".tables"
sqlite3 db/verdant_demo.sqlite3 ".schema customers"
sqlite3 db/verdant_demo.sqlite3 "SELECT * FROM customer_portfolio LIMIT 10;"
```
