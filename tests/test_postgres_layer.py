from __future__ import annotations

import os
from pathlib import Path

import pytest

from eoip.config import load_company_profile, load_generator_config
from eoip.database import (
    apply_migrations,
    connect_database,
    load_dataset,
    raw_row_counts,
    refresh_dimensional_model,
    validate_database,
    validate_dimensional_model,
)
from eoip.generator import ERPGenerator


ROOT = Path(__file__).resolve().parents[1]
DATABASE_URL = os.environ.get("EOIP_TEST_DATABASE_URL")


@pytest.mark.skipif(not DATABASE_URL, reason="EOIP_TEST_DATABASE_URL is not configured")
def test_postgres_raw_and_staging_pipeline():
    company = load_company_profile(ROOT / "tests" / "fixtures" / "company.yaml")
    config = load_generator_config(ROOT / "config" / "generator.yaml")
    dataset = ERPGenerator(company, config, scale_factor=0.002).generate()
    expected_counts = {name: len(frame) for name, frame in dataset.items()}

    with connect_database(DATABASE_URL) as connection:
        migrations = apply_migrations(connection)
        assert migrations == [
            "001_create_schemas.sql",
            "010_raw_tables.sql",
            "020_staging_views.sql",
            "030_dw_tables.sql",
            "040_semantic_views.sql",
            "050_sales_margin_reporting_views.sql",
            "060_executive_overview_views.sql",
            "070_inventory_reporting_views.sql",
        ]

        loaded = load_dataset(connection, dataset, truncate=True)
        assert loaded == expected_counts

        report = validate_database(
            connection,
            expected_row_counts=expected_counts,
        )
        assert report["passed"], report

        refresh_dimensional_model(connection)
        dw_report = validate_dimensional_model(connection)
        assert dw_report["passed"], dw_report

        with connection.cursor() as cursor:
            cursor.execute("SELECT COUNT(*) FROM stg.sales_document_line")
            staged_sales_rows = int(cursor.fetchone()[0])
            assert staged_sales_rows == (
                expected_counts["sales_invoice_line"]
                + expected_counts["sales_credit_memo_line"]
            )

            cursor.execute(
                """
                SELECT COUNT(*)
                FROM stg.sales_document_line
                WHERE document_type = 'credit_memo'
                  AND (quantity_signed >= 0 OR net_sales_signed >= 0)
                """
            )
            assert int(cursor.fetchone()[0]) == 0

            cursor.execute(
                """
                SELECT COUNT(*)
                FROM stg.inventory_balance
                WHERE available_quantity <= 0
                """
            )
            assert int(cursor.fetchone()[0]) > 0

        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    (SELECT COUNT(*) FROM dw.fact_sales),
                    (SELECT COUNT(*) FROM dw.fact_sales_order),
                    (SELECT COUNT(*) FROM dw.fact_inventory_movement),
                    (SELECT COUNT(*) FROM dw.fact_inventory_snapshot),
                    (SELECT COALESCE(SUM(net_sales_signed), 0) FROM dw.fact_sales),
                    (SELECT COALESCE(SUM(cogs_signed), 0) FROM dw.fact_sales)
                """
            )
            first_dw_snapshot = cursor.fetchone()

        refresh_dimensional_model(connection)
        second_dw_report = validate_dimensional_model(connection)
        assert second_dw_report["passed"], second_dw_report

        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    (SELECT COUNT(*) FROM dw.fact_sales),
                    (SELECT COUNT(*) FROM dw.fact_sales_order),
                    (SELECT COUNT(*) FROM dw.fact_inventory_movement),
                    (SELECT COUNT(*) FROM dw.fact_inventory_snapshot),
                    (SELECT COALESCE(SUM(net_sales_signed), 0) FROM dw.fact_sales),
                    (SELECT COALESCE(SUM(cogs_signed), 0) FROM dw.fact_sales)
                """
            )
            second_dw_snapshot = cursor.fetchone()

        assert first_dw_snapshot == second_dw_snapshot

        reloaded = load_dataset(connection, dataset, truncate=True)
        assert reloaded == expected_counts
        assert raw_row_counts(connection) == expected_counts

        refresh_dimensional_model(connection)
        assert validate_dimensional_model(connection)["passed"]
