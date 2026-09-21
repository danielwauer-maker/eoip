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
    validate_database,
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
        ]

        loaded = load_dataset(connection, dataset, truncate=True)
        assert loaded == expected_counts

        report = validate_database(
            connection,
            expected_row_counts=expected_counts,
        )
        assert report["passed"], report

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

        reloaded = load_dataset(connection, dataset, truncate=True)
        assert reloaded == expected_counts
        assert raw_row_counts(connection) == expected_counts
