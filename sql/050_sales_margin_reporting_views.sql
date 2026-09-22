CREATE OR REPLACE VIEW semantic.v_sales_margin_monthly_reference AS
WITH sales_month AS (
    SELECT
        DATE_TRUNC('month', d.full_date)::DATE AS month_start,
        TO_CHAR(DATE_TRUNC('month', d.full_date), 'YYYY-MM') AS year_month,
        SUM(fs.net_sales_signed) AS net_sales,
        SUM(fs.cogs_signed) AS cogs,
        SUM(fs.quantity_signed) AS units_sold,
        SUM(fs.gross_sales_signed) AS gross_sales,
        SUM(fs.discount_signed) AS discount_value,
        SUM(
            CASE
                WHEN fs.source_document_type = 'invoice'
                    THEN fs.net_sales_signed
                ELSE 0
            END
        ) AS invoice_sales,
        SUM(
            CASE
                WHEN fs.source_document_type = 'credit_memo'
                    THEN -fs.net_sales_signed
                ELSE 0
            END
        ) AS return_value,
        COUNT(DISTINCT fs.customer_key) FILTER (
            WHERE fs.net_sales_signed <> 0
        ) AS active_customers
    FROM dw.fact_sales fs
    JOIN dw.dim_date d
      ON d.date_key = fs.date_key
    GROUP BY 1, 2
),
order_month AS (
    SELECT
        DATE_TRUNC('month', d.full_date)::DATE AS month_start,
        COUNT(DISTINCT fo.sales_order_id) AS order_count,
        SUM(fo.net_order_amount) AS ordered_net_value
    FROM dw.fact_sales_order fo
    JOIN dw.dim_date d
      ON d.date_key = fo.order_date_key
    GROUP BY 1
)
SELECT
    s.month_start,
    s.year_month,
    s.net_sales,
    s.net_sales - s.cogs AS gross_profit,
    CASE
        WHEN s.net_sales = 0 THEN NULL
        ELSE ((s.net_sales - s.cogs) / s.net_sales) * 100
    END AS gross_margin_pct,
    s.units_sold,
    s.discount_value,
    CASE
        WHEN s.gross_sales = 0 THEN NULL
        ELSE (s.discount_value / s.gross_sales) * 100
    END AS discount_rate_pct,
    s.return_value,
    CASE
        WHEN s.invoice_sales = 0 THEN NULL
        ELSE (s.return_value / s.invoice_sales) * 100
    END AS return_rate_pct,
    s.active_customers,
    COALESCE(o.order_count, 0) AS order_count,
    CASE
        WHEN COALESCE(o.order_count, 0) = 0 THEN NULL
        ELSE o.ordered_net_value / o.order_count
    END AS average_order_value
FROM sales_month s
LEFT JOIN order_month o
  ON o.month_start = s.month_start
ORDER BY s.month_start;


