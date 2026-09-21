from __future__ import annotations

import argparse
import json
from pathlib import Path

from .config import load_company_profile, load_generator_config
from .generator import ERPGenerator, dataset_fingerprint, export_dataset
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


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "generate":
        raise SystemExit(run_generate(args))

    raise SystemExit(1)


if __name__ == "__main__":
    main()
