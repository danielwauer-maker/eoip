from __future__ import annotations

import math
import re
from pathlib import Path
from typing import Any

import psycopg
import yaml


REQUIRED_KPI_FIELDS = {
    "id",
    "name",
    "domain",
    "format",
    "business_definition",
    "decision_use",
    "grain",
    "numerator",
    "denominator",
    "source_lineage",
    "dimensions",
    "time_behavior",
    "sign_policy",
    "zero_behavior",
    "dax",
    "sql_reference",
}


def load_kpi_catalog(path: str | Path) -> dict[str, Any]:
    with Path(path).open("r", encoding="utf-8") as handle:
        raw = yaml.safe_load(handle)
    if raw.get("schema_version") != 1:
        raise ValueError("Unsupported KPI catalog schema_version.")
    return raw["kpi_catalog"]


def dax_measure_names(path: str | Path) -> set[str]:
    text = Path(path).read_text(encoding="utf-8")
    names: set[str] = set()
    for line in text.splitlines():
        match = re.match(r"^(.+?)\s*:=\s*$", line.strip())
        if match:
            names.add(match.group(1).strip())
    return names


def validate_kpi_catalog(
    catalog: dict[str, Any],
    *,
    dax_path: str | Path | None = None,
) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []

    def add(name: str, passed: bool, **details: Any) -> None:
        checks.append({"name": name, "passed": bool(passed), "details": details})

    kpis = catalog.get("kpis", [])
    ids = [str(kpi.get("id")) for kpi in kpis]
    names = [str(kpi.get("name")) for kpi in kpis]
    dax_names = [str(kpi.get("dax", {}).get("measure_name")) for kpi in kpis]

    add(
        "governed_kpi_count",
        len(kpis) == int(catalog["identity_source"]["frozen_count"]) == 18,
        actual=len(kpis),
        expected=18,
    )
    add(
        "unique_kpi_ids",
        len(ids) == len(set(ids)),
        duplicate_count=len(ids) - len(set(ids)),
    )
    add(
        "unique_kpi_names",
        len(names) == len(set(names)),
        duplicate_count=len(names) - len(set(names)),
    )
    add(
        "unique_dax_measure_names",
        len(dax_names) == len(set(dax_names)),
        duplicate_count=len(dax_names) - len(set(dax_names)),
    )

    missing_fields: dict[str, list[str]] = {}
    invalid_lineage: list[str] = []
    invalid_dax: list[str] = []
    invalid_sql_reference: list[str] = []

    for kpi in kpis:
        kpi_id = str(kpi.get("id"))
        missing = sorted(REQUIRED_KPI_FIELDS - set(kpi))
        if missing:
            missing_fields[kpi_id] = missing

        lineage = kpi.get("source_lineage", {})
        if not lineage.get("tables") or not lineage.get("fields"):
            invalid_lineage.append(kpi_id)

        dax = kpi.get("dax", {})
        if not dax.get("measure_name") or not dax.get("expression"):
            invalid_dax.append(kpi_id)

        reference = kpi.get("sql_reference", {})
        if reference.get("view") != "semantic.v_kpi_reference" or not reference.get("scope"):
            invalid_sql_reference.append(kpi_id)

    add("required_kpi_metadata", not missing_fields, missing=missing_fields)
    add("source_lineage_present", not invalid_lineage, invalid=invalid_lineage)
    add("dax_definition_present", not invalid_dax, invalid=invalid_dax)
    add(
        "sql_reference_contract",
        not invalid_sql_reference,
        invalid=invalid_sql_reference,
    )

    if dax_path is not None:
        file_measures = dax_measure_names(dax_path)
        missing_measures = sorted(set(dax_names) - file_measures)
        add(
            "dax_file_contains_all_governed_measures",
            not missing_measures,
            missing=missing_measures,
            parsed_measure_count=len(file_measures),
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


def validate_semantic_database(
    connection: psycopg.Connection,
    catalog: dict[str, Any],
) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []

    def add(name: str, passed: bool, **details: Any) -> None:
        checks.append({"name": name, "passed": bool(passed), "details": details})

    catalog_ids = {str(kpi["id"]) for kpi in catalog["kpis"]}

    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT kpi_id, numeric_value, reference_scope
            FROM semantic.v_kpi_reference
            ORDER BY kpi_id
            """
        )
        rows = cursor.fetchall()

        sql_ids = [str(row[0]) for row in rows]
        add(
            "sql_reference_kpi_count",
            len(rows) == 18,
            actual=len(rows),
            expected=18,
        )
        add(
            "sql_reference_unique_ids",
            len(sql_ids) == len(set(sql_ids)),
            duplicate_count=len(sql_ids) - len(set(sql_ids)),
        )
        add(
            "catalog_sql_id_set_match",
            set(sql_ids) == catalog_ids,
            missing_in_sql=sorted(catalog_ids - set(sql_ids)),
            unexpected_in_sql=sorted(set(sql_ids) - catalog_ids),
        )

        non_finite: list[str] = []
        null_values: list[str] = []
        for kpi_id, value, _scope in rows:
            if value is None:
                null_values.append(str(kpi_id))
                continue
            numeric = float(value)
            if not math.isfinite(numeric):
                non_finite.append(str(kpi_id))

        add(
            "sql_reference_values_available",
            not null_values and not non_finite,
            null_values=null_values,
            non_finite=non_finite,
        )

        cursor.execute(
            """
            SELECT
                (SELECT COUNT(*) FROM semantic.v_inventory_position),
                (SELECT COUNT(*) FROM dw.fact_inventory_snapshot)
            """
        )
        semantic_rows, snapshot_rows = map(int, cursor.fetchone())
        add(
            "inventory_position_grain",
            semantic_rows == snapshot_rows,
            semantic_rows=semantic_rows,
            snapshot_rows=snapshot_rows,
        )

        cursor.execute(
            """
            SELECT COUNT(*)
            FROM semantic.v_inventory_position
            WHERE positive_inventory_value < 0
               OR excess_inventory_value_60d < 0
               OR average_daily_units_90d < 0
            """
        )
        negative_screening_values = int(cursor.fetchone()[0])
        add(
            "inventory_screening_values_non_negative",
            negative_screening_values == 0,
            invalid_rows=negative_screening_values,
        )

        cursor.execute(
            """
            SELECT
                COUNT(*) FILTER (WHERE slow_moving_flag),
                COUNT(*) FILTER (WHERE stockout_risk_flag),
                COUNT(*) FILTER (WHERE excess_inventory_value_60d > 0)
            FROM semantic.v_inventory_position
            """
        )
        slow_rows, risk_rows, excess_rows = map(int, cursor.fetchone())
        add(
            "inventory_test_patterns_present",
            slow_rows > 0 and risk_rows > 0 and excess_rows > 0,
            slow_moving_positions=slow_rows,
            stockout_risk_positions=risk_rows,
            excess_positions=excess_rows,
        )

        cursor.execute(
            """
            SELECT
                MAX(ABS(
                    CASE
                        WHEN kpi_id = 'gross_profit' THEN numeric_value
                    END
                )),
                (
                    SELECT
                        ABS(
                            COALESCE(SUM(net_sales_signed), 0)
                            - COALESCE(SUM(cogs_signed), 0)
                        )
                    FROM dw.fact_sales
                )
            FROM semantic.v_kpi_reference
            """
        )
        reference_gp, direct_gp = cursor.fetchone()
        reference_gp = float(reference_gp or 0)
        direct_gp = float(direct_gp or 0)
        add(
            "gross_profit_reference_reconciliation",
            abs(abs(reference_gp) - abs(direct_gp)) <= 0.02,
            reference=round(reference_gp, 2),
            direct=round(direct_gp, 2),
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
