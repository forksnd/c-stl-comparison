#!/usr/bin/env python3
import argparse
import pathlib
import re
import subprocess
import sys
from collections import defaultdict


SIZE_LINE_PATTERN = re.compile(r"^(?P<size>\d+) bytes for (?P<exe>.+)\.exe$")
TABLE_HEADER_PATTERN = re.compile(r"^\| (array|umap)-(int|str|mpz) size \| bytes \|$")

SUFFIX_TO_LABEL = {
    "CC": "CC",
    "ccc": "CCC",
    "cmc": "CMC",
    "collectionsC": "CollecC",
    "ctl": "CTL",
    "glib": "GLIB",
    "klib": "KLIB",
    "mlib": "M*LIB",
    "stb": "STB_DS",
    "stc": "STC",
    "stl": "STL",
}


def parse_row(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def format_table(rows: list[list[str]]) -> str:
    widths = [max(len(row[i]) for row in rows) for i in range(len(rows[0]))]

    def fmt_row(row: list[str]) -> str:
        return "| " + " | ".join(cell.ljust(widths[i]) for i, cell in enumerate(row)) + " |"

    header = fmt_row(rows[0])
    separator = "|" + "|".join("-" * (width + 2) for width in widths) + "|"
    body = "\n".join(fmt_row(row) for row in rows[1:])
    return "\n".join([header, separator, body])


def run_measure_size(repo_root: pathlib.Path) -> str:
    completed = subprocess.run(
        ["make", "measure-size"],
        cwd=repo_root,
        text=True,
        capture_output=True,
    )

    if completed.returncode != 0:
        if completed.stderr:
            print(completed.stderr, file=sys.stderr, end="")
        raise SystemExit(completed.returncode)

    return completed.stdout


def load_measure_size_output(args: argparse.Namespace, repo_root: pathlib.Path) -> str:
    if args.measure_size_log is not None:
        return pathlib.Path(args.measure_size_log).read_text(encoding="utf-8")
    return run_measure_size(repo_root)


def parse_measure_size_output(output: str) -> dict[str, list[tuple[str, int]]]:
    table_sizes: dict[str, list[tuple[str, int]]] = defaultdict(list)

    for line in output.splitlines():
        match = SIZE_LINE_PATTERN.match(line.strip())
        if match is None:
            continue

        size = int(match.group("size"))
        exe = match.group("exe")
        prefix, suffix = exe.rsplit("-", 1)
        label = SUFFIX_TO_LABEL.get(suffix, suffix)
        table_sizes[prefix].append((label, size))

    return table_sizes


def update_size_table(table_text: str, table_sizes: dict[str, list[tuple[str, int]]]) -> str:
    lines = table_text.splitlines()
    header_cells = parse_row(lines[0])
    header_match = re.match(r"(array|umap)-(int|str|mpz) size", header_cells[0])
    if not header_match:
        return table_text

    table_prefix = header_match.group(1)
    table_kind = header_match.group(2)
    prefix = f"{table_prefix}-{table_kind}"
    rows = table_sizes.get(prefix, [])

    body_rows = [[label, str(size)] for label, size in rows]
    if not body_rows:
        body_rows = [["NA", "NA"]]

    return format_table([header_cells, *body_rows])


def update_readme(text: str, table_sizes: dict[str, list[tuple[str, int]]]) -> tuple[str, int]:
    lines = text.splitlines()
    updated_lines: list[str] = []
    replacements = 0
    i = 0

    while i < len(lines):
        line = lines[i]
        if TABLE_HEADER_PATTERN.match(line) and i + 1 < len(lines) and lines[i + 1].startswith("|-"):
            table_start = i
            table_end = i + 2
            while table_end < len(lines) and lines[table_end].startswith("|"):
                table_end += 1

            table_text = "\n".join(lines[table_start:table_end])
            updated_lines.append(update_size_table(table_text, table_sizes))
            replacements += 1
            i = table_end
            continue

        updated_lines.append(line)
        i += 1

    return "\n".join(updated_lines), replacements


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run make measure-size and update README size tables."
    )
    parser.add_argument(
        "--readme",
        default="README.md",
        help="Path to README file to update (default: README.md).",
    )
    parser.add_argument(
        "--measure-size-log",
        help="Read measure-size output from a file instead of running make measure-size.",
    )
    args = parser.parse_args()

    readme_path = pathlib.Path(args.readme).resolve()
    repo_root = readme_path.parent

    try:
        readme_text = readme_path.read_text(encoding="utf-8")
    except OSError as exc:
        print(f"error: cannot read {readme_path}: {exc}", file=sys.stderr)
        return 1

    measure_size_output = load_measure_size_output(args, repo_root)
    table_sizes = parse_measure_size_output(measure_size_output)

    new_text, replacements = update_readme(readme_text, table_sizes)
    if replacements == 0:
        print("error: no matching size tables found", file=sys.stderr)
        return 2

    if new_text != readme_text:
        readme_path.write_text(
            new_text + ("\n" if readme_text.endswith("\n") else ""),
            encoding="utf-8",
        )
        print(f"updated {readme_path} ({replacements} tables)")
    else:
        print(f"no changes needed in {readme_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())