from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from .generator import ENTITY_ORDER


PRIMARY_KEYS = {
    "customer": "customer_id",
    "product_category": "product_category_id",
    "product": "product_id",
    "warehouse": "warehouse_id",
    "salesperson": "salesperson_id",
    "supplier": "supplier_id",
    "sales_order_header": "sales_order_id",
    "sales_order_line": "sales_order_line_id",
    "sales_invoice_header": "sales_invoice_id",
    "sales_invoice_line": "sales_invoice_line_id",
    "sales_credit_memo_header": "sales_credit_memo_id",
    "sales_credit_memo_line": "sales_credit_memo_line_id",
    "purchase_receipt_header": "purchase_receipt_id",
    "purchase_receipt_line": "purchase_receipt_line_id",
    "warehouse_transfer_header": "transfer_id",
    "warehouse_transfer_line": "transfer_line_id",
    "inventory_ledger_entry": "inventory_ledger_entry_id",
    "value_entry": "value_entry_id",
    "inventory_balance": "inventory_balance_id",
}


FOREIGN_KEYS = [
    ("customer", "salesperson_id", "salesperson", "salesperson_id"),
    ("product", "product_category_id", "product_category", "product_category_id"),
    ("product", "preferred_supplier_id", "supplier", "supplier_id"),
    ("sales_order_header", "customer_id", "customer", "customer_id"),
    ("sales_order_header", "salesperson_id", "salesperson", "salesperson_id"),
    ("sales_order_line", "sales_order_id", "sales_order_header", "sales_order_id"),
    ("sales_order_line", "product_id", "product", "product_id"),
    ("sales_order_line", "warehouse_id", "warehouse", "warehouse_id"),
    ("sales_invoice_header", "customer_id", "customer", "customer_id"),
    ("sales_invoice_header", "salesperson_id", "salesperson", "salesperson_id"),
    ("sales_invoice_line", "sales_invoice_id", "sales_invoice_header", "sales_invoice_id"),
    ("sales_invoice_line", "product_id", "product", "product_id"),
    ("sales_invoice_line", "warehouse_id", "warehouse", "warehouse_id"),
    ("sales_credit_memo_header", "customer_id", "customer", "customer_id"),
    ("sales_credit_memo_line", "sales_credit_memo_id", "sales_credit_memo_header", "sales_credit_memo_id"),
    ("sales_credit_memo_line", "product_id", "product", "product_id"),
    ("sales_credit_memo_line", "warehouse_id", "warehouse", "warehouse_id"),
    ("purchase_receipt_header", "supplier_id", "supplier", "supplier_id"),
    ("purchase_receipt_header", "warehouse_id", "warehouse", "warehouse_id"),
    ("purchase_receipt_line", "purchase_receipt_id", "purchase_receipt_header", "purchase_receipt_id"),
    ("purchase_receipt_line", "product_id", "product", "product_id"),
    ("warehouse_transfer_header", "from_warehouse_id", "warehouse", "warehouse_id"),
    ("warehouse_transfer_header", "to_warehouse_id", "warehouse", "warehouse_id"),
    ("warehouse_transfer_line", "transfer_id", "warehouse_transfer_header", "transfer_id"),
    ("warehouse_transfer_line", "product_id", "product", "product_id"),
    ("inventory_ledger_entry", "product_id", "product", "product_id"),
    ("inventory_ledger_entry", "warehouse_id", "warehouse", "warehouse_id"),
    ("value_entry", "inventory_ledger_entry_id", "inventory_ledger_entry", "inventory_ledger_entry_id"),
    ("inventory_balance", "product_id", "product", "product_id"),
    ("inventory_balance", "warehouse_id", "warehouse", "warehouse_id"),
]


def _check(name: str, passed: bool, details: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "name": name,
        "passed": bool(passed),
        "details": details or {},
    }