CREATE OR REPLACE VIEW semantic.v_sales_margin_driver_reference AS
WITH customer_driver AS (
    SELECT
        'customer'::TEXT AS entity_type,
        c.customer_id::TEXT AS entity_key,
        c.customer_name::TEXT AS entity_label,
        c.customer_group::TEXT AS entity_group,
        SUM(fs.net_sales_signed) AS net_sales,
        SUM(fs.cogs_signed) AS cogs,
        SUM(fs.quantity_signed) AS units_sold,
        SUM(fs.gross_sales_signed) AS gross_sales,
        SUM(fs.discount_signed) AS discount_value,
        SUM(
            CASE
                WHEN fs.source_document_type = 'invoice'
                    THEN fs.net_sales_signed
                ELSE 0
            END
        ) AS invoice_sales,
        SUM(
            CASE
                WHEN fs.source_document_type = 'credit_memo'
                    THEN -fs.net_sales_signed
                ELSE 0
            END
        ) AS return_value
    FROM dw.fact_sales fs
    JOIN dw.dim_customer c
      ON c.customer_key = fs.customer_key
    GROUP BY c.customer_id, c.customer_name, c.customer_group
),
product_driver AS (
    SELECT
        'product'::TEXT AS entity_type,
        p.product_id::TEXT AS entity_key,
        p.product_name::TEXT AS entity_label,
        p.category_name::TEXT AS entity_group,
        SUM(fs.net_sales_signed) AS net_sales,
        SUM(fs.cogs_signed) AS cogs,
        SUM(fs.quantity_signed) AS units_sold,
        SUM(fs.gross_sales_signed) AS gross_sales,
        SUM(fs.discount_signed) AS discount_value,
        SUM(
            CASE
                WHEN fs.source_document_type = 'invoice'
                    THEN fs.net_sales_signed
                ELSE 0
            END
        ) AS invoice_sales,
        SUM(
            CASE
                WHEN fs.source_document_type = 'credit_memo'
                    THEN -fs.net_sales_signed
                ELSE 0
            END
        ) AS return_value
    FROM dw.fact_sales fs
    JOIN dw.dim_product p
      ON p.product_key = fs.product_key
    GROUP BY p.product_id, p.product_name, p.category_name
),
category_driver AS (
    SELECT
        'category'::TEXT AS entity_type,
        p.category_code::TEXT AS entity_key,
        p.category_name::TEXT AS entity_label,
        p.category_name::TEXT AS entity_group,
        SUM(fs.net_sales_signed) AS net_sales,
        SUM(fs.cogs_signed) AS cogs,
        SUM(fs.quantity_signed) AS units_sold,
        SUM(fs.gross_sales_signed) AS gross_sales,
        SUM(fs.discount_signed) AS discount_value,
        SUM(
            CASE
                WHEN fs.source_document_type = 'invoice'
                    THEN fs.net_sales_signed
                ELSE 0
            END
        ) AS invoice_sales,
        SUM(
            CASE
                WHEN fs.source_document_type = 'credit_memo'
                    THEN -fs.net_sales_signed
                ELSE 0
            END
        ) AS return_value
    FROM dw.fact_sales fs
    JOIN dw.dim_product p
      ON p.product_key = fs.product_key
    GROUP BY p.category_code, p.category_name
),
combined AS (
    SELECT * FROM customer_driver
    UNION ALL
    SELECT * FROM product_driver
    UNION ALL
    SELECT * FROM category_driver
),
metrics AS (
    SELECT
        entity_type,
        entity_key,
        entity_label,
        entity_group,
        net_sales,
        net_sales - cogs AS gross_profit,
        CASE
            WHEN net_sales = 0 THEN NULL
            ELSE ((net_sales - cogs) / net_sales) * 100
        END AS gross_margin_pct,
        units_sold,
        discount_value,
        CASE
            WHEN gross_sales = 0 THEN NULL
            ELSE (discount_value / gross_sales) * 100
        END AS discount_rate_pct,
        return_value,
        CASE
            WHEN invoice_sales = 0 THEN NULL
            ELSE (return_value / invoice_sales) * 100
        END AS return_rate_pct
    FROM combined
)
SELECT
    entity_type,
    entity_key,
    entity_label,
    entity_group,
    net_sales,
    gross_profit,
    gross_margin_pct,
    units_sold,
    discount_value,
    discount_rate_pct,
    return_value,
    return_rate_pct,
    DENSE_RANK() OVER (
        PARTITION BY entity_type
        ORDER BY net_sales DESC NULLS LAST
    ) AS net_sales_rank,
    DENSE_RANK() OVER (
        PARTITION BY entity_type
        ORDER BY gross_profit DESC NULLS LAST
    ) AS gross_profit_rank,
    DENSE_RANK() OVER (
        PARTITION BY entity_type
        ORDER BY discount_rate_pct DESC NULLS LAST
    ) AS discount_rate_rank,
    DENSE_RANK() OVER (
        PARTITION BY entity_type
        ORDER BY return_rate_pct DESC NULLS LAST
    ) AS return_rate_rank
FROM metrics;


CREATE OR REPLACE VIEW semantic.v_sales_margin_exception_reference AS
WITH overall AS (
    SELECT
        MAX(CASE WHEN kpi_id = 'gross_margin_pct' THEN numeric_value END)
            AS gross_margin_pct,
        MAX(CASE WHEN kpi_id = 'discount_rate_pct' THEN numeric_value END)
            AS discount_rate_pct,
        MAX(CASE WHEN kpi_id = 'return_rate_pct' THEN numeric_value END)
            AS return_rate_pct,
        MAX(CASE WHEN kpi_id = 'net_sales' THEN numeric_value END)
            AS total_net_sales
    FROM semantic.v_kpi_reference
),
scored AS (
    SELECT
        d.*,
        CASE
            WHEN d.gross_margin_pct < o.gross_margin_pct - 5.0 THEN TRUE
            ELSE FALSE
        END AS low_margin_flag,
        CASE
            WHEN d.discount_rate_pct > o.discount_rate_pct + 2.0 THEN TRUE
            ELSE FALSE
        END AS high_discount_flag,
        CASE
            WHEN d.return_rate_pct > o.return_rate_pct + 2.0 THEN TRUE
            ELSE FALSE
        END AS high_return_flag,
        CASE
            WHEN d.net_sales >= ABS(o.total_net_sales) * 0.005 THEN TRUE
            ELSE FALSE
        END AS material_sales_flag
    FROM semantic.v_sales_margin_driver_reference d
    CROSS JOIN overall o
    WHERE d.entity_type IN ('customer', 'product')
)
SELECT
    entity_type,
    entity_key,
    entity_label,
    entity_group,
    net_sales,
    gross_profit,
    gross_margin_pct,
    discount_value,
    discount_rate_pct,
    return_value,
    return_rate_pct,
    low_margin_flag,
    high_discount_flag,
    high_return_flag,
    material_sales_flag,
    (
        low_margin_flag::INTEGER
        + high_discount_flag::INTEGER
        + high_return_flag::INTEGER
    ) AS exception_count
FROM scored
WHERE material_sales_flag
  AND (
      low_margin_flag
      OR high_discount_flag
      OR high_return_flag
  );
