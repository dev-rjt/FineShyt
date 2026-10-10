-- Verdant demo database schema (SQLite 3).
-- Synthetic hackathon data only. Foreign keys are enforced by the builder.

PRAGMA foreign_keys = ON;

CREATE TABLE schema_metadata (
    schema_version TEXT PRIMARY KEY,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    dataset_name TEXT NOT NULL,
    customer_count INTEGER NOT NULL CHECK (customer_count >= 0)
);

CREATE TABLE customers (
    customer_id TEXT PRIMARY KEY,
    age INTEGER NOT NULL CHECK (age BETWEEN 18 AND 120),
    income_band TEXT NOT NULL,
    postcode TEXT NOT NULL,
    home_owner INTEGER NOT NULL CHECK (home_owner IN (0, 1)),
    digital_usage REAL NOT NULL CHECK (digital_usage BETWEEN 0 AND 1),
    sustainability_preference REAL NOT NULL CHECK (sustainability_preference BETWEEN 0 AND 1),
    region TEXT NOT NULL
);

CREATE TABLE green_products (
    product_id TEXT PRIMARY KEY,
    product_name TEXT NOT NULL UNIQUE,
    category TEXT NOT NULL,
    eligibility TEXT NOT NULL,
    sustainability_metric TEXT NOT NULL
);

CREATE TABLE customer_products (
    customer_product_id INTEGER PRIMARY KEY AUTOINCREMENT,
    customer_id TEXT NOT NULL REFERENCES customers(customer_id) ON DELETE CASCADE,
    product TEXT NOT NULL,
    start_date TEXT NOT NULL,
    balance REAL NOT NULL,
    status TEXT NOT NULL,
    UNIQUE (customer_id, product, start_date)
);

CREATE TABLE bank_transactions (
    transaction_id TEXT PRIMARY KEY,
    customer_id TEXT NOT NULL REFERENCES customers(customer_id) ON DELETE CASCADE,
    transaction_date TEXT NOT NULL,
    merchant_description TEXT NOT NULL,
    amount REAL NOT NULL CHECK (amount >= 0),
    debit_credit TEXT NOT NULL CHECK (debit_credit IN ('debit', 'credit'))
);

CREATE TABLE vehicles (
    customer_id TEXT PRIMARY KEY REFERENCES customers(customer_id) ON DELETE CASCADE,
    vehicle_type TEXT NOT NULL,
    fuel_type TEXT NOT NULL,
    vehicle_age REAL NOT NULL CHECK (vehicle_age >= 0),
    annual_mileage REAL CHECK (annual_mileage >= 0)
);

CREATE TABLE energy_usage (
    customer_id TEXT NOT NULL REFERENCES customers(customer_id) ON DELETE CASCADE,
    month TEXT NOT NULL,
    electricity_kwh REAL CHECK (electricity_kwh >= 0),
    gas_kwh REAL CHECK (gas_kwh >= 0),
    PRIMARY KEY (customer_id, month)
);

CREATE TABLE digital_usage (
    customer_id TEXT NOT NULL REFERENCES customers(customer_id) ON DELETE CASCADE,
    month TEXT NOT NULL,
    digital_statements INTEGER NOT NULL CHECK (digital_statements >= 0),
    paper_statements INTEGER NOT NULL CHECK (paper_statements >= 0),
    digital_transactions INTEGER NOT NULL CHECK (digital_transactions >= 0),
    branch_visits INTEGER NOT NULL CHECK (branch_visits >= 0),
    PRIMARY KEY (customer_id, month)
);

CREATE TABLE emission_factors (
    activity TEXT PRIMARY KEY,
    unit TEXT NOT NULL,
    kg_co2e_per_unit REAL NOT NULL CHECK (kg_co2e_per_unit >= 0),
    source TEXT NOT NULL,
    factor_id TEXT NOT NULL UNIQUE,
    source_year INTEGER,
    factor_version TEXT NOT NULL
);

CREATE TABLE model_assumptions (
    assumption_id TEXT PRIMARY KEY,
    low REAL NOT NULL,
    central REAL NOT NULL,
    high REAL NOT NULL,
    unit TEXT NOT NULL,
    source TEXT NOT NULL,
    version TEXT NOT NULL,
    CHECK (low <= central AND central <= high)
);

