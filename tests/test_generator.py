from __future__ import annotations

import json
from pathlib import Path

from eoip.config import load_company_profile, load_generator_config
from eoip.generator import ENTITY_ORDER, ERPGenerator, dataset_fingerprint, export_dataset
from eoip.validate import validate_dataset


ROOT = Path(__file__).resolve().parents[1]
COMPANY = ROOT / "tests" / "fixtures" / "company.yaml"
CONFIG = ROOT / "config" / "generator.yaml"


def generate_small():
    company = load_company_profile(COMPANY)
    config = load_generator_config(CONFIG)
    generator = ERPGenerator(company, config, scale_factor=0.002)
    return generator.generate()


def test_generates_all_required_entities_and_passes_invariants():
    dataset = generate_small()

    assert list(dataset) == ENTITY_ORDER
    assert len(dataset) == 19
    assert all(len(dataset[name]) > 0 for name in ENTITY_ORDER)

    validation = validate_dataset(dataset)

    assert validation["passed"], validation
    assert validation["failed_count"] == 0


def test_same_seed_produces_identical_fingerprint():
    first = generate_small()
    second = generate_small()

    assert dataset_fingerprint(first) == dataset_fingerprint(second)


def test_different_seed_changes_fingerprint():
    company = load_company_profile(COMPANY)
    config = load_generator_config(CONFIG)

    first = ERPGenerator(company, config, scale_factor=0.002).generate()

    changed = load_generator_config(CONFIG)
    changed["generator"]["seed"] = int(changed["generator"]["seed"]) + 1
    second = ERPGenerator(company, changed, scale_factor=0.002).generate()

    assert dataset_fingerprint(first) != dataset_fingerprint(second)


def test_export_writes_manifest_and_validation(tmp_path):
    dataset = generate_small()
    validation = validate_dataset(dataset)

    export_dataset(dataset, tmp_path, validation=validation)

    assert (tmp_path / "manifest.json").exists()
    assert (tmp_path / "validation.json").exists()
    assert all((tmp_path / f"{name}.csv").exists() for name in ENTITY_ORDER)

    manifest = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
    validation_report = json.loads((tmp_path / "validation.json").read_text(encoding="utf-8"))

    assert manifest["fingerprint"] == dataset_fingerprint(dataset)
    assert validation_report["passed"] is True
    assert validation_report["dataset_fingerprint"] == manifest["fingerprint"]


def test_business_patterns_exist():
    dataset = generate_small()

    assert len(dataset["sales_invoice_line"]) > 0
    assert len(dataset["sales_credit_memo_line"]) > 0
    assert len(dataset["warehouse_transfer_line"]) > 0

    balances = dataset["inventory_balance"]
    assert (balances["reserved_quantity"] > 0).any()
    assert (balances["available_quantity"] <= 0).any()

    value_entries = dataset["value_entry"]
    assert (value_entries["entry_type"] == "sale").any()
    assert (value_entries["sales_amount_actual"] > 0).any()
