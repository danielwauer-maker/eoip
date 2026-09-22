# EOIP Executive Overview

**Work package:** EOIP-07  
**Page contract:** `powerbi/executive-overview.yaml`  
**Governed KPI source:** `semantic/kpi-catalog.yaml`

## Purpose

The Executive Overview is the top-level management page of EOIP V1.

It answers three questions before the user drills anywhere else:

1. **What is happening?**
2. **Where is it happening?**
3. **Which area deserves management attention next?**

The page deliberately combines commercial performance, gross-margin quality and inventory exposure without introducing a separate executive-only KPI layer.

## KPI strip

The six headline KPIs are:

- Net Sales
- Sales Growth %
- Gross Profit
- Gross Margin %
- Inventory Value
- Stockout-Risk SKU Count

These represent:

```text
Commercial scale
+ direction
+ profit contribution
+ margin quality
+ working capital
+ availability exposure
```

## Driver layer

### Sales, Gross Profit & Growth Trend

Reuses the EOIP-08 monthly reference layer and governed DAX measures.

The visual allows management to distinguish:

- sales growth with matching gross-profit growth;
- sales growth with deteriorating margin quality;
- declining sales and profit;
- short-term volatility versus sustained movement.

### Category Sales vs Gross Margin

Each category is positioned by:

- X = Net Sales
- Y = Gross Margin %
- Bubble Size = Inventory Value

This intentionally combines commercial importance with current working-capital exposure.

No composite score is created.

### Management Attention

The SQL reference view uses transparent screening flags:

- Gross Margin % more than 5 percentage points below overall context;
- Excess Inventory >= 25% of current category inventory value;
- at least one Stockout-Risk SKU;
- category must represent at least 2% of Net Sales or 2% of Inventory Value.

These rules are **screening logic**, not KPI definitions and not quantified business-impact claims.

## Navigation

The Executive page is the report entry point and links to:

- Sales Performance
- Margin & Discount Intelligence
- Customer & Product Performance
- Inventory Overview
- Inventory Risk & Working Capital

Filter context should be preserved where Power BI supports it.

## SQL validation

### semantic.v_executive_kpi_reference

Provides the governed Executive KPI subset from `semantic.v_kpi_reference`.

### semantic.v_executive_category_reference

Combines category-level sales/margin values with category-level inventory exposure.

### semantic.v_executive_attention_reference

Provides an independently testable reference list for management-attention behavior.

## Scope boundary

The Executive Overview does not introduce:

- contribution margin;
- cost-to-serve;
- safety-stock recommendations;
- reorder recommendations;
- autonomous recommendations;
- realized savings claims.

Those belong to later specialized projects or EOIP-10 traceable business-impact cases.

## Rendering boundary

The analytical contract is Power-BI-ready.

Final PBIR/PBIX rendering and visual QA remain the Power BI Desktop step so Microsoft-generated report metadata is preserved rather than fabricated.
