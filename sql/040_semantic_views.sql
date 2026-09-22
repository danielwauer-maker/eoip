CREATE SCHEMA IF NOT EXISTS semantic;

CREATE OR REPLACE VIEW semantic.v_inventory_position AS
WITH snapshot AS (
    SELECT MAX(d.full_date) AS snapshot_date
    FROM dw.fact_inventory_snapshot s
    JOIN dw.dim_date d
      ON d.date_key = s.date_key
),
sales_activity AS (
    SELECT
        fs.product_key,
        fs.warehouse_key,
        SUM(
            CASE
                WHEN fs.source_document_type = 'invoice'
                 AND fs.quantity_signed > 0
                 AND d.full_date BETWEEN (s.snapshot_date - INTERVAL '89 days')::DATE
                                     AND s.snapshot_date
                    THEN fs.quantity_signed
                ELSE 0
            END
        ) AS trailing_90d_invoice_units,
        MAX(
            CASE
                WHEN fs.source_document_type = 'invoice'
                 AND fs.quantity_signed > 0
                 AND d.full_date <= s.snapshot_date
                    THEN d.full_date
                ELSE NULL
            END
        ) AS last_positive_sale_date
    FROM dw.fact_sales fs
    JOIN dw.dim_date d
      ON d.date_key = fs.date_key
    CROSS JOIN snapshot s
    GROUP BY fs.product_key, fs.warehouse_key
),
open_demand AS (
    SELECT
        product_key,
        warehouse_key,
        SUM(outstanding_quantity) AS open_order_quantity
    FROM dw.fact_sales_order
    WHERE outstanding_quantity > 0
    GROUP BY product_key, warehouse_key
),
position AS (
    SELECT
        d.full_date AS snapshot_date,
        s.product_key,
        s.warehouse_key,
        s.on_hand_quantity,
        s.reserved_quantity,
        s.available_quantity,
        s.unit_cost_at_snapshot,
        GREATEST(s.on_hand_quantity, 0) * s.unit_cost_at_snapshot
            AS positive_inventory_value,
        COALESCE(a.trailing_90d_invoice_units, 0) AS trailing_90d_invoice_units,
        COALESCE(a.trailing_90d_invoice_units, 0) / 90.0
            AS average_daily_units_90d,
        a.last_positive_sale_date,
        CASE
            WHEN a.last_positive_sale_date IS NULL THEN NULL
            ELSE d.full_date - a.last_positive_sale_date
        END AS days_since_last_positive_sale,
        COALESCE(o.open_order_quantity, 0) AS open_order_quantity
    FROM dw.fact_inventory_snapshot s
    JOIN dw.dim_date d
      ON d.date_key = s.date_key
    LEFT JOIN sales_activity a
      ON a.product_key = s.product_key
     AND a.warehouse_key = s.warehouse_key
    LEFT JOIN open_demand o
      ON o.product_key = s.product_key
     AND o.warehouse_key = s.warehouse_key
)
SELECT
    snapshot_date,
    product_key,
    warehouse_key,
    on_hand_quantity,
    reserved_quantity,
    available_quantity,
    unit_cost_at_snapshot,
    ROUND(positive_inventory_value, 4) AS positive_inventory_value,
    trailing_90d_invoice_units,
    average_daily_units_90d,
    last_positive_sale_date,
    days_since_last_positive_sale,
    open_order_quantity,
    CASE
        WHEN average_daily_units_90d > 0
            THEN on_hand_quantity / average_daily_units_90d
        ELSE NULL
    END AS stock_coverage_days,
    CASE
        WHEN last_positive_sale_date IS NULL
          OR last_positive_sale_date < (snapshot_date - INTERVAL '89 days')::DATE
            THEN TRUE
        ELSE FALSE
    END AS slow_moving_flag,
    average_daily_units_90d * 60.0 AS target_stock_quantity_60d,
    GREATEST(
        GREATEST(on_hand_quantity, 0) - (average_daily_units_90d * 60.0),
        0
    ) AS excess_quantity_60d,
    ROUND(
        GREATEST(
            GREATEST(on_hand_quantity, 0) - (average_daily_units_90d * 60.0),
            0
        ) * unit_cost_at_snapshot,
        4
    ) AS excess_inventory_value_60d,
    CASE
        WHEN open_order_quantity > 0
         AND open_order_quantity > GREATEST(available_quantity, 0)
            THEN TRUE
        ELSE FALSE
    END AS stockout_risk_flag
FROM position;

