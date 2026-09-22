# EOIP Inventory Intelligence

**Work package:** EOIP-09  
**Report contract:** `powerbi/inventory-intelligence.yaml`  
**Governed KPI source:** `semantic/kpi-catalog.yaml`

## Purpose

EOIP-09 creates the two inventory pages in the frozen EOIP V1 report:

1. **Inventory Overview**
2. **Inventory Risk & Working Capital**

The goal is management visibility and screening — not inventory optimization.

EOIP intentionally stops before ABC/XYZ segmentation, safety-stock recommendations, reorder points or forecasting. Those capabilities belong to InventoryIQ.

## Page 1 — Inventory Overview

The page answers:

- How much positive inventory value is currently held?
- How efficiently is current inventory supporting recent COGS?
- How many days of recent demand does current stock cover?
- Which categories and warehouses concentrate value and risk?

Headline KPIs:

- Inventory Value
- Inventory Turnover
- Stock Coverage Days
- Slow-Moving Inventory Value
- Excess Inventory Value
- Stockout-Risk SKU Count

Driver views:

- inventory value and excess by category;
- category Coverage vs Turnover scatter sized by Inventory Value;
- warehouse matrix for value, turnover, coverage and stockout risk.

## Page 2 — Inventory Risk & Working Capital

The second page shifts from portfolio position to management attention.

It focuses on:

- slow-moving value;
- excess value;
- stockout-risk products;
- high-value/high-coverage product positions;
- warehouse risk concentration;
- exact Product × Warehouse evidence.

The detail view exposes operational fields such as:

- available quantity;
- open order quantity;
- days since last positive sale;
- slow-moving flag;
- stockout-risk flag.

These fields support explanation but are not new KPI identities.

## Reporting reference layer

### semantic.v_inventory_reporting_position

One row per current Product × Warehouse position enriched with:

- product/category;
- warehouse;
- current quantity/value;
- trailing-90-day demand;
- stock coverage;
- slow-moving status;
- excess quantity/value;
- open demand;
- stockout risk;
- trailing-365-day COGS;
- position-level turnover;
- transparent risk-signal count.

### semantic.v_inventory_category_reference

Aggregates the inventory position to category while preserving the governed KPI logic.

### semantic.v_inventory_warehouse_reference

Provides the equivalent warehouse aggregation.

### semantic.v_inventory_risk_detail_reference

Provides the product/warehouse detail required to validate the risk page.

## KPI methodology

No methodology changes are introduced in EOIP-09.

The page reuses the EOIP-06 definitions:

- **Inventory Value** = positive on-hand × snapshot unit cost;
- **Inventory Turnover** = trailing 365-day net COGS / current positive inventory value;
- **Stock Coverage Days** = current on-hand / trailing-90-day average daily positive invoice units;
- **Slow-Moving** = no positive posted invoice units in trailing 90 days;
- **Excess** = stock above 60 days of trailing-90-day demand;
- **Stockout Risk** = open demand above non-negative available quantity.

## Important interpretation boundary

**Excess Inventory Value is not automatically a working-capital saving.**

It is a screening value that identifies stock above the EOIP V1 coverage policy.

Any later working-capital business case must document:

- target action;
- feasible reduction;
- constraints;
- assumptions;
- evidence class.

That belongs to EOIP-10 / InventoryIQ rather than this page.

## Validation

Automated tests should prove:

- both required inventory pages exist;
- only governed inventory KPIs are used;
- layouts stay inside the report grid;
- category additive values reconcile to governed KPI references;
- warehouse additive values reconcile to the same source population;
- global Turnover and Coverage can be recomputed from category numerator/denominator totals;
- risk-detail grain matches current Product × Warehouse positions;
- slow-moving, excess and stockout patterns exist in the generated validation dataset;
- risk-signal counts are internally consistent;
- no InventoryIQ optimization concepts are introduced.

## Rendering boundary

The complete analytical contract is Power-BI-ready.

Final PBIR/PBIX rendering and visual QA remain the Power BI Desktop step.
