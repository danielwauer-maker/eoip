CREATE OR REPLACE VIEW semantic.v_executive_category_reference AS
WITH sales_category AS (
    SELECT
        entity_key AS category_code,
        entity_label AS category_name,
        net_sales,
        gross_profit,
        gross_margin_pct,
        discount_rate_pct,
        return_rate_pct
    FROM semantic.v_sales_margin_driver_reference
    WHERE entity_type = 'category'
),
inventory_category AS (
    SELECT
        p.category_code,
        p.category_name,
        SUM(i.positive_inventory_value) AS inventory_value,
        SUM(
            CASE
                WHEN i.slow_moving_flag THEN i.positive_inventory_value
                ELSE 0
            END
        ) AS slow_moving_inventory_value,
        SUM(i.excess_inventory_value_60d) AS excess_inventory_value,
        COUNT(DISTINCT i.product_key) FILTER (
            WHERE i.stockout_risk_flag
        ) AS stockout_risk_sku_count
    FROM semantic.v_inventory_position i
    JOIN dw.dim_product p
      ON p.product_key = i.product_key
    GROUP BY p.category_code, p.category_name
)
SELECT
    COALESCE(s.category_code, i.category_code) AS category_code,
    COALESCE(s.category_name, i.category_name) AS category_name,
    COALESCE(s.net_sales, 0) AS net_sales,
    COALESCE(s.gross_profit, 0) AS gross_profit,
    s.gross_margin_pct,
    s.discount_rate_pct,
    s.return_rate_pct,
    COALESCE(i.inventory_value, 0) AS inventory_value,
    COALESCE(i.slow_moving_inventory_value, 0) AS slow_moving_inventory_value,
    COALESCE(i.excess_inventory_value, 0) AS excess_inventory_value,
    COALESCE(i.stockout_risk_sku_count, 0) AS stockout_risk_sku_count,
    CASE
        WHEN COALESCE(i.inventory_value, 0) = 0 THEN NULL
        ELSE COALESCE(i.excess_inventory_value, 0) / i.inventory_value
    END AS excess_inventory_share
FROM sales_category s
FULL OUTER JOIN inventory_category i
  ON i.category_code = s.category_code;


CREATE OR REPLACE VIEW semantic.v_executive_attention_reference AS
WITH overall AS (
    SELECT
        MAX(CASE WHEN kpi_id = 'net_sales' THEN numeric_value END) AS net_sales,
        MAX(CASE WHEN kpi_id = 'gross_margin_pct' THEN numeric_value END) AS gross_margin_pct,
        MAX(CASE WHEN kpi_id = 'inventory_value' THEN numeric_value END) AS inventory_value
    FROM semantic.v_kpi_reference
),
scored AS (
    SELECT
        c.*,
        CASE
            WHEN c.gross_margin_pct IS NOT NULL
             AND c.gross_margin_pct < o.gross_margin_pct - 5.0
                THEN TRUE
            ELSE FALSE
        END AS low_margin_flag,
        CASE
            WHEN c.inventory_value > 0
             AND COALESCE(c.excess_inventory_share, 0) >= 0.25
                THEN TRUE
            ELSE FALSE
        END AS excess_inventory_flag,
        CASE
            WHEN c.stockout_risk_sku_count > 0
                THEN TRUE
            ELSE FALSE
        END AS availability_risk_flag,
        CASE
            WHEN c.net_sales >= ABS(o.net_sales) * 0.02
              OR c.inventory_value >= ABS(o.inventory_value) * 0.02
                THEN TRUE
            ELSE FALSE
        END AS material_flag
    FROM semantic.v_executive_category_reference c
    CROSS JOIN overall o
)
SELECT
    category_code,
    category_name,
    net_sales,
    gross_profit,
    gross_margin_pct,
    inventory_value,
    slow_moving_inventory_value,
    excess_inventory_value,
    stockout_risk_sku_count,
    low_margin_flag,
    excess_inventory_flag,
    availability_risk_flag,
    material_flag,
    (
        low_margin_flag::INTEGER
        + excess_inventory_flag::INTEGER
        + availability_risk_flag::INTEGER
    ) AS attention_signal_count
FROM scored
WHERE material_flag
  AND (
      low_margin_flag
      OR excess_inventory_flag
      OR availability_risk_flag
  );


CREATE OR REPLACE VIEW semantic.v_executive_kpi_reference AS
SELECT
    kpi_id,
    numeric_value,
    reference_scope
FROM semantic.v_kpi_reference
WHERE kpi_id IN (
    'net_sales',
    'sales_growth_pct',
    'gross_profit',
    'gross_margin_pct',
    'inventory_value',
    'stockout_risk_sku_count',
    'active_customers',
    'excess_inventory_value',
    'slow_moving_inventory_value',
    'return_rate_pct',
    'discount_rate_pct'
);