def validate_dataset(dataset: dict[str, pd.DataFrame]) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []

    missing_entities = [name for name in ENTITY_ORDER if name not in dataset]
    checks.append(
        _check(
            "required_entities",
            not missing_entities,
            {"missing": missing_entities, "expected_count": len(ENTITY_ORDER)},
        )
    )
    if missing_entities:
        return _result(checks)

    for entity, key in PRIMARY_KEYS.items():
        frame = dataset[entity]
        missing_column = key not in frame.columns
        if missing_column:
            checks.append(_check(f"pk:{entity}", False, {"missing_column": key}))
            continue
        duplicate_count = int(frame[key].duplicated().sum())
        null_count = int(frame[key].isna().sum())
        checks.append(
            _check(
                f"pk:{entity}",
                duplicate_count == 0 and null_count == 0,
                {
                    "key": key,
                    "rows": int(len(frame)),
                    "duplicates": duplicate_count,
                    "nulls": null_count,
                },
            )
        )

    for child, child_key, parent, parent_key in FOREIGN_KEYS:
        child_frame = dataset[child]
        parent_frame = dataset[parent]
        if child_key not in child_frame.columns or parent_key not in parent_frame.columns:
            checks.append(
                _check(
                    f"fk:{child}.{child_key}->{parent}.{parent_key}",
                    False,
                    {"reason": "missing_column"},
                )
            )
            continue

        values = child_frame[child_key].dropna()
        valid = set(parent_frame[parent_key].dropna().tolist())
        invalid = values[~values.isin(valid)]
        checks.append(
            _check(
                f"fk:{child}.{child_key}->{parent}.{parent_key}",
                invalid.empty,
                {"invalid_count": int(len(invalid))},
            )
        )

    invoice_header = dataset["sales_invoice_header"]
    invoice_line = dataset["sales_invoice_line"]
    if not invoice_header.empty and not invoice_line.empty:
        line_totals = (
            invoice_line.groupby("sales_invoice_id", as_index=False)["net_line_amount"]
            .sum()
            .rename(columns={"net_line_amount": "line_total"})
        )
        invoice_recon = invoice_header[["sales_invoice_id", "total_net_amount"]].merge(
            line_totals, on="sales_invoice_id", how="left"
        )
        invoice_recon["line_total"] = invoice_recon["line_total"].fillna(0.0)
        invoice_recon["difference"] = (
            invoice_recon["total_net_amount"] - invoice_recon["line_total"]
        ).abs()
        max_diff = float(invoice_recon["difference"].max())
        checks.append(
            _check(
                "sales_invoice_header_line_reconciliation",
                max_diff <= 0.02,
                {"max_absolute_difference": round(max_diff, 4)},
            )
        )

        line_formula_diff = (
            invoice_line["gross_line_amount"]
            - invoice_line["discount_amount"]
            - invoice_line["net_line_amount"]
        ).abs()
        max_line_diff = float(line_formula_diff.max())
        checks.append(
            _check(
                "sales_invoice_line_amount_formula",
                max_line_diff <= 0.02,
                {"max_absolute_difference": round(max_line_diff, 4)},
            )
        )
    else:
        checks.append(_check("sales_invoice_header_line_reconciliation", False, {"reason": "no_invoices"}))

    credit_header = dataset["sales_credit_memo_header"]
    credit_line = dataset["sales_credit_memo_line"]
    if not credit_header.empty and not credit_line.empty:
        credit_totals = (
            credit_line.groupby("sales_credit_memo_id", as_index=False)["net_credit_amount"]
            .sum()
            .rename(columns={"net_credit_amount": "line_total"})
        )
        credit_recon = credit_header[["sales_credit_memo_id", "total_net_amount"]].merge(
            credit_totals, on="sales_credit_memo_id", how="left"
        )
        credit_recon["difference"] = (
            credit_recon["total_net_amount"] - credit_recon["line_total"].fillna(0.0)
        ).abs()
        max_credit_diff = float(credit_recon["difference"].max())
        checks.append(
            _check(
                "credit_memo_header_line_reconciliation",
                max_credit_diff <= 0.02,
                {"max_absolute_difference": round(max_credit_diff, 4)},
            )
        )

        invoice_refs = invoice_line.merge(
            invoice_header[["sales_invoice_id", "invoice_no"]],
            on="sales_invoice_id",
            how="left",
        )[["invoice_no", "line_no", "quantity"]].copy()
        invoice_refs["ref_key"] = (
            invoice_refs["invoice_no"].astype(str)
            + ":"
            + invoice_refs["line_no"].astype(int).astype(str)
        )
        original_qty = dict(zip(invoice_refs["ref_key"], invoice_refs["quantity"]))

        credit_keys = (
            credit_line["original_invoice_no"].astype(str)
            + ":"
            + credit_line["original_invoice_line_no"].astype(int).astype(str)
        )
        missing_return_refs = int((~credit_keys.isin(original_qty.keys())).sum())
        excessive_returns = 0
        for key, qty in zip(credit_keys, credit_line["return_quantity"]):
            if key in original_qty and float(qty) > float(original_qty[key]) + 1e-9:
                excessive_returns += 1

        checks.append(
            _check(
                "return_reference_integrity",
                missing_return_refs == 0 and excessive_returns == 0,
                {
                    "missing_original_line_refs": missing_return_refs,
                    "return_qty_above_original_qty": excessive_returns,
                },
            )
        )
    else:
        checks.append(_check("credit_memo_header_line_reconciliation", False, {"reason": "no_returns"}))
        checks.append(_check("return_reference_integrity", False, {"reason": "no_returns"}))

    ledger = dataset["inventory_ledger_entry"]
    transfer_rows = ledger[ledger["transfer_pair_id"].notna()].copy()
    if not transfer_rows.empty:
        transfer_recon = transfer_rows.groupby(
            ["transfer_pair_id", "product_id"], as_index=False
        )["quantity"].sum()
        max_transfer_diff = float(transfer_recon["quantity"].abs().max())
        transfer_pair_counts = transfer_rows.groupby("transfer_pair_id").size()
        invalid_pair_count = int((transfer_pair_counts != 2).sum())
        checks.append(
            _check(
                "warehouse_transfer_reconciliation",
                max_transfer_diff <= 1e-9 and invalid_pair_count == 0,
                {
                    "max_quantity_difference": round(max_transfer_diff, 6),
                    "invalid_pair_count": invalid_pair_count,
                },
            )
        )
    else:
        checks.append(_check("warehouse_transfer_reconciliation", False, {"reason": "no_transfers"}))

    balance = dataset["inventory_balance"]
    ledger_balance = (
        ledger.groupby(["product_id", "warehouse_id"], as_index=False)["quantity"]
        .sum()
        .rename(columns={"quantity": "ledger_quantity"})
    )
    balance_recon = balance.merge(
        ledger_balance,
        on=["product_id", "warehouse_id"],
        how="outer",
    ).fillna(0.0)
    balance_recon["difference"] = (
        balance_recon["on_hand_quantity"] - balance_recon["ledger_quantity"]
    ).abs()
    max_balance_diff = float(balance_recon["difference"].max()) if not balance_recon.empty else 0.0
    checks.append(
        _check(
            "inventory_balance_reconciliation",
            max_balance_diff <= 1e-6,
            {"max_quantity_difference": round(max_balance_diff, 8)},
        )
    )

    value = dataset["value_entry"]
    checks.append(
        _check(
            "value_entry_one_to_one_with_ledger",
            len(value) == len(ledger)
            and value["inventory_ledger_entry_id"].nunique() == len(ledger),
            {
                "ledger_rows": int(len(ledger)),
                "value_rows": int(len(value)),
                "linked_ledger_ids": int(value["inventory_ledger_entry_id"].nunique()),
            },
        )
    )

    sale_values = value[value["entry_type"] == "sale"]
    checks.append(
        _check(
            "sale_value_and_cost_lineage",
            not sale_values.empty
            and bool((sale_values["sales_amount_actual"] > 0).all())
            and bool((sale_values["cost_amount_actual"] >= 0).all()),
            {"sale_value_entries": int(len(sale_values))},
        )
    )

    return _result(checks)


def _result(checks: list[dict[str, Any]]) -> dict[str, Any]:
    failed = [check for check in checks if not check["passed"]]
    return {
        "schema_version": 1,
        "passed": not failed,
        "check_count": len(checks),
        "passed_count": len(checks) - len(failed),
        "failed_count": len(failed),
        "failed_checks": [check["name"] for check in failed],
        "checks": checks,
    }
