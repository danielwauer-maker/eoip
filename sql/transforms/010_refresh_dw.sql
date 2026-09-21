TRUNCATE TABLE
    dw.fact_sales,
    dw.fact_sales_order,
    dw.fact_inventory_movement,
    dw.fact_inventory_snapshot,
    dw.dim_customer,
    dw.dim_product,
    dw.dim_warehouse,
    dw.dim_salesperson,
    dw.dim_date
RESTART IDENTITY CASCADE;

WITH bounds AS (
    SELECT
        LEAST(
            (SELECT MIN(order_date) FROM raw.sales_order_header),
            (SELECT MIN(posting_date) FROM raw.sales_invoice_header),
            (SELECT MIN(posting_date) FROM raw.inventory_ledger_entry)
        ) AS min_date,
        GREATEST(
            (SELECT MAX(promised_delivery_date) FROM raw.sales_order_line),
            (SELECT MAX(posting_date) FROM raw.sales_credit_memo_header),
            (SELECT MAX(snapshot_date) FROM raw.inventory_balance),
            (SELECT MAX(posting_date) FROM raw.inventory_ledger_entry)
        ) AS max_date
),
dates AS (
    SELECT generate_series(min_date, max_date, INTERVAL '1 day')::DATE AS full_date
    FROM bounds
)
INSERT INTO dw.dim_date (
    date_key,
    full_date,
    calendar_year,
    calendar_quarter,
    calendar_month,
    month_name,
    year_month,
    iso_week,
    day_of_month,
    iso_day_of_week,
    day_name,
    is_weekend
)
SELECT
    TO_CHAR(full_date, 'YYYYMMDD')::INTEGER,
    full_date,
    EXTRACT(YEAR FROM full_date)::INTEGER,
    EXTRACT(QUARTER FROM full_date)::INTEGER,
    EXTRACT(MONTH FROM full_date)::INTEGER,
    TO_CHAR(full_date, 'FMMonth'),
    TO_CHAR(full_date, 'YYYY-MM'),
    EXTRACT(WEEK FROM full_date)::INTEGER,
    EXTRACT(DAY FROM full_date)::INTEGER,
    EXTRACT(ISODOW FROM full_date)::INTEGER,
    TO_CHAR(full_date, 'FMDay'),
    EXTRACT(ISODOW FROM full_date)::INTEGER IN (6, 7)
FROM dates
ORDER BY full_date;

INSERT INTO dw.dim_customer (
    customer_id,
    customer_no,
    customer_name,
    customer_group,
    country_code,
    postal_region,
    payment_terms_code,
    blocked_flag,
    created_date
)
SELECT
    customer_id,
    customer_no,
    customer_name,
    customer_group,
    country_code,
    postal_region,
    payment_terms_code,
    blocked_flag,
    created_date
FROM stg.customer
ORDER BY customer_id;

INSERT INTO dw.dim_product (
    product_id,
    product_no,
    product_name,
    product_category_id,
    category_code,
    category_name,
    base_unit_of_measure,
    standard_sales_price,
    standard_unit_cost,
    preferred_supplier_id,
    replenishment_lead_time_days,
    discontinued_flag,
    created_date
)
SELECT
    product_id,
    product_no,
    product_name,
    product_category_id,
    category_code,
    category_name,
    base_unit_of_measure,
    standard_sales_price,
    standard_unit_cost,
    preferred_supplier_id,
    replenishment_lead_time_days,
    discontinued_flag,
    created_date
FROM stg.product
ORDER BY product_id;

INSERT INTO dw.dim_warehouse (
    warehouse_id,
    warehouse_code,
    warehouse_name,
    region,
    active_flag
)
SELECT
    warehouse_id,
    warehouse_code,
    warehouse_name,
    region,
    active_flag
FROM raw.warehouse
ORDER BY warehouse_id;

INSERT INTO dw.dim_salesperson (
    salesperson_id,
    salesperson_code,
    display_name,
    sales_region,
    active_flag
)
SELECT
    salesperson_id,
    salesperson_code,
    display_name,
    sales_region,
    active_flag
FROM raw.salesperson
ORDER BY salesperson_id;

WITH value_by_document_line AS (
    SELECT
        CASE
            WHEN document_type = 'sales_invoice' THEN 'invoice'
            WHEN document_type = 'sales_credit_memo' THEN 'credit_memo'
        END AS sales_document_type,
        document_no,
        document_line_no,
        SUM(cost_amount_actual) AS cogs_signed
    FROM stg.value_movement
    WHERE document_type IN ('sales_invoice', 'sales_credit_memo')
    GROUP BY 1, document_no, document_line_no
)
INSERT INTO dw.fact_sales (
    date_key,
    customer_key,
    product_key,
    warehouse_key,
    salesperson_key,
    source_document_type,
    source_document_id,
    source_document_no,
    source_line_no,
    quantity_signed,
    gross_sales_signed,
    discount_signed,
    net_sales_signed,
    cogs_signed
)
SELECT
    dd.date_key,
    dc.customer_key,
    dp.product_key,
    dw.warehouse_key,
    ds.salesperson_key,
    s.document_type,
    s.document_id,
    s.document_no,
    s.line_no,
    s.quantity_signed,
    s.gross_sales_signed,
    s.discount_signed,
    s.net_sales_signed,
    COALESCE(v.cogs_signed, 0)
