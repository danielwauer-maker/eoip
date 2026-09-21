CREATE TABLE IF NOT EXISTS raw.salesperson (
    salesperson_id TEXT PRIMARY KEY,
    salesperson_code TEXT NOT NULL UNIQUE,
    display_name TEXT NOT NULL,
    sales_region TEXT NOT NULL,
    active_flag BOOLEAN NOT NULL
);

CREATE TABLE IF NOT EXISTS raw.supplier (
    supplier_id TEXT PRIMARY KEY,
    supplier_no TEXT NOT NULL UNIQUE,
    supplier_name TEXT NOT NULL,
    country_code TEXT NOT NULL,
    default_lead_time_days INTEGER NOT NULL,
    active_flag BOOLEAN NOT NULL
);

CREATE TABLE IF NOT EXISTS raw.product_category (
    product_category_id TEXT PRIMARY KEY,
    category_code TEXT NOT NULL UNIQUE,
    category_name TEXT NOT NULL,
    parent_category_id TEXT NULL
);

CREATE TABLE IF NOT EXISTS raw.warehouse (
    warehouse_id TEXT PRIMARY KEY,
    warehouse_code TEXT NOT NULL UNIQUE,
    warehouse_name TEXT NOT NULL,
    region TEXT NOT NULL,
    active_flag BOOLEAN NOT NULL
);

CREATE TABLE IF NOT EXISTS raw.customer (
    customer_id TEXT PRIMARY KEY,
    customer_no TEXT NOT NULL UNIQUE,
    customer_name TEXT NOT NULL,
    customer_group TEXT NOT NULL,
    country_code TEXT NOT NULL,
    postal_region TEXT NOT NULL,
    salesperson_id TEXT NOT NULL REFERENCES raw.salesperson(salesperson_id),
    payment_terms_code TEXT NOT NULL,
    blocked_flag BOOLEAN NOT NULL,
    created_date DATE NOT NULL
);

CREATE TABLE IF NOT EXISTS raw.product (
    product_id TEXT PRIMARY KEY,
    product_no TEXT NOT NULL UNIQUE,
    product_name TEXT NOT NULL,
    product_category_id TEXT NOT NULL REFERENCES raw.product_category(product_category_id),
    base_unit_of_measure TEXT NOT NULL,
    standard_sales_price NUMERIC(18,4) NOT NULL,
    standard_unit_cost NUMERIC(18,4) NOT NULL,
    preferred_supplier_id TEXT NOT NULL REFERENCES raw.supplier(supplier_id),
    replenishment_lead_time_days INTEGER NOT NULL,
    discontinued_flag BOOLEAN NOT NULL,
    created_date DATE NOT NULL
);

CREATE TABLE IF NOT EXISTS raw.sales_order_header (
    sales_order_id TEXT PRIMARY KEY,
    order_no TEXT NOT NULL UNIQUE,
    customer_id TEXT NOT NULL REFERENCES raw.customer(customer_id),
    order_date DATE NOT NULL,
    requested_delivery_date DATE NOT NULL,
    salesperson_id TEXT NOT NULL REFERENCES raw.salesperson(salesperson_id),
    currency_code TEXT NOT NULL,
    status TEXT NOT NULL,
    document_discount_amount NUMERIC(18,4) NOT NULL,
    created_at TIMESTAMP NOT NULL
);

CREATE TABLE IF NOT EXISTS raw.sales_order_line (
    sales_order_line_id TEXT PRIMARY KEY,
    sales_order_id TEXT NOT NULL REFERENCES raw.sales_order_header(sales_order_id),
    line_no INTEGER NOT NULL,
    product_id TEXT NOT NULL REFERENCES raw.product(product_id),
    warehouse_id TEXT NOT NULL REFERENCES raw.warehouse(warehouse_id),
    ordered_quantity NUMERIC(18,4) NOT NULL,
    shipped_quantity NUMERIC(18,4) NOT NULL,
    invoiced_quantity NUMERIC(18,4) NOT NULL,
    outstanding_quantity NUMERIC(18,4) NOT NULL,
    unit_price NUMERIC(18,4) NOT NULL,
    line_discount_pct NUMERIC(9,4) NOT NULL,
    line_discount_amount NUMERIC(18,4) NOT NULL,
    net_line_amount NUMERIC(18,4) NOT NULL,
    promised_delivery_date DATE NOT NULL,
    line_status TEXT NOT NULL,
    UNIQUE (sales_order_id, line_no)
);

