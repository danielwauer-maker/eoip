CREATE SCHEMA IF NOT EXISTS dw;

CREATE TABLE IF NOT EXISTS dw.dim_date (
    date_key INTEGER PRIMARY KEY,
    full_date DATE NOT NULL UNIQUE,
    calendar_year INTEGER NOT NULL,
    calendar_quarter INTEGER NOT NULL,
    calendar_month INTEGER NOT NULL,
    month_name TEXT NOT NULL,
    year_month TEXT NOT NULL,
    iso_week INTEGER NOT NULL,
    day_of_month INTEGER NOT NULL,
    iso_day_of_week INTEGER NOT NULL,
    day_name TEXT NOT NULL,
    is_weekend BOOLEAN NOT NULL
);

CREATE TABLE IF NOT EXISTS dw.dim_customer (
    customer_key BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    customer_id TEXT NOT NULL UNIQUE,
    customer_no TEXT NOT NULL UNIQUE,
    customer_name TEXT NOT NULL,
    customer_group TEXT NOT NULL,
    country_code TEXT NOT NULL,
    postal_region TEXT NOT NULL,
    payment_terms_code TEXT NOT NULL,
    blocked_flag BOOLEAN NOT NULL,
    created_date DATE NOT NULL
);

CREATE TABLE IF NOT EXISTS dw.dim_product (
    product_key BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    product_id TEXT NOT NULL UNIQUE,
    product_no TEXT NOT NULL UNIQUE,
    product_name TEXT NOT NULL,
    product_category_id TEXT NOT NULL,
    category_code TEXT NOT NULL,
    category_name TEXT NOT NULL,
    base_unit_of_measure TEXT NOT NULL,
    standard_sales_price NUMERIC(18,4) NOT NULL,
    standard_unit_cost NUMERIC(18,4) NOT NULL,
    preferred_supplier_id TEXT NOT NULL,
    replenishment_lead_time_days INTEGER NOT NULL,
    discontinued_flag BOOLEAN NOT NULL,
    created_date DATE NOT NULL
);

CREATE TABLE IF NOT EXISTS dw.dim_warehouse (
    warehouse_key BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    warehouse_id TEXT NOT NULL UNIQUE,
    warehouse_code TEXT NOT NULL UNIQUE,
    warehouse_name TEXT NOT NULL,
    region TEXT NOT NULL,
    active_flag BOOLEAN NOT NULL
);

CREATE TABLE IF NOT EXISTS dw.dim_salesperson (
    salesperson_key BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    salesperson_id TEXT NOT NULL UNIQUE,
    salesperson_code TEXT NOT NULL UNIQUE,
    display_name TEXT NOT NULL,
    sales_region TEXT NOT NULL,
    active_flag BOOLEAN NOT NULL
);

CREATE TABLE IF NOT EXISTS dw.fact_sales (
    sales_fact_key BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    date_key INTEGER NOT NULL REFERENCES dw.dim_date(date_key),
    customer_key BIGINT NOT NULL REFERENCES dw.dim_customer(customer_key),
    product_key BIGINT NOT NULL REFERENCES dw.dim_product(product_key),
    warehouse_key BIGINT NOT NULL REFERENCES dw.dim_warehouse(warehouse_key),
    salesperson_key BIGINT NOT NULL REFERENCES dw.dim_salesperson(salesperson_key),
    source_document_type TEXT NOT NULL,
    source_document_id TEXT NOT NULL,
    source_document_no TEXT NOT NULL,
    source_line_no INTEGER NOT NULL,
    quantity_signed NUMERIC(18,4) NOT NULL,
    gross_sales_signed NUMERIC(18,4) NOT NULL,
    discount_signed NUMERIC(18,4) NOT NULL,
    net_sales_signed NUMERIC(18,4) NOT NULL,
    cogs_signed NUMERIC(18,4) NOT NULL,
    UNIQUE (source_document_type, source_document_id, source_line_no)
);

