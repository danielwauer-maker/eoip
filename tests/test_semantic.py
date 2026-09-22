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
from eoip.semantic import (
    load_kpi_catalog,
    validate_kpi_catalog,
    validate_semantic_database,
)


ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "semantic" / "kpi-catalog.yaml"
DAX = ROOT / "powerbi" / "measures.dax"
DATABASE_URL = os.environ.get("EOIP_TEST_DATABASE_URL")


def test_kpi_catalog_and_dax_contract():
    catalog = load_kpi_catalog(CATALOG)
    report = validate_kpi_catalog(catalog, dax_path=DAX)

    assert report["passed"], report
    assert len(catalog["kpis"]) == 18


@pytest.mark.skipif(not DATABASE_URL, reason="EOIP_TEST_DATABASE_URL is not configured")
def test_semantic_kpi_reference_layer():
    company = load_company_profile(ROOT / "tests" / "fixtures" / "company.yaml")
    config = load_generator_config(ROOT / "config" / "generator.yaml")
    dataset = ERPGenerator(company, config, scale_factor=0.002).generate()
    catalog = load_kpi_catalog(CATALOG)

    with connect_database(DATABASE_URL) as connection:
        migrations = apply_migrations(connection)
        assert "040_semantic_views.sql" in migrations

        load_dataset(connection, dataset, truncate=True)
        refresh_dimensional_model(connection)

        report = validate_semantic_database(connection, catalog)
        assert report["passed"], report

        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT COUNT(*), COUNT(DISTINCT kpi_id)
                FROM semantic.v_kpi_reference
                """
            )
            row_count, distinct_count = map(int, cursor.fetchone())
            assert row_count == 18
            assert distinct_count == 18

            cursor.execute(
                """
                SELECT numeric_value
                FROM semantic.v_kpi_reference
                WHERE kpi_id = 'gross_margin_pct'
                """
            )
            gross_margin_pct = float(cursor.fetchone()[0])
            assert -1000 < gross_margin_pct < 100

            cursor.execute(
                """
                SELECT numeric_value
                FROM semantic.v_kpi_reference
                WHERE kpi_id = 'stockout_risk_sku_count'
                """
            )
            assert float(cursor.fetchone()[0]) > 0