CREATE TABLE IF NOT EXISTS raw.sales_invoice_header (
    sales_invoice_id TEXT PRIMARY KEY,
    invoice_no TEXT NOT NULL UNIQUE,
    customer_id TEXT NOT NULL REFERENCES raw.customer(customer_id),
    invoice_date DATE NOT NULL,
    posting_date DATE NOT NULL,
    salesperson_id TEXT NOT NULL REFERENCES raw.salesperson(salesperson_id),
    currency_code TEXT NOT NULL,
    source_order_no TEXT NOT NULL,
    document_discount_amount NUMERIC(18,4) NOT NULL,
    total_net_amount NUMERIC(18,4) NOT NULL,
    total_tax_amount NUMERIC(18,4) NOT NULL
);

CREATE TABLE IF NOT EXISTS raw.sales_invoice_line (
    sales_invoice_line_id TEXT PRIMARY KEY,
    sales_invoice_id TEXT NOT NULL REFERENCES raw.sales_invoice_header(sales_invoice_id),
    line_no INTEGER NOT NULL,
    source_order_no TEXT NOT NULL,
    source_order_line_no INTEGER NOT NULL,
    product_id TEXT NOT NULL REFERENCES raw.product(product_id),
    warehouse_id TEXT NOT NULL REFERENCES raw.warehouse(warehouse_id),
    quantity NUMERIC(18,4) NOT NULL,
    unit_price NUMERIC(18,4) NOT NULL,
    gross_line_amount NUMERIC(18,4) NOT NULL,
    discount_amount NUMERIC(18,4) NOT NULL,
    net_line_amount NUMERIC(18,4) NOT NULL,
    UNIQUE (sales_invoice_id, line_no)
);

CREATE TABLE IF NOT EXISTS raw.sales_credit_memo_header (
    sales_credit_memo_id TEXT PRIMARY KEY,
    credit_memo_no TEXT NOT NULL UNIQUE,
    customer_id TEXT NOT NULL REFERENCES raw.customer(customer_id),
    posting_date DATE NOT NULL,
    original_invoice_no TEXT NOT NULL,
    reason_code TEXT NOT NULL,
    total_net_amount NUMERIC(18,4) NOT NULL
);

CREATE TABLE IF NOT EXISTS raw.sales_credit_memo_line (
    sales_credit_memo_line_id TEXT PRIMARY KEY,
    sales_credit_memo_id TEXT NOT NULL REFERENCES raw.sales_credit_memo_header(sales_credit_memo_id),
    line_no INTEGER NOT NULL,
    original_invoice_no TEXT NOT NULL,
    original_invoice_line_no INTEGER NOT NULL,
    product_id TEXT NOT NULL REFERENCES raw.product(product_id),
    warehouse_id TEXT NOT NULL REFERENCES raw.warehouse(warehouse_id),
    return_quantity NUMERIC(18,4) NOT NULL,
    unit_price NUMERIC(18,4) NOT NULL,
    discount_amount NUMERIC(18,4) NOT NULL,
    net_credit_amount NUMERIC(18,4) NOT NULL,
    disposition TEXT NOT NULL,
    UNIQUE (sales_credit_memo_id, line_no)
);

