from __future__ import annotations

from pathlib import Path
from typing import Any

import psycopg
import yaml


EXPECTED_PAGE_IDS = {"inventory_overview", "inventory_risk"}
EXPECTED_KPIS = {
    "inventory_value",
    "inventory_turnover",
    "stock_coverage_days",
    "slow_moving_inventory_value",
    "excess_inventory_value",
    "stockout_risk_sku_count",
}


def load_inventory_report_spec(path: str | Path) -> dict[str, Any]:
    with Path(path).open("r", encoding="utf-8") as handle:
        raw = yaml.safe_load(handle)
    if raw.get("schema_version") != 1:
        raise ValueError("Unsupported Inventory Intelligence schema_version.")
    return raw["report"]


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


def validate_inventory_report_spec(
    report: dict[str, Any],
    kpi_catalog: dict[str, Any],
) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []

    def add(name: str, passed: bool, **details: Any) -> None:
        checks.append({"name": name, "passed": bool(passed), "details": details})

    governed = {str(item["id"]) for item in kpi_catalog["kpis"]}
    pages = report.get("pages", [])
    page_ids = [str(page["id"]) for page in pages]

    add(
        "inventory_page_identity_contract",
        set(page_ids) == EXPECTED_PAGE_IDS and len(page_ids) == 2,
        actual=page_ids,
        expected=sorted(EXPECTED_PAGE_IDS),
    )

    required = {
        str(item)
        for item in report.get("validation", {}).get("required_kpis", [])
    }
    add(
        "inventory_required_kpi_contract",
        required == EXPECTED_KPIS,
        configured=sorted(required),
        expected=sorted(EXPECTED_KPIS),
    )

    grid_columns = int(report["page_canvas"]["grid_columns"])
    visual_ids: list[str] = []
    unknown_kpis: dict[str, list[str]] = {}
    non_inventory_kpis: dict[str, list[str]] = {}
    layout_errors: list[str] = []
    count_errors: dict[str, dict[str, int]] = {}
    missing_decision_use: list[str] = []
    missing_questions: list[str] = []

    for page in pages:
        visuals = page.get("visuals", [])
        if int(page.get("visual_count", -1)) != len(visuals):
            count_errors[str(page["id"])] = {
                "declared": int(page.get("visual_count", -1)),
                "actual": len(visuals),
            }
        if not page.get("business_questions"):
            missing_questions.append(str(page["id"]))

        for visual in visuals:
            visual_id = str(visual["id"])
            visual_ids.append(visual_id)

            used = {str(item) for item in visual.get("kpis", [])}
            unknown = sorted(used - governed)
            if unknown:
                unknown_kpis[visual_id] = unknown

            outside_inventory = sorted(used - EXPECTED_KPIS)
            if outside_inventory:
                non_inventory_kpis[visual_id] = outside_inventory

            pos = visual.get("position", {})
            x = int(pos.get("x", -1))
            y = int(pos.get("y", -1))
            width = int(pos.get("w", -1))
            height = int(pos.get("h", -1))
            if x < 0 or y < 0 or width <= 0 or height <= 0 or x + width > grid_columns:
                layout_errors.append(visual_id)

            if not visual.get("decision_use"):
                missing_decision_use.append(visual_id)

    add("visual_count_contract", not count_errors, errors=count_errors)
    add(
        "unique_inventory_visual_ids",
        len(visual_ids) == len(set(visual_ids)),
        duplicate_count=len(visual_ids) - len(set(visual_ids)),
    )
    add("governed_kpis_only", not unknown_kpis, unknown=unknown_kpis)
    add(
        "inventory_kpis_only",
        not non_inventory_kpis,
        non_inventory=non_inventory_kpis,
    )
    add("visual_layout_within_grid", not layout_errors, invalid=layout_errors)
    add(
        "visual_decision_use_documented",
        not missing_decision_use,
        missing=missing_decision_use,
    )
    add(
        "page_business_questions_documented",
        not missing_questions,
        missing=missing_questions,
    )

    forbidden = {
        str(item).lower()
        for item in report.get("validation", {}).get(
            "forbidden_business_concepts",
            [],
        )
    }
    report_without_validation = dict(report)
    report_without_validation.pop("validation", None)
    body_text = "\n".join(_collect_strings(report_without_validation)).lower()
    found = sorted(item for item in forbidden if item in body_text)
    add(
        "inventoryiq_scope_boundary_respected",
        not found,
        forbidden_found=found,
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


def validate_inventory_reporting_database(
    connection: psycopg.Connection,
) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []

    def add(name: str, passed: bool, **details: Any) -> None:
        checks.append({"name": name, "passed": bool(passed), "details": details})

    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT
                MAX(CASE WHEN kpi_id = 'inventory_value' THEN numeric_value END),
                MAX(CASE WHEN kpi_id = 'inventory_turnover' THEN numeric_value END),
                MAX(CASE WHEN kpi_id = 'stock_coverage_days' THEN numeric_value END),
                MAX(CASE WHEN kpi_id = 'slow_moving_inventory_value' THEN numeric_value END),
                MAX(CASE WHEN kpi_id = 'excess_inventory_value' THEN numeric_value END),
                MAX(CASE WHEN kpi_id = 'stockout_risk_sku_count' THEN numeric_value END)
            FROM semantic.v_kpi_reference
            """
        )
        (
            ref_inventory,
            ref_turnover,
            ref_coverage,
            ref_slow,
            ref_excess,
            ref_stockout,
        ) = [float(value or 0) for value in cursor.fetchone()]

        cursor.execute(
            """
            SELECT
                SUM(inventory_value),
                SUM(trailing_365d_cogs),
                SUM(on_hand_quantity),
                SUM(average_daily_units_90d),
                SUM(slow_moving_inventory_value),
                SUM(excess_inventory_value),
                SUM(stockout_risk_sku_count),
                COUNT(*)
            FROM semantic.v_inventory_category_reference
            """
        )
        (
            cat_inventory,
            cat_cogs,
            cat_on_hand,
            cat_daily,
            cat_slow,
            cat_excess,
            cat_stockout,
            category_count,
        ) = cursor.fetchone()

        cat_inventory = float(cat_inventory or 0)
        cat_cogs = float(cat_cogs or 0)
        cat_on_hand = float(cat_on_hand or 0)
        cat_daily = float(cat_daily or 0)
        cat_slow = float(cat_slow or 0)
        cat_excess = float(cat_excess or 0)
        cat_stockout = float(cat_stockout or 0)

        derived_turnover = cat_cogs / cat_inventory if cat_inventory else 0.0
        derived_coverage = cat_on_hand / cat_daily if cat_daily else 0.0

        category_differences = {
            "inventory_value": cat_inventory - ref_inventory,
            "inventory_turnover": derived_turnover - ref_turnover,
            "stock_coverage_days": derived_coverage - ref_coverage,
            "slow_moving_inventory_value": cat_slow - ref_slow,
            "excess_inventory_value": cat_excess - ref_excess,
            "stockout_risk_sku_count": cat_stockout - ref_stockout,
        }
        add(
            "inventory_category_reconciles_to_governed_kpis",
            int(category_count) > 0
            and all(abs(value) <= 0.02 for value in category_differences.values()),
            category_count=int(category_count),
            differences={
                key: round(value, 6)
                for key, value in category_differences.items()
            },
        )

        cursor.execute(
            """
            SELECT
                SUM(inventory_value),
                SUM(trailing_365d_cogs),
                SUM(on_hand_quantity),
                SUM(average_daily_units_90d),
                SUM(slow_moving_inventory_value),
                SUM(excess_inventory_value),
                COUNT(*)
            FROM semantic.v_inventory_warehouse_reference
            """
        )
        (
            wh_inventory,
            wh_cogs,
            wh_on_hand,
            wh_daily,
            wh_slow,
            wh_excess,
            warehouse_count,
        ) = cursor.fetchone()

        wh_inventory = float(wh_inventory or 0)
        wh_cogs = float(wh_cogs or 0)
        wh_on_hand = float(wh_on_hand or 0)
        wh_daily = float(wh_daily or 0)
        wh_slow = float(wh_slow or 0)
        wh_excess = float(wh_excess or 0)

        warehouse_differences = {
            "inventory_value": wh_inventory - ref_inventory,
            "inventory_turnover": (
                (wh_cogs / wh_inventory if wh_inventory else 0.0)
                - ref_turnover
            ),
            "stock_coverage_days": (
                (wh_on_hand / wh_daily if wh_daily else 0.0)
                - ref_coverage
            ),
            "slow_moving_inventory_value": wh_slow - ref_slow,
            "excess_inventory_value": wh_excess - ref_excess,
        }
        add(
            "inventory_warehouse_reconciles_to_governed_kpis",
            int(warehouse_count) > 0
            and all(abs(value) <= 0.02 for value in warehouse_differences.values()),
            warehouse_count=int(warehouse_count),
            differences={
                key: round(value, 6)
                for key, value in warehouse_differences.items()
            },
        )

        cursor.execute(
            """
            SELECT
                (SELECT COUNT(*) FROM semantic.v_inventory_risk_detail_reference),
                (SELECT COUNT(*) FROM semantic.v_inventory_position)
            """
        )
        risk_rows, position_rows = map(int, cursor.fetchone())
        add(
            "inventory_risk_detail_grain",
            risk_rows == position_rows,
            risk_rows=risk_rows,
            inventory_position_rows=position_rows,
        )

        cursor.execute(
            """
            SELECT
                COUNT(*) FILTER (WHERE slow_moving_flag),
                COUNT(*) FILTER (WHERE excess_inventory_value > 0),
                COUNT(*) FILTER (WHERE stockout_risk_flag),
                COUNT(*) FILTER (
                    WHERE risk_signal_count
                        <> (
                            slow_moving_flag::INTEGER
                            + (excess_inventory_value > 0)::INTEGER
                            + stockout_risk_flag::INTEGER
                        )
                ),
                COUNT(*) FILTER (
                    WHERE inventory_value < 0
                       OR excess_inventory_value < 0
                       OR average_daily_units_90d < 0
                )
            FROM semantic.v_inventory_risk_detail_reference
            """
        )
        slow_rows, excess_rows, stockout_rows, bad_signal_rows, negative_rows = map(
            int,
            cursor.fetchone(),
        )
        add(
            "inventory_risk_patterns_present",
            slow_rows > 0 and excess_rows > 0 and stockout_rows > 0,
            slow_moving_positions=slow_rows,
            excess_positions=excess_rows,
            stockout_positions=stockout_rows,
        )
        add(
            "inventory_risk_signal_contract",
            bad_signal_rows == 0,
            invalid_rows=bad_signal_rows,
        )
        add(
            "inventory_reporting_values_non_negative",
            negative_rows == 0,
            invalid_rows=negative_rows,
        )

        cursor.execute(
            """
            SELECT COUNT(*)
            FROM semantic.v_inventory_risk_detail_reference
            WHERE working_capital_attention_flag
                <> (slow_moving_flag OR excess_inventory_value > 0)
               OR availability_attention_flag <> stockout_risk_flag
            """
        )
        bad_attention_rows = int(cursor.fetchone()[0])
        add(
            "inventory_attention_flags_reconcile",
            bad_attention_rows == 0,
            invalid_rows=bad_attention_rows,
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
