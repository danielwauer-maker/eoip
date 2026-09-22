from __future__ import annotations

import re
from pathlib import Path


_MEASURE_HEADER = re.compile(r"^(.+?)\s*:=\s*$")


def parse_dax_measures(text: str) -> list[tuple[str, str]]:
    """Parse the canonical measures.dax file into ordered (name, expression) pairs."""
    measures: list[tuple[str, str]] = []
    current_name: str | None = None
    current_lines: list[str] = []

    def flush() -> None:
        nonlocal current_name, current_lines
        if current_name is None:
            return
        expression = "\n".join(current_lines).strip()
        if not expression:
            raise ValueError(f"Measure {current_name!r} has no DAX expression.")
        measures.append((current_name, expression))
        current_name = None
        current_lines = []

    for raw_line in text.splitlines():
        stripped = raw_line.strip()
        match = _MEASURE_HEADER.match(stripped)
        if match:
            flush()
            current_name = match.group(1).strip()
            continue

        if current_name is None:
            continue

        # Section comments document the canonical DAX file but are not part of a measure.
        if stripped.startswith("--"):
            continue
        current_lines.append(raw_line.rstrip())

    flush()

    names = [name for name, _expression in measures]
    if len(names) != len(set(names)):
        duplicates = sorted({name for name in names if names.count(name) > 1})
        raise ValueError(f"Duplicate DAX measure names: {duplicates}")

    return measures


def render_measure_table_tmdl(
    measures: list[tuple[str, str]],
    *,
    table_name: str = "_Measures",
) -> str:
    """Render a measure-only calculated table for the PBIP semantic model."""
    lines: list[str] = [f"table {table_name}", ""]

    for name, expression in measures:
        safe_name = name.replace("'", "''")
        lines.append(f"\tmeasure '{safe_name}' = ```")
        for expression_line in expression.splitlines():
            lines.append(f"\t\t\t{expression_line}")
        lines.append("\t\t\t```")
        lines.append("")

    lines.extend(
        [
            "\tcolumn Value",
            "\t\tdataType: int64",
            "\t\tisHidden",
            "\t\tformatString: 0",
            "\t\tsummarizeBy: sum",
            "\t\tsourceColumn: [Value]",
            "",
            f"\tpartition {table_name} = calculated",
            "\t\tmode: import",
            "\t\tsource = {1}",
            "",
        ]
    )
    return "\n".join(lines)


def sync_powerbi_measures(
    dax_path: str | Path,
    tmdl_path: str | Path,
) -> dict[str, object]:
    dax_file = Path(dax_path)
    output_file = Path(tmdl_path)

    measures = parse_dax_measures(dax_file.read_text(encoding="utf-8"))
    rendered = render_measure_table_tmdl(measures)

    output_file.parent.mkdir(parents=True, exist_ok=True)
    output_file.write_text(rendered, encoding="utf-8")

    return {
        "measure_count": len(measures),
        "source": str(dax_file),
        "output": str(output_file),
    }
