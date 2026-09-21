# EOIP — Enterprise Operational Intelligence Platform

EOIP is the flagship enterprise analytics project in the **Enterprise Data & AI Portfolio 2027**.

This repository contains the technical implementation. Portfolio governance, roadmap, business-impact rules and the canonical NordWerk company profile remain in the central portfolio repository:

- `danielwauer-maker/enterprise-data-ai-portfolio`

## Current delivery phase

**EOIP-03 — Reproducible Synthetic ERP Data Generation**

The generator creates operational ERP-style source data rather than BI-ready facts.

It produces:

- customer
- product_category
- product
- warehouse
- salesperson
- supplier
- sales_order_header
- sales_order_line
- sales_invoice_header
- sales_invoice_line
- sales_credit_memo_header
- sales_credit_memo_line
- purchase_receipt_header
- purchase_receipt_line
- warehouse_transfer_header
- warehouse_transfer_line
- inventory_ledger_entry
- value_entry
- inventory_balance

## Source-of-truth boundary

Important NordWerk business-scale values are **not duplicated manually here**.

The generator receives the canonical profile file from the portfolio repository:

```text
enterprise-data-ai-portfolio/data/companies/nordwerk.yaml
```

EOIP owns generator behavior such as random seed, history period, distributions and technical output configuration.

## Local setup

```bash
python -m venv .venv
source .venv/bin/activate
# Windows PowerShell: .venv\Scripts\Activate.ps1

pip install -e ".[dev]"
```

## Generate a dataset

Assuming the two repositories are checked out next to each other:

```bash
eoip generate \
  --company-profile ../enterprise-data-ai-portfolio/data/companies/nordwerk.yaml \
  --config config/generator.yaml \
  --output data/generated
```

For a fast local smoke run:

```bash
eoip generate \
  --company-profile ../enterprise-data-ai-portfolio/data/companies/nordwerk.yaml \
  --config config/generator.yaml \
  --output data/generated-smoke \
  --scale-factor 0.002
```

## Validation

Every generation writes `validation.json`.

The validation layer checks:

- required 19 source entities
- unique primary keys
- mandatory foreign keys
- invoice header/line reconciliation
- returns against original invoices
- warehouse transfer reconciliation
- inventory ledger to inventory balance reconciliation
- deterministic dataset fingerprint

Run tests with:

```bash
pytest
```

## Architecture principle

EOIP intentionally separates:

```text
ERP-style source data
    ↓
Raw / staging
    ↓
Dimensional model
    ↓
KPIs / DAX
    ↓
Power BI
    ↓
Business decisions
    ↓
Traceable impact
```

The current generator implements only the first layer.
