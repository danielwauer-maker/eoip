from __future__ import annotations

import os
from pathlib import Path

import pytest

from eoip.config import load_company_profile, load_generator_config
from eoip.database import (
    apply_migrations,
    connect_database,
    load_dataset,
    refresh_dimensional_model,
)
from eoip.generator import ERPGenerator
from eoip.reporting import (
    load_report_spec,
    validate_report_spec,
    validate_sales_margin_database,
)
from eoip.semantic import load_kpi_catalog


ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "semantic" / "kpi-catalog.yaml"
REPORT_SPEC = ROOT / "powerbi" / "report-pages.yaml"
DATABASE_URL = os.environ.get("EOIP_TEST_DATABASE_URL")


def test_sales_margin_report_contract():
    catalog = load_kpi_catalog(CATALOG)
    report = load_report_spec(REPORT_SPEC)

    result = validate_report_spec(report, catalog)
    assert result["passed"], result

    page_ids = {page["id"] for page in report["pages"]}
    assert page_ids == {
        "sales_performance",
        "margin_discount",
        "customer_product",
    }


@pytest.mark.skipif(not DATABASE_URL, reason="EOIP_TEST_DATABASE_URL is not configured")
def test_sales_margin_reporting_reference_views():
    company = load_company_profile(ROOT / "tests" / "fixtures" / "company.yaml")
    config = load_generator_config(ROOT / "config" / "generator.yaml")
    dataset = ERPGenerator(company, config, scale_factor=0.002).generate()

    with connect_database(DATABASE_URL) as connection:
        migrations = apply_migrations(connection)
        assert "050_sales_margin_reporting_views.sql" in migrations

        load_dataset(connection, dataset, truncate=True)
        refresh_dimensional_model(connection)

        result = validate_sales_margin_database(connection)
        assert result["passed"], result

        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT entity_type, entity_label, net_sales
                FROM semantic.v_sales_margin_driver_reference
                WHERE net_sales_rank = 1
                ORDER BY entity_type
                """
            )
            leaders = cursor.fetchall()
            assert {str(row[0]) for row in leaders} == {
                "customer",
                "product",
                "category",
            }
