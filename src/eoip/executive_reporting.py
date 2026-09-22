from __future__ import annotations

from pathlib import Path
from typing import Any

import psycopg
import yaml


EXPECTED_REQUIRED_KPIS = {
    "net_sales",
    "sales_growth_pct",
    "gross_profit",
    "gross_margin_pct",
    "inventory_value",
    "stockout_risk_sku_count",
}


def load_executive_spec(path: str | Path) -> dict[str, Any]:
    with Path(path).open("r", encoding="utf-8") as handle:
        raw = yaml.safe_load(handle)
    if raw.get("schema_version") != 1:
        raise ValueError("Unsupported Executive Overview schema_version.")
    return raw["page"]


def _collect_strings(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        result: list[str] = []
        for key, item in value.items():
            result.extend(_collect_strings(key))
            result.extend(_collect_strings(item))
        return result
    if isinstance(value, list):
        result: list[str] = []
        for item in value:
            result.extend(_collect_strings(item))
        return result
    return []


def validate_executive_spec(
    page: dict[str, Any],
    kpi_catalog: dict[str, Any],
) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []

    def add(name: str, passed: bool, **details: Any) -> None:
        checks.append({"name": name, "passed": bool(passed), "details": details})

    governed = {str(item["id"]) for item in kpi_catalog["kpis"]}
    visuals = page.get("visuals", [])
    visual_ids = [str(item["id"]) for item in visuals]

    add(
        "executive_page_identity",
        page.get("id") == "executive_overview",
        actual=page.get("id"),
    )
    add(
        "visual_count_contract",
        int(page.get("visual_count", -1)) == len(visuals) == 9,
        declared=page.get("visual_count"),
        actual=len(visuals),
    )
    add(
        "unique_visual_ids",
        len(visual_ids) == len(set(visual_ids)),
        duplicate_count=len(visual_ids) - len(set(visual_ids)),
    )

    grid_columns = int(page["page_canvas"]["grid_columns"])
    layout_errors: list[str] = []
    unknown_kpis: dict[str, list[str]] = {}
    missing_decision_use: list[str] = []

    for visual in visuals:
        visual_id = str(visual["id"])
        pos = visual.get("position", {})
        x = int(pos.get("x", -1))
        y = int(pos.get("y", -1))
        width = int(pos.get("w", -1))
        height = int(pos.get("h", -1))
        if x < 0 or y < 0 or width <= 0 or height <= 0 or x + width > grid_columns:
            layout_errors.append(visual_id)

        unknown = sorted({str(k) for k in visual.get("kpis", [])} - governed)
        if unknown:
            unknown_kpis[visual_id] = unknown

        if not visual.get("decision_use"):
            missing_decision_use.append(visual_id)

    add("visual_layout_within_grid", not layout_errors, invalid=layout_errors)
    add("governed_kpis_only", not unknown_kpis, unknown=unknown_kpis)
    add(
        "visual_decision_use_documented",
        not missing_decision_use,
        missing=missing_decision_use,
    )

    required = {
        str(item)
        for item in page.get("validation", {}).get("required_kpis", [])
    }
    add(
        "required_executive_kpi_contract",
        required == EXPECTED_REQUIRED_KPIS,
        configured=sorted(required),
        expected=sorted(EXPECTED_REQUIRED_KPIS),
    )

    navigation = {
        str(item["page_id"])
        for item in page.get("navigation", {}).get("targets", [])
    }
    expected_navigation = {
        "sales_performance",
        "margin_discount",
        "customer_product",
        "inventory_overview",
        "inventory_risk",
    }
    add(
        "detail_navigation_contract",
        navigation == expected_navigation,
        configured=sorted(navigation),
        expected=sorted(expected_navigation),
    )

    forbidden = {
        str(item).lower()
        for item in page.get("validation", {}).get(
            "forbidden_business_concepts",
            [],
        )
    }
    page_without_validation = dict(page)
    page_without_validation.pop("validation", None)
    body_text = "\n".join(_collect_strings(page_without_validation)).lower()
    found_forbidden = sorted(item for item in forbidden if item in body_text)
    add(
        "scope_boundary_respected",
        not found_forbidden,
        forbidden_found=found_forbidden,
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


def validate_executive_database(
    connection: psycopg.Connection,
) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []

    def add(name: str, passed: bool, **details: Any) -> None:
        checks.append({"name": name, "passed": bool(passed), "details": details})

    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT COUNT(*), COUNT(DISTINCT kpi_id)
            FROM semantic.v_executive_kpi_reference
            """
        )
        kpi_count, distinct_kpi_count = map(int, cursor.fetchone())
        add(
            "executive_kpi_reference_contract",
            kpi_count == distinct_kpi_count == 11,
            row_count=kpi_count,
            distinct_count=distinct_kpi_count,
        )

        cursor.execute(
            """
            SELECT
                SUM(net_sales),
                SUM(gross_profit),
                SUM(inventory_value),
                SUM(slow_moving_inventory_value),
                SUM(excess_inventory_value),
                SUM(stockout_risk_sku_count),
                COUNT(*)
            FROM semantic.v_executive_category_reference
            """
        )
        (
            cat_sales,
            cat_gp,
            cat_inventory,
            cat_slow,
            cat_excess,
            cat_risk,
            category_count,
        ) = cursor.fetchone()

        cursor.execute(
            """
            SELECT
                MAX(CASE WHEN kpi_id = 'net_sales' THEN numeric_value END),
                MAX(CASE WHEN kpi_id = 'gross_profit' THEN numeric_value END),
                MAX(CASE WHEN kpi_id = 'inventory_value' THEN numeric_value END),
                MAX(CASE WHEN kpi_id = 'slow_moving_inventory_value' THEN numeric_value END),
                MAX(CASE WHEN kpi_id = 'excess_inventory_value' THEN numeric_value END),
                MAX(CASE WHEN kpi_id = 'stockout_risk_sku_count' THEN numeric_value END)
            FROM semantic.v_kpi_reference
            """
        )
        refs = cursor.fetchone()

        actuals = [
            float(cat_sales or 0),
            float(cat_gp or 0),
            float(cat_inventory or 0),
            float(cat_slow or 0),
            float(cat_excess or 0),
            float(cat_risk or 0),
        ]
        expected = [float(value or 0) for value in refs]
        differences = [actual - exp for actual, exp in zip(actuals, expected)]

        add(
            "executive_category_reconciles_to_governed_kpis",
            int(category_count) > 0
            and all(abs(value) <= 0.02 for value in differences),
            category_count=int(category_count),
            differences=[round(value, 6) for value in differences],
        )

        cursor.execute(
            """
            SELECT COUNT(*)
            FROM semantic.v_executive_category_reference
            WHERE inventory_value < 0
               OR slow_moving_inventory_value < 0
               OR excess_inventory_value < 0
               OR stockout_risk_sku_count < 0
            """
        )
        invalid_inventory_rows = int(cursor.fetchone()[0])
        add(
            "executive_category_inventory_values_non_negative",
            invalid_inventory_rows == 0,
            invalid_rows=invalid_inventory_rows,
        )

        cursor.execute(
            """
            SELECT
                COUNT(*),
                COUNT(*) FILTER (
                    WHERE attention_signal_count < 1
                       OR NOT material_flag
                )
            FROM semantic.v_executive_attention_reference
            """
        )
        attention_rows, invalid_attention_rows = map(int, cursor.fetchone())
        add(
            "executive_attention_contract",
            invalid_attention_rows == 0,
            row_count=attention_rows,
            invalid_rows=invalid_attention_rows,
        )

        cursor.execute(
            """
            SELECT COUNT(*)
            FROM semantic.v_executive_attention_reference
            WHERE attention_signal_count
                <> (
                    low_margin_flag::INTEGER
                    + excess_inventory_flag::INTEGER
                    + availability_risk_flag::INTEGER
                )
            """
        )
        invalid_signal_counts = int(cursor.fetchone()[0])
        add(
            "attention_signal_count_reconciles",
            invalid_signal_counts == 0,
            invalid_rows=invalid_signal_counts,
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
