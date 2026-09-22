# EOIP KPI Dictionary & DAX Foundation v1.0

**Work package:** EOIP-06  
**Canonical KPI definitions:** `semantic/kpi-catalog.yaml`  
**DAX implementation:** `powerbi/measures.dax`  
**SQL reference layer:** `semantic.v_kpi_reference`

## Purpose

EOIP-06 creates one governed analytical language between SQL, Power BI and the business.

The 18 KPI identities were frozen before implementation. This work package does **not** add new KPIs. It defines exactly how each agreed KPI behaves.

The semantic chain is:

```text
ERP source
  → raw
  → staging
  → dimensional warehouse
  → semantic helper views
  → governed KPI definitions
  → DAX measures
  → Power BI pages
```

## Design rules

1. KPI logic is centralized rather than rewritten inside individual visuals.
2. Additive base measures are separated from ratios.
3. Credit memos stay negative in the sales fact.
4. Return KPIs convert negative credit values into positive presentation magnitude.
5. Gross Profit is always Net Sales minus actual COGS.
6. Gross Margin % is recalculated in filter context and is never summed.
7. Inventory V1 rules are explicit screening policies, not optimization recommendations.
8. SQL reference calculations exist so future Power BI results can be reconciled independently from DAX.

## KPI dictionary

| KPI | Business definition | Core formula |
| --- | --- | --- |
| Net Sales | Posted invoice sales net of discounts and credits/returns | Sum signed net sales |
| Sales Growth % | Change in Net Sales versus same period prior year | (Sales − Sales PY) / abs(Sales PY) |
| Gross Profit | Commercial gross profit before downstream cost-to-serve | Net Sales − COGS |
| Gross Margin % | Gross Profit relative to Net Sales | Gross Profit / Net Sales |
| Order Count | Distinct sales orders in order-date context | Distinct sales_order_id |
| Average Order Value | Average ordered net value | Ordered Net Value / Order Count |
| Active Customers | Customers with posted sales activity | Distinct customer_key |
| Units Sold | Net units after returns | Sum signed quantity |
| Discount Value | Net granted discount after credit reversals | Sum signed discount |
| Discount Rate % | Discount intensity against pre-discount sales | Discount / Gross Sales |
| Return Value | Positive magnitude of credit-memo Net Sales | − Credit Memo Sales |
| Return Rate % | Return value relative to positive invoice sales | Return Value / Invoice Sales |
| Inventory Value | Current positive inventory asset value | Positive On Hand × Snapshot Unit Cost |
| Inventory Turnover | Recent COGS throughput against current inventory | TTM COGS / Current Inventory Value |
| Stock Coverage Days | Current stock relative to recent daily demand | On Hand / 90d Avg Daily Units |
| Slow-Moving Inventory Value | Inventory without positive invoice movement for 90 days | Sum flagged inventory value |
| Excess Inventory Value | Inventory above 60 days of recent demand | Excess Qty × Snapshot Unit Cost |
| Stockout-Risk SKU Count | Products where open demand exceeds available stock | Distinct flagged products |

## Time semantics

### Sales Growth %

Power BI uses the selected date context and compares it with the same period one year earlier through `DATEADD`.

The SQL reference value uses the latest loaded 12-month period versus the preceding 12-month period. This is a **validation scope**, not a replacement for dynamic DAX behavior.

### Order metrics

Order Count and Average Order Value use **order date**, not invoice posting date.

That separates demand creation from realized posted sales.

### Inventory snapshot

Inventory KPIs are evaluated against the latest available inventory snapshot.

EOIP V1 currently materializes one current inventory snapshot. Time-series inventory optimization is intentionally deferred to InventoryIQ.

## Inventory V1 policy

The inventory rules are deliberately transparent and modest.

### Inventory Value

Only positive on-hand quantity contributes to inventory asset value.

Negative inventory remains visible in availability risk but does not create a negative working-capital asset.

### Inventory Turnover

EOIP V1 uses:

```text
Trailing 365-day net COGS
÷ Current positive Inventory Value
```

This is documented as a current-balance turnover proxy because EOIP V1 does not materialize historical average inventory values.

### Stock Coverage Days

Demand baseline:

```text
Positive posted invoice units in trailing 90 days
÷ 90
```

Coverage:

```text
Current on-hand quantity
÷ Average daily units
```

No-demand positions return BLANK for coverage and are handled separately through Slow-Moving Inventory Value.

### Slow-Moving Inventory

A product/warehouse position is slow-moving when it has had no positive posted invoice quantity in the trailing 90 days.

### Excess Inventory

EOIP V1 uses a simple management-screening threshold of **60 coverage days**:

```text
Target quantity
= trailing 90d average daily units × 60

Excess quantity
= max(positive on hand − target quantity, 0)

Excess value
= excess quantity × snapshot unit cost
```

This is not a safety-stock recommendation.

### Stockout Risk

A product/warehouse position is at risk when:

```text
open order quantity > max(available quantity, 0)
```

The KPI counts distinct products with at least one flagged warehouse.

## Power BI model additions

The existing dimensions and facts remain unchanged.

Import the PostgreSQL view:

`semantic.v_inventory_position`

as Power BI table:

`inventory_position`

Recommended relationships:

- `inventory_position.product_key → dim_product.product_key`
- `inventory_position.warehouse_key → dim_warehouse.warehouse_key`
- `inventory_position.snapshot_date → dim_date.full_date`

The helper table is a semantic convenience layer. It does not replace the governed dimensional warehouse.

## Validation strategy

`semantic.v_kpi_reference` returns one SQL reference value for every governed KPI ID.

The automated test suite verifies:

- exactly 18 KPI definitions;
- unique KPI IDs and DAX measure names;
- required metadata fields;
- exactly 18 SQL reference rows;
- identical catalog and SQL KPI ID sets;
- non-negative inventory screening values;
- stockout-risk patterns exist in generated test data;
- Power BI DAX file contains every governed KPI measure.

This makes later Power BI validation possible without using the report itself as the calculation authority.

## Scope boundary

EOIP-06 deliberately does not introduce:

- ABC/XYZ segmentation;
- safety-stock calculation;
- reorder-point optimization;
- advanced demand forecasting;
- cost-to-serve;
- contribution margin;
- supplier performance;
- purchase-price variance.

Those remain owned by InventoryIQ, MarginGuard and ProcureGuard.
