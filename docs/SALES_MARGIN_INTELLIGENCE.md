# EOIP Sales & Margin Intelligence

**Work package:** EOIP-08  
**Report contract:** `powerbi/report-pages.yaml`  
**Governed KPI source:** `semantic/kpi-catalog.yaml`  
**DAX source:** `powerbi/measures.dax`

## Reporting scope

EOIP-08 implements the three commercial pages defined in the frozen EOIP V1 requirements:

1. **Sales Performance**
2. **Margin & Discount Intelligence**
3. **Customer & Product Performance**

Together with EOIP-07 Executive Overview and EOIP-09 Inventory Intelligence, these form the agreed five-page EOIP V1 report.

## Why the report definition is stored as data

The visual design is version controlled before final Power BI rendering.

`powerbi/report-pages.yaml` defines:

- business question per page;
- visual identity and type;
- canvas position;
- governed KPI IDs;
- dimension hierarchies;
- sorting and Top-N behavior;
- conditional-formatting intent;
- interaction rules;
- SQL validation references.

This prevents the analytical story from existing only inside a binary report file.

Power BI remains the target rendering environment. The repository does not fabricate a `.pbix` binary.

## Page 1 — Sales Performance

Primary purpose: explain sales direction and its commercial drivers.

Top KPI strip:

- Net Sales
- Sales Growth %
- Units Sold
- Order Count
- Average Order Value
- Active Customers

Driver visuals:

- monthly Net Sales / Gross Profit / Growth trend;
- Net Sales by Product Category;
- salesperson → customer group → customer matrix.

The page deliberately separates **posted sales** from **order-entry demand**. Net Sales uses posting date; Order Count and Average Order Value use order date.

## Page 2 — Margin & Discount Intelligence

Primary purpose: expose gross-margin quality and commercial leakage.

Top KPI strip:

- Gross Profit
- Gross Margin %
- Discount Value
- Discount Rate %
- Return Value
- Return Rate %

Driver visuals:

- customer Net Sales vs Gross Margin scatter;
- discount and return leakage by category;
- material margin attention list.

The attention list does not introduce a new KPI. It uses the existing governed metrics plus transparent exception rules in `semantic.v_sales_margin_exception_reference`.

Reference exception logic:

- Gross Margin more than 5 percentage points below portfolio context;
- Discount Rate more than 2 percentage points above context;
- Return Rate more than 2 percentage points above context;
- only commercially material rows at or above 0.5% of Net Sales enter the reference list.

These thresholds are report-screening rules, not financial impact claims.

## Page 3 — Customer & Product Performance

Primary purpose: compare commercial contribution across customer and product hierarchies.

Visuals:

- Top Customers by Net Sales;
- Top Products by Gross Profit;
- Category → Product matrix;
- Customer Group → Customer matrix;
- Product Sales vs Gross Margin scatter;
- Customer × Product detail table.

The page supports the management progression:

```text
Where is performance concentrated?
        ↓
Which customer/category/product drives it?
        ↓
Is the effect sales, margin, discount or returns?
        ↓
Which specific combinations require review?
```

## SQL reference layer

### semantic.v_sales_margin_monthly_reference

Provides month-level validation for:

- Net Sales
- Gross Profit
- Gross Margin %
- Units Sold
- Discount Value / Rate
- Return Value / Rate
- Active Customers
- Order Count
- Average Order Value

### semantic.v_sales_margin_driver_reference

Provides reference rankings at:

- customer
- product
- category

Metrics remain the governed EOIP KPI definitions.

### semantic.v_sales_margin_exception_reference

Provides a transparent static reference set for leakage/attention validation.

Power BI can remain dynamic through governed DAX measures; this SQL view exists to validate expected exception behavior independently of the report rendering.

## Interaction contract

Global slicers persist across all three EOIP-08 pages:

- Date
- Customer Group
- Product Category
- Warehouse
- Salesperson

Selections cross-filter compatible visuals.

Matrices use hierarchy expansion rather than separate duplicate pages.

No visual contains a hidden replacement KPI formula.

## Validation

Automated tests prove:

- all three required pages exist;
- every visual references governed KPI IDs only;
- visual IDs are unique;
- declared visual counts match reality;
- layout coordinates stay inside the 12-column grid;
- business questions and decision purpose are documented;
- MarginGuard concepts remain outside EOIP;
- monthly SQL values reconcile to governed KPI totals;
- category driver totals reconcile to governed KPIs;
- customer/product/category rankings are populated;
- exception rows satisfy their own materiality/flag contract.

## Rendering boundary

The repository now contains a complete Power-BI-ready analytical contract and validation layer.

Final PBIR/PBIX rendering should be created or opened in Power BI Desktop so that Microsoft-generated report metadata remains valid rather than hand-fabricating undocumented visual metadata.

Microsoft's PBIR format is source-control friendly and publicly documented, so a future Power BI Desktop save can be committed as reviewable report files instead of a binary-only artifact.
