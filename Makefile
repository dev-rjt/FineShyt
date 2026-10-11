.PHONY: setup train database impacts test run verify

PYTHON := product_app/.venv/bin/python

setup:
	test -x product_app/.venv/bin/python || python3 -m venv product_app/.venv
	$(PYTHON) -m pip install --upgrade pip
	$(PYTHON) -m pip install -r requirements.txt -r product_app/requirements-app.txt -r requirements-rai.txt

# Retrain all models (seeded), then reshape outputs for the API and rebuild the database.
train:
	cd product_app && .venv/bin/python run_pipeline.py
	$(MAKE) impacts database

impacts:
	$(PYTHON) product_app/rebuild_impacts.py

database:
	$(PYTHON) db/build_demo_db.py

test:
	PYTHONPATH=product_app $(PYTHON) -m pytest product_app/tests -q
	PYTHONPATH=src:. $(PYTHON) -m pytest tests -q
	$(PYTHON) -m pytest integrations/engine_reference/tests -q
	PYTHONPATH=ml $(PYTHON) -m pytest ml/tests -q

verify: impacts database test

run:
	cd product_app && ./run_demo.sh