-- One model-ready feature snapshot per customer. This is separated from source
-- tables so that feature lineage and model inputs remain inspectable.
CREATE TABLE customer_features (
    customer_id TEXT PRIMARY KEY REFERENCES customers(customer_id) ON DELETE CASCADE,
    age INTEGER NOT NULL,
    income_idx INTEGER NOT NULL,
    home_owner INTEGER NOT NULL,
    digital_usage REAL NOT NULL,
    sustainability_preference REAL NOT NULL,
    urban REAL NOT NULL,
    region TEXT NOT NULL,
    has_vehicle INTEGER NOT NULL,
    fuel_type_code REAL,
    vehicle_type_code REAL,
    vehicle_age REAL,
    annual_mileage REAL,
    has_vehicle_loan INTEGER NOT NULL,
    has_mortgage INTEGER NOT NULL,
    has_isa INTEGER NOT NULL,
    has_savings INTEGER NOT NULL,
    has_credit_card INTEGER NOT NULL,
    has_personal_loan INTEGER NOT NULL,
    holds_GP01 INTEGER NOT NULL,
    holds_GP02 INTEGER NOT NULL,
    holds_GP03 INTEGER NOT NULL,
    holds_GP04 INTEGER NOT NULL,
    total_balance REAL NOT NULL,
    n_products REAL NOT NULL,
    elec_kwh_yr REAL,
    gas_kwh_yr REAL,
    heating_kwh_yr REAL,
    winter_gas_share REAL,
    paper_stmts_yr INTEGER,
    paper_share REAL,
    digital_tx_m REAL,
    branch_visits_m REAL,
    digital_tx_trend REAL,
    spend_fuel_m REAL,
    spend_electricity_m REAL,
    spend_gas_m REAL,
    spend_public_transport_m REAL,
    spend_home_improvement_m REAL,
    spend_automotive_m REAL,
    spend_utilities_m REAL,
    spend_other_m REAL,
    fuel_spend_m REAL,
    home_impr_spend_m REAL,
    total_spend_m REAL,
    fuel_share_of_spend REAL,
    n_fuel_txn REAL,
    inflow_m REAL,
    fuel_spend_trend REAL,
    txn_cat_mean_conf REAL,
    data_timestamp TEXT NOT NULL
);

CREATE TABLE recommendations (
    customer_id TEXT NOT NULL REFERENCES customers(customer_id) ON DELETE CASCADE,
    opportunity TEXT NOT NULL,
    product_id TEXT NOT NULL REFERENCES green_products(product_id),
    propensity REAL CHECK (propensity BETWEEN 0 AND 1),
    confidence REAL CHECK (confidence BETWEEN 0 AND 1),
    recommend INTEGER NOT NULL CHECK (recommend IN (0, 1)),
    reason_codes TEXT,
    data_timestamp TEXT NOT NULL,
    split TEXT NOT NULL CHECK (split IN ('train', 'val', 'test')),
    impact_status TEXT NOT NULL,
    est_avoided_kg_co2e_yr REAL,
    impact_json TEXT NOT NULL,
    PRIMARY KEY (customer_id, opportunity)
);

CREATE INDEX idx_transactions_customer_date ON bank_transactions(customer_id, transaction_date);
CREATE INDEX idx_products_customer ON customer_products(customer_id);
CREATE INDEX idx_energy_month ON energy_usage(month);
CREATE INDEX idx_digital_month ON digital_usage(month);
CREATE INDEX idx_recommendations_priority ON recommendations(recommend, opportunity, propensity DESC);

CREATE VIEW customer_portfolio AS
SELECT
    c.customer_id,
    c.region,
    c.income_band,
    COUNT(CASE WHEN r.recommend = 1 THEN 1 END) AS relevant_opportunities,
    MAX(CASE WHEN r.recommend = 1 THEN r.propensity END) AS highest_interest_signal,
    COALESCE(SUM(CASE WHEN r.recommend = 1 THEN r.est_avoided_kg_co2e_yr ELSE 0 END), 0) AS potential_kg_co2e_per_year
FROM customers AS c
LEFT JOIN recommendations AS r ON r.customer_id = c.customer_id
GROUP BY c.customer_id, c.region, c.income_band;