FROM stg.sales_document_line s
JOIN dw.dim_date dd
  ON dd.full_date = s.posting_date
JOIN dw.dim_customer dc
  ON dc.customer_id = s.customer_id
JOIN dw.dim_product dp
  ON dp.product_id = s.product_id
JOIN dw.dim_warehouse dw
  ON dw.warehouse_id = s.warehouse_id
JOIN dw.dim_salesperson ds
  ON ds.salesperson_id = s.salesperson_id
LEFT JOIN value_by_document_line v
  ON v.sales_document_type = s.document_type
 AND v.document_no = s.document_no
 AND v.document_line_no = s.line_no
ORDER BY s.posting_date, s.document_no, s.line_no;

INSERT INTO dw.fact_sales_order (
    order_date_key,
    promised_delivery_date_key,
    customer_key,
    product_key,
    warehouse_key,
    salesperson_key,
    sales_order_id,
    order_no,
    sales_order_line_id,
    line_no,
    order_status,
    line_status,
    ordered_quantity,
    shipped_quantity,
    invoiced_quantity,
    outstanding_quantity,
    net_order_amount
)
SELECT
    od.date_key,
    pd.date_key,
    dc.customer_key,
    dp.product_key,
    dw.warehouse_key,
    ds.salesperson_key,
    s.sales_order_id,
    s.order_no,
    s.sales_order_line_id,
    s.line_no,
    s.order_status,
    s.line_status,
    s.ordered_quantity,
    s.shipped_quantity,
    s.invoiced_quantity,
    s.outstanding_quantity,
    s.net_line_amount
FROM stg.sales_order_line s
JOIN dw.dim_date od
  ON od.full_date = s.order_date
JOIN dw.dim_date pd
  ON pd.full_date = s.promised_delivery_date
JOIN dw.dim_customer dc
  ON dc.customer_id = s.customer_id
JOIN dw.dim_product dp
  ON dp.product_id = s.product_id
JOIN dw.dim_warehouse dw
  ON dw.warehouse_id = s.warehouse_id
JOIN dw.dim_salesperson ds
  ON ds.salesperson_id = s.salesperson_id
ORDER BY s.order_date, s.order_no, s.line_no;

INSERT INTO dw.fact_inventory_movement (
    date_key,
    product_key,
    warehouse_key,
    inventory_ledger_entry_id,
    entry_no,
    entry_type,
    document_type,
    document_no,
    document_line_no,
    source_entity_type,
    source_entity_id,
    transfer_pair_id,
    quantity_signed,
    actual_cost_amount,
    inventory_value_movement_signed
)
SELECT
    dd.date_key,
    dp.product_key,
    dw.warehouse_key,
    m.inventory_ledger_entry_id,
    m.entry_no,
    m.entry_type,
    m.document_type,
    m.document_no,
    m.document_line_no,
    m.source_entity_type,
    m.source_entity_id,
    m.transfer_pair_id,
    m.quantity_signed,
    COALESCE(v.cost_amount_actual, 0),
    CASE
        WHEN m.entry_type IN ('purchase_receipt', 'positive_adjustment', 'transfer_in')
            THEN ABS(COALESCE(v.cost_amount_actual, 0))
        WHEN m.entry_type IN ('sale', 'negative_adjustment', 'transfer_out')
            THEN -ABS(COALESCE(v.cost_amount_actual, 0))
        WHEN m.entry_type = 'sales_return' AND m.quantity_signed > 0
            THEN ABS(COALESCE(v.cost_amount_actual, 0))
        ELSE 0
    END
FROM stg.inventory_movement m
JOIN dw.dim_date dd
  ON dd.full_date = m.posting_date
JOIN dw.dim_product dp
  ON dp.product_id = m.product_id
JOIN dw.dim_warehouse dw
  ON dw.warehouse_id = m.warehouse_id
LEFT JOIN stg.value_movement v
  ON v.inventory_ledger_entry_id = m.inventory_ledger_entry_id
ORDER BY m.entry_no;

INSERT INTO dw.fact_inventory_snapshot (
    date_key,
    product_key,
    warehouse_key,
    on_hand_quantity,
    reserved_quantity,
    available_quantity,
    unit_cost_at_snapshot,
    inventory_value_standard_cost
)
SELECT
    dd.date_key,
    dp.product_key,
    dw.warehouse_key,
    s.on_hand_quantity,
    s.reserved_quantity,
    s.available_quantity,
    dp.standard_unit_cost,
    ROUND(s.on_hand_quantity * dp.standard_unit_cost, 4)
FROM stg.inventory_balance s
JOIN dw.dim_date dd
  ON dd.full_date = s.snapshot_date
JOIN dw.dim_product dp
  ON dp.product_id = s.product_id
JOIN dw.dim_warehouse dw
  ON dw.warehouse_id = s.warehouse_id
ORDER BY s.product_id, s.warehouse_id;
