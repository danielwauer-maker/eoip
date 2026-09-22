# EOIP Pre-Render Visual QA

**Scope:** EOIP-07, EOIP-08, EOIP-09  
**Stage:** Before Power BI Desktop rendering  
**Result:** PASS WITH RESOLVED FINDINGS

## Objective

This QA checks whether the report contracts are visually and semantically ready to render in Power BI.

It is not the final visual QA. Final QA still requires the actual PBIR/PBIX render at 100% zoom.

## Resolved high-priority findings

### 1. Commercial period vs inventory snapshot ambiguity

**Finding:** Executive Overview combines Sales/Margin measures that follow a selected date range with Inventory measures that represent a point-in-time snapshot.

Without an explicit rule, a shared date slicer could make Inventory cards blank or imply that inventory value is historical for the selected sales period.

**Resolution:**

- Inventory DAX measures now explicitly remove the commercial `dim_date` filter.
- COGS TTM anchors itself to the latest inventory snapshot while removing the external commercial date filter.
- Executive Overview now requires the visible note:

> Sales/Margin = selected period · Inventory = latest snapshot

- Inventory pages must not expose the commercial date slicer.

**Why this matters:** This avoids mixing flow measures and stock measures without explaining their different time semantics.

### 2. Margin Attention table grain mismatch

**Finding:** The EOIP-08 report contract described Customer × Category rows, while the SQL validation reference contains entity-level customer or product exceptions.

**Resolution:**

- The visual is now **Customer Margin Attention**.
- Row grain is Customer.
- Validation explicitly filters the reference set to `entity_type = customer`.
- Table is limited to Top 12 and explicitly sorted by Net Sales.

**Why this matters:** The visual and the independent SQL validation now represent the same analytical grain.

## Resolved medium-priority findings

### 3. Top-N density

Customer and Product ranking bars on the Customer & Product page were Top 15.

At 16:9 portfolio presentation size this is unnecessarily dense.

**Resolution:** Both are now Top 10.

### 4. Inventory risk scatter grain

The Product Coverage vs Inventory Value scatter used Product as detail even though risk is Product × Warehouse.

**Resolution:** Warehouse is now used as the legend, so positions remain distinguishable across the four warehouse locations.

### 5. Cross-page date context

A sales date filter should not silently carry into the point-in-time Inventory pages.

**Resolution:** The design system explicitly preserves customer/product/warehouse context but does not preserve commercial date context to Inventory.

## Cross-page visual system

The canonical visual system is now `powerbi/visual-design-system.yaml`.

Key rules:

- 1440 × 810, 16:9
- consistent page header and compact filter bar
- KPI strip first
- driver visuals before detail tables
- Top-N bars generally limited to 10
- attention tables generally limited to 10–15 visible rows
- dual-axis commercial trends use currency on primary axis and percentages on secondary axis
- color never acts as the only signal
- Executive/detail navigation is consistent
- reset-filter control is mandatory
- Inventory pages visibly state the latest snapshot context

## Page-level QA

### EOIP-07 — Executive Overview

**Assessment:** Strong executive hierarchy.

The page moves from:

1. headline performance;
2. trend;
3. category portfolio position;
4. management attention.

The main semantic risk was mixed period/snapshot behavior and is now resolved.

### EOIP-08 — Sales Performance

**Assessment:** Good information density.

Six KPI cards are justified because the page separates value, growth, volume, order activity, average order size and customer breadth.

The monthly combo chart should use:

- Net Sales and Gross Profit on primary currency axis;
- Sales Growth % on secondary percentage axis;
- restrained labels.

### EOIP-08 — Margin & Discount Intelligence

**Assessment:** Strong analytical narrative.

The page progresses from gross profit/margin to leakage and then to an attention list.

Customer scatter should avoid labeling every point. Use labels on selection or only for the most material customers.

### EOIP-08 — Customer & Product Performance

**Assessment:** Most information-dense commercial page.

Top-N reduction to 10 improves readability.

Matrices should open at the top hierarchy level; users expand only when investigating.

### EOIP-09 — Inventory Overview

**Assessment:** Strong management screening page.

The Category Coverage vs Turnover scatter is useful because bubble size adds Inventory Value without introducing a composite score.

Inventory snapshot context must remain visible.

### EOIP-09 — Inventory Risk & Working Capital

**Assessment:** Appropriate detail depth.

Warehouse legend on the risk scatter preserves Product × Warehouse interpretation.

The Product × Warehouse detail table should be the final evidence layer rather than the visual focus.

## Final Power BI visual QA still required

After rendering in Power BI Desktop, verify:

- actual text clipping and font sizes;
- axis label density;
- legend behavior;
- conditional-formatting contrast;
- table row heights;
- scatter overplotting;
- slicer synchronization;
- navigation buttons;
- tooltip readability;
- 100% zoom readability;
- screenshot quality for the public portfolio.

EOIP-07/08/09 must remain `in_progress` until that final render QA is complete.
