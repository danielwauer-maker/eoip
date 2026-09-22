from __future__ import annotations

from pathlib import Path
from typing import Any

import psycopg
import yaml


EXPECTED_PAGE_IDS = {
    "sales_performance",
    "margin_discount",
    "customer_product",
}


def load_report_spec(path: str | Path) -> dict[str, Any]:
    with Path(path).open("r", encoding="utf-8") as handle:
        raw = yaml.safe_load(handle)
    if raw.get("schema_version") != 1:
        raise ValueError("Unsupported report specification schema_version.")
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
        result = []
        for item in value:
            result.extend(_collect_strings(item))
        return result
    return []


def validate_report_spec(
    report: dict[str, Any],
    kpi_catalog: dict[str, Any],
) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []

    def add(name: str, passed: bool, **details: Any) -> None:
        checks.append({"name": name, "passed": bool(passed), "details": details})

    governed_kpis = {str(item["id"]) for item in kpi_catalog["kpis"]}
    pages = report.get("pages", [])
    page_ids = [str(page.get("id")) for page in pages]

    add(
        "expected_sales_margin_pages",
        set(page_ids) == EXPECTED_PAGE_IDS and len(page_ids) == 3,
        actual=page_ids,
        expected=sorted(EXPECTED_PAGE_IDS),
    )
    add(
        "unique_page_ids",
        len(page_ids) == len(set(page_ids)),
        duplicate_count=len(page_ids) - len(set(page_ids)),
    )

    visual_ids: list[str] = []
    unknown_kpis: dict[str, list[str]] = {}
    layout_errors: list[str] = []
    visual_count_errors: dict[str, dict[str, int]] = {}
    missing_decision_use: list[str] = []
    missing_questions: list[str] = []

    grid_columns = int(report["page_canvas"]["grid_columns"])

    for page in pages:
        page_id = str(page["id"])
        visuals = page.get("visuals", [])
        if int(page.get("visual_count", -1)) != len(visuals):
            visual_count_errors[page_id] = {
                "declared": int(page.get("visual_count", -1)),
                "actual": len(visuals),
            }

        if not page.get("business_questions"):
            missing_questions.append(page_id)

        for visual in visuals:
            visual_id = str(visual["id"])
            visual_ids.append(visual_id)

            if not visual.get("decision_use"):
                missing_decision_use.append(visual_id)

            kpis = {str(item) for item in visual.get("kpis", [])}
            unexpected = sorted(kpis - governed_kpis)
            if unexpected:
                unknown_kpis[visual_id] = unexpected

            position = visual.get("position", {})
            x = int(position.get("x", -1))
            y = int(position.get("y", -1))
            width = int(position.get("w", -1))
            height = int(position.get("h", -1))
            if (
                x < 0
                or y < 0
                or width <= 0
                or height <= 0
                or x + width > grid_columns
            ):
                layout_errors.append(visual_id)

    add(
        "visual_count_contract",
        not visual_count_errors,
        errors=visual_count_errors,
    )
    add(
        "unique_visual_ids",
        len(visual_ids) == len(set(visual_ids)),
        duplicate_count=len(visual_ids) - len(set(visual_ids)),
    )
    add(
        "visuals_use_governed_kpis_only",
        not unknown_kpis,
        unknown=unknown_kpis,
    )
    add(
        "visual_layout_within_grid",
        not layout_errors,
        invalid=layout_errors,
    )
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
    searchable = "\n".join(_collect_strings(report)).lower()
    found_forbidden = sorted(
        concept
        for concept in forbidden
        if concept in searchable.replace(
            "\n  forbidden_business_concepts:\n",
            "\n",
        )
    )
    # Ignore the validation declaration itself when checking the report body.
    report_without_validation = dict(report)
    report_without_validation.pop("validation", None)
    body_text = "\n".join(_collect_strings(report_without_validation)).lower()
    found_forbidden = sorted(
        concept for concept in forbidden if concept in body_text
    )
    add(
        "scope_boundary_respected",
        not found_forbidden,
        forbidden_found=found_forbidden,
    )

    required_sql_views = {
        "semantic.v_sales_margin_monthly_reference",
        "semantic.v_sales_margin_driver_reference",
        "semantic.v_sales_margin_exception_reference",
    }
    configured_sql_views = {
        str(item)
        for item in report.get("validation", {}).get("sql_views", [])
    }
    add(
        "sql_validation_views_declared",
        configured_sql_views == required_sql_views,
        configured=sorted(configured_sql_views),
        expected=sorted(required_sql_views),
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


def validate_sales_margin_database(
    connection: psycopg.Connection,
) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []

    def add(name: str, passed: bool, **details: Any) -> None:
        checks.append({"name": name, "passed": bool(passed), "details": details})

    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT
                COUNT(*),
                MIN(month_start),
                MAX(month_start),
                SUM(net_sales),
                SUM(gross_profit),
                SUM(discount_value),
                SUM(return_value)
            FROM semantic.v_sales_margin_monthly_reference
            """
        )
        (
            month_count,
            min_month,
            max_month,
            monthly_sales,
            monthly_gp,
            monthly_discount,
            monthly_return,
        ) = cursor.fetchone()

        add(
            "monthly_reference_has_history",
            int(month_count) >= 12 and min_month is not None and max_month is not None,
            month_count=int(month_count),
            min_month=str(min_month),
            max_month=str(max_month),
        )

        cursor.execute(
            """
            SELECT
                MAX(CASE WHEN kpi_id = 'net_sales' THEN numeric_value END),
                MAX(CASE WHEN kpi_id = 'gross_profit' THEN numeric_value END),
                MAX(CASE WHEN kpi_id = 'discount_value' THEN numeric_value END),
                MAX(CASE WHEN kpi_id = 'return_value' THEN numeric_value END)
            FROM semantic.v_kpi_reference
            """
        )
        ref_sales, ref_gp, ref_discount, ref_return = cursor.fetchone()

        reconciliations = {
            "net_sales": (float(monthly_sales or 0), float(ref_sales or 0)),
            "gross_profit": (float(monthly_gp or 0), float(ref_gp or 0)),
            "discount_value": (
                float(monthly_discount or 0),
                float(ref_discount or 0),
            ),
            "return_value": (
                float(monthly_return or 0),
                float(ref_return or 0),
            ),
        }
        differences = {
            name: round(actual - expected, 6)
            for name, (actual, expected) in reconciliations.items()
        }
        add(
            "monthly_reference_reconciles_to_governed_kpis",
            all(abs(value) <= 0.02 for value in differences.values()),
            differences=differences,
        )

        cursor.execute(
            """
            SELECT entity_type, COUNT(*), MIN(net_sales_rank), MIN(gross_profit_rank)
            FROM semantic.v_sales_margin_driver_reference
            GROUP BY entity_type
            ORDER BY entity_type
            """
        )
        driver_rows = cursor.fetchall()
        driver_types = {str(row[0]) for row in driver_rows}
        add(
            "driver_reference_has_expected_grains",
            driver_types == {"customer", "product", "category"}
            and all(int(row[1]) > 0 for row in driver_rows)
            and all(int(row[2]) == 1 for row in driver_rows)
            and all(int(row[3]) == 1 for row in driver_rows),
            rows=[
                {
                    "entity_type": str(row[0]),
                    "row_count": int(row[1]),
                    "min_sales_rank": int(row[2]),
                    "min_gp_rank": int(row[3]),
                }
                for row in driver_rows
            ],
        )

        cursor.execute(
            """
            SELECT
                SUM(net_sales),
                SUM(gross_profit),
                SUM(discount_value),
                SUM(return_value)
            FROM semantic.v_sales_margin_driver_reference
            WHERE entity_type = 'category'
            """
        )
        cat_sales, cat_gp, cat_discount, cat_return = map(float, cursor.fetchone())

        category_diffs = {
            "net_sales": cat_sales - float(ref_sales or 0),
            "gross_profit": cat_gp - float(ref_gp or 0),
            "discount_value": cat_discount - float(ref_discount or 0),
            "return_value": cat_return - float(ref_return or 0),
        }
        add(
            "category_driver_reconciles_to_governed_kpis",
            all(abs(value) <= 0.02 for value in category_diffs.values()),
            differences={
                key: round(value, 6)
                for key, value in category_diffs.items()
            },
        )

        cursor.execute(
            """
            SELECT
                COUNT(*),
                COUNT(*) FILTER (
                    WHERE exception_count < 1
                       OR NOT material_sales_flag
                ),
                COUNT(*) FILTER (WHERE low_margin_flag),
                COUNT(*) FILTER (WHERE high_discount_flag),
                COUNT(*) FILTER (WHERE high_return_flag)
            FROM semantic.v_sales_margin_exception_reference
            """
        )
        (
            exception_rows,
            invalid_exception_rows,
            low_margin_rows,
            high_discount_rows,
            high_return_rows,
        ) = map(int, cursor.fetchone())

        add(
            "exception_reference_contract",
            invalid_exception_rows == 0,
            row_count=exception_rows,
            invalid_rows=invalid_exception_rows,
            low_margin_rows=low_margin_rows,
            high_discount_rows=high_discount_rows,
            high_return_rows=high_return_rows,
        )

        cursor.execute(
            """
            SELECT
                COUNT(*)
            FROM semantic.v_sales_margin_monthly_reference
            WHERE gross_margin_pct IS NOT NULL
              AND (gross_margin_pct < -1000 OR gross_margin_pct > 1000)
            """
        )
        invalid_margin_rows = int(cursor.fetchone()[0])
        add(
            "monthly_margin_values_plausible",
            invalid_margin_rows == 0,
            invalid_rows=invalid_margin_rows,
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
