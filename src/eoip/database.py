from __future__ import annotations

import io
import json
from pathlib import Path
from typing import Any

import pandas as pd
import psycopg
from psycopg import sql

from .generator import ENTITY_ORDER


LOAD_ORDER = [
    "salesperson",
    "supplier",
    "product_category",
    "warehouse",
    "customer",
    "product",
    "sales_order_header",
    "sales_order_line",
    "sales_invoice_header",
    "sales_invoice_line",
    "sales_credit_memo_header",
    "sales_credit_memo_line",
    "purchase_receipt_header",
    "purchase_receipt_line",
    "warehouse_transfer_header",
    "warehouse_transfer_line",
    "inventory_ledger_entry",
    "value_entry",
    "inventory_balance",
]


def project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def connect_database(database_url: str) -> psycopg.Connection:
    return psycopg.connect(database_url)


def apply_migrations(
    connection: psycopg.Connection,
    *,
    sql_dir: str | Path | None = None,
) -> list[str]:
    directory = Path(sql_dir) if sql_dir is not None else project_root() / "sql"
    files = sorted(directory.glob("*.sql"))
    if not files:
        raise FileNotFoundError(f"No SQL migration files found in {directory}")

    applied: list[str] = []
    with connection.cursor() as cursor:
        for path in files:
            cursor.execute(path.read_text(encoding="utf-8"))
            applied.append(path.name)
    connection.commit()
    return applied


def truncate_raw(connection: psycopg.Connection) -> None:
    identifiers = [
        sql.SQL("{}.{}").format(sql.Identifier("raw"), sql.Identifier(name))
        for name in reversed(LOAD_ORDER)
    ]
    statement = sql.SQL("TRUNCATE TABLE {} RESTART IDENTITY CASCADE").format(
        sql.SQL(", ").join(identifiers)
    )
    with connection.cursor() as cursor:
        cursor.execute(statement)
    connection.commit()


def _copy_frame(
    connection: psycopg.Connection,
    table_name: str,
    frame: pd.DataFrame,
) -> None:
    if frame.empty:
        return

    buffer = io.StringIO()
    frame.to_csv(
        buffer,
        index=False,
        header=True,
        na_rep="",
        date_format="%Y-%m-%d",
    )
    buffer.seek(0)

    columns = [sql.Identifier(column) for column in frame.columns]
    statement = sql.SQL(
        "COPY {}.{} ({}) FROM STDIN WITH (FORMAT CSV, HEADER TRUE)"
    ).format(
        sql.Identifier("raw"),
        sql.Identifier(table_name),
        sql.SQL(", ").join(columns),
    )

    with connection.cursor() as cursor:
        with cursor.copy(statement) as copy:
            copy.write(buffer.getvalue())


def load_dataset(
    connection: psycopg.Connection,
    dataset: dict[str, pd.DataFrame],
    *,
    truncate: bool = True,
) -> dict[str, int]:
    missing = [name for name in ENTITY_ORDER if name not in dataset]
    if missing:
        raise ValueError(f"Dataset is missing required entities: {missing}")

    if truncate:
        truncate_raw(connection)

    for name in LOAD_ORDER:
        _copy_frame(connection, name, dataset[name])

    connection.commit()
    return raw_row_counts(connection)


def load_csv_directory(path: str | Path) -> dict[str, pd.DataFrame]:
    directory = Path(path)
    dataset: dict[str, pd.DataFrame] = {}
    for name in ENTITY_ORDER:
        file_path = directory / f"{name}.csv"
        if not file_path.exists():
            raise FileNotFoundError(f"Missing generated source file: {file_path}")
        dataset[name] = pd.read_csv(file_path)
    return dataset


def raw_row_counts(connection: psycopg.Connection) -> dict[str, int]:
    counts: dict[str, int] = {}
    with connection.cursor() as cursor:
        for name in ENTITY_ORDER:
            query = sql.SQL("SELECT COUNT(*) FROM {}.{}").format(
                sql.Identifier("raw"),
                sql.Identifier(name),
            )
            cursor.execute(query)
            counts[name] = int(cursor.fetchone()[0])
    return counts