CREATE TABLE IF NOT EXISTS raw.purchase_receipt_header (
    purchase_receipt_id TEXT PRIMARY KEY,
    receipt_no TEXT NOT NULL UNIQUE,
    supplier_id TEXT NOT NULL REFERENCES raw.supplier(supplier_id),
    warehouse_id TEXT NOT NULL REFERENCES raw.warehouse(warehouse_id),
    posting_date DATE NOT NULL,
    supplier_document_no TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS raw.purchase_receipt_line (
    purchase_receipt_line_id TEXT PRIMARY KEY,
    purchase_receipt_id TEXT NOT NULL REFERENCES raw.purchase_receipt_header(purchase_receipt_id),
    line_no INTEGER NOT NULL,
    product_id TEXT NOT NULL REFERENCES raw.product(product_id),
    quantity NUMERIC(18,4) NOT NULL,
    unit_cost NUMERIC(18,4) NOT NULL,
    UNIQUE (purchase_receipt_id, line_no)
);

CREATE TABLE IF NOT EXISTS raw.warehouse_transfer_header (
    transfer_id TEXT PRIMARY KEY,
    transfer_no TEXT NOT NULL UNIQUE,
    from_warehouse_id TEXT NOT NULL REFERENCES raw.warehouse(warehouse_id),
    to_warehouse_id TEXT NOT NULL REFERENCES raw.warehouse(warehouse_id),
    posting_date DATE NOT NULL,
    status TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS raw.warehouse_transfer_line (
    transfer_line_id TEXT PRIMARY KEY,
    transfer_id TEXT NOT NULL REFERENCES raw.warehouse_transfer_header(transfer_id),
    line_no INTEGER NOT NULL,
    product_id TEXT NOT NULL REFERENCES raw.product(product_id),
    quantity NUMERIC(18,4) NOT NULL,
    UNIQUE (transfer_id, line_no)
);

CREATE TABLE IF NOT EXISTS raw.inventory_ledger_entry (
    inventory_ledger_entry_id TEXT PRIMARY KEY,
    entry_no BIGINT NOT NULL UNIQUE,
    product_id TEXT NOT NULL REFERENCES raw.product(product_id),
    warehouse_id TEXT NOT NULL REFERENCES raw.warehouse(warehouse_id),
    posting_date DATE NOT NULL,
    entry_type TEXT NOT NULL,
    quantity NUMERIC(18,4) NOT NULL,
    remaining_quantity NUMERIC(18,4) NOT NULL,
    document_type TEXT NOT NULL,
    document_no TEXT NOT NULL,
    document_line_no INTEGER NOT NULL,
    source_entity_type TEXT NOT NULL,
    source_entity_id TEXT NOT NULL,
    transfer_pair_id TEXT NULL
);

CREATE TABLE IF NOT EXISTS raw.value_entry (
    value_entry_id TEXT PRIMARY KEY,
    value_entry_no BIGINT NOT NULL UNIQUE,
    inventory_ledger_entry_id TEXT NOT NULL REFERENCES raw.inventory_ledger_entry(inventory_ledger_entry_id),
    posting_date DATE NOT NULL,
    entry_type TEXT NOT NULL,
    cost_amount_actual NUMERIC(18,4) NOT NULL,
    sales_amount_actual NUMERIC(18,4) NOT NULL,
    discount_amount NUMERIC(18,4) NOT NULL,
    document_type TEXT NOT NULL,
    document_no TEXT NOT NULL,
    document_line_no INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS raw.inventory_balance (
    inventory_balance_id TEXT PRIMARY KEY,
    product_id TEXT NOT NULL REFERENCES raw.product(product_id),
    warehouse_id TEXT NOT NULL REFERENCES raw.warehouse(warehouse_id),
    snapshot_date DATE NOT NULL,
    on_hand_quantity NUMERIC(18,4) NOT NULL,
    reserved_quantity NUMERIC(18,4) NOT NULL,
    available_quantity NUMERIC(18,4) NOT NULL,
    UNIQUE (product_id, warehouse_id)
);

CREATE INDEX IF NOT EXISTS ix_raw_invoice_line_product
    ON raw.sales_invoice_line(product_id);
CREATE INDEX IF NOT EXISTS ix_raw_invoice_header_posting_date
    ON raw.sales_invoice_header(posting_date);
CREATE INDEX IF NOT EXISTS ix_raw_ledger_product_warehouse_date
    ON raw.inventory_ledger_entry(product_id, warehouse_id, posting_date);
CREATE INDEX IF NOT EXISTS ix_raw_value_document
    ON raw.value_entry(document_type, document_no, document_line_no);
