# Synthetic ERP Generator

## Design intent

The generator produces operational transaction history that is realistic enough to support the EOIP analytical questions without storing the final BI KPIs as source columns.

It follows the canonical source model defined in the central portfolio repository:

`data/eoip/domain-model.yaml`

## Reproducibility

Generation is controlled by:

- fixed random seed
- explicit YAML configuration
- canonical NordWerk company profile
- deterministic NumPy and Faker state

Two runs with the same inputs must produce the same dataset fingerprint.

## Scale

The committed default configuration uses a small scale factor so development and CI remain fast.

Full portfolio generation can increase the scale factor to `1.0`. Company counts such as customers, products, suppliers and warehouse locations are read from the canonical NordWerk profile rather than copied into this repository.

## Business patterns

The generator intentionally creates non-uniform behavior:

- concentrated customers
- concentrated products
- monthly seasonality
- modest annual growth
- heterogeneous discounts
- returns
- open order exposure
- slow-moving and excess stock
- low/negative available stock for a subset of items
- warehouse transfers

These patterns exist so EOIP can produce meaningful analytical findings rather than perfectly uniform demo data.

## Ledger model

Physical movements are written to `inventory_ledger_entry`.

Values are written to `value_entry`.

For sales:

- physical quantity is negative
- sales value is positive
- actual cost is positive

For returns:

- physical quantity is positive only when restocked
- sales value is negative
- actual cost reversal is negative

Transfers create equal and opposite quantity/value movements between warehouses.

## Output

Each entity is exported as CSV and a `validation.json` report is written beside the data.

Generated data itself should not be committed to Git because the dataset is reproducible.
