CREATE OR REPLACE VIEW stg.customer AS
SELECT
    customer_id,
    customer_no,
    customer_name,
    customer_group,
    country_code,
    postal_region,
    salesperson_id,
    payment_terms_code,
    blocked_flag,
    created_date
FROM raw.customer;

CREATE OR REPLACE VIEW stg.product AS
SELECT
    p.product_id,
    p.product_no,
    p.product_name,
    p.product_category_id,
    pc.category_code,
    pc.category_name,
    p.base_unit_of_measure,
    p.standard_sales_price,
    p.standard_unit_cost,
    p.preferred_supplier_id,
    p.replenishment_lead_time_days,
    p.discontinued_flag,
    p.created_date
FROM raw.product p
JOIN raw.product_category pc
  ON pc.product_category_id = p.product_category_id;

CREATE OR REPLACE VIEW stg.sales_order_line AS
SELECT
    h.sales_order_id,
    h.order_no,
    h.customer_id,
    h.salesperson_id,
    h.order_date,
    h.requested_delivery_date,
    h.status AS order_status,
    l.sales_order_line_id,
    l.line_no,
    l.product_id,
    l.warehouse_id,
    l.ordered_quantity,
    l.shipped_quantity,
    l.invoiced_quantity,
    l.outstanding_quantity,
    l.unit_price,
    l.line_discount_pct,
    l.line_discount_amount,
    l.net_line_amount,
    l.promised_delivery_date,
    l.line_status
FROM raw.sales_order_header h
JOIN raw.sales_order_line l
  ON l.sales_order_id = h.sales_order_id;

CREATE OR REPLACE VIEW stg.sales_document_line AS
SELECT
    'invoice'::TEXT AS document_type,
    h.sales_invoice_id AS document_id,
    h.invoice_no AS document_no,
    h.posting_date,
    h.customer_id,
    h.salesperson_id,
    l.line_no,
    l.product_id,
    l.warehouse_id,
    l.quantity AS quantity_signed,
    l.gross_line_amount AS gross_sales_signed,
    l.discount_amount AS discount_signed,
    l.net_line_amount AS net_sales_signed,
    l.source_order_no,
    l.source_order_line_no
FROM raw.sales_invoice_header h
JOIN raw.sales_invoice_line l
  ON l.sales_invoice_id = h.sales_invoice_id

UNION ALL

SELECT
    'credit_memo'::TEXT AS document_type,
    h.sales_credit_memo_id AS document_id,
    h.credit_memo_no AS document_no,
    h.posting_date,
    h.customer_id,
    orig.salesperson_id,
    l.line_no,
    l.product_id,
    l.warehouse_id,
    -l.return_quantity AS quantity_signed,
    -(l.net_credit_amount + l.discount_amount) AS gross_sales_signed,
    -l.discount_amount AS discount_signed,
    -l.net_credit_amount AS net_sales_signed,
    l.original_invoice_no AS source_order_no,
    l.original_invoice_line_no AS source_order_line_no
FROM raw.sales_credit_memo_header h
JOIN raw.sales_credit_memo_line l
  ON l.sales_credit_memo_id = h.sales_credit_memo_id
LEFT JOIN raw.sales_invoice_header orig
  ON orig.invoice_no = l.original_invoice_no;

CREATE OR REPLACE VIEW stg.inventory_movement AS
SELECT
    inventory_ledger_entry_id,
    entry_no,
    product_id,
    warehouse_id,
    posting_date,
    entry_type,
    quantity AS quantity_signed,
    remaining_quantity,
    document_type,
    document_no,
    document_line_no,
    source_entity_type,
    source_entity_id,
    transfer_pair_id
FROM raw.inventory_ledger_entry;

CREATE OR REPLACE VIEW stg.value_movement AS
SELECT
    ve.value_entry_id,
    ve.value_entry_no,
    ve.inventory_ledger_entry_id,
    ile.product_id,
    ile.warehouse_id,
    ve.posting_date,
    ve.entry_type,
    ve.cost_amount_actual,
    ve.sales_amount_actual,
    ve.discount_amount,
    ve.document_type,
    ve.document_no,
    ve.document_line_no
FROM raw.value_entry ve
JOIN raw.inventory_ledger_entry ile
  ON ile.inventory_ledger_entry_id = ve.inventory_ledger_entry_id;

CREATE OR REPLACE VIEW stg.inventory_balance AS
SELECT
    inventory_balance_id,
    product_id,
    warehouse_id,
    snapshot_date,
    on_hand_quantity,
    reserved_quantity,
    available_quantity
FROM raw.inventory_balance;

CREATE OR REPLACE VIEW stg.purchase_receipt_line AS
SELECT
    h.purchase_receipt_id,
    h.receipt_no,
    h.supplier_id,
    h.warehouse_id,
    h.posting_date,
    l.purchase_receipt_line_id,
    l.line_no,
    l.product_id,
    l.quantity,
    l.unit_cost
FROM raw.purchase_receipt_header h
JOIN raw.purchase_receipt_line l
  ON l.purchase_receipt_id = h.purchase_receipt_id;

CREATE OR REPLACE VIEW stg.warehouse_transfer_line AS
SELECT
    h.transfer_id,
    h.transfer_no,
    h.from_warehouse_id,
    h.to_warehouse_id,
    h.posting_date,
    l.transfer_line_id,
    l.line_no,
    l.product_id,
    l.quantity
FROM raw.warehouse_transfer_header h
JOIN raw.warehouse_transfer_line l
  ON l.transfer_id = h.transfer_id;