CREATE OR REPLACE VIEW semantic.v_kpi_reference AS
WITH sales_bounds AS (
    SELECT MAX(d.full_date) AS max_sales_date
    FROM dw.fact_sales fs
    JOIN dw.dim_date d
      ON d.date_key = fs.date_key
),
snapshot_bounds AS (
    SELECT MAX(snapshot_date) AS snapshot_date
    FROM semantic.v_inventory_position
),
sales_totals AS (
    SELECT
        COALESCE(SUM(net_sales_signed), 0) AS net_sales,
        COALESCE(SUM(gross_sales_signed), 0) AS gross_sales,
        COALESCE(SUM(discount_signed), 0) AS discount_value,
        COALESCE(SUM(cogs_signed), 0) AS cogs,
        COALESCE(SUM(quantity_signed), 0) AS net_units,
        COALESCE(SUM(
            CASE WHEN source_document_type = 'invoice' THEN net_sales_signed ELSE 0 END
        ), 0) AS invoice_sales,
        COALESCE(SUM(
            CASE WHEN source_document_type = 'credit_memo' THEN -net_sales_signed ELSE 0 END
        ), 0) AS return_value,
        COUNT(DISTINCT customer_key) AS active_customers
    FROM dw.fact_sales
),
order_totals AS (
    SELECT
        COUNT(DISTINCT sales_order_id) AS order_count,
        COALESCE(SUM(net_order_amount), 0) AS ordered_net_value
    FROM dw.fact_sales_order
),
growth AS (
    SELECT
        COALESCE(SUM(
            CASE
                WHEN d.full_date > (b.max_sales_date - INTERVAL '1 year')::DATE
                 AND d.full_date <= b.max_sales_date
                    THEN fs.net_sales_signed
                ELSE 0
            END
        ), 0) AS current_12m_sales,
        COALESCE(SUM(
            CASE
                WHEN d.full_date > (b.max_sales_date - INTERVAL '2 years')::DATE
                 AND d.full_date <= (b.max_sales_date - INTERVAL '1 year')::DATE
                    THEN fs.net_sales_signed
                ELSE 0
            END
        ), 0) AS previous_12m_sales
    FROM dw.fact_sales fs
    JOIN dw.dim_date d
      ON d.date_key = fs.date_key
    CROSS JOIN sales_bounds b
),
inventory_totals AS (
    SELECT
        COALESCE(SUM(positive_inventory_value), 0) AS inventory_value,
        COALESCE(
            SUM(on_hand_quantity)
            / NULLIF(SUM(average_daily_units_90d), 0),
            0
        ) AS stock_coverage_days,
        COALESCE(SUM(
            CASE WHEN slow_moving_flag THEN positive_inventory_value ELSE 0 END
        ), 0) AS slow_moving_inventory_value,
        COALESCE(SUM(excess_inventory_value_60d), 0) AS excess_inventory_value,
        COUNT(DISTINCT product_key) FILTER (WHERE stockout_risk_flag)
            AS stockout_risk_sku_count
    FROM semantic.v_inventory_position
),
trailing_cogs AS (
    SELECT
        COALESCE(SUM(fs.cogs_signed), 0) AS cogs_365d
    FROM dw.fact_sales fs
    JOIN dw.dim_date d
      ON d.date_key = fs.date_key
    CROSS JOIN snapshot_bounds b
    WHERE d.full_date BETWEEN (b.snapshot_date - INTERVAL '364 days')::DATE
                          AND b.snapshot_date
)
SELECT 'net_sales'::TEXT AS kpi_id,
       st.net_sales::NUMERIC AS numeric_value,
       'all_loaded_sales'::TEXT AS reference_scope
FROM sales_totals st
UNION ALL
SELECT 'sales_growth_pct',
       CASE
           WHEN g.previous_12m_sales = 0 THEN NULL
           ELSE ((g.current_12m_sales - g.previous_12m_sales)
                 / ABS(g.previous_12m_sales)) * 100
       END,
       'latest_12_months_vs_previous_12_months'
FROM growth g
UNION ALL
SELECT 'gross_profit',
       (st.net_sales - st.cogs),
       'all_loaded_sales'
FROM sales_totals st
UNION ALL
SELECT 'gross_margin_pct',
       CASE WHEN st.net_sales = 0 THEN NULL
            ELSE ((st.net_sales - st.cogs) / st.net_sales) * 100 END,
       'all_loaded_sales'
FROM sales_totals st
UNION ALL
SELECT 'order_count',
       ot.order_count::NUMERIC,
       'all_loaded_orders'
FROM order_totals ot
UNION ALL
SELECT 'average_order_value',
       CASE WHEN ot.order_count = 0 THEN NULL
            ELSE ot.ordered_net_value / ot.order_count END,
       'all_loaded_orders'
FROM order_totals ot
UNION ALL
SELECT 'active_customers',
       st.active_customers::NUMERIC,
       'all_loaded_sales'
FROM sales_totals st
UNION ALL
SELECT 'units_sold',
       st.net_units,
       'all_loaded_sales'
FROM sales_totals st
UNION ALL
SELECT 'discount_value',
       st.discount_value,
       'all_loaded_sales'
FROM sales_totals st
UNION ALL
SELECT 'discount_rate_pct',
       CASE WHEN st.gross_sales = 0 THEN NULL
            ELSE (st.discount_value / st.gross_sales) * 100 END,
       'all_loaded_sales'
FROM sales_totals st
UNION ALL
SELECT 'return_value',
       st.return_value,
       'all_loaded_sales'
FROM sales_totals st
UNION ALL
SELECT 'return_rate_pct',
       CASE WHEN st.invoice_sales = 0 THEN NULL
            ELSE (st.return_value / st.invoice_sales) * 100 END,
       'all_loaded_sales'
FROM sales_totals st
UNION ALL
SELECT 'inventory_value',
       it.inventory_value,
       'latest_inventory_snapshot'
FROM inventory_totals it
UNION ALL
SELECT 'inventory_turnover',
       CASE WHEN it.inventory_value = 0 THEN NULL
            ELSE tc.cogs_365d / it.inventory_value END,
       'trailing_365d_cogs_over_current_positive_inventory_value'
FROM inventory_totals it
CROSS JOIN trailing_cogs tc
UNION ALL
SELECT 'stock_coverage_days',
       it.stock_coverage_days,
       'current_on_hand_over_trailing_90d_average_daily_invoice_units'
FROM inventory_totals it
UNION ALL
SELECT 'slow_moving_inventory_value',
       it.slow_moving_inventory_value,
       'no_positive_invoice_units_in_trailing_90_days'
FROM inventory_totals it
UNION ALL
SELECT 'excess_inventory_value',
       it.excess_inventory_value,
       'inventory_above_60_days_of_trailing_90d_average_demand'
FROM inventory_totals it
UNION ALL
SELECT 'stockout_risk_sku_count',
       it.stockout_risk_sku_count::NUMERIC,
       'distinct_products_with_open_demand_above_available_quantity'
FROM inventory_totals it;
