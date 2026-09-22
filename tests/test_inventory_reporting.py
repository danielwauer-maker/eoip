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
from eoip.inventory_reporting import (
    load_inventory_report_spec,
    validate_inventory_report_spec,
    validate_inventory_reporting_database,
)
from eoip.semantic import load_kpi_catalog


ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "semantic" / "kpi-catalog.yaml"
INVENTORY_SPEC = ROOT / "powerbi" / "inventory-intelligence.yaml"
DATABASE_URL = os.environ.get("EOIP_TEST_DATABASE_URL")


def test_inventory_report_contract():
    catalog = load_kpi_catalog(CATALOG)
    report = load_inventory_report_spec(INVENTORY_SPEC)

    result = validate_inventory_report_spec(report, catalog)
    assert result["passed"], result


@pytest.mark.skipif(not DATABASE_URL, reason="EOIP_TEST_DATABASE_URL is not configured")
def test_inventory_reporting_reference_views():
    company = load_company_profile(ROOT / "tests" / "fixtures" / "company.yaml")
    config = load_generator_config(ROOT / "config" / "generator.yaml")
    dataset = ERPGenerator(company, config, scale_factor=0.002).generate()

    with connect_database(DATABASE_URL) as connection:
        migrations = apply_migrations(connection)
        assert "070_inventory_reporting_views.sql" in migrations

        load_dataset(connection, dataset, truncate=True)
        refresh_dimensional_model(connection)

        result = validate_inventory_reporting_database(connection)
        assert result["passed"], result

        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT COUNT(*)
                FROM semantic.v_inventory_risk_detail_reference
                WHERE risk_signal_count >= 2
                """
            )
            assert int(cursor.fetchone()[0]) > 0
