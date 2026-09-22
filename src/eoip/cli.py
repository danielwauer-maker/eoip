from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from .config import load_company_profile, load_generator_config
from .database import (
    apply_migrations,
    connect_database,
    load_csv_directory,
    load_dataset,
    refresh_dimensional_model,
    validate_database,
    validate_dimensional_model,
    write_database_validation,
)
from .generator import ERPGenerator, dataset_fingerprint, export_dataset
from .powerbi import sync_powerbi_measures
from .validate import validate_dataset


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="eoip")
    sub = parser.add_subparsers(dest="command", required=True)

    generate = sub.add_parser("generate", help="Generate a reproducible synthetic ERP dataset.")
    generate.add_argument("--company-profile", required=True, help="Path to canonical NordWerk company YAML.")
    generate.add_argument("--config", default="config/generator.yaml", help="Generator YAML configuration.")
    generate.add_argument("--output", default="data/generated", help="Output directory.")
    generate.add_argument("--scale-factor", type=float, default=None, help="Override configured scale factor.")
    generate.add_argument(
        "--allow-validation-failures",
        action="store_true",
        help="Export even when validation checks fail.",
    )

    load_db = sub.add_parser(
        "load-db",
        help="Apply SQL migrations and load a generated dataset into PostgreSQL.",
    )
    load_db.add_argument(
        "--database-url",
        default=os.environ.get("DATABASE_URL"),
        help="PostgreSQL connection URL. Defaults to DATABASE_URL.",
    )
    load_db.add_argument(
        "--input",
        default="data/generated",
        help="Directory containing generated CSV source entities.",
    )
    load_db.add_argument(
        "--validation-output",
        default=None,
        help="Optional path for database validation JSON. Defaults inside input directory.",
    )

    build_dw = sub.add_parser(
        "build-dw",
        help="Refresh and validate the EOIP dimensional warehouse from staging.",
    )
    build_dw.add_argument(
        "--database-url",
        default=os.environ.get("DATABASE_URL"),
        help="PostgreSQL connection URL. Defaults to DATABASE_URL.",
    )
    build_dw.add_argument(
        "--validation-output",
        default="data/dw-validation.json",
        help="Path for dimensional-model validation JSON.",
    )

    sync_measures = sub.add_parser(
        "sync-powerbi-measures",
        help="Generate the PBIP _Measures TMDL table from canonical powerbi/measures.dax.",
    )
    sync_measures.add_argument(
        "--dax",
        default="powerbi/measures.dax",
        help="Canonical DAX measure source.",
    )
    sync_measures.add_argument(
        "--output",
        default="powerbi/EOIP/EOIP.SemanticModel/definition/tables/_Measures.tmdl",
        help="Generated PBIP TMDL measure-table output.",
    )

    return parser


def run_generate(args: argparse.Namespace) -> int:
    company = load_company_profile(args.company_profile)
    config = load_generator_config(args.config)
    generator = ERPGenerator(company, config, scale_factor=args.scale_factor)
    dataset = generator.generate()
    validation = validate_dataset(dataset)
    fingerprint = dataset_fingerprint(dataset)

    summary = {
        "company": company.name,
        "seed": generator.seed,
        "scale_factor": generator.scale_factor,
        "history_start": generator.start_date.date().isoformat(),
        "history_end": generator.end_date.date().isoformat(),
        "fingerprint": fingerprint,
        "validation_passed": validation["passed"],
        "entities": {name: int(len(frame)) for name, frame in dataset.items()},
    }

    print(json.dumps(summary, indent=2, ensure_ascii=False))

    if not validation["passed"] and not args.allow_validation_failures:
        print("Validation failed. Dataset was not exported.")
        print(json.dumps(validation, indent=2, ensure_ascii=False))
        return 2

    export_dataset(dataset, Path(args.output), validation=validation)
    return 0


def run_load_db(args: argparse.Namespace) -> int:
    if not args.database_url:
        raise SystemExit("A PostgreSQL URL is required via --database-url or DATABASE_URL.")

    dataset = load_csv_directory(args.input)
    expected_counts = {name: int(len(frame)) for name, frame in dataset.items()}

    with connect_database(args.database_url) as connection:
        migrations = apply_migrations(connection)
        loaded_counts = load_dataset(connection, dataset, truncate=True)
        validation = validate_database(
            connection,
            expected_row_counts=expected_counts,
        )

    output_path = (
        Path(args.validation_output)
        if args.validation_output
        else Path(args.input) / "database-validation.json"
    )
    write_database_validation(validation, output_path)

    print(
        json.dumps(
            {
                "migrations": migrations,
                "loaded_rows": loaded_counts,
                "validation_passed": validation["passed"],
                "validation_output": str(output_path),
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    return 0 if validation["passed"] else 2


def run_build_dw(args: argparse.Namespace) -> int:
    if not args.database_url:
        raise SystemExit("A PostgreSQL URL is required via --database-url or DATABASE_URL.")

    with connect_database(args.database_url) as connection:
        apply_migrations(connection)
        refresh_dimensional_model(connection)
        validation = validate_dimensional_model(connection)

    output_path = Path(args.validation_output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    write_database_validation(validation, output_path)

    print(
        json.dumps(
            {
                "validation_passed": validation["passed"],
                "validation_output": str(output_path),
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    return 0 if validation["passed"] else 2


def run_sync_powerbi_measures(args: argparse.Namespace) -> int:
    result = sync_powerbi_measures(args.dax, args.output)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "generate":
        raise SystemExit(run_generate(args))
    if args.command == "load-db":
        raise SystemExit(run_load_db(args))
    if args.command == "build-dw":
        raise SystemExit(run_build_dw(args))
    if args.command == "sync-powerbi-measures":
        raise SystemExit(run_sync_powerbi_measures(args))

    raise SystemExit(1)


if __name__ == "__main__":
    main()