def validate_database(
    connection: psycopg.Connection,
    *,
    expected_row_counts: dict[str, int] | None = None,
) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []

    def add(name: str, passed: bool, **details: Any) -> None:
        checks.append(
            {
                "name": name,
                "passed": bool(passed),
                "details": details,
            }
        )

    counts = raw_row_counts(connection)
    if expected_row_counts is not None:
        mismatches = {
            name: {
                "expected": int(expected_row_counts[name]),
                "actual": int(counts[name]),
            }
            for name in ENTITY_ORDER
            if int(expected_row_counts[name]) != int(counts[name])
        }
        add(
            "raw_row_counts_match_source",
            not mismatches,
            mismatches=mismatches,
        )

    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT
                (SELECT COUNT(*) FROM stg.sales_document_line),
                (SELECT COUNT(*) FROM raw.sales_invoice_line)
                + (SELECT COUNT(*) FROM raw.sales_credit_memo_line)
            """
        )
        staged_sales, expected_sales = map(int, cursor.fetchone())
        add(
            "staging_sales_document_line_count",
            staged_sales == expected_sales,
            staged=staged_sales,
            expected=expected_sales,
        )

        cursor.execute(
            """
            SELECT
                (SELECT COUNT(*) FROM raw.inventory_balance),
                (SELECT COUNT(*) FROM raw.product)
                * (SELECT COUNT(*) FROM raw.warehouse)
            """
        )
        balance_rows, expected_balance_rows = map(int, cursor.fetchone())
        add(
            "inventory_balance_complete_product_warehouse_grid",
            balance_rows == expected_balance_rows,
            actual=balance_rows,
            expected=expected_balance_rows,
        )

        cursor.execute(
            """
            SELECT COALESCE(MAX(ABS(quantity_sum)), 0)
            FROM (
                SELECT transfer_pair_id, product_id, SUM(quantity) AS quantity_sum
                FROM raw.inventory_ledger_entry
                WHERE transfer_pair_id IS NOT NULL
                GROUP BY transfer_pair_id, product_id
            ) x
            """
        )
        transfer_diff = float(cursor.fetchone()[0])
        add(
            "warehouse_transfer_quantity_reconciliation",
            transfer_diff <= 0.000001,
            max_absolute_difference=transfer_diff,
        )

        cursor.execute(
            """
            SELECT COALESCE(MAX(ABS(h.total_net_amount - x.line_total)), 0)
            FROM raw.sales_invoice_header h
            JOIN (
                SELECT sales_invoice_id, SUM(net_line_amount) AS line_total
                FROM raw.sales_invoice_line
                GROUP BY sales_invoice_id
            ) x
              ON x.sales_invoice_id = h.sales_invoice_id
            """
        )
        invoice_diff = float(cursor.fetchone()[0])
        add(
            "invoice_header_line_reconciliation",
            invoice_diff <= 0.02,
            max_absolute_difference=invoice_diff,
        )

        cursor.execute(
            """
            SELECT
                (SELECT COUNT(*) FROM raw.value_entry),
                (SELECT COUNT(*) FROM raw.inventory_ledger_entry),
                (SELECT COUNT(DISTINCT inventory_ledger_entry_id) FROM raw.value_entry)
            """
        )
        value_rows, ledger_rows, linked_ledger_rows = map(int, cursor.fetchone())
        add(
            "value_entry_ledger_lineage",
            value_rows == ledger_rows == linked_ledger_rows,
            value_rows=value_rows,
            ledger_rows=ledger_rows,
            linked_ledger_rows=linked_ledger_rows,
        )

        cursor.execute(
            """
            SELECT COALESCE(MAX(ABS(b.on_hand_quantity - x.ledger_quantity)), 0)
            FROM raw.inventory_balance b
            JOIN (
                SELECT product_id, warehouse_id, SUM(quantity) AS ledger_quantity
                FROM raw.inventory_ledger_entry
                GROUP BY product_id, warehouse_id
            ) x
              ON x.product_id = b.product_id
             AND x.warehouse_id = b.warehouse_id
            """
        )
        balance_diff = float(cursor.fetchone()[0])
        add(
            "inventory_ledger_balance_reconciliation",
            balance_diff <= 0.000001,
            max_absolute_difference=balance_diff,
        )

        cursor.execute(
            """
            SELECT
                COALESCE(SUM(net_sales_signed), 0),
                COALESCE((SELECT SUM(net_line_amount) FROM raw.sales_invoice_line), 0)
                - COALESCE((SELECT SUM(net_credit_amount) FROM raw.sales_credit_memo_line), 0)
            FROM stg.sales_document_line
            """
        )
        staged_net_sales, source_net_sales = map(float, cursor.fetchone())
        add(
            "staging_net_sales_sign_convention",
            abs(staged_net_sales - source_net_sales) <= 0.02,
            staged_net_sales=round(staged_net_sales, 2),
            source_net_sales=round(source_net_sales, 2),
        )

        cursor.execute(
            """
            SELECT
                COUNT(*) FILTER (
                    WHERE document_type = 'credit_memo'
                      AND (quantity_signed >= 0 OR net_sales_signed >= 0)
                ),
                COUNT(*) FILTER (WHERE document_type = 'credit_memo')
            FROM stg.sales_document_line
            """
        )
        invalid_credit_signs, credit_rows = map(int, cursor.fetchone())
        add(
            "credit_memo_staging_signs",
            credit_rows > 0 and invalid_credit_signs == 0,
            credit_rows=credit_rows,
            invalid_rows=invalid_credit_signs,
        )

    failed = [check for check in checks if not check["passed"]]
    return {
        "schema_version": 1,
        "passed": not failed,
        "check_count": len(checks),
        "passed_count": len(checks) - len(failed),
        "failed_count": len(failed),
        "failed_checks": [check["name"] for check in failed],
        "raw_row_counts": counts,
        "checks": checks,
    }



def refresh_dimensional_model(
    connection: psycopg.Connection,
    *,
    transform_path: str | Path | None = None,
) -> None:
    path = (
        Path(transform_path)
        if transform_path is not None
        else project_root() / "sql" / "transforms" / "010_refresh_dw.sql"
    )
    if not path.exists():
        raise FileNotFoundError(f"Dimensional refresh SQL not found: {path}")
    with connection.cursor() as cursor:
        cursor.execute(path.read_text(encoding="utf-8"))
    connection.commit()


def validate_dimensional_model(connection: psycopg.Connection) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []

    def add(name: str, passed: bool, **details: Any) -> None:
        checks.append({"name": name, "passed": bool(passed), "details": details})

    with connection.cursor() as cursor:
        for dim, raw_table in [
            ("dim_customer", "customer"),
            ("dim_product", "product"),
            ("dim_warehouse", "warehouse"),
            ("dim_salesperson", "salesperson"),
        ]:
            cursor.execute(
                sql.SQL(
                    "SELECT (SELECT COUNT(*) FROM dw.{}), "
                    "(SELECT COUNT(*) FROM raw.{})"
                ).format(sql.Identifier(dim), sql.Identifier(raw_table))
            )
            dim_rows, source_rows = map(int, cursor.fetchone())
            add(
                f"{dim}_row_count",
                dim_rows == source_rows,
                dimensional=dim_rows,
                source=source_rows,
            )

        cursor.execute(
            """
            SELECT
                (SELECT COUNT(*) FROM dw.fact_sales),
                (SELECT COUNT(*) FROM stg.sales_document_line)
            """
        )
        fact_rows, stage_rows = map(int, cursor.fetchone())
        add(
            "fact_sales_grain",
            fact_rows == stage_rows,
            fact_rows=fact_rows,
            staging_rows=stage_rows,
        )

        cursor.execute(
            """
            SELECT
                COALESCE((SELECT SUM(net_sales_signed) FROM dw.fact_sales), 0),
                COALESCE((SELECT SUM(net_sales_signed) FROM stg.sales_document_line), 0),
                COALESCE((SELECT SUM(cogs_signed) FROM dw.fact_sales), 0),
                COALESCE((
                    SELECT SUM(cost_amount_actual)
                    FROM stg.value_movement
                    WHERE document_type IN ('sales_invoice', 'sales_credit_memo')
                ), 0)
            """
        )
        fact_sales, stage_sales, fact_cogs, source_cogs = map(float, cursor.fetchone())
        add(
            "fact_sales_value_reconciliation",
            abs(fact_sales - stage_sales) <= 0.02
            and abs(fact_cogs - source_cogs) <= 0.02,
            fact_net_sales=round(fact_sales, 2),
            stage_net_sales=round(stage_sales, 2),
            fact_cogs=round(fact_cogs, 2),
            source_cogs=round(source_cogs, 2),
        )

        cursor.execute(
            """
            SELECT COUNT(*)
            FROM dw.fact_sales
            WHERE source_document_type = 'credit_memo'
              AND (
                  quantity_signed >= 0
                  OR net_sales_signed >= 0
                  OR cogs_signed >= 0
              )
            """
        )
        invalid_credit_rows = int(cursor.fetchone()[0])
        add(
            "fact_sales_credit_signs",
            invalid_credit_rows == 0,
            invalid_rows=invalid_credit_rows,
        )

        cursor.execute(
            """
            SELECT
                (SELECT COUNT(*) FROM dw.fact_sales_order),
                (SELECT COUNT(*) FROM stg.sales_order_line),
                COALESCE((SELECT SUM(outstanding_quantity) FROM dw.fact_sales_order), 0),
                COALESCE((SELECT SUM(outstanding_quantity) FROM stg.sales_order_line), 0)
            """
        )
        fact_order_rows, stage_order_rows, fact_outstanding, stage_outstanding = cursor.fetchone()
        add(
            "fact_sales_order_reconciliation",
            int(fact_order_rows) == int(stage_order_rows)
            and abs(float(fact_outstanding) - float(stage_outstanding)) <= 0.000001,
            fact_rows=int(fact_order_rows),
            staging_rows=int(stage_order_rows),
            fact_outstanding=float(fact_outstanding),
            staging_outstanding=float(stage_outstanding),
        )

        cursor.execute(
            """
            SELECT
                (SELECT COUNT(*) FROM dw.fact_inventory_movement),
                (SELECT COUNT(*) FROM stg.inventory_movement),
                COALESCE((SELECT SUM(quantity_signed) FROM dw.fact_inventory_movement), 0),
                COALESCE((SELECT SUM(quantity_signed) FROM stg.inventory_movement), 0)
            """
        )
        fact_move_rows, stage_move_rows, fact_qty, stage_qty = cursor.fetchone()
        add(
            "fact_inventory_movement_reconciliation",
            int(fact_move_rows) == int(stage_move_rows)
            and abs(float(fact_qty) - float(stage_qty)) <= 0.000001,
            fact_rows=int(fact_move_rows),
            staging_rows=int(stage_move_rows),
            fact_quantity=float(fact_qty),
            staging_quantity=float(stage_qty),
        )

        cursor.execute(
            """
            SELECT
                (SELECT COUNT(*) FROM dw.fact_inventory_snapshot),
                (SELECT COUNT(*) FROM stg.inventory_balance),
                COALESCE((SELECT SUM(on_hand_quantity) FROM dw.fact_inventory_snapshot), 0),
                COALESCE((SELECT SUM(on_hand_quantity) FROM stg.inventory_balance), 0)
            """
        )
        fact_snap_rows, stage_snap_rows, fact_on_hand, stage_on_hand = cursor.fetchone()
        add(
            "fact_inventory_snapshot_reconciliation",
            int(fact_snap_rows) == int(stage_snap_rows)
            and abs(float(fact_on_hand) - float(stage_on_hand)) <= 0.000001,
            fact_rows=int(fact_snap_rows),
            staging_rows=int(stage_snap_rows),
            fact_on_hand=float(fact_on_hand),
            staging_on_hand=float(stage_on_hand),
        )

        cursor.execute(
            """
            SELECT COUNT(*)
            FROM dw.fact_inventory_snapshot
            WHERE ABS(
                inventory_value_standard_cost
                - ROUND(on_hand_quantity * unit_cost_at_snapshot, 4)
            ) > 0.0001
            """
        )
        bad_snapshot_values = int(cursor.fetchone()[0])
        add(
            "inventory_snapshot_value_formula",
            bad_snapshot_values == 0,
            invalid_rows=bad_snapshot_values,
        )

        cursor.execute(
            """
            SELECT COUNT(*)
            FROM dw.fact_sales fs
            LEFT JOIN dw.dim_date d ON d.date_key = fs.date_key
            LEFT JOIN dw.dim_customer c ON c.customer_key = fs.customer_key
            LEFT JOIN dw.dim_product p ON p.product_key = fs.product_key
            LEFT JOIN dw.dim_warehouse w ON w.warehouse_key = fs.warehouse_key
            LEFT JOIN dw.dim_salesperson s ON s.salesperson_key = fs.salesperson_key
            WHERE d.date_key IS NULL
               OR c.customer_key IS NULL
               OR p.product_key IS NULL
               OR w.warehouse_key IS NULL
               OR s.salesperson_key IS NULL
            """
        )
        unresolved_sales_keys = int(cursor.fetchone()[0])
        add(
            "fact_sales_dimension_resolution",
            unresolved_sales_keys == 0,
            unresolved_rows=unresolved_sales_keys,
        )

        cursor.execute(
            """
            SELECT
                (SELECT MIN(full_date) FROM dw.dim_date),
                (SELECT MAX(full_date) FROM dw.dim_date),
                (SELECT COUNT(*) FROM dw.dim_date)
            """
        )
        min_date, max_date, date_rows = cursor.fetchone()
        expected_date_rows = (max_date - min_date).days + 1 if min_date and max_date else 0
        add(
            "dim_date_contiguous",
            int(date_rows) == expected_date_rows,
            min_date=str(min_date),
            max_date=str(max_date),
            rows=int(date_rows),
            expected=expected_date_rows,
        )

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

def write_database_validation(
    report: dict[str, Any],
    path: str | Path,
) -> None:
    Path(path).write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
