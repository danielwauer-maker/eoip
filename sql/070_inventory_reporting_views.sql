CREATE OR REPLACE VIEW semantic.v_inventory_reporting_position AS
WITH snapshot AS (
    SELECT MAX(snapshot_date) AS snapshot_date
    FROM semantic.v_inventory_position
),
cogs_by_position AS (
    SELECT
        fs.product_key,
        fs.warehouse_key,
        SUM(fs.cogs_signed) AS trailing_365d_cogs
    FROM dw.fact_sales fs
    JOIN dw.dim_date d
      ON d.date_key = fs.date_key
    CROSS JOIN snapshot s
    WHERE d.full_date BETWEEN (s.snapshot_date - INTERVAL '364 days')::DATE
                          AND s.snapshot_date
    GROUP BY fs.product_key, fs.warehouse_key
)
SELECT
    i.snapshot_date,
    i.product_key,
    p.product_id,
    p.product_no,
    p.product_name,
    p.category_code,
    p.category_name,
    i.warehouse_key,
    w.warehouse_id,
    w.warehouse_code,
    w.warehouse_name,
    w.region AS warehouse_region,
    i.on_hand_quantity,
    i.reserved_quantity,
    i.available_quantity,
    i.unit_cost_at_snapshot,
    i.positive_inventory_value,
    i.trailing_90d_invoice_units,
    i.average_daily_units_90d,
    i.last_positive_sale_date,
    i.days_since_last_positive_sale,
    i.open_order_quantity,
    i.stock_coverage_days,
    i.slow_moving_flag,
    i.target_stock_quantity_60d,
    i.excess_quantity_60d,
    i.excess_inventory_value_60d,
    i.stockout_risk_flag,
    COALESCE(c.trailing_365d_cogs, 0) AS trailing_365d_cogs,
    CASE
        WHEN i.positive_inventory_value = 0 THEN NULL
        ELSE COALESCE(c.trailing_365d_cogs, 0) / i.positive_inventory_value
    END AS position_inventory_turnover,
    (
        i.slow_moving_flag::INTEGER
        + (i.excess_inventory_value_60d > 0)::INTEGER
        + i.stockout_risk_flag::INTEGER
    ) AS risk_signal_count
FROM semantic.v_inventory_position i
JOIN dw.dim_product p
  ON p.product_key = i.product_key
JOIN dw.dim_warehouse w
  ON w.warehouse_key = i.warehouse_key
LEFT JOIN cogs_by_position c
  ON c.product_key = i.product_key
 AND c.warehouse_key = i.warehouse_key;


CREATE OR REPLACE VIEW semantic.v_inventory_category_reference AS
SELECT
    category_code,
    category_name,
    SUM(positive_inventory_value) AS inventory_value,
    SUM(trailing_365d_cogs) AS trailing_365d_cogs,
    CASE
        WHEN SUM(positive_inventory_value) = 0 THEN NULL
        ELSE SUM(trailing_365d_cogs) / SUM(positive_inventory_value)
    END AS inventory_turnover,
    SUM(on_hand_quantity) AS on_hand_quantity,
    SUM(average_daily_units_90d) AS average_daily_units_90d,
    CASE
        WHEN SUM(average_daily_units_90d) = 0 THEN NULL
        ELSE SUM(on_hand_quantity) / SUM(average_daily_units_90d)
    END AS stock_coverage_days,
    SUM(
        CASE WHEN slow_moving_flag THEN positive_inventory_value ELSE 0 END
    ) AS slow_moving_inventory_value,
    SUM(excess_inventory_value_60d) AS excess_inventory_value,
    COUNT(DISTINCT product_key) FILTER (
        WHERE stockout_risk_flag
    ) AS stockout_risk_sku_count,
    COUNT(DISTINCT product_key) AS product_count,
    COUNT(*) FILTER (WHERE slow_moving_flag) AS slow_moving_position_count,
    COUNT(*) FILTER (WHERE excess_inventory_value_60d > 0) AS excess_position_count,
    COUNT(*) FILTER (WHERE stockout_risk_flag) AS stockout_risk_position_count
FROM semantic.v_inventory_reporting_position
GROUP BY category_code, category_name;


CREATE OR REPLACE VIEW semantic.v_inventory_warehouse_reference AS
SELECT
    warehouse_id,
    warehouse_code,
    warehouse_name,
    warehouse_region,
    SUM(positive_inventory_value) AS inventory_value,
    SUM(trailing_365d_cogs) AS trailing_365d_cogs,
    CASE
        WHEN SUM(positive_inventory_value) = 0 THEN NULL
        ELSE SUM(trailing_365d_cogs) / SUM(positive_inventory_value)
    END AS inventory_turnover,
    SUM(on_hand_quantity) AS on_hand_quantity,
    SUM(average_daily_units_90d) AS average_daily_units_90d,
    CASE
        WHEN SUM(average_daily_units_90d) = 0 THEN NULL
        ELSE SUM(on_hand_quantity) / SUM(average_daily_units_90d)
    END AS stock_coverage_days,
    SUM(
        CASE WHEN slow_moving_flag THEN positive_inventory_value ELSE 0 END
    ) AS slow_moving_inventory_value,
    SUM(excess_inventory_value_60d) AS excess_inventory_value,
    COUNT(DISTINCT product_key) FILTER (
        WHERE stockout_risk_flag
    ) AS stockout_risk_sku_count,
    COUNT(*) FILTER (WHERE stockout_risk_flag) AS stockout_risk_position_count
FROM semantic.v_inventory_reporting_position
GROUP BY warehouse_id, warehouse_code, warehouse_name, warehouse_region;


CREATE OR REPLACE VIEW semantic.v_inventory_risk_detail_reference AS
SELECT
    snapshot_date,
    product_key,
    product_id,
    product_no,
    product_name,
    category_code,
    category_name,
    warehouse_key,
    warehouse_id,
    warehouse_code,
    warehouse_name,
    on_hand_quantity,
    reserved_quantity,
    available_quantity,
    positive_inventory_value AS inventory_value,
    average_daily_units_90d,
    stock_coverage_days,
    days_since_last_positive_sale,
    open_order_quantity,
    slow_moving_flag,
    excess_quantity_60d,
    excess_inventory_value_60d AS excess_inventory_value,
    stockout_risk_flag,
    trailing_365d_cogs,
    position_inventory_turnover,
    risk_signal_count,
    CASE
        WHEN slow_moving_flag OR excess_inventory_value_60d > 0
            THEN TRUE
        ELSE FALSE
    END AS working_capital_attention_flag,
    CASE
        WHEN stockout_risk_flag THEN TRUE
        ELSE FALSE
    END AS availability_attention_flag
FROM semantic.v_inventory_reporting_position;
