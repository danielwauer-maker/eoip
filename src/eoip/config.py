from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True)
class CompanyProfile:
    company_id: str
    name: str
    employees: int
    annual_revenue_eur: float
    products: int
    customers: int
    suppliers: int
    warehouse_locations: int
    inventory_value_eur: float
    annual_procurement_volume_eur: float


def load_yaml(path: str | Path) -> dict[str, Any]:
    with Path(path).open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def load_company_profile(path: str | Path) -> CompanyProfile:
    raw = load_yaml(path)
    company = raw["company"]
    profile = company["profile"]
    return CompanyProfile(
        company_id=str(company["id"]),
        name=str(company["name"]),
        employees=int(profile["employees"]),
        annual_revenue_eur=float(profile["annual_revenue_eur"]),
        products=int(profile["products"]),
        customers=int(profile["customers"]),
        suppliers=int(profile["suppliers"]),
        warehouse_locations=int(profile["warehouse_locations"]),
        inventory_value_eur=float(profile["inventory_value_eur"]),
        annual_procurement_volume_eur=float(profile["annual_procurement_volume_eur"]),
    )


def load_generator_config(path: str | Path) -> dict[str, Any]:
    raw = load_yaml(path)
    if raw.get("schema_version") != 1:
        raise ValueError("Unsupported generator configuration schema_version.")
    return raw
