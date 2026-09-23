# EOIP Power BI Rendering Runbook

**Scope:** EOIP-07, EOIP-08, EOIP-09
**Purpose:** Reproducible final rendering of the governed EOIP analytical model in Power BI Desktop.

## 1. Prerequisites

- Docker Desktop
- Python 3.12+
- Power BI Desktop
- both repositories checked out next to each other:
  - `enterprise-data-ai-portfolio`
  - `eoip`

## 2. Prepare the local EOIP environment

From the `eoip` repository:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
```

Start PostgreSQL 16:

```powershell
docker compose up -d postgres
```

Local connection:

```text
Server: localhost
Port: 5432
Database: eoip
User: eoip
Password: eoip_local
```

Connection URL:

```text
postgresql://eoip:eoip_local@localhost:5432/eoip
```

## 3. Generate the reproducible source dataset

```powershell
eoip generate `
  --company-profile ..\enterprise-data-ai-portfolio\data\companies\nordwerk.yaml `
  --config config\generator.yaml `
  --output data\generated
```

Expected outcome:

- 19 ERP-style source entities
- `validation.json`
- deterministic output from the configured seed
- no BI-ready KPI facts generated artificially

## 4. Load PostgreSQL and build the warehouse

```powershell
eoip load-db `
  --database-url postgresql://eoip:eoip_local@localhost:5432/eoip `
  --input data\generated

eoip build-dw `
  --database-url postgresql://eoip:eoip_local@localhost:5432/eoip
```

Expected validation:

- database validation passes
- dimensional-model validation passes
- SQL migrations `001` through `070` apply cleanly

## 5. Power BI connection

In Power BI Desktop:

1. Get data
2. Select PostgreSQL database
3. Server: `localhost:5432`
4. Database: `eoip`
5. Data connectivity mode: **Import**
6. Authentication:
   - User: `eoip`
   - Password: `eoip_local`

Import mode is preferred for EOIP V1 because the local dataset is deterministic and analytical rather than operationally real-time.

## 6. Minimum analytical model to import

### Dimensions

- `dw.dim_date`
- `dw.dim_customer`
- `dw.dim_product`
- `dw.dim_warehouse`
- `dw.dim_salesperson`

### Facts

- `dw.fact_sales`
- `dw.fact_sales_order`

### Semantic helper

- `semantic.v_inventory_position`

Optional for investigation but not required by the governed report pages:

- `dw.fact_inventory_movement`
- `dw.fact_inventory_snapshot`

The SQL reporting reference views under `semantic.v_*_reference` exist primarily for independent validation. They should not replace the governed star-schema/DAX calculation path in the production report.

## 7. Relationships

Use one-to-many, single-direction relationships from dimensions to facts.

### fact_sales

- `dim_date.date_key → fact_sales.date_key`
- `dim_customer.customer_key → fact_sales.customer_key`
- `dim_product.product_key → fact_sales.product_key`
- `dim_warehouse.warehouse_key → fact_sales.warehouse_key`
- `dim_salesperson.salesperson_key → fact_sales.salesperson_key`

### fact_sales_order

- `dim_date.date_key → fact_sales_order.order_date_key`
- `dim_customer.customer_key → fact_sales_order.customer_key`
- `dim_product.product_key → fact_sales_order.product_key`
- `dim_warehouse.warehouse_key → fact_sales_order.warehouse_key`
- `dim_salesperson.salesperson_key → fact_sales_order.salesperson_key`

### inventory_position

- `dim_product.product_key → inventory_position.product_key`
- `dim_warehouse.warehouse_key → inventory_position.warehouse_key`

Do not use the commercial date slicer as a normal filter on inventory measures. EOIP inventory KPIs represent the latest snapshot.

## 8. Date model

Mark `dim_date` as the Power BI date table using `dim_date.full_date`.

Commercial measures use the selected reporting period.

Inventory measures use latest-snapshot semantics and explicitly ignore the external commercial date context where required.

Visible mixed-context note on Executive Overview:

> Sales/Margin = selected period · Inventory = latest snapshot

## 9. Measures

Canonical DAX source: `powerbi/measures.dax`

Create a dedicated Power BI measure table, for example `_Measures`.

Do not recreate formulas independently inside report visuals.

The frozen EOIP V1 KPI identity set contains exactly 18 governed KPIs.

## 10. Visual system

Canonical source: `powerbi/visual-design-system.yaml`

Key rules:

- 16:9 canvas
- 1440 × 810 design reference
- consistent page header
- compact filter bar
- KPI strip first
- driver visuals before evidence/detail tables
- restrained enterprise color semantics
- reset-filter control
- detail pages provide navigation back to Executive Overview
- readable at 100% zoom

## 11. Rendering order

1. Executive Overview
2. Sales Performance
3. Margin & Discount Intelligence
4. Customer & Product Performance
5. Inventory Overview
6. Inventory Risk & Working Capital

## 12. Page contracts

- Executive Overview: `powerbi/executive-overview.yaml`
- Sales & Margin pages: `powerbi/report-pages.yaml`
- Inventory pages: `powerbi/inventory-intelligence.yaml`

## 13. First-page rendering sequence — Executive Overview

### Header

- Title: Executive Overview
- Context note: Sales/Margin = selected period · Inventory = latest snapshot

### Filter bar

- Date
- Customer Group
- Product Category
- Warehouse
- Salesperson

### KPI strip

- Net Sales
- Sales Growth %
- Gross Profit
- Gross Margin %
- Inventory Value
- Stockout-Risk SKU Count

### Analytical body

- Sales / Gross Profit / Sales Growth trend
- Category Sales vs Gross Margin scatter
- Management Attention table

### Navigation

Buttons to the Sales/Margin and Inventory detail pages.

## 14. Final visual QA

Canonical checklist: `docs/PRE_RENDER_VISUAL_QA.md`

At 100% zoom verify:

- text clipping
- font size
- axis density
- legend density
- data-label noise
- conditional-formatting contrast
- scatter overplotting
- table row heights
- slicer synchronization
- page navigation
- tooltip readability
- snapshot/period context
- accessibility
- screenshot quality

## 15. Completion rule

EOIP-07, EOIP-08 and EOIP-09 remain `in_progress` until:

- all pages are rendered in Power BI Desktop;
- the report is saved as source-controlled Power BI project/report artifacts where supported;
- final visual QA passes;
- portfolio screenshots/demo evidence exist.

Only then may the three work packages earn their combined 9 weighted completion points.