CREATE TABLE IF NOT EXISTS dw.fact_sales_order (
    sales_order_fact_key BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    order_date_key INTEGER NOT NULL REFERENCES dw.dim_date(date_key),
    promised_delivery_date_key INTEGER NOT NULL REFERENCES dw.dim_date(date_key),
    customer_key BIGINT NOT NULL REFERENCES dw.dim_customer(customer_key),
    product_key BIGINT NOT NULL REFERENCES dw.dim_product(product_key),
    warehouse_key BIGINT NOT NULL REFERENCES dw.dim_warehouse(warehouse_key),
    salesperson_key BIGINT NOT NULL REFERENCES dw.dim_salesperson(salesperson_key),
    sales_order_id TEXT NOT NULL,
    order_no TEXT NOT NULL,
    sales_order_line_id TEXT NOT NULL UNIQUE,
    line_no INTEGER NOT NULL,
    order_status TEXT NOT NULL,
    line_status TEXT NOT NULL,
    ordered_quantity NUMERIC(18,4) NOT NULL,
    shipped_quantity NUMERIC(18,4) NOT NULL,
    invoiced_quantity NUMERIC(18,4) NOT NULL,
    outstanding_quantity NUMERIC(18,4) NOT NULL,
    net_order_amount NUMERIC(18,4) NOT NULL
);

CREATE TABLE IF NOT EXISTS dw.fact_inventory_movement (
    inventory_movement_fact_key BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    date_key INTEGER NOT NULL REFERENCES dw.dim_date(date_key),
    product_key BIGINT NOT NULL REFERENCES dw.dim_product(product_key),
    warehouse_key BIGINT NOT NULL REFERENCES dw.dim_warehouse(warehouse_key),
    inventory_ledger_entry_id TEXT NOT NULL UNIQUE,
    entry_no BIGINT NOT NULL,
    entry_type TEXT NOT NULL,
    document_type TEXT NOT NULL,
    document_no TEXT NOT NULL,
    document_line_no INTEGER NOT NULL,
    source_entity_type TEXT NOT NULL,
    source_entity_id TEXT NOT NULL,
    transfer_pair_id TEXT NULL,
    quantity_signed NUMERIC(18,4) NOT NULL,
    actual_cost_amount NUMERIC(18,4) NOT NULL,
    inventory_value_movement_signed NUMERIC(18,4) NOT NULL
);

CREATE TABLE IF NOT EXISTS dw.fact_inventory_snapshot (
    inventory_snapshot_fact_key BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    date_key INTEGER NOT NULL REFERENCES dw.dim_date(date_key),
    product_key BIGINT NOT NULL REFERENCES dw.dim_product(product_key),
    warehouse_key BIGINT NOT NULL REFERENCES dw.dim_warehouse(warehouse_key),
    on_hand_quantity NUMERIC(18,4) NOT NULL,
    reserved_quantity NUMERIC(18,4) NOT NULL,
    available_quantity NUMERIC(18,4) NOT NULL,
    unit_cost_at_snapshot NUMERIC(18,4) NOT NULL,
    inventory_value_standard_cost NUMERIC(18,4) NOT NULL,
    UNIQUE (date_key, product_key, warehouse_key)
);

CREATE INDEX IF NOT EXISTS ix_fact_sales_date_product
    ON dw.fact_sales(date_key, product_key);
CREATE INDEX IF NOT EXISTS ix_fact_sales_customer
    ON dw.fact_sales(customer_key);
CREATE INDEX IF NOT EXISTS ix_fact_sales_order_open
    ON dw.fact_sales_order(outstanding_quantity)
    WHERE outstanding_quantity > 0;
CREATE INDEX IF NOT EXISTS ix_fact_inventory_movement_product_date
    ON dw.fact_inventory_movement(product_key, date_key);
CREATE INDEX IF NOT EXISTS ix_fact_inventory_snapshot_product
    ON dw.fact_inventory_snapshot(product_key, date_key);
